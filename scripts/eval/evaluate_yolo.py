"""Evaluates a YOLO model and saves a JSON summary (<runs_dir>/eval/<tag>_summary.json).

Available evaluations:
  - test:            clean split (matches the model has not seen).
  - valid:           validation split of data.yaml.
  - test_single_cls: test with all classes merged; measures whether the object is detected even
                     if the class (left/right team, goalkeeper...) is wrong.

Without arguments it evaluates the reference model football_player_detection_v12 (6 classes):
    python3 evaluate_yolo.py
    python3 evaluate_yolo.py --model .../best.pt --data .../data.yaml --imgsz 1280 --tag detector_4cls_1280 test
"""
import argparse
import json
import os

import torch
from ultralytics import YOLO
from offside_inference import config

BASELINE_DATA = os.path.join(config.path("dataset_dir"), "football_detection_yolo", "data.yaml")
BASELINE_MODEL = os.path.join(config.path("runs_dir"), "detect", "football_player_detection_v12", "weights", "best.pt")
OUTPUT_DIR = os.path.join(config.path("runs_dir"), "eval")

EVALUATIONS = {
    "test": dict(split="test"),
    "valid": dict(split="val"),
    "test_single_cls": dict(split="test", single_cls=True),
}


def summarize(metrics):
    box = metrics.box
    summary = {
        "precision": float(box.mp),
        "recall": float(box.mr),
        "mAP50": float(box.map50),
        "mAP50-95": float(box.map),
        "speed_ms_per_image": metrics.speed,
        "per_class": {},
    }
    for i, class_id in enumerate(box.ap_class_index):
        summary["per_class"][metrics.names[int(class_id)]] = {
            "precision": float(box.p[i]),
            "recall": float(box.r[i]),
            "mAP50": float(box.ap50[i]),
            "mAP50-95": float(box.ap[i]),
        }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=BASELINE_MODEL)
    parser.add_argument("--data", default=BASELINE_DATA)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--tag", default="baseline_v12")
    parser.add_argument("evaluations", nargs="*", default=list(EVALUATIONS))
    args = parser.parse_args()

    # As in training: do not starve the desktop of video memory
    torch.cuda.set_per_process_memory_fraction(0.8, 0)

    model = YOLO(args.model)
    summary_path = os.path.join(OUTPUT_DIR, f"{args.tag}_summary.json")
    results = {}
    for name in args.evaluations:
        print(f"\n=== Evaluación: {args.tag} / {name} (imgsz {args.imgsz}) ===", flush=True)
        metrics = model.val(
            data=args.data,
            imgsz=args.imgsz,
            batch=args.batch,
            device="0",
            workers=8,
            project=OUTPUT_DIR,
            name=f"{args.tag}_{name}",
            exist_ok=True,
            **EVALUATIONS[name],
        )
        results[name] = summarize(metrics)
        if EVALUATIONS[name].get("single_cls"):
            # With single_cls Ultralytics labels the merged class with the name of class 0
            del results[name]["per_class"]
        with open(summary_path, "w") as f:
            json.dump({"model": args.model, "imgsz": args.imgsz, "results": results}, f, indent=2)

    print(json.dumps(results, indent=2))
