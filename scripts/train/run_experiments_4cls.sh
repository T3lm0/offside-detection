#!/usr/bin/env bash
# 4-class detector experiment: trains at 640 and 1280 px with the same epochs and evaluates both on
# test (unseen matches). The 640 model is also evaluated at 1280 px to separate the effect of
# training at higher resolution from only running inference at higher resolution.
#
# Run detached from the terminal:
#   setsid nohup ./run_experiments_4cls.sh > logs/experiment_4cls.log 2>&1 &
set -u
cd "$(dirname "$0")"
DATA="$(python3 -c 'from offside_inference import config; print(config.path("dataset_dir"))')/football_detection_yolo_4cls/data.yaml"
EVAL="../eval/evaluate_yolo.py"
RUNS="$(python3 -c 'from offside_inference import config; print(config.path("runs_dir"))')/detect"

echo "[$(date '+%F %T')] Inicio"
./train_safe.sh --imgsz 640 --batch 32 --workers 8 --epochs 12 --close-mosaic 2 --patience 5 --name detector_4cls_640
echo "[$(date '+%F %T')] Fin entrenamiento 640 (código $?)"
./train_safe.sh --imgsz 1280 --batch 8 --workers 8 --epochs 12 --close-mosaic 2 --patience 5 --name detector_4cls_1280
echo "[$(date '+%F %T')] Fin entrenamiento 1280 (código $?)"

for cfg in "detector_4cls_640 640 32" "detector_4cls_640 1280 16" "detector_4cls_1280 1280 16"; do
    set -- $cfg
    weights="$RUNS/$1/weights/best.pt"
    if [ -f "$weights" ]; then
        python3 "$EVAL" --model "$weights" --data "$DATA" --imgsz "$2" --batch "$3" \
            --tag "${1}_inf$2" test test_single_cls
        echo "[$(date '+%F %T')] Evaluado $1 a $2 px (código $?)"
    else
        echo "[$(date '+%F %T')] Falta $weights, no se evalúa"
    fi
done
echo "[$(date '+%F %T')] EXPERIMENTO TERMINADO"
