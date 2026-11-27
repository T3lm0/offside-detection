"""Full-resolution 640x640 crops for training a ball-only detector.

The 4-class detector downscales the frame from 1920 to 1280 px and the ball, 5-15 px, ends up at
3-10 px: almost no signal left. Here each crop comes from the original frame without downscaling
and the model trains at 640, so it sees the ball with all its pixels. At inference time it is run
over overlapping windows covering the whole frame (SAHI-style tiling).

Each image with a ball gives crops containing the whole ball at different positions, plus crops
without a ball centred on a player's feet: white boots are what gets confused with the ball most,
so the model learns not to mark them.

Sources:
  - SoccerNet (<dataset_dir>/football_detection_yolo_4cls): 1 of every --paso-soccernet train
    frames; validation from its validation sequences (not trained). From test, the TEST_APARTE
    sequences are kept for measurement (1 of every 25 frames to test) and, with
    --test-a-entrenamiento, the others are trained like train: new scenes are worth more than more
    consecutive frames of the same ones. Different sequences may come from the same SoccerNet match.
  - Club World Cup CVAT exports (YOLO 1.1 with images): all to training, with --recortes-cwc crops
    per image.

Output: <dataset_dir>/balon_recortes/{images,labels}/{train,val,test}/ and data.yaml (1 class: ball).

Usage: python3 prepare_ball_crops.py export.zip [other_export.zip ...] [--test-a-entrenamiento]
"""
import argparse
import glob
import os
import shutil
import zipfile

import cv2
import numpy as np

from offside_inference import config

DATASET = config.path("dataset_dir")
SOCCERNET = os.path.join(DATASET, "football_detection_yolo_4cls")
OUT = os.path.join(DATASET, "balon_recortes")
TILE = 640
MARGIN = 24  # the ball stays at least this far from the crop border (px)
BALL = 3  # ball class in the 4-class labels
PERSON = (0, 1, 2)
# SoccerNet test sequences never used for training (1 of every 5, plus the ones used in the app)
TEST_APARTE = {"SNMOT-116", "SNMOT-121", "SNMOT-126", "SNMOT-131", "SNMOT-134", "SNMOT-136", "SNMOT-141",
               "SNMOT-146", "SNMOT-187", "SNMOT-191", "SNMOT-192", "SNMOT-197"}


def read_labels(lines, w, h):
    """[(class, x1, y1, x2, y2)] in pixels from YOLO lines."""
    out = []
    for line in lines:
        p = line.split()
        if len(p) != 5:
            continue
        c, x, y, bw, bh = int(p[0]), *map(float, p[1:])
        out.append((c, (x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h))
    return out


def clamp_origin(cx, cy, w, h):
    """Corner of a TILE crop centred on (cx, cy) that stays inside the image."""
    return int(np.clip(cx - TILE / 2, 0, max(0, w - TILE))), int(np.clip(cy - TILE / 2, 0, max(0, h - TILE)))


def inside(box, x0, y0, margin=0):
    _, x1, y1, x2, y2 = box
    return x1 >= x0 + margin and y1 >= y0 + margin and x2 <= x0 + TILE - margin and y2 <= y0 + TILE - margin


def touches(box, x0, y0):
    _, x1, y1, x2, y2 = box
    return x2 > x0 and y2 > y0 and x1 < x0 + TILE and y1 < y0 + TILE


def tiles_for(labels, w, h, rng, positives, negatives):
    """Crop corners: with the whole ball at a random position, and without a ball at someone's feet."""
    balls = [b for b in labels if b[0] == BALL]
    people = [b for b in labels if b[0] in PERSON]
    out = []
    for ball in balls[:1]:
        _, x1, y1, x2, y2 = ball
        for _ in range(positives):
            # Any position that keeps the whole ball away from the border
            lo_x, hi_x = max(0, x2 + MARGIN - TILE), min(w - TILE, x1 - MARGIN)
            lo_y, hi_y = max(0, y2 + MARGIN - TILE), min(h - TILE, y1 - MARGIN)
            if lo_x > hi_x or lo_y > hi_y:
                break
            out.append((int(rng.uniform(lo_x, hi_x)), int(rng.uniform(lo_y, hi_y))))
    for _ in range(negatives):
        for _ in range(10):
            if people:
                _, px1, py1, px2, py2 = people[rng.integers(len(people))]
                x0, y0 = clamp_origin((px1 + px2) / 2 + rng.uniform(-80, 80), py2 + rng.uniform(-80, 80), w, h)
            else:
                x0, y0 = int(rng.uniform(0, w - TILE)), int(rng.uniform(0, h - TILE))
            if not any(touches(b, x0, y0) for b in balls):
                out.append((x0, y0))
                break
    return out


def write_tiles(image, labels, corners, split, stem):
    h, w = image.shape[:2]
    balls = [b for b in labels if b[0] == BALL]
    n_pos = 0
    for k, (x0, y0) in enumerate(corners):
        crop = image[y0:y0 + TILE, x0:x0 + TILE]
        if crop.shape[:2] != (TILE, TILE):
            continue
        lines = []
        for _, x1, y1, x2, y2 in balls:
            if inside((0, x1, y1, x2, y2), x0, y0):
                cx, cy = (x1 + x2) / 2 - x0, (y1 + y2) / 2 - y0
                lines.append(f"0 {cx / TILE:.6f} {cy / TILE:.6f} {(x2 - x1) / TILE:.6f} {(y2 - y1) / TILE:.6f}")
        n_pos += bool(lines)
        name = f"{stem}_{k}"
        cv2.imwrite(os.path.join(OUT, "images", split, name + ".jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
        with open(os.path.join(OUT, "labels", split, name + ".txt"), "w") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
    return n_pos, len(corners) - n_pos


def soccernet(split, step, rng, positives, negatives, counts, out_split=None, keep=lambda seq: True):
    images = sorted(glob.glob(os.path.join(SOCCERNET, "images", split, "*.jpg")))
    out_split = out_split or {"valid": "val"}.get(split, split)
    for path in images:
        if int(path[-10:-4]) % step != 1 or not keep(os.path.basename(path).split("_")[0]):
            continue
        stem = os.path.basename(path)[:-4]
        label = os.path.join(SOCCERNET, "labels", split, stem + ".txt")
        if not os.path.exists(label):
            continue
        image = cv2.imread(path)
        h, w = image.shape[:2]
        with open(label) as f:
            labels = read_labels(f.read().splitlines(), w, h)
        p, n = write_tiles(image, labels, tiles_for(labels, w, h, rng, positives, negatives), out_split, stem)
        counts[out_split][0] += p
        counts[out_split][1] += n


def cvat(path, rng, positives, negatives, counts):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if z.read("obj.names").decode().split() != ["player", "goalkeeper", "referee", "ball"]:
            raise SystemExit(f"{path}: clases distintas de player, goalkeeper, referee, ball")
        for n in sorted(names):
            if not (n.startswith("obj_train_data/") and n.endswith(".jpg")):
                continue
            image = cv2.imdecode(np.frombuffer(z.read(n), np.uint8), cv2.IMREAD_COLOR)
            h, w = image.shape[:2]
            label = n[:-4] + ".txt"
            labels = read_labels(z.read(label).decode().splitlines() if label in names else [], w, h)
            stem = "cwc_" + os.path.basename(n)[:-4]
            p, k = write_tiles(image, labels, tiles_for(labels, w, h, rng, positives, negatives), "train", stem)
            counts["train"][0] += p
            counts["train"][1] += k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exports", nargs="*", help="Exportaciones de CVAT (YOLO 1.1 con imágenes)")
    ap.add_argument("--paso-soccernet", type=int, default=5, help="1 de cada N fotogramas de SoccerNet train")
    ap.add_argument("--recortes-cwc", type=int, default=4, help="Recortes con balón por imagen del Mundial de Clubes")
    ap.add_argument("--test-a-entrenamiento", action="store_true",
                    help="Entrenar también las secuencias de test de SoccerNet fuera de TEST_APARTE")
    ap.add_argument("--semilla", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.semilla)
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for d in ("images", "labels"):
        for s in ("train", "val", "test"):
            os.makedirs(os.path.join(OUT, d, s))
    counts = {s: [0, 0] for s in ("train", "val", "test")}
    soccernet("train", args.paso_soccernet, rng, 1, 1, counts)
    if args.test_a_entrenamiento:
        soccernet("test", args.paso_soccernet, rng, 1, 1, counts, "train", lambda seq: seq not in TEST_APARTE)
    for path in args.exports:
        cvat(path, rng, args.recortes_cwc, 2, counts)
    soccernet("valid", 10, rng, 1, 1, counts)
    soccernet("test", 25, rng, 1, 1, counts, keep=lambda seq: seq in TEST_APARTE)
    with open(os.path.join(OUT, "data.yaml"), "w") as f:
        f.write(f"path: {OUT}\ntrain: images/train\nval: images/val\ntest: images/test\n\nnc: 1\nnames:\n  0: ball\n"
                f"\n# Recortes de {TILE} px sin reducir. Mundial de Clubes: {' '.join(map(os.path.basename, args.exports))}\n")
    for s, (p, n) in counts.items():
        print(f"{s}: {p} recortes con balón, {n} sin balón")
    print(f"Salida en {OUT}")


if __name__ == "__main__":
    main()
