"""Fine-tunes the 4-class detector (det1280) with the corrected Club World Cup images.

Starts from the det1280 weights (without modifying them) and trains on <dataset_dir>/cwc_detector
(see prepare_training.py). With every match in training, validation is SoccerNet: it shows that the
model does not forget, not which epoch is best, so a fixed number of epochs is trained without early
stopping and the model to use is last.pt.

Output: <runs_dir>/detect/det1280_cwc_<date>/

Progress is written to <runs_dir>/monitor/<date>_cwc/ (pipeline.log with the detector_1280 stage and
gpu.csv every 10 s) and the YOLO output to <runs_dir>/logs/det1280_cwc_<date>.log.

Usage: python3 train_finetune.py [--epocas 20] [--device 0]
"""
import argparse
import glob
import os
import subprocess
import sys
import threading
import time

from ultralytics import YOLO

from offside_inference import config

RUNS = os.path.join(config.path("runs_dir"), "detect")
DATA = os.path.join(config.path("dataset_dir"), "cwc_detector", "data.yaml")
MONITOR_RUNS = os.path.join(config.path("runs_dir"), "monitor")
TRAIN_LOGS = os.path.join(config.path("runs_dir"), "logs")
GPU_QUERY = "temperature.gpu,power.draw,clocks.sm,clocks.mem,utilization.gpu,memory.used,clocks_event_reasons.active,pstate"


def note(run_dir, text):
    with open(os.path.join(run_dir, "pipeline.log"), "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")


def sample_gpu(path, stop):
    """gpu.csv with GPU and RAM readings every 10 s, for the progress timeline."""
    with open(path, "w") as f:
        f.write("hora,temp_c,potencia_w,mhz_sm,mhz_mem,uso_pct,vram_mib,limitacion,pstate,ram_disponible_mb\n")
    while not stop.wait(10):
        try:
            gpu = subprocess.run(["nvidia-smi", f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout.strip().replace(" ", "")
            with open("/proc/meminfo") as m:
                free = next(int(l.split()[1]) // 1024 for l in m if l.startswith("MemAvailable"))
        except (OSError, subprocess.SubprocessError, StopIteration):
            continue
        with open(path, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')},{gpu},{free}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epocas", type=int, default=20)
    ap.add_argument("--device", default="0")
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()
    weights = sorted(glob.glob(os.path.join(RUNS, "det1280_2*", "weights", "best.pt")), key=os.path.getmtime)[-1]
    stamp = time.strftime("%Y%m%d_%H%M")
    run_dir = os.path.join(MONITOR_RUNS, f"{stamp}_cwc")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(TRAIN_LOGS, exist_ok=True)
    log_name = f"det1280_cwc_{stamp}.log"
    # YOLO output (progress bars included) to the log file
    log = open(os.path.join(TRAIN_LOGS, log_name), "a", buffering=1)
    os.dup2(log.fileno(), sys.stdout.fileno())
    os.dup2(log.fileno(), sys.stderr.fileno())
    note(run_dir, "Ajuste fino de det1280 con el Mundial de Clubes (scripts/broadcast/train_finetune.py)")
    note(run_dir, ">>> Etapa detector_1280")
    with open(os.path.join(run_dir, "pipeline.log"), "a", encoding="utf-8") as f:
        f.write(f"Log: logs/{log_name}\n")
    stop = threading.Event()
    threading.Thread(target=sample_gpu, args=(os.path.join(run_dir, "gpu.csv"), stop), daemon=True).start()
    code = 1
    try:
        print(f"Partiendo de {weights}", flush=True)
        YOLO(weights).train(
            data=DATA, imgsz=1280, epochs=args.epocas, batch=args.batch, device=args.device,
            optimizer="SGD", lr0=0.002, lrf=0.1, warmup_epochs=1, patience=args.epocas + 1,
            close_mosaic=5, project=RUNS, name=f"det1280_cwc_{stamp}", exist_ok=False,
            plots=True, workers=4)
        code = 0
    finally:
        stop.set()
        note(run_dir, f"<<< Etapa detector_1280 terminada con código {code}")
        note(run_dir, "Entrenamiento terminado")


if __name__ == "__main__":
    main()
