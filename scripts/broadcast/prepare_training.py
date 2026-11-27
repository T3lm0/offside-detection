"""Detector training set from the Club World Cup images corrected in CVAT.

Input: the CVAT "YOLO 1.1" export (with images), with the same classes as the 4-class detector
(player, goalkeeper, referee, ball). Images deleted in CVAT are not exported and not used.

Split by match, never by frame: matches in --validacion are not seen in training and measure
whether the model generalises to a new match. With 250 images the training matches are few compared
with SoccerNet's 36,000, so they are repeated (--repeticiones) and 1 of every --paso-soccernet
SoccerNet frames is taken (consecutive frames are almost identical), so the model does not forget
what it already knows.

Output in <dataset_dir>/cwc_detector/:
    images/{train,val}/, labels/{train,val}/   Club World Cup images
    train.txt          training list: repeated Club World Cup + SoccerNet sample
    val.txt            Club World Cup validation matches
    val_soccernet.txt  SoccerNet validation (to check it does not get worse at what it did well)
    data.yaml          for Ultralytics (val = Club World Cup)
    reparto.csv        image, match, split, objects per class

Usage: python3 prepare_training.py export.zip --validacion PSG-BAY
       python3 prepare_training.py export.zip --validacion     # every match in training
"""
import argparse
import csv
import glob
import os
import shutil
import zipfile
from collections import Counter

from offside_inference import config

DATASET = config.path("dataset_dir")
SOCCERNET = os.path.join(DATASET, "football_detection_yolo_4cls")
OUT = os.path.join(DATASET, "cwc_detector")
CLASSES = ["player", "goalkeeper", "referee", "ball"]
MATCHES = ["RM-JUV", "RM-PSG", "RM-BVB", "PSG-BAY", "FLU-HIL", "INT-FLU"]


def match_of(stem):
    return next(m for m in MATCHES if f"_{m}_" in f"_{stem}_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export", help="Zip de CVAT en formato YOLO 1.1 con imágenes")
    ap.add_argument("--validacion", nargs="*", default=["PSG-BAY"],
                    help="Partidos que no se entrenan; sin ninguno se valida con SoccerNet")
    ap.add_argument("--repeticiones", type=int, default=4)
    ap.add_argument("--paso-soccernet", type=int, default=25)
    args = ap.parse_args()
    with zipfile.ZipFile(args.export) as z:
        names = z.read("obj.names").decode().split()
        if names != CLASSES:
            raise SystemExit(f"Clases de la exportación {names}, se esperaban {CLASSES}")
        if os.path.exists(OUT):
            shutil.rmtree(OUT)
        rows, lists = [], {"train": [], "val": []}
        for n in sorted(z.namelist()):
            if not (n.startswith("obj_train_data/") and n.endswith(".jpg")):
                continue
            stem = os.path.basename(n)[:-4]
            match = match_of(stem)
            split = "val" if match in args.validacion else "train"
            label = n[:-4] + ".txt"
            lines = z.read(label).decode().split("\n") if label in z.namelist() else []
            lines = [l for l in lines if l.strip()]
            for d in ("images", "labels"):
                os.makedirs(os.path.join(OUT, d, split), exist_ok=True)
            image = os.path.join(OUT, "images", split, stem + ".jpg")
            with open(image, "wb") as f:
                f.write(z.read(n))
            with open(os.path.join(OUT, "labels", split, stem + ".txt"), "w") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
            lists[split].append(image)
            count = Counter(CLASSES[int(l.split()[0])] for l in lines)
            rows.append({"imagen": stem, "partido": match, "conjunto": split, **{c: count[c] for c in CLASSES}})

    soccernet = sorted(glob.glob(os.path.join(SOCCERNET, "images", "train", "*.jpg")))
    soccernet = [p for p in soccernet if int(p[-10:-4]) % args.paso_soccernet == 1]
    soccernet_val = sorted(glob.glob(os.path.join(SOCCERNET, "images", "valid", "*.jpg")))
    soccernet_val = [p for p in soccernet_val if int(p[-10:-4]) % args.paso_soccernet == 1]
    with open(os.path.join(OUT, "train.txt"), "w") as f:
        f.write("\n".join(lists["train"] * args.repeticiones + soccernet) + "\n")
    with open(os.path.join(OUT, "val.txt"), "w") as f:
        f.write("\n".join(lists["val"]) + "\n")
    with open(os.path.join(OUT, "val_soccernet.txt"), "w") as f:
        f.write("\n".join(soccernet_val) + "\n")
    val = "val.txt" if lists["val"] else "val_soccernet.txt"
    note = f"{' '.join(args.validacion)} (Mundial de Clubes)" if lists["val"] else "SoccerNet (todo el Mundial de Clubes se entrena)"
    with open(os.path.join(OUT, "data.yaml"), "w") as f:
        f.write(f"path: {OUT}\ntrain: train.txt\nval: {val}\n\nnc: {len(CLASSES)}\nnames:\n"
                + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES))
                + f"\n# Validación: {note}\n")
    with open(os.path.join(OUT, "reparto.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["imagen", "partido", "conjunto"] + CLASSES)
        w.writeheader()
        w.writerows(rows)

    for split in ("train", "val"):
        mine = [r for r in rows if r["conjunto"] == split]
        totals = {c: sum(r[c] for r in mine) for c in CLASSES}
        print(f"{split}: {len(mine)} imágenes de {sorted({r['partido'] for r in mine})} {totals}")
    print(f"train.txt: {len(lists['train'])} × {args.repeticiones} del Mundial de Clubes + {len(soccernet)} de SoccerNet")
    print(f"val_soccernet.txt: {len(soccernet_val)} imágenes. Salida en {OUT}")


if __name__ == "__main__":
    main()
