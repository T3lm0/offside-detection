#!/usr/bin/env bash
# Runs train_detector.py with limited RAM (if exceeded, the kernel kills the training instead of
# freezing the machine) and logs RAM and video memory every 5 s to logs/.
# Arguments are passed through to train_detector.py.
set -u
cd "$(dirname "$0")"
mkdir -p logs
STAMP=$(date +%Y%m%d_%H%M%S)
TRAIN_LOG="logs/train_${STAMP}.log"
RES_LOG="logs/resources_${STAMP}.csv"
MEMORY_MAX="${MEMORY_MAX:-20G}"

echo "hora,ram_usada_mb,ram_disponible_mb,swap_usada_mb,vram_usada_mb,gpu_util" > "$RES_LOG"
(
    while true; do
        ram=$(free -m | awk '/^Mem/{print $3","$7} /^Swap/{s=$3} END{print ","s}' | tr -d '\n')
        gpu=$(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits | tr -d ' ')
        echo "$(date +%H:%M:%S),${ram},${gpu}" >> "$RES_LOG"
        sleep 5
    done
) &
MONITOR_PID=$!
trap 'kill $MONITOR_PID 2>/dev/null' EXIT

echo "Log: $TRAIN_LOG | Recursos: $RES_LOG | Límite RAM: $MEMORY_MAX"
systemd-run --user --scope --quiet -p MemoryMax="$MEMORY_MAX" -p MemorySwapMax=0 \
    python3 train_detector.py "$@" > "$TRAIN_LOG" 2>&1
STATUS=$?
echo "Fin con código $STATUS" | tee -a "$TRAIN_LOG"
exit $STATUS
