"""Set of frames to improve ball detection (and players, goalkeepers and referees along the way),
taken from the Club World Cup matches and pre-labelled for review in CVAT.

The detector fails most on the ball leaving the foot: passes, crosses, free kicks and restarts. So
most frames come from those moments (ESPN events already synchronised with the video), plus some
open play so the set is not biased:

    fuera_de_juego, gol      the seconds before the event (the pass), 3 frames per second
    saque_esquina            5 to 45 s after it is awarded (the corner is taken in that window)
    saque_puerta             5 to 40 s after the shot wide
    falta                    5 to 40 s after the foul (the free kick)
    disparo                  the 6 s before the shot (the previous pass)
    juego                    random instants of each half

Main camera only: shots with fewer than 6 detected people or with large people (close-ups, replays)
are dropped. Frames come from the original recordings, not from the re-encoded clips.

Pre-labels: the current detector (full frame and enlarged foot crops) corrected with the frame's
calibration (HRNet with the stadium camera position fixed):
  - people not standing on the pitch are dropped (ball kids, bench, camera operators); referees may
    be up to 3 m outside (assistants on the touchline);
  - goalkeeper: the detector rarely marks it in these broadcasts (it learnt SoccerNet's kits), so
    for each goal it is, among those within 11 m of the goal line whose colour differs from both
    teams, the one closest to the line;
  - referees: the detector's only if their colour matches neither team, plus "players" of neither
    team's colour next to the touchline (assistants). Not on the pitch: striped shirts also give a
    colour that matches neither team;
  - ball: at most one, inside the pitch and, if there is one, next to someone's feet. Never on the
    feet (the bottom quarter of a person's box): there the detector confuses white boots with the
    ball and its confidence does not separate them. Not on the penalty or centre spots either.
Frames that do not calibrate are dropped (they are usually not from the main camera). They are
sorted by review priority: first those with an unlabelled candidate on the feet (check whether it is
the ball or a boot), then ball next to a player, no ball, and loose ball.

Output in conjunto_balon/mezcla/ (or conjunto_balon/<match>/ with --por-partido):
    imagenes.zip      to create the task in CVAT
    anotaciones.zip   "YOLO 1.1" format for "Upload annotations" in that task
    indice.csv        where each frame comes from (event, minute, video, frame)

Usage:
    python3 ball_dataset.py                     # 250 frames from every match in conjunto_balon/mezcla
    python3 ball_dataset.py --balon --total 700 --nombre balon_lote1 --semilla 1 --excluir conjunto_balon/mezcla/indice.csv
                                                # ball batch, without repeating annotated frames
    python3 ball_dataset.py --partidos FLU-HIL --por-partido 250   # one set per match
"""
import argparse
import csv
import json
import os
import sys
import zipfile

import cv2
import numpy as np

from offside_inference import config
from offside_inference.detection import (FrameDetector, ball_near_feet, box_bottom, choose_ball,
                                         default_detector)
from offside_inference.session import MAX_MARK_ERROR_PX, MIN_MARKS, Session
from offside_inference.teams import assign_teams, jersey_color

HERE = config.path("broadcast_dir")
OUT = os.path.join(HERE, "conjunto_balon")
CLASSES = ["player", "goalkeeper", "referee", "ball"]
# type: (from, to, frames per second) relative to the ESPN timestamp
VENTANAS = {
    "fuera_de_juego": (-10, 0, 3), "gol": (-12, 0, 3), "saque_esquina": (5, 45, 1),
    "saque_puerta": (5, 40, 1), "falta": (5, 40, 0.5), "disparo": (-6, 0, 2),
}
# Share of the total for each group
CUPO = {"fuera_de_juego": 0.15, "gol": 0.15, "saque_esquina": 0.1, "saque_puerta": 0.1, "falta": 0.15,
        "disparo": 0.1, "juego": 0.25}
# Ball batch (--balon): more passes, crosses and free kicks, which is where it fails
CUPO_BALON = {"fuera_de_juego": 0.2, "gol": 0.15, "saque_esquina": 0.15, "saque_puerta": 0.05, "falta": 0.15,
              "disparo": 0.15, "juego": 0.15}
EXCLUDE_S = 1.0  # minimum gap to an already annotated frame (s)
MIN_PEOPLE, MAX_PERSON_HEIGHT = 6, 0.15  # main camera: many small people


def candidates(match, events, rng):
    """[(group, video second, half, event)] for this match, shuffled per group."""
    groups = {g: [] for g in CUPO}
    for e in events:
        if e["partido"] != match["partido"] or e["en_video"] != "1" or e["tipo"] not in VENTANAS:
            continue
        a, b, fps = VENTANAS[e["tipo"]]
        t0 = float(e["video_s"])
        for t in np.arange(t0 + a, t0 + b + 1e-6, 1 / fps):
            groups[e["tipo"]].append((e["tipo"], round(float(t), 2), e["parte"], e))
    for part, info in match["partes"].items():
        # Open play: random instants of each half (45 min + approximate stoppage time)
        start = max(0.0, info["inicio_s"])
        end = min(info["duracion_video_s"], info["inicio_s"] + 50 * 60)
        for t in rng.uniform(start, end, 400):
            groups["juego"].append(("juego", round(float(t), 2), part, None))
    for g in groups.values():
        rng.shuffle(g)
    return groups


def video_of(match, part):
    return os.path.join(CONFIG["carpeta_videos"], match["partes"][str(part)]["video"])


def read_at(cap, t, fps):
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
    ok, frame = cap.read()
    return frame if ok else None


def main_camera(people, h):
    if len(people) < MIN_PEOPLE:
        return False
    heights = [(p["box"][3] - p["box"][1]) / h for p in people]
    return float(np.median(heights)) < MAX_PERSON_HEIGHT


PITCH_X, PITCH_Y, REFEREE_Y = 53.5, 35.0, 37.0  # pitch + margin (m); assistants on the touchline
KEEPER_X, KEEPER_Y = 52.5 - 11.0, 15.0  # goalkeeper zone: 11 m from the goal line
KEEPER_MIN_COLOR = 20.0  # minimum Lab distance to both teams


def calibrate(session, frame, index, people):
    """Frame camera with the stadium position fixed, or None if it does not fit the lines."""
    c = session._calibrate_frame(frame, index, [p["box"] for p in people])
    ok = c["cam"] is not None and c["n"] >= MIN_MARKS and c["med"] <= MAX_MARK_ERROR_PX
    return (c["cam"], c["med"]) if ok else (None, None)


def pre_label(detector, frame, people, whole_ball, cam, extra=()):
    """People on the pitch with corrected roles and at most one ball.

    Args:
        extra: candidates from the ball-only detector (relabel.py). It was trained with crops of boots
            without a ball, so with confidence of at least TRUST_BALL_MODEL a candidate is accepted
            even on someone's feet.

    Returns:
        (people, ball, ball next to someone's feet, candidate found on the feet).
    """
    for p in people:
        p["ground"] = cam.to_ground([box_bottom(p["box"])])[0][:2]
    people = [p for p in people if abs(p["ground"][0]) <= PITCH_X
              and abs(p["ground"][1]) <= (REFEREE_Y if p["role"] == "referee" else PITCH_Y)]
    colors = {i: [c] for i, p in enumerate(people) if (c := jersey_color(frame, p["box"])) is not None}
    # Teams are clustered with everyone: the detector labels whole kits that look like SoccerNet's as
    # referee or goalkeeper, and outside the clustering they had no team. Those of neither team come out
    # as outliers.
    _, team_bgr, odd = assign_teams(colors, {i: "player" for i in range(len(people))}, min_samples=1,
                                    min_outlier_dist=40.0)
    centers = cv2.cvtColor(np.uint8([team_bgr]), cv2.COLOR_BGR2LAB)[0].astype(float)
    team_dist = {i: float(np.min(np.linalg.norm(centers - colors[i][0], axis=1))) for i in colors}
    for i, p in enumerate(people):
        # Detector referee only if their colour matches neither team; the goalkeeper is decided below
        if p["role"] == "goalkeeper" or (p["role"] == "referee" and team_dist.get(i, 0.0) < KEEPER_MIN_COLOR):
            p["role"] = "player"
    # Goalkeeper: for each goal, among those near the goal line with a colour away from both teams, the
    # closest to the line (a goalkeeper's purple can be close to a team's maroon, so being an outlier on
    # the whole pitch is not enough)
    for side in (-1, 1):
        # Referees included: the detector sometimes calls an oddly coloured goalkeeper a referee
        zone = [i for i, p in enumerate(people) if i in colors
                and side * p["ground"][0] >= KEEPER_X and abs(p["ground"][1]) <= KEEPER_Y]
        if not zone:
            continue
        # Among the odd colours, the one closest to the goal line: the oddest of all fails with striped
        # shirts (they average to a grey that matches neither team)
        odd_zone = [i for i in zone if team_dist[i] >= KEEPER_MIN_COLOR]
        if odd_zone:
            people[max(odd_zone, key=lambda i: side * people[i]["ground"][0])]["role"] = "goalkeeper"
    # A "player" of neither team's colour next to the touchline is an assistant referee (not on the
    # pitch: striped shirts also give a colour that matches neither team)
    for i, p in enumerate(people):
        if p["role"] == "player" and i in odd and abs(p["ground"][1]) >= PITCH_Y - 3:
            p["role"] = "referee"
    boxes = [p["box"] for p in people if p["role"] != "referee"]
    cands = (whole_ball or {}).get("candidates", []) + ball_near_feet(
        detector.model, frame, boxes, detector.device, detector.roles, conf=0.3)
    # White boots and the penalty or centre spots are confused with the ball and confidence does not
    # separate them: no ball is pre-labelled on someone's feet or on those spots
    on_boot = [c for c in cands if on_feet(c["box"], [p["box"] for p in people])]
    cands = [c for c in cands if not any(c is b for b in on_boot) and not on_spot(c["box"], cam)]
    cands += [c for c in extra if not on_spot(c["box"], cam)
              and (c["conf"] >= TRUST_BALL_MODEL or not on_feet(c["box"], [p["box"] for p in people]))]
    feet = [p["ground"] for p in people if p["role"] != "referee"]
    ball = choose_ball(cands, feet, cam)
    return people, ball, bool(ball and ball["near_player"]), bool(on_boot)


BOOT_FROM = 0.75  # bottom part of a person's box (fraction of their height) where the feet are
SPOTS = [(0.0, 0.0), (-41.5, 0.0), (41.5, 0.0)]
SPOT_M = 0.7
TRUST_BALL_MODEL = 0.5


def on_feet(ball_box, person_boxes):
    cx, cy = (ball_box[0] + ball_box[2]) / 2, (ball_box[1] + ball_box[3]) / 2
    return any(x1 <= cx <= x2 and y1 + BOOT_FROM * (y2 - y1) <= cy <= y2 + 2 for x1, y1, x2, y2 in person_boxes)


def on_spot(ball_box, cam):
    g = cam.to_ground([box_bottom(ball_box)])[0][:2]
    return any(np.hypot(g[0] - x, g[1] - y) <= SPOT_M for x, y in SPOTS)


def yolo_line(cls, box, w, h):
    x1, y1, x2, y2 = box
    return f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}"


def sample(match, events, detector, session, total, rng, cupo=CUPO, taken_frames=()):
    """Pre-labelled frames of a match, split per group by quota, more than EXCLUDE_S away from the frames
    in taken_frames ({(video, frame)} already annotated in another set).
    """
    name = match["partido"]
    groups = candidates(match, events, rng)
    session.center = {"center": np.asarray(match["camara"]["centro"], float), "source": "estadio",
                      "frames": 0, "spread_m": 0.0}
    caps = {}
    rows, uncalibrated = [], 0
    # Quota per group with the remainders distributed (they add up to exactly total); whatever a group
    # without enough events lacks goes to open play, which comes last
    exact = {g: total * share for g, share in cupo.items()}
    quota = {g: int(v) for g, v in exact.items()}
    for g in sorted(exact, key=lambda g: quota[g] - exact[g])[:total - sum(quota.values())]:
        quota[g] += 1
    missing = 0
    annotated = {}
    for video, f in taken_frames:
        annotated.setdefault(video, []).append(f)
    for group in cupo:
        want, taken = quota[group] + (missing if group == "juego" else 0), 0
        for _, t, part, event in groups[group]:
            if taken >= want:
                break
            path = video_of(match, part)
            index = int(round(t * match["fps"]))
            if any(abs(index - f) < EXCLUDE_S * match["fps"] for f in annotated.get(os.path.basename(path), [])):
                continue
            if path not in caps:
                caps[path] = cv2.VideoCapture(path)
            frame = read_at(caps[path], t, match["fps"])
            if frame is None:
                continue
            h, w = frame.shape[:2]
            people, whole_ball = detector(frame)
            if not main_camera(people, h):
                continue
            cam, error_px = calibrate(session, frame, int(round(t * match["fps"])), people)
            if cam is None:
                uncalibrated += 1
                continue
            people, ball, near, on_boot = pre_label(detector, frame, people, whole_ball, cam)
            # Review priority: 0 = possible unlabelled ball on the feet (pass or boot),
            # 1 = ball next to a player, 2 = no ball, 3 = loose ball
            priority = (0 if ball is None and on_boot else 1 if ball is not None and near
                        else 2 if ball is None else 3)
            stem = f"{name}_p{part}_{group}_{int(t // 60):03d}m{t % 60:04.1f}s"
            rows.append({"stem": stem, "partido": name, "prioridad": priority, "grupo": group, "parte": part, "video": os.path.basename(path),
                         "video_s": t, "fotograma": int(round(t * match["fps"])),
                         "evento": "" if event is None else f"{event['minuto']} {event['tipo']}",
                         "balon_pre": "" if ball is None else f"{ball['conf']:.2f} {ball.get('source', 'fotograma')}",
                         "porteros": sum(p["role"] == "goalkeeper" for p in people), "error_px": round(error_px, 2),
                         "frame": frame, "people": people, "ball": ball})
            taken += 1
        missing += want - taken
        print(f"  {group}: {taken}/{want}", flush=True)
    for cap in caps.values():
        cap.release()
    counts = [sum(r["prioridad"] == p for r in rows) for p in (0, 1, 2, 3)]
    print(f"{name}: {len(rows)} fotogramas (posible balón en los pies sin marcar {counts[0]}, balón junto a "
          f"un jugador {counts[1]}, sin balón {counts[2]}, balón suelto {counts[3]}; con portero "
          f"{sum(r['porteros'] > 0 for r in rows)}; descartados por no calibrar {uncalibrated})", flush=True)
    return rows


def write(rows, out, rng):
    """imagenes.zip, anotaciones.zip (YOLO 1.1) and indice.csv in out."""
    os.makedirs(os.path.join(out, "obj_train_data"), exist_ok=True)
    # Review order: priority and, within it, random (file names start with the order)
    rows.sort(key=lambda r: (r["prioridad"], rng.random()))
    index = []
    with zipfile.ZipFile(os.path.join(out, "imagenes.zip"), "w") as zimg, \
            zipfile.ZipFile(os.path.join(out, "anotaciones.zip"), "w") as zann:
        names = []
        for i, r in enumerate(rows, 1):
            fname = f"{i:04d}_{r['stem']}"
            ok, jpg = cv2.imencode(".jpg", r["frame"], [cv2.IMWRITE_JPEG_QUALITY, 95])
            zimg.writestr(f"{fname}.jpg", jpg.tobytes())
            h, w = r["frame"].shape[:2]
            lines = [yolo_line(CLASSES.index(p["role"]), p["box"], w, h) for p in r["people"]]
            if r["ball"] is not None:
                lines.append(yolo_line(CLASSES.index("ball"), r["ball"]["box"], w, h))
            zann.writestr(f"obj_train_data/{fname}.txt", "\n".join(lines) + "\n")
            names.append(f"data/obj_train_data/{fname}.jpg")
            index.append({k: v for k, v in r.items() if k not in ("frame", "people", "ball", "stem")} | {"imagen": f"{fname}.jpg"})
        zann.writestr("obj.names", "\n".join(CLASSES) + "\n")
        zann.writestr("obj.data", f"classes = {len(CLASSES)}\ntrain = data/train.txt\nnames = data/obj.names\nbackup = backup/\n")
        zann.writestr("train.txt", "\n".join(names) + "\n")
    os.rmdir(os.path.join(out, "obj_train_data"))
    with open(os.path.join(out, "indice.csv"), "w", newline="", encoding="utf-8") as f:
        fields = ["imagen", "partido", "prioridad", "grupo", "parte", "evento", "video", "video_s", "fotograma", "balon_pre",
                  "porteros", "error_px"]
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(index)
    print(f"{len(rows)} fotogramas en {out}")


def main():
    global CONFIG
    ap = argparse.ArgumentParser()
    ap.add_argument("--partidos", nargs="+", default=None)
    ap.add_argument("--por-partido", type=int, default=None, help="Un conjunto por partido con N fotogramas cada uno")
    ap.add_argument("--total", type=int, default=250, help="Un solo conjunto con N fotogramas repartidos entre los partidos")
    ap.add_argument("--nombre", default="mezcla", help="Carpeta del conjunto único")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--balon", action="store_true", help="Reparto para el balón (CUPO_BALON)")
    ap.add_argument("--excluir", nargs="*", default=[], help="indice.csv de conjuntos ya anotados")
    ap.add_argument("--device", default="0")
    args = ap.parse_args()
    with open(os.path.join(HERE, "partidos.json"), encoding="utf-8") as f:
        CONFIG = json.load(f)
    with open(os.path.join(HERE, "eventos", "eventos.csv"), encoding="utf-8") as f:
        events = list(csv.DictReader(f))
    detector = FrameDetector(default_detector(), args.device)
    session = Session(device=args.device)
    matches = [m for m in CONFIG["partidos"] if not args.partidos or m["partido"] in args.partidos]
    missing = [video_of(m, part) for m in matches for part in m["partes"] if not os.path.exists(video_of(m, part))]
    if missing:
        sys.exit("No se encuentran los vídeos (¿está montado el disco?):\n  " + "\n  ".join(missing))
    cupo = CUPO_BALON if args.balon else CUPO
    taken_frames = set()
    for path in args.excluir:
        with open(path, encoding="utf-8") as f:
            taken_frames |= {(r["video"], int(r["fotograma"])) for r in csv.DictReader(f)}
    try:
        if args.por_partido:
            for match in matches:
                print(match["partido"], flush=True)
                rng = np.random.default_rng(args.semilla)
                write(sample(match, events, detector, session, args.por_partido, rng, cupo, taken_frames),
                      os.path.join(OUT, match["partido"]), rng)
        else:
            # Split evenly: with a single match the model would learn its kits, stadium and lighting
            rng = np.random.default_rng(args.semilla)
            rows = []
            for k, match in enumerate(matches):
                n = args.total // len(matches) + (k < args.total % len(matches))
                print(f"{match['partido']} ({n})", flush=True)
                rows += sample(match, events, detector, session, n, rng, cupo, taken_frames)
            write(rows, os.path.join(OUT, args.nombre), rng)
    finally:
        session.close()


CONFIG = None

if __name__ == "__main__":
    main()
