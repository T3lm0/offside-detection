# Data and weights

This folder is ignored by git except for this file. Nothing needed to run the models is included
in the repository: no datasets, videos, annotations or trained weights. [docs/data.md](../docs/data.md)
explains how the data was built.

Default layout (change it in `configs/paths.yaml` or with environment variables):

```
data/
├── datasets/                     OFFSIDE_DATASET_DIR
│   ├── SoccerNet/tracking-2023/  downloaded with the SoccerNet pip package (requires accepting its terms)
│   ├── football_detection_yolo/          scripts/data/soccernet_to_yolo.py
│   ├── football_detection_yolo_4cls/     scripts/data/build_merged_dataset.py
│   ├── cwc_detector/                     scripts/broadcast/prepare_training.py
│   └── balon_recortes/                   scripts/broadcast/prepare_ball_crops.py
└── broadcast/                    OFFSIDE_BROADCAST_DIR
    ├── partidos.json             your recordings (copy configs/partidos.example.json)
    ├── eventos/                  scripts/broadcast/espn_events.py
    ├── clips/                    scripts/broadcast/cut_clips.py
    ├── conjunto_balon/           scripts/broadcast/ball_dataset.py (CVAT sets)
    └── banco/                    scripts/broadcast/bench.py
runs/                             OFFSIDE_RUNS_DIR: trained detectors (<runs>/detect/<name>/weights/best.pt)
third_party/soccernet-calibration-sportlight/   OFFSIDE_CALIB_REPO
```

## What you need to run an analysis

1. **A 4-class detector** (`player`, `goalkeeper`, `referee`, `ball`) at
   `runs/detect/det1280_<anything>/weights/best.pt`. Train it on SoccerNet with
   `scripts/train/train_safe.sh --imgsz 1280 --batch 8 --name det1280_soccernet`. Any Ultralytics
   YOLO detector with those class names also works.
2. **The pose model** `yolo11m-pose.pt`, downloaded automatically by Ultralytics.
3. **The calibration HRNet:** clone
   [soccernet-calibration-sportlight](https://github.com/NikolasEnt/soccernet-calibration-sportlight)
   into `third_party/`, build its Docker image with its `make build` (tagged
   `soccernet-calibration:<version>`; this project expects `0.0.2`), and train a model
   with `scripts/train/train_calibration.sh` (checkpoints end up in
   `data/experiments/*/evalai-*.pth` inside that repository). That repository has no licence file,
   so it is not included or redistributed here.

   `train_calibration.sh` passes options (`train_params.max_hours`, ImageNet initialisation of the
   backbone, `data_params.timeout`, `GPU_MEM_FRACTION`) that come from local modifications to
   Sportlight's training script. They are not part of this repository, so with an unmodified clone
   use Sportlight's own training instructions instead.
