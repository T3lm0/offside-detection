"""Regenerates the YOLO labels of football_detection_yolo from SoccerNet tracking-2023.

SoccerNet writes the left goalkeeper as "goalkeepers team left" (with an s), so names are
normalised before mapping them; otherwise that goalkeeper is lost.

The existing train/valid/test split is kept: each frame is written to the split where its image
lives inside images/.

Usage:
    python3 soccernet_to_yolo.py --check   # only compare with the current labels
    python3 soccernet_to_yolo.py           # overwrite the labels
"""
import argparse
import configparser
import os
from collections import Counter, defaultdict

from offside_inference import config

DATASET_DIR = config.path("dataset_dir")
SOCCERNET_DIR = os.path.join(DATASET_DIR, "SoccerNet", "tracking-2023")
YOLO_DIR = os.path.join(DATASET_DIR, "football_detection_yolo")
SPLITS = ("train", "valid", "test")

# Must match names in data.yaml
CLASS_IDS = {
    "player team left": 0,
    "player team right": 1,
    "goalkeeper team left": 2,
    "goalkeeper team right": 3,
    "referee": 4,
    "ball": 5,
}


def normalize_class(name):
    name = " ".join(name.strip().lower().split())
    return name.replace("goalkeepers", "goalkeeper")


def read_sequence(seq_dir):
    """Returns (width, height, {tracklet_id: class}, {frame: [(id, x, y, w, h)]})."""
    seqinfo = configparser.ConfigParser()
    seqinfo.read(os.path.join(seq_dir, "seqinfo.ini"))
    width = int(seqinfo["Sequence"]["imWidth"])
    height = int(seqinfo["Sequence"]["imHeight"])

    gameinfo = configparser.ConfigParser()
    gameinfo.read(os.path.join(seq_dir, "gameinfo.ini"))
    tracklet_class = {}
    for key, value in gameinfo["Sequence"].items():
        if key.startswith("trackletid_"):
            class_name = normalize_class(value.split(";")[0])
            # "other" and any unknown category are dropped
            if class_name in CLASS_IDS:
                tracklet_class[int(key.split("_")[1])] = CLASS_IDS[class_name]

    boxes = defaultdict(list)
    with open(os.path.join(seq_dir, "gt", "gt.txt")) as f:
        for line in f:
            fields = line.strip().split(",")
            if len(fields) < 6:
                continue
            frame, track_id = int(fields[0]), int(fields[1])
            x, y, w, h = map(float, fields[2:6])
            boxes[frame].append((track_id, x, y, w, h))
    return width, height, tracklet_class, boxes


def to_yolo_lines(width, height, tracklet_class, frame_boxes):
    lines = []
    for track_id, x, y, w, h in frame_boxes:
        if track_id not in tracklet_class:
            continue
        cx = (x + w / 2) / width
        cy = (y + h / 2) / height
        lines.append(f"{tracklet_class[track_id]} {cx:.6f} {cy:.6f} {w / width:.6f} {h / height:.6f}")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Comparar sin escribir nada")
    args = parser.parse_args()

    # Split each frame belongs to, from where its image is
    split_of = {}
    for split in SPLITS:
        for name in os.listdir(os.path.join(YOLO_DIR, "images", split)):
            split_of[os.path.splitext(name)[0]] = split

    stats = Counter()
    class_counts = {split: Counter() for split in SPLITS}
    for sn_split in ("train", "test"):
        split_dir = os.path.join(SOCCERNET_DIR, sn_split)
        for seq in sorted(os.listdir(split_dir)):
            width, height, tracklet_class, boxes = read_sequence(os.path.join(split_dir, seq))
            n_frames = len(os.listdir(os.path.join(split_dir, seq, "img1")))
            for frame in range(1, n_frames + 1):
                stem = f"{seq}_{frame:06d}"
                if stem not in split_of:
                    stats["sin_imagen"] += 1
                    continue
                split = split_of[stem]
                new_lines = to_yolo_lines(width, height, tracklet_class, boxes.get(frame, []))
                for line in new_lines:
                    class_counts[split][int(line.split()[0])] += 1

                label_path = os.path.join(YOLO_DIR, "labels", split, stem + ".txt")
                if args.check:
                    with open(label_path) as f:
                        old_lines = [l.strip() for l in f if l.strip()]
                    # Apart from the left goalkeeper lines, the result must be identical
                    if old_lines == [l for l in new_lines if not l.startswith("2 ")]:
                        stats["iguales"] += 1
                    else:
                        stats["distintos"] += 1
                        if stats["distintos"] <= 5:
                            print(f"Diferencia en {label_path}")
                else:
                    with open(label_path, "w") as f:
                        f.write("\n".join(new_lines) + ("\n" if new_lines else ""))
                    stats["escritos"] += 1

    print(dict(stats))
    for split in SPLITS:
        print(split, dict(sorted(class_counts[split].items())))


if __name__ == "__main__":
    main()
