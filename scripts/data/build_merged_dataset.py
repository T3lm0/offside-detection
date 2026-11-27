"""Builds football_detection_yolo_4cls from football_detection_yolo.

  - Merges the team classes into player, goalkeeper, referee and ball. Teams are assigned later
    (by shirt colour) because a detector does not generalise left/right to unseen matches.
  - Splits train/valid by sequence instead of by frame: VAL_PER_GAME non-consecutive sequences of
    each match go to validation. Test is unchanged.

Images are hard-linked (no extra disk space).
"""
import configparser
import os
import shutil
from collections import Counter, defaultdict

from offside_inference import config

DATASET_DIR = config.path("dataset_dir")
SOCCERNET_TRAIN_DIR = os.path.join(DATASET_DIR, "SoccerNet", "tracking-2023", "train")
SOURCE_DIR = os.path.join(DATASET_DIR, "football_detection_yolo")
TARGET_DIR = os.path.join(DATASET_DIR, "football_detection_yolo_4cls")

# Original class (6 classes) -> new class (4 classes)
CLASS_MAP = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 3}
NAMES = ["player", "goalkeeper", "referee", "ball"]
VAL_PER_GAME = 3


def pick_val_sequences():
    sequences_by_game = defaultdict(list)
    for seq in sorted(os.listdir(SOCCERNET_TRAIN_DIR)):
        gameinfo = configparser.ConfigParser()
        gameinfo.read(os.path.join(SOCCERNET_TRAIN_DIR, seq, "gameinfo.ini"))
        sequences_by_game[gameinfo["Sequence"]["gameID"]].append(seq)

    val = set()
    for game, seqs in sorted(sequences_by_game.items()):
        # Spread over the match so contiguous clips are not taken
        step = len(seqs) // VAL_PER_GAME
        chosen = [seqs[step // 2 + i * step] for i in range(VAL_PER_GAME)]
        print(f"Partido {game}: {len(seqs)} secuencias, validación = {chosen}")
        val.update(chosen)
    return val


def main():
    val_sequences = pick_val_sequences()
    if os.path.exists(TARGET_DIR):
        shutil.rmtree(TARGET_DIR)

    stats = Counter()
    for source_split in ("train", "valid", "test"):
        image_dir = os.path.join(SOURCE_DIR, "images", source_split)
        for name in sorted(os.listdir(image_dir)):
            stem = os.path.splitext(name)[0]
            if source_split == "test":
                split = "test"
            else:
                split = "valid" if stem.split("_")[0] in val_sequences else "train"

            for sub in ("images", "labels"):
                os.makedirs(os.path.join(TARGET_DIR, sub, split), exist_ok=True)
            os.link(os.path.join(image_dir, name), os.path.join(TARGET_DIR, "images", split, name))

            with open(os.path.join(SOURCE_DIR, "labels", source_split, stem + ".txt")) as f:
                lines = [l.split() for l in f if l.strip()]
            new_lines = [" ".join([str(CLASS_MAP[int(l[0])])] + l[1:]) for l in lines]
            with open(os.path.join(TARGET_DIR, "labels", split, stem + ".txt"), "w") as f:
                f.write("\n".join(new_lines) + ("\n" if new_lines else ""))

            stats[f"{split}_imagenes"] += 1
            for l in new_lines:
                stats[f"{split}_{NAMES[int(l.split()[0])]}"] += 1

    with open(os.path.join(TARGET_DIR, "data.yaml"), "w") as f:
        f.write(f"path: {TARGET_DIR}\n")
        f.write("train: images/train\nval: images/valid\ntest: images/test\n\n")
        f.write(f"nc: {len(NAMES)}\nnames:\n")
        for i, n in enumerate(NAMES):
            f.write(f"  {i}: {n}\n")
        f.write(f"\n# Secuencias de validación: {' '.join(sorted(val_sequences))}\n")

    for key in sorted(stats):
        print(f"{key}: {stats[key]}")


if __name__ == "__main__":
    main()
