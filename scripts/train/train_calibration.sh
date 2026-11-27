#!/usr/bin/env bash
# Trains the pitch keypoint model used for camera calibration (HRNet-W48 from Sportlight's solution,
# 1st in SoccerNet Camera Calibration 2023) inside its Docker container.
#
#  - Backbone initialised with timm ImageNet weights (hrnet_w48.ms_in1k); training from scratch
#    does not converge.
#  - RAM and VRAM are limited so the machine stays responsive.
#  - Stops at the end of the epoch that exhausts MAX_HOURS.
#
# Usage: ./train_calibration.sh NAME MAX_HOURS [Hydra overrides...]
#   ./train_calibration.sh pipeline_20261022 4.5
#   ./train_calibration.sh test 1 train_params.max_epochs=1 'data.train=[/workdir/data/dataset_smoke/train]'
# Output goes to <calibration_repo>/data/experiments/HRNet_57_NAME/.
set -u
REPO="$(python3 -c 'from offside_inference import config; print(config.path("calibration_repo"))')"
IMAGE="soccernet-calibration:0.0.2"
PRETRAIN_HOST="$REPO/data/pretrain/hrnet_w48_imagenet_timm.pth"
RUN_NAME="${1:?Falta el nombre de la ejecución}"
MAX_HOURS="${2:?Faltan las horas máximas}"
shift 2

if [ ! -f "$PRETRAIN_HOST" ]; then
    echo "Faltan los pesos ImageNet en $PRETRAIN_HOST" >&2
    exit 1
fi

# Files are created by root inside the container: hand them back to the user at the end
OWNER="$(id -u):$(id -g)"
docker run --rm --gpus all --ipc=host \
    --memory=20g --memory-swap=20g \
    --name "calibracion_${RUN_NAME}" \
    -e GPU_MEM_FRACTION=0.85 \
    -v "$REPO:/workdir/" \
    "$IMAGE" \
    bash -c 'python src/models/hrnet/train.py "$@"; status=$?
             chown -R '"$OWNER"' /workdir/data/experiments /workdir/outputs 2>/dev/null
             exit $status' _ \
        metadata.run_name="$RUN_NAME" \
        data_params.num_workers=6 \
        data_params.batch_size=4 \
        data_params.timeout=600 \
        model.params.nn_module.hrnet_config.pretrain=/workdir/data/pretrain/hrnet_w48_imagenet_timm.pth \
        train_params.max_hours="$MAX_HOURS" \
        "$@"
