"""Ball-only detector trained on full-resolution 640 px crops (see prepare_ball_crops.py).

Starts from the det1280 weights (the network already knows football; the head is rebuilt for one
class) without modifying them. It trains at 640, the crop size, so the ball is not downscaled. The
scale augmentation is lower than the default (0.25 instead of 0.5): with 0.5 a 6 px ball would
shrink to 3. Validation uses crops from the SoccerNet validation sequences; the best model is best.pt.

Output: <runs_dir>/detect/balon_<date>/, progress in <runs_dir>/monitor/<date>_balon/ and
<runs_dir>/logs/balon_<date>.log

Usage: python3 train_ball.py [--epocas 60] [--batch 32] [--device 0]
"""
import argparse
import glob
import os
import sys
import threading
import time

from ultralytics import YOLO

from offside_inference import config
from train_finetune import MONITOR_RUNS, RUNS, TRAIN_LOGS, note, sample_gpu

DATA = os.path.join(config.path("dataset_dir"), "balon_recortes", "data.yaml")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epocas", type=int, default=60)
    ap.add_argument("--paciencia", type=int, default=15)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--device", default="0")
    args = ap.parse_args()
    weights = sorted(glob.glob(os.path.join(RUNS, "det1280_2*", "weights", "best.pt")), key=os.path.getmtime)[-1]
    stamp = time.strftime("%Y%m%d_%H%M")
    run_dir = os.path.join(MONITOR_RUNS, f"{stamp}_balon")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(TRAIN_LOGS, exist_ok=True)
    log_name = f"balon_{stamp}.log"
    log = open(os.path.join(TRAIN_LOGS, log_name), "a", buffering=1)
    os.dup2(log.fileno(), sys.stdout.fileno())
    os.dup2(log.fileno(), sys.stderr.fileno())
    note(run_dir, "Detector solo de balón a resolución completa (scripts/broadcast/train_ball.py)")
    note(run_dir, ">>> Etapa detector_balon")
    with open(os.path.join(run_dir, "pipeline.log"), "a", encoding="utf-8") as f:
        f.write(f"Log: logs/{log_name}\n")
    stop = threading.Event()
    threading.Thread(target=sample_gpu, args=(os.path.join(run_dir, "gpu.csv"), stop), daemon=True).start()
    code = 1
    try:
        print(f"Partiendo de {weights}", flush=True)
        YOLO(weights).train(
            data=DATA, imgsz=640, epochs=args.epocas, patience=args.paciencia, batch=args.batch,
            device=args.device, scale=0.25, close_mosaic=10, project=RUNS, name=f"balon_{stamp}",
            exist_ok=False, plots=True, workers=6)
        code = 0
    finally:
        stop.set()
        note(run_dir, f"<<< Etapa detector_balon terminada con código {code}")
        note(run_dir, "Entrenamiento terminado")


if __name__ == "__main__":
    main()
