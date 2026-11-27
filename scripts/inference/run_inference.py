"""Inference pipeline: from a video (or folder of images) to the 3D analysis of the play.

  1. Detection and tracking of players, goalkeepers, referees and ball (YOLO + ByteTrack)
  2. Camera in every frame: calibrated keyframe + tracking (pan and zoom) refined on the pitch lines
  3. Teams by shirt colour
  4. 2D pose of each player (YOLO-pose on their crop) lifted to 3D with the camera
  5. Offside position in the pass frame (given by the user)
  6. offside-analysis JSON for the 3D viewer + pass image with the lines drawn

Example (SoccerNet clip with an offside):
    python3 run_inference.py --input <dataset_dir>/SoccerNet/tracking-2023/test/SNMOT-191/img1 \
        --keyframe keyframes/SNMOT-191.json --start 476 --end 560 --pass-frame 531 \
        --output outputs/SNMOT-191.json
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import cv2
import numpy as np

from offside_inference import camera as camlib
from offside_inference import config
from offside_inference.detection import (DEFAULT_POSE, Tracker, ball_near_feet, box_bottom, choose_ball, default_detector,
                                         track_roles)
from offside_inference.drawing import draw_pass_frame
from offside_inference.export import write_analysis
from offside_inference.frames import FrameSource
from offside_inference.offside import clean_joints, evaluate
from offside_inference.pose import COCO_JOINTS, PoseEstimator
from offside_inference.teams import assign_teams, jersey_color, keeper_colors



def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def keyframe_camera(spec, frame, image_size, people_boxes):
    """Keyframe camera from the lines and points marked in it."""
    def field(v):
        return camlib.FIELD_POINTS[v] if isinstance(v, str) else tuple(v)
    points = [(field(p["field"]), tuple(p["image"])) for p in spec.get("points", [])]
    lines = [(l["field"], camlib.line_from_points(*l["image"])) for l in spec.get("lines", [])]
    H = camlib.homography_from_correspondences(points, lines)
    cam, _ = camlib.camera_from_homography(H, image_size)
    cam, med, n = camlib.refine_camera(cam, frame, people_boxes, fix_center=False)
    return cam, med, n


def track_camera(frames, key_number, key_cam, boxes_by_frame):
    """Camera of every frame, from the keyframe forwards and backwards."""
    numbers = [n for n, _ in frames]
    index = {n: i for i, n in enumerate(numbers)}
    cams = {key_number: (key_cam, 0.0, "clave")}
    for step in (1, -1):
        i = index[key_number]
        cam = key_cam
        prev_gray = cv2.cvtColor(frames[i][1], cv2.COLOR_BGR2GRAY)
        i += step
        while 0 <= i < len(frames):
            number, frame = frames[i]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            boxes = boxes_by_frame.get(number, [])
            H_rel = camlib.frame_motion(prev_gray, gray, boxes)
            predicted = camlib.predict_with_motion(cam, H_rel) if H_rel is not None else cam
            # Refine from the prediction and from the previous camera, and keep the one that fits best
            options = [camlib.refine_camera(start, frame, boxes) for start in (predicted, cam)]
            refined, med, n = min(options, key=lambda o: o[1])
            if n >= 40 and med < 3.0:
                cam, quality, method = refined, med, "líneas"
            else:
                cam, quality, method = predicted, float("nan"), "movimiento" if H_rel is not None else "sin cambio"
            cams[number] = (cam, quality, method)
            prev_gray = gray
            i += step
    return cams


def smooth_tracks(per_frame, key, window=5):
    """Centred moving average per track of a numeric field (position or joints)."""
    series = defaultdict(list)
    for f_idx, players in enumerate(per_frame):
        for p in players:
            if p.get(key) is not None:
                series[p["id"]].append((f_idx, p))
    half = window // 2
    for items in series.values():
        values = [np.array(p[key], float) for _, p in items]
        frames_idx = [f for f, _ in items]
        for k, (f, p) in enumerate(items):
            near = [values[j] for j in range(max(0, k - half), min(len(items), k + half + 1))
                    if abs(frames_idx[j] - f) <= half and values[j].shape == values[k].shape]
            p[key] = np.nanmean(near, axis=0) if key == "ground" else _smooth_joints(near)


def _smooth_joints(near):
    """Averages each joint only over the frames where it is reliable (confidence > 0)."""
    arr = np.stack(near)
    valid = arr[:, :, 3] > 0
    out = np.full(arr.shape[1:], np.nan)
    count = valid.sum(axis=0)
    for j in np.nonzero(count)[0]:
        out[j, :3] = arr[valid[:, j], j, :3].mean(axis=0)
        out[j, 3] = arr[valid[:, j], j, 3].mean()
    out[count == 0, 3] = 0.0
    return out


def interpolate_ball(per_frame, max_gap):
    """Fills short gaps of the ball by linear interpolation between detections (confidence 0.3).

    Interpolated positions are flagged with "ball_interpolated": they are used to draw the ball and
    compare it with the line, but not to decide who had it.
    """
    known = [i for i, f in enumerate(per_frame) if f["ball"] is not None]
    filled = 0
    for a, b in zip(known[:-1], known[1:]):
        if 1 < b - a <= max_gap:
            pa, pb = np.array(per_frame[a]["ball"][:2]), np.array(per_frame[b]["ball"][:2])
            for i in range(a + 1, b):
                x, y = pa + (pb - pa) * (i - a) / (b - a)
                per_frame[i]["ball"] = (x, y, 0.3)
                per_frame[i]["ball_interpolated"] = True
                filled += 1
    return filled


def find_passer(per_frame, pass_index, max_frames):
    """Player closest to the ball at the last real detection before the pass (at most max_frames)."""
    for i in range(pass_index, max(-1, pass_index - max_frames - 1), -1):
        f = per_frame[i]
        if f["ball"] is None or f.get("ball_interpolated"):
            continue
        bx, by = f["ball"][:2]
        candidates = [(np.hypot(p["ground"][0] - bx, p["ground"][1] - by), p) for p in f["players"]
                      if p["role"] != "referee" and p.get("team") is not None]
        if candidates:
            d, p = min(candidates, key=lambda c: c[0])
            if d < 2.5:
                return p["id"], p["team"], f["frame"], d
    return None, None, None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Vídeo o carpeta de imágenes")
    ap.add_argument("--output", required=True, help="JSON de salida (formato offside-analysis)")
    ap.add_argument("--keyframe", required=True, help="JSON con las líneas/puntos del campo de un fotograma")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--fps", type=float, help="Fotogramas por segundo (carpetas de imágenes; 25 por defecto)")
    ap.add_argument("--pass-frame", type=int, help="Fotograma del pase (si no se indica, no se evalúa)")
    ap.add_argument("--passer", type=int, help="Pista del pasador (por defecto, el más cercano al balón)")
    ap.add_argument("--attack-direction", type=int, choices=[-1, 1], help="+1 si se ataca hacia +X")
    ap.add_argument("--detector", default=None)
    ap.add_argument("--pose", default=DEFAULT_POSE)
    ap.add_argument("--no-pose", action="store_true")
    ap.add_argument("--device", default="cpu", help="cpu o el índice de la GPU (0)")
    ap.add_argument("--imgsz", type=int, default=1280)
    args = ap.parse_args()

    detector_path = args.detector or default_detector()
    with open(args.keyframe) as f:
        key_spec = json.load(f)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    log(f"Leyendo fotogramas de {args.input}")
    source = FrameSource(args.input, args.start, args.end, args.fps)
    frames = list(source)
    if not frames:
        sys.exit("No hay fotogramas en el rango indicado")
    numbers = [n for n, _ in frames]
    frame_of = dict(frames)
    log(f"{len(frames)} fotogramas ({numbers[0]}-{numbers[-1]}), {source.size[0]}x{source.size[1]} a {source.fps:g} fps")

    # 1. Detection and tracking
    log(f"Detección y seguimiento con {os.path.relpath(detector_path, config.ROOT)}")
    tracker = Tracker(detector_path, args.device, args.imgsz)
    detections, balls = {}, {}
    for number, frame in frames:
        detections[number], ball = tracker(frame)
        # Candidates from the full frame and from enlarged foot crops (chosen later with the camera)
        balls[number] = (ball or {}).get("candidates", []) + ball_near_feet(
            tracker.model, frame, [p["box"] for p in detections[number] if p["role"] != "referee"],
            args.device, tracker.roles)
    roles = track_roles(detections)
    for people in detections.values():
        for p in people:
            p["role"] = roles[p["track"]]
    boxes_by_frame = {n: [p["box"] for p in people] for n, people in detections.items()}
    log(f"{len(roles)} pistas ({sum(r == 'player' for r in roles.values())} jugadores); "
        f"candidatos a balón en {sum(bool(b) for b in balls.values())} fotogramas")

    # 2. Camera
    key_number = key_spec["frame"]
    if key_number not in frame_of:
        sys.exit(f"El fotograma clave {key_number} no está en el rango leído")
    key_cam, key_med, key_n = keyframe_camera(key_spec, frame_of[key_number], source.size, boxes_by_frame[key_number])
    C = key_cam.center
    log(f"Cámara del fotograma clave: focal {key_cam.focal:.0f} px, posición ({C[0]:.1f}, {C[1]:.1f}, {C[2]:.1f}) m, "
        f"marcas a {key_med:.2f} px de las líneas ({key_n} puntos)")
    cams = track_camera(frames, key_number, key_cam, boxes_by_frame)
    by_lines = sum(1 for _, q, m in cams.values() if m == "líneas")
    log(f"Cámara ajustada a las líneas en {by_lines + 1} de {len(frames)} fotogramas; el resto, por movimiento")

    # 3. Teams
    colors = defaultdict(list)
    for number, people in detections.items():
        for p in people:
            c = jersey_color(frame_of[number], p["box"])
            if c is not None:
                colors[p["track"]].append(c)
    teams, team_bgr, odd = assign_teams(colors, roles)
    for t in odd:
        roles[t] = "referee"
    for people in detections.values():
        for p in people:
            p["role"] = roles[p["track"]]
    log(f"Equipos: {sum(1 for t in teams.values() if t == 0)} y {sum(1 for t in teams.values() if t == 1)} jugadores"
        + (f"; {len(odd)} con un color de ningún equipo (se tratan como árbitros): {sorted(odd)}" if odd else ""))

    # 4. Pose and 3D
    pose = None if args.no_pose else PoseEstimator(args.pose, args.device)
    per_frame = []
    for number, frame in frames:
        cam = cams[number][0]
        people = [p for p in detections[number] if p["role"] != "ball"]
        poses = pose(frame, [p["box"] for p in people]) if pose else [None] * len(people)
        players = []
        for p, kp in zip(people, poses):
            ground = cam.to_ground([box_bottom(p["box"])])[0][:2]
            joints = None
            if kp is not None and (kp[:, 2] >= 0.3).sum() >= 8:
                xyz = cam.to_vertical_plane(kp[:, :2], ground)
                xyz[:, 2] = np.clip(xyz[:, 2], 0, 2.3)
                conf = np.where(kp[:, 2] >= 0.3, kp[:, 2], 0.0)
                joints, _ = clean_joints(np.c_[xyz, conf], COCO_JOINTS, kp, p["box"])
            players.append({"id": p["track"], "role": p["role"], "box": p["box"], "conf": p["conf"],
                            "ground": ground, "joints": joints})
        # Only inside the pitch and, if there is one, the one next to a player's feet
        chosen = choose_ball(balls[number], [p["ground"] for p in players if p["role"] != "referee"], cam)
        ball = None if chosen is None else (*chosen["ground"], chosen["conf"])
        per_frame.append({"frame": number, "time": (number - numbers[0]) / source.fps, "players": players, "ball": ball})
    filled = interpolate_ball(per_frame, max_gap=int(1.2 * source.fps))
    log(f"Balón interpolado en {filled} fotogramas sin detección (huecos de hasta 1,2 s)")
    smooth_tracks([f["players"] for f in per_frame], "ground")
    smooth_tracks([f["players"] for f in per_frame], "joints")
    with_pose = sum(p["joints"] is not None for f in per_frame for p in f["players"])
    total = sum(len(f["players"]) for f in per_frame)
    log(f"Pose 3D en {with_pose} de {total} detecciones ({100 * with_pose / max(1, total):.0f} %)")

    # Goalkeeper: to the team whose centroid is closest to their mean position
    mean_x = defaultdict(list)
    for f in per_frame:
        for p in f["players"]:
            mean_x[p["id"]].append(p["ground"][0])
    team_center = [np.mean([np.mean(mean_x[t]) for t, team in teams.items() if team == k] or [0]) for k in (0, 1)]
    for t, role in roles.items():
        if role == "goalkeeper":
            teams[t] = int(np.argmin([abs(np.mean(mean_x[t]) - c) for c in team_center]))
    keeper_bgr = keeper_colors(teams, roles, colors, team_bgr)
    for f in per_frame:
        for p in f["players"]:
            p["team"] = teams.get(p["id"])

    # 5. Offside
    events, attack_direction = [], args.attack_direction
    warnings = [f"Detector: {os.path.basename(os.path.dirname(os.path.dirname(detector_path)))}",
                "Puntos del cuerpo llevados a 3D con un plano vertical por jugador (aproximación monocular)",
                "Pose COCO-17: los tobillos sustituyen a la punta del pie"]
    if args.pass_frame is not None:
        f = next((f for f in per_frame if f["frame"] == args.pass_frame), None)
        if f is None:
            sys.exit(f"El fotograma del pase {args.pass_frame} no está en el rango leído")
        cam, quality, method = cams[args.pass_frame]
        # Uncertainty: calibration error in metres (near the visible area) + pose / plane
        px_err = quality if np.isfinite(quality) else 4.0
        g = cam.to_ground([[source.size[0] / 2, source.size[1] / 2], [source.size[0] / 2 + 1, source.size[1] / 2]])
        m_per_px = float(np.linalg.norm(g[1] - g[0]))
        uncertainty = float(np.hypot(px_err * m_per_px * 2, 0.15))
        ball_xy = f["ball"][:2] if f["ball"] is not None else None
        passer, attacking_team = args.passer, None
        if passer is None:
            passer, attacking_team, seen_at, dist = find_passer(per_frame, per_frame.index(f), int(0.8 * source.fps))
            if passer is not None:
                log(f"Pasador: pista {passer} (equipo {attacking_team}), a {dist:.1f} m del balón en el fotograma {seen_at}")
        if args.attack_direction is not None and attacking_team is not None:
            # With the attacking direction known, each goalkeeper belongs to the team defending the goal on
            # their side. Assigning by distance to each team's centre fails when the attack is pushed forward
            for t, role in roles.items():
                if role == "goalkeeper" and mean_x[t]:
                    own_goal = np.sign(np.mean(mean_x[t]))
                    teams[t] = attacking_team if own_goal == -args.attack_direction else 1 - attacking_team
            for fr in per_frame:
                for p in fr["players"]:
                    p["team"] = teams.get(p["id"])
            keeper_bgr = keeper_colors(teams, roles, colors, team_bgr)
        result = evaluate(f["players"], ball_xy, COCO_JOINTS, args.attack_direction, passer, attacking_team, uncertainty)
        if f.get("ball_interpolated"):
            result["warnings"].append("Balón interpolado en el fotograma del pase (no detectado)")
        result["warnings"].append(f"Cámara del fotograma del pase: {method}"
                                  + (f" ({quality:.1f} px)" if np.isfinite(quality) else ""))
        attack_direction = result.get("attack_direction", attack_direction)
        log(f"Fotograma {args.pass_frame}: {result['status']}"
            + (f", margen {100 * result['margin_m']:+.1f} cm ±{100 * uncertainty:.0f} cm, atacante {result['attacker']['id']} "
               f"({result['attacker']['joint']}), defensor {result['defender']['id']} ({result['defender']['joint']})"
               if "margin_m" in result else ""))
        for w in result["warnings"]:
            log(f"  aviso: {w}")
        event = {"id": f"pase_{args.pass_frame}", "type": "pass", "frame": args.pass_frame,
                 "time": f["time"], "passer": result.get("passer"), "receiver": result.get("attacker", {}).get("id"),
                 "attacking_team": f"team{result['attacking_team']}" if "attacking_team" in result else None,
                 "offside": result}
        events.append(event)
        draw_pass_frame(frame_of[args.pass_frame], cam, f["players"], team_bgr, result,
                        os.path.splitext(args.output)[0] + f"_pase_{args.pass_frame}.jpg")

    # 6. Export
    entities = [{"id": t, "team": "officials" if role == "referee" else f"team{teams[t]}" if t in teams else "officials",
                 "role": role, "number": str(t)} for t, role in sorted(roles.items())]
    title = f"{os.path.basename(os.path.normpath(args.input))} ({numbers[0]}-{numbers[-1]})"
    write_analysis(args.output, title=title,
                   source_info={"input": os.path.abspath(args.input), "detector": detector_path,
                                "pose": None if args.no_pose else args.pose, "keyframe": os.path.abspath(args.keyframe)},
                   fps=source.fps, frames=per_frame, entities=entities, team_colors=team_bgr,
                   keeper_colors=keeper_bgr, attack_direction=attack_direction, events=events, warnings=warnings)
    log(f"Análisis escrito en {args.output}")


if __name__ == "__main__":
    main()
