"""Re-pre-labels an already extracted set (imagenes.zip + indice.csv from ball_dataset.py) without
reading the videos, adding the ball-only detector (train_ball.py) to the 4-class detector.

The ball detector scans the frame at full resolution in overlapping 640 windows (4 x 2 at 1080p).
Its candidates are merged with the 4-class detector's and choose_ball decides with the calibration,
as in ball_dataset.py; since it was trained with boots without a ball, with confidence
>= TRUST_BALL_MODEL a candidate is accepted even on a player's feet.

Output: conjunto_balon/<name>/ (imagenes.zip, anotaciones.zip, indice.csv), same as ball_dataset.py.

Usage: python3 relabel.py conjunto_balon/balon_lote1 --nombre balon_lote1_v2 [--limite 20]
"""
import argparse
import csv
import glob
import json
import os
import zipfile

import cv2
import numpy as np
from ultralytics import YOLO

import ball_dataset as cb
from train_finetune import RUNS

TILE, BALL_CONF = 640, 0.15


def ball_model_default():
    return sorted(glob.glob(os.path.join(RUNS, "balon_2*", "weights", "best.pt")), key=os.path.getmtime)[-1]


def tile_origins(size):
    n = max(1, int(np.ceil((size - TILE) / (TILE * 0.66))) + 1)
    return [int(round(v)) for v in np.linspace(0, size - TILE, n)] if size > TILE else [0]


def ball_tiles(model, frame, device):
    """Ball detector candidates over overlapping windows, without duplicates (8 px)."""
    h, w = frame.shape[:2]
    origins = [(x, y) for y in tile_origins(h) for x in tile_origins(w)]
    crops = [frame[y:y + TILE, x:x + TILE] for x, y in origins]
    found = []
    for (x0, y0), r in zip(origins, model.predict(crops, imgsz=TILE, conf=BALL_CONF, device=device, verbose=False)):
        for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
            found.append({"box": [b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0], "conf": float(c), "source": "balon"})
    kept = []
    for d in sorted(found, key=lambda d: -d["conf"]):
        cx, cy = (d["box"][0] + d["box"][2]) / 2, (d["box"][1] + d["box"][3]) / 2
        if all(abs(cx - (k["box"][0] + k["box"][2]) / 2) > 8 or abs(cy - (k["box"][1] + k["box"][3]) / 2) > 8
               for k in kept):
            kept.append(d)
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("conjunto", help="Carpeta con imagenes.zip e indice.csv")
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--modelo-balon", default=None)
    ap.add_argument("--limite", type=int, default=None, help="Solo las N primeras (prueba)")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--device", default="0")
    args = ap.parse_args()
    with open(os.path.join(cb.HERE, "partidos.json"), encoding="utf-8") as f:
        matches = {m["partido"]: m for m in json.load(f)["partidos"]}
    with open(os.path.join(args.conjunto, "indice.csv"), encoding="utf-8") as f:
        index = list(csv.DictReader(f))[:args.limite]
    detector = cb.FrameDetector(cb.default_detector(), args.device)
    ball_path = args.modelo_balon or ball_model_default()
    ball_model = YOLO(ball_path)
    print(f"Detector: {cb.default_detector()}\nBalón: {ball_path}", flush=True)
    session = cb.Session(device=args.device)
    rows, uncalibrated, sources = [], 0, {}
    try:
        with zipfile.ZipFile(os.path.join(args.conjunto, "imagenes.zip")) as z:
            for i, r in enumerate(index):
                frame = cv2.imdecode(np.frombuffer(z.read(r["imagen"]), np.uint8), cv2.IMREAD_COLOR)
                m = matches[r["partido"]]
                session.center = {"center": np.asarray(m["camara"]["centro"], float), "source": "estadio",
                                  "frames": 0, "spread_m": 0.0}
                people, whole_ball = detector(frame)
                cam, error_px = cb.calibrate(session, frame, int(r["fotograma"]), people)
                if cam is None:
                    uncalibrated += 1
                    continue
                extra = ball_tiles(ball_model, frame, args.device)
                people, ball, near, on_boot = cb.pre_label(detector, frame, people, whole_ball, cam, extra)
                priority = (0 if ball is None and on_boot else 1 if ball is not None and near
                            else 2 if ball is None else 3)
                src = "" if ball is None else ball.get("source", "fotograma")
                sources[src or "ninguno"] = sources.get(src or "ninguno", 0) + 1
                rows.append({**{k: r[k] for k in ("partido", "grupo", "parte", "evento", "video", "video_s", "fotograma")},
                             "stem": r["imagen"][5:-4], "prioridad": priority,
                             "balon_pre": "" if ball is None else f"{ball['conf']:.2f} {src}",
                             "porteros": sum(p["role"] == "goalkeeper" for p in people), "error_px": round(error_px, 2),
                             "frame": frame, "people": people, "ball": ball})
                if i % 50 == 0:
                    print(f"{i}/{len(index)}", flush=True)
    finally:
        session.close()
    cb.write(rows, os.path.join(cb.OUT, args.nombre), np.random.default_rng(args.semilla))
    counts = [sum(r["prioridad"] == p for r in rows) for p in (0, 1, 2, 3)]
    print(f"Prioridades 0-3: {counts}; balón elegido de: {sources}; sin calibrar: {uncalibrated}")


if __name__ == "__main__":
    main()
