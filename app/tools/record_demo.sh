#!/usr/bin/env bash
# Rebuilds the viewer and records the demo videos.
# QML files are compiled into the executable: without rebuilding, changes in qml/ do not show in the video.
#
#   tools/record_demo.sh                 # both formats
#   tools/record_demo.sh historia        # vertical only (1080x1920)
#   tools/record_demo.sh horizontal      # horizontal only (1920x1080)
set -euo pipefail

cd "$(dirname "$0")/.."
formatos=("${@:-historia horizontal}")
read -r -a formatos <<< "${formatos[*]}"

cmake --build build -j"$(nproc)"
mkdir -p videos

for formato in "${formatos[@]}"; do
    case "$formato" in
        historia)   tam=1080x1920; ventana=540x960 ;;
        horizontal) tam=1920x1080; ventana=960x540 ;;
        *) echo "Formato desconocido: $formato (historia u horizontal)" >&2; exit 1 ;;
    esac
    echo "Grabando videos/demo_$formato.mp4 ($tam)..."
    ./build/offside_viewer sample_data/jugada_sintetica.json \
        --demo "videos/demo_$formato.mp4" --demo-size "$tam" --size "$ventana" 2>&1 \
        | grep -v "^qml: Grabando" || true
    [[ -s "videos/demo_$formato.mp4" ]] || { echo "No se generó videos/demo_$formato.mp4" >&2; exit 1; }
done
