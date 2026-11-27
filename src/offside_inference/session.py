"""Single-frame analysis, as done by the application.

  1. open: a video, an image, several images or a folder
  2. prepare(pass frame): calibration of THAT frame with the HRNet (refined on the white lines),
     player detection and teams by colour
  3. propose: given the attacked goal and the chosen attacker, proposes the second-last defender
  4. analyze(attacker, defender, goal): 2D -> 3D pose and Law 11; writes the viewer JSON and the
     pass image with the lines

Players are identified by their number in the frame (1..N from left to right).
"""
import os
import re
import shutil
import tempfile
import time

import cv2
import numpy as np
import torch

from . import camera as camlib
from . import config
from .camera import HALF_LENGTH, HALF_WIDTH
from .detection import DEFAULT_POSE, FrameDetector, ball_near_feet, box_bottom, choose_ball, default_detector
from .drawing import draw_pass_frame
from .export import hex_color, write_analysis
from .frames import MediaSource
from .hrnet import HrnetServer, fit_homography, ground_points
from .offside import check_2d, clean_joints, evaluate_selected, parts_on_ground_2d
from .pose import COCO_JOINTS, PoseEstimator
from .teams import assign_teams, jersey_color, keeper_colors

RESULTS = os.path.join(config.path("output_dir"), "app")
MIN_MARKS, MAX_MARK_ERROR_PX = 40, 3.0  # acceptable fit to the white lines
# If the pass frame calibrates badly: nearby frames to try (±2 s every 0.4 s) and what a good
# calibration is (HRNet points that fit and marking error)
NEIGHBOR_RANGE, NEIGHBOR_STEP = 50, 10
GOOD_INLIERS, GOOD_ERROR_PX = 8, 1.5
# Main camera position: video frames calibrated to estimate it, how many must agree and at what
# distance (m) a free calibration is no longer that camera
CENTER_SAMPLES, CENTER_MIN_FRAMES, CENTER_AGREE_M, CENTER_OFF_M = 12, 3, 4.0, 6.0
GOOD_INLIERS_FIXED = 3  # with a fixed position a few HRNet points are enough


def _quiet(*_args, **_kwargs):
    pass


class Session:
    def __init__(self, device=None, detector=None, pose=None, out_dir=RESULTS, camera_center=None):
        """Creates a session.

        Args:
            camera_center: (x, y, z) position of the main camera if known (e.g. the stadium's); otherwise
                it is estimated from several frames of each video.
        """
        self.device = device or ("0" if torch.cuda.is_available() else "cpu")
        self.detector_path = detector or default_detector()
        self.pose_path = pose or DEFAULT_POSE
        self.out_dir = out_dir
        self.tmp = tempfile.mkdtemp(prefix="fuera_de_juego_")
        self.hrnet = HrnetServer(self.tmp)
        self._detector = self._pose = None
        self.source = None
        self.prepared = {}
        self.known_center = None if camera_center is None else np.asarray(camera_center, float)
        self.center = None  # {"center", "frames", "spread_m", "source"} of the open source

    def close(self):
        self.hrnet.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_camera_center(self, center):
        """Known main camera position for the videos opened next (None: estimate it)."""
        self.known_center = None if center is None else np.asarray(center, float)
        self.center = None

    # 1. Source
    def open(self, paths):
        self.source = MediaSource(paths)
        self.prepared.clear()
        self.center = None
        s = self.source
        return {"kind": s.kind, "name": s.name, "count": s.count, "fps": s.fps, "width": s.size[0], "height": s.size[1],
                "first_number": s.number(0), "last_number": s.number(s.count - 1)}

    def index_of(self, number):
        if number not in self.source.numbers:
            raise ValueError(f"No hay ningún fotograma {number} (van del {self.source.number(0)} al "
                             f"{self.source.number(self.source.count - 1)})")
        return self.source.numbers.index(number)

    def frame_image(self, index, max_width=1600):
        """JPEG of the frame for display (downscaled to max_width)."""
        image = self.source.read(index)
        h, w = image.shape[:2]
        if w > max_width:
            image = cv2.resize(image, (max_width, round(h * max_width / w)), interpolation=cv2.INTER_AREA)
        path = os.path.join(self.tmp, f"vista_{index}.jpg")
        cv2.imwrite(path, image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return {"index": index, "number": self.source.number(index), "path": path}

    # 2. Calibration and detection
    def prepare(self, index, progress=_quiet):
        t0 = time.monotonic()
        frame = self.source.read(index)
        h, w = frame.shape[:2]
        if self._detector is None:
            progress("Cargando el detector de jugadores…")
            self._detector = FrameDetector(self.detector_path, self.device)
        progress("Detectando jugadores…")
        people, ball = self._detector(frame)
        boxes = [p["box"] for p in people]

        progress("Calibrando la cámara con el HRNet" + ("…" if self.hrnet.process else " (la primera vez tarda unos segundos)…"))
        if self.center is None:
            self.center = self._camera_center(progress)
        calibration, cam = self._calibrate(frame, index, boxes, progress)

        # Teams by shirt colour in this frame
        colors = {p["id"]: [c] for p in people if (c := jersey_color(frame, p["box"])) is not None}
        roles = {p["id"]: p["role"] for p in people}
        teams, team_bgr, odd = assign_teams(colors, roles, min_samples=1, min_outlier_dist=40.0)
        for p in people:
            if p["id"] in odd:
                p["role"] = "referee"
            p["team"] = teams.get(p["id"])
            p["color"] = colors.get(p["id"], [None])[0]
            p["ground"] = cam.to_ground([box_bottom(p["box"])])[0][:2] if cam is not None else None
        # Ball: candidates from the full frame and from enlarged crops around each player's feet
        candidates = (ball or {}).get("candidates", []) + ball_near_feet(
            self._detector.model, frame, [p["box"] for p in people if p["role"] != "referee"],
            self.device, self._detector.roles)
        feet = [p["ground"] for p in people if p["role"] != "referee" and p.get("ground") is not None]
        ball = choose_ball(candidates, feet, cam)

        self.prepared[index] = {"frame": frame, "cam": cam, "calibration": calibration, "people": people,
                                "ball": ball, "team_bgr": team_bgr, "colors": colors}
        return {
            "index": index, "number": self.source.number(index), "width": w, "height": h,
            "calibration": calibration,
            "players": [{"id": p["id"], "role": p["role"], "team": p["team"], "conf": round(p["conf"], 2),
                         "box": [round(float(v), 1) for v in p["box"]],
                         "ground": None if p["ground"] is None else [round(float(v), 2) for v in p["ground"]]}
                        for p in people],
            "ball": None if ball is None else {"box": [round(float(v), 1) for v in ball["box"]], "conf": round(ball["conf"], 2),
                                               "ground": None if cam is None else [round(float(v), 2) for v in ball["ground"]]},
            "team_colors": [hex_color(c) for c in team_bgr],
            "seconds": round(time.monotonic() - t0, 1),
        }

    def _camera_center(self, progress):
        """Main camera position: the known one, or the median of good calibrations of several frames
        spread over the video (replays and other cameras are left out because they disagree with the
        majority). None if there are not enough.
        """
        if self.known_center is not None:
            return {"center": self.known_center, "frames": 0, "spread_m": 0.0, "source": "conocida"}
        stored = _stored_center(self.source.path)
        if stored is not None:
            return {"center": stored, "frames": 0, "spread_m": 0.0, "source": "camara.json"}
        if self.source.count < CENTER_MIN_FRAMES:
            return {"center": None, "frames": 0, "spread_m": None, "source": "sin estimar (pocos fotogramas)"}
        progress("Situando la cámara principal con varios fotogramas del vídeo…")
        indices = np.unique(np.linspace(0, self.source.count - 1, CENTER_SAMPLES).round().astype(int))
        centers = []
        for j in indices:
            other = self.source.read(int(j))
            c = self._calibrate_frame(other, int(j), [p["box"] for p in self._detector(other)[0]], use_center=False)
            if _good(c):
                centers.append(c["cam"].center)
        if len(centers) < CENTER_MIN_FRAMES:
            return {"center": None, "frames": len(centers), "spread_m": None,
                    "source": f"sin estimar (solo {len(centers)} fotogramas calibran bien)"}
        centers = np.array(centers)
        med = np.median(centers, axis=0)
        agree = centers[np.linalg.norm(centers - med, axis=1) <= CENTER_AGREE_M]
        if len(agree) < CENTER_MIN_FRAMES:
            return {"center": None, "frames": len(agree), "spread_m": None,
                    "source": "sin estimar (las calibraciones no coinciden)"}
        center = np.median(agree, axis=0)
        spread = float(np.median(np.linalg.norm(agree - center, axis=1)))
        return {"center": center, "frames": len(agree), "spread_m": round(spread, 2), "source": "estimada"}

    def _calibrate_frame(self, frame, index, boxes, use_center=True):
        """Calibration of one frame from its HRNet points, refined on its white lines.

        Free: a homography and from it the full camera (position included). If the main camera position
        is known, also orientation and zoom only (2-3 points are enough), and that one is kept if it fits
        the lines well.
        """
        h, w = frame.shape[:2]
        path = os.path.join(self.tmp, f"fotograma_{index}.jpg")
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        points = ground_points(self.hrnet.keypoints(path))
        H, inliers = fit_homography(points)
        good = [p for p, ok in zip(points, inliers) if ok]
        c = {"index": index, "points": points, "inliers": inliers, "good": len(good), "cam": None,
             "med": float("inf"), "n": 0, "method": "libre", "offset_m": None}
        if H is not None and len(good) >= 4:
            H = camlib.homography_from_correspondences([(tuple(p["field"]), tuple(p["image"])) for p in good])
            try:
                cam, _ = camlib.camera_from_homography(H, (w, h))
                c["cam"], c["med"], c["n"] = camlib.refine_camera(cam, frame, boxes, fix_center=False)
            except ValueError:  # inconsistent points: no free solution
                pass
        center = self.center["center"] if use_center and self.center else None
        if center is None:
            return c
        if c["cam"] is not None:
            c["offset_m"] = round(float(np.linalg.norm(c["cam"].center - center)), 1)
        cam, fixed_inliers = camlib.camera_with_fixed_center([p["field"] for p in points], [p["image"] for p in points],
                                                            center, (w, h))
        if cam is None:
            return c
        cam, med, n = camlib.refine_camera(cam, frame, boxes, fix_center=True)
        fixed = {**c, "inliers": fixed_inliers, "good": int(sum(fixed_inliers)), "cam": cam, "med": med, "n": n,
                 "method": "posición fija"}
        return fixed if n >= MIN_MARKS and med <= MAX_MARK_ERROR_PX else c

    def _calibrate(self, frame, index, boxes, progress):
        """Calibrates the pass frame.

        If its markings are not enough (e.g. only the far penalty area is visible), looks for a frame within
        2 s that calibrates better and follows the camera's pan and zoom from it to the pass frame, as
        run_inference.py does with the keyframe.
        """
        h, w = frame.shape[:2]
        direct = self._calibrate_frame(frame, index, boxes)
        best, anchor = direct, None
        if self.source.count > 1 and not _good(direct):
            progress("Pocas líneas en este fotograma: buscando uno cercano que calibre mejor…")
            for dist in range(NEIGHBOR_STEP, NEIGHBOR_RANGE + 1, NEIGHBOR_STEP):
                for j in (index + dist, index - dist):
                    if 0 <= j < self.source.count:
                        other = self.source.read(j)
                        c = self._calibrate_frame(other, j, [p["box"] for p in self._detector(other)[0]])
                        if c["cam"] is not None and (anchor is None or _score(c) > _score(anchor)):
                            anchor = c
                if anchor is not None and _good(anchor):
                    break
            if anchor is not None and _score(anchor) > _score(direct):
                progress(f"Siguiendo la cámara desde el fotograma {self.source.number(anchor['index'])}…")
                followed = self._follow(anchor["cam"], anchor["index"], index)
                if followed["cam"] is not None and _score(followed) > _score(direct):
                    best = {**followed, "points": anchor["points"], "inliers": anchor["inliers"], "good": anchor["good"],
                            "method": anchor.get("method", "libre")}  # tracking keeps the anchor's position

        points, inliers = best["points"], best["inliers"]
        center = self.center or {}
        info = {"ok": False, "dubious": False, "points": len(points), "inliers": best["good"],
                "method": best.get("method", "libre"), "free_offset_m": direct.get("offset_m"),
                "camera_center": None if center.get("center") is None else [round(float(v), 1) for v in center["center"]],
                "camera_center_source": center.get("source"), "camera_center_frames": center.get("frames"),
                "hrnet_points": [{"image": p["image"], "name": p["hrnet"].lower(), "ok": ok} for p, ok in zip(points, inliers)]
                                if best is direct else []}
        cam = best["cam"]
        if cam is None:
            info["message"] = (f"No evaluable: el HRNet solo encuentra {direct['good']} puntos fiables del campo en este "
                               f"fotograma (hacen falta 4) ni en los cercanos. Prueba con otro en el que se vean más líneas.")
            return info, None
        med, n = best["med"], best["n"]
        info.update({"ok": True, "error_px": round(float(med), 2) if np.isfinite(med) else None, "marks": int(n),
                     "focal": round(cam.focal), "camera": [round(float(v), 1) for v in cam.center],
                     "lines": _image_polylines(cam, w, h), "footprint": _footprint(cam, w, h)})
        info["dubious"] = bool(n < MIN_MARKS or not med < MAX_MARK_ERROR_PX)
        # Free calibration with the camera far from its place: another camera or a false solution
        offset = None if center.get("center") is None else float(np.linalg.norm(cam.center - center["center"]))
        if info["method"] == "libre" and offset is not None and offset > CENTER_OFF_M:
            info["dubious"] = True
            info["off_center_m"] = round(offset, 1)
        if best is direct:
            text = f"{best['good']} de {len(points)} puntos del HRNet"
        else:
            info["anchor"] = self.source.number(best["index"])
            text = (f"Calibrado en el fotograma {info['anchor']} ({best['good']} puntos del HRNet) y seguido hasta este "
                    f"(aquí solo encajaban {direct['good']})")
        if info["method"] == "posición fija":
            text += f", con la cámara en su posición ({center['source']})"
        elif info.get("off_center_m") is not None:
            text += (f"; la cámara queda a {info['off_center_m']:.0f} m de su posición habitual "
                     "(¿repetición u otra cámara?)")
        info["message"] = (text + (f"; marcas a {med:.1f} px de las líneas" if np.isfinite(med) else "")
                           + (" — calibración dudosa: revisa que las líneas proyectadas coincidan" if info["dubious"] else ""))
        return info, cam

    def _follow(self, cam, start, end):
        """Camera for frame end from the one at start, frame by frame (pan and zoom)."""
        step = 1 if end > start else -1
        prev_gray = cv2.cvtColor(self.source.read(start), cv2.COLOR_BGR2GRAY)
        med, n = float("nan"), 0
        for i in range(start + step, end + step, step):
            frame = self.source.read(i)
            boxes = [p["box"] for p in self._detector(frame)[0]]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            H_rel = camlib.frame_motion(prev_gray, gray, boxes)
            predicted = camlib.predict_with_motion(cam, H_rel) if H_rel is not None else cam
            refined, med, n = min((camlib.refine_camera(c, frame, boxes) for c in (predicted, cam)), key=lambda o: o[1])
            if n >= MIN_MARKS and med < MAX_MARK_ERROR_PX:
                cam = refined
            else:
                cam, med = predicted, float("nan")
            prev_gray = gray
        return {"index": start, "cam": cam, "med": med, "n": n}

    def _prepared(self, index):
        if index not in self.prepared:
            raise ValueError("Ese fotograma no está preparado: primero hay que calibrarlo y detectar a los jugadores")
        return self.prepared[index]

    # 3. Second-last defender proposal
    def propose(self, index, direction, attacker):
        prep = self._prepared(index)
        if prep["cam"] is None:
            return {"defender": None, "reason": "Sin calibración"}
        people = prep["people"]
        att = _player(people, attacker)
        defenders = [p for p in people if p["id"] != attacker and self._team_for(p, direction, att) == "defending"]
        if not defenders:
            return {"defender": None, "reason": "No se ve a ningún defensor"}
        defenders.sort(key=lambda p: -direction * p["ground"][0])
        deepest = defenders[0]
        gx, gy = deepest["ground"]
        # The goalkeeper may be detected as an outfield player: the deepest one inside the goal area
        keeper_like = deepest["role"] == "goalkeeper" or (direction * gx > 52.5 - 5.5 - 1.0 and abs(gy) < 9.16 + 1.0)
        if keeper_like and len(defenders) >= 2:
            return {"defender": defenders[1]["id"], "reason": f"El más retrasado ({deepest['id']}) parece el portero"}
        return {"defender": deepest["id"],
                "reason": "Defensor más retrasado a la vista; se supone que el portero está fuera del plano"}

    def _team_for(self, p, direction, attacker):
        """attacking, defending or None (referees and unknown), relative to the attacker's team."""
        if p["role"] == "referee":
            return None
        if p["role"] == "goalkeeper":
            # Each goalkeeper defends the goal on their side
            return "defending" if p["ground"] is not None and np.sign(p["ground"][0]) == direction else "attacking"
        if p["team"] is None or attacker["team"] is None:
            return None
        return "attacking" if p["team"] == attacker["team"] else "defending"

    # 4. 3D pose and Law 11
    def analyze(self, index, attacker, defender, direction, progress=_quiet, ball="auto"):
        """Runs the analysis.

        Args:
            ball: "auto" (the detector's), "none" (the user says it does not count or is not visible) or
                [u, v], the image point where the user marks the ball (assumed on the ground).
        """
        t0 = time.monotonic()
        prep = self._prepared(index)
        cam, frame, people = prep["cam"], prep["frame"], prep["people"]
        if cam is None:
            raise ValueError(prep["calibration"]["message"])
        att = _player(people, attacker)
        dfd = _player(people, defender)
        for p in (att, dfd):  # if the user picks them, they are a player even if their colour set them aside
            if p["role"] == "referee":
                p["role"] = "player"
        # Analysis teams 0/1: the attacker's team attacks; goalkeepers by their side
        attacking_team = att["team"] if att["team"] is not None else (1 - dfd["team"] if dfd["team"] is not None else 0)
        for p in people:
            side = self._team_for(p, direction, {**att, "team": attacking_team})
            p["analysis_team"] = None if side is None else attacking_team if side == "attacking" else 1 - attacking_team
        dfd["analysis_team"] = 1 - attacking_team
        att["analysis_team"] = attacking_team

        if self._pose is None:
            progress("Cargando el modelo de pose…")
            self._pose = PoseEstimator(self.pose_path, self.device)
        progress("Estimando la pose 3D de los jugadores…")
        poses = self._pose(frame, [p["box"] for p in people])
        players, discarded = [], {}
        for p, kp in zip(people, poses):
            joints = None
            if kp is not None and (kp[:, 2] >= 0.3).sum() >= 8:
                xyz = cam.to_vertical_plane(kp[:, :2], p["ground"])
                xyz[:, 2] = np.clip(xyz[:, 2], 0, 2.3)
                joints = np.c_[xyz, np.where(kp[:, 2] >= 0.3, kp[:, 2], 0.0)]
                joints, discarded[p["id"]] = clean_joints(joints, COCO_JOINTS, kp, p["box"])
            players.append({"id": p["id"], "role": p["role"], "team": p["analysis_team"], "box": p["box"],
                            "conf": p["conf"], "ground": p["ground"], "joints": joints, "kp2d": kp,
                            "parts_2d": parts_on_ground_2d(cam, kp, joints, COCO_JOINTS, box_bottom(p["box"]))})

        ball_uv = None
        if isinstance(ball, (list, tuple)):
            ball_uv = [round(float(v), 1) for v in ball[:2]]
            ground = cam.to_ground([ball[:2]])[0][:2]
            ball, ball_source = {"box": [ball[0], ball[1], ball[0], ball[1]], "conf": 1.0, "ground": ground}, "user"
        elif ball == "none":
            ball, ball_source = None, "none"
        else:
            ball, ball_source = prep["ball"], "detector"
        ball_xy = None if ball is None else ball["ground"]
        uncertainty = self._uncertainty(cam, prep["calibration"], [att["box"], dfd["box"]])
        result = evaluate_selected(players, ball_xy, COCO_JOINTS, direction, attacker, defender, uncertainty)
        result["ball_source"] = ball_source
        result["ball_xy"] = None if ball_xy is None else [round(float(v), 3) for v in ball_xy]
        result["ball_uv"] = ball_uv  # image point marked by the user
        if ball_source == "none":
            result["warnings"] = [w for w in result["warnings"] if not w.startswith("Balón no detectado")]
            result["warnings"].append("Sin balón (indicado por el usuario): la línea solo depende del defensor")
        if result["status"] in ("offside", "onside"):
            by_id = {p["id"]: p for p in players}
            result["check_2d"] = check_2d(by_id[attacker]["parts_2d"], by_id[defender]["parts_2d"], ball_xy, direction, result)
            if not result["check_2d"]["agrees"]:
                result["warnings"].append(
                    f"En 2D (sin la pose 3D) sale otra decisión (margen {100 * result['check_2d']['margin_m']:+.0f} cm): "
                    "revisa la pose del atacante y del defensor")
            result["discarded_joints"] = {str(pid): discarded.get(pid, []) for pid in (attacker, defender)}
        if prep["calibration"].get("dubious"):
            result["warnings"].append("Calibración dudosa: las marcas no encajan bien con las líneas del campo")
        if ball is not None and ball_source == "detector":
            result["warnings"].append("Balón tomado del detector y supuesto en el suelo: compruébalo en la imagen "
                                      "(si no es el del pase, márcalo a mano o indica «sin balón»)")

        # Output: viewer JSON and pass image
        progress("Guardando el análisis…")
        os.makedirs(self.out_dir, exist_ok=True)
        number = self.source.number(index)
        stem = os.path.join(self.out_dir, f"{re.sub(r'[^A-Za-z0-9_-]+', '_', self.source.name)}_f{number}")
        team_bgr = prep["team_bgr"]
        roles = {p["id"]: p["role"] for p in people}
        teams = {p["id"]: p["analysis_team"] for p in people if p["analysis_team"] is not None}
        entities = [{"id": p["id"], "team": f"team{teams[p['id']]}" if p["id"] in teams else "officials",
                     "role": p["role"], "number": str(p["id"])} for p in people]
        event = {"id": f"fotograma_{number}", "type": "pass", "frame": number, "time": 0.0, "passer": None,
                 "receiver": attacker, "attacking_team": f"team{attacking_team}", "offside": result}
        write_analysis(stem + ".json", title=f"{self.source.name} · fotograma {number}",
                       source_info={"input": self.source.name, "frame": number, "detector": self.detector_path,
                                    "pose": self.pose_path, "calibration": f"HRNet ({os.path.basename(self.hrnet.checkpoint)})",
                                    "selection": "atacante y defensor elegidos por el usuario"},
                       fps=self.source.fps,
                       frames=[{"frame": number, "time": 0.0, "players": players,
                                "ball": None if ball is None else (*ball["ground"], ball["conf"])}],
                       entities=entities, team_colors=team_bgr,
                       keeper_colors=keeper_colors(teams, roles, prep["colors"], team_bgr),
                       attack_direction=direction, events=[event], warnings=[])
        draw_pass_frame(frame, cam, players, team_bgr, result, stem + "_var.jpg")
        return {**{k: result.get(k) for k in ("status", "within_uncertainty", "margin_m", "uncertainty_m", "warnings",
                                               "check_2d", "discarded_joints", "ball_source")},
                "line_source": result.get("line", {}).get("source"),
                "attacker_joint": result.get("attacker", {}).get("joint"),
                "defender_joint": result.get("defender", {}).get("joint"),
                "json": stem + ".json", "image": stem + "_var.jpg", "seconds": round(time.monotonic() - t0, 1)}

    @staticmethod
    def _uncertainty(cam, calibration, boxes):
        """Calibration error in metres where the players are (twice the marking error) plus 15 cm of pose."""
        # No measured error (camera tracked without markings to confirm it): assume a high one
        px_err = calibration.get("error_px")
        if px_err is None or not np.isfinite(px_err):
            px_err = 4.0
        m_per_px = 0.0
        for box in boxes:
            u, v = box_bottom(box)
            g = cam.to_ground([[u, v], [u + 1, v]])
            m_per_px = max(m_per_px, float(np.linalg.norm(g[1] - g[0])))
        return float(np.hypot(px_err * m_per_px * 2, 0.15))


def _stored_center(path):
    """Camera position stored in a camara.json next to the video or in a parent folder
    (written by scripts/broadcast/stadium_camera.py).
    """
    import json
    folder = os.path.dirname(os.path.abspath(path))
    for _ in range(4):
        candidate = os.path.join(folder, "camara.json")
        if os.path.exists(candidate):
            with open(candidate, encoding="utf-8") as f:
                return np.asarray(json.load(f)["centro"], float)
        folder = os.path.dirname(folder)
    return None


def _good(c):
    needed = GOOD_INLIERS_FIXED if c.get("method") == "posición fija" else GOOD_INLIERS
    return c["cam"] is not None and c["good"] >= needed and c["n"] >= MIN_MARKS and c["med"] <= GOOD_ERROR_PX


def _score(c):
    """For comparing calibrations: a camera exists, it fits enough markings and with a small error."""
    med = c["med"] if np.isfinite(c["med"]) else MAX_MARK_ERROR_PX
    return (c["cam"] is not None, c["n"] >= MIN_MARKS, -med)


def _player(people, pid):
    for p in people:
        if p["id"] == pid:
            return p
    raise ValueError(f"No hay ningún jugador con el número {pid} en este fotograma")


def _image_polylines(cam, w, h, step=0.5):
    """Pitch markings projected into the image, split where they fall behind the camera or far outside."""
    H = camlib.homography_from_camera(cam)
    out = []
    for poly in camlib.pitch_polylines():
        dense = np.concatenate([np.linspace(a, b, max(2, int(np.linalg.norm(b - a) / step))) for a, b in zip(poly[:-1], poly[1:])])
        p = H @ np.c_[dense, np.ones(len(dense))].T
        ok = p[2] > 1e-9
        uv = (p[:2] / np.where(ok, p[2], 1)).T
        ok &= (uv[:, 0] > -w) & (uv[:, 0] < 2 * w) & (uv[:, 1] > -h) & (uv[:, 1] < 2 * h)
        run = []
        for good, q in zip(ok, uv):
            if good:
                run.append([round(float(q[0]), 1), round(float(q[1]), 1)])
            elif len(run) > 1:
                out.append(run[::2] + run[-1:])
                run = []
            else:
                run = []
        if len(run) > 1:
            out.append(run[::2] + run[-1:])
    return out


def _footprint(cam, w, h):
    """Part of the grass visible in the image (polygon in metres), for the minimap."""
    us, vs = np.meshgrid(np.linspace(0, w, 25), np.linspace(0, h, 15))
    uv = np.c_[us.ravel(), vs.ravel()]
    C = cam.center
    d = cam.ray(uv)
    s = -C[2] / d[:, 2]
    g = C[:2] + s[:, None] * d[:, :2]
    keep = (s > 0) & (np.abs(g[:, 0]) < 75) & (np.abs(g[:, 1]) < 55)
    if keep.sum() < 3:
        return []
    hull = cv2.convexHull(g[keep].astype(np.float32))[:, 0, :]
    return [[round(float(x), 2), round(float(y), 2)] for x, y in hull]
