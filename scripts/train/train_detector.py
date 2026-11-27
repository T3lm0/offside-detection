"""Trains the 4-class detector (player, goalkeeper, referee, ball) on football_detection_yolo_4cls.

Starts from the COCO weights of yolov8s.pt rather than football_player_detection_v12, because that
model was trained on frames from sequences that are now in validation.

The GPU also drives the display: the video memory PyTorch may reserve is capped so that a batch
that is too large raises a CUDA error instead of freezing the desktop. To cap RAM, launch it with
train_safe.sh.

Usage:
    ./train_safe.sh --imgsz 640 --batch 32
    ./train_safe.sh --imgsz 1280 --batch 8
"""
import argparse
import os

import torch
from ultralytics import YOLO
from offside_inference import config

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_YAML_PATH = os.path.join(config.path("dataset_dir"), "football_detection_yolo_4cls", "data.yaml")
BASE_MODEL = "yolov8s.pt"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA_YAML_PATH)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--close-mosaic", type=int, default=10, help="Últimas épocas sin mosaico")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--fraction", type=float, default=1.0, help="Fracción de train a usar (pruebas rápidas)")
    parser.add_argument("--name", default=None)
    parser.add_argument("--gpu-mem-fraction", type=float, default=0.8)
    parser.add_argument("--val", action=argparse.BooleanOptionalAction, default=True)
    # To keep improving an already trained model (daily sessions)
    parser.add_argument("--weights", default=BASE_MODEL, help="Pesos iniciales (por defecto, COCO)")
    parser.add_argument("--time", type=float, default=None, help="Horas de entrenamiento; sustituye a --epochs")
    parser.add_argument("--lr0", type=float, default=None, help="Tasa de aprendizaje inicial (por defecto, la de YOLO)")
    parser.add_argument("--resume", default=None,
                        help="last.pt de un entrenamiento interrumpido: lo continúa con su configuración original")
    args = parser.parse_args()

    torch.cuda.set_per_process_memory_fraction(args.gpu_mem_fraction, 0)

    if args.resume:
        # Ultralytics restores data, epochs and optimizer from the checkpoint; only the device is set
        YOLO(args.resume).train(resume=True, device="0", workers=args.workers)
        raise SystemExit(0)

    # Only passed when given, so Ultralytics defaults are kept
    extra = {k: v for k, v in (("time", args.time), ("lr0", args.lr0)) if v is not None}
    if args.lr0 is not None:
        # With optimizer=auto Ultralytics ignores lr0 and picks its own rate
        extra["optimizer"] = "SGD"

    model = YOLO(args.weights)
    model.train(
        **extra,
        data=args.data,
        imgsz=args.imgsz,
        batch=args.batch,
        epochs=args.epochs,
        patience=args.patience,
        close_mosaic=args.close_mosaic,
        workers=args.workers,
        fraction=args.fraction,
        val=args.val,
        device="0",
        seed=0,
        project=os.path.join(config.path("runs_dir"), "detect"),
        name=args.name or f"detector_4cls_{args.imgsz}",
    )
