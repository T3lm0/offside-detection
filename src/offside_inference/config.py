"""Project paths from configs/paths.yaml, overridable with environment variables."""
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_FILE = os.environ.get("OFFSIDE_CONFIG", os.path.join(ROOT, "configs", "paths.yaml"))
ENV = {
    "runs_dir": "OFFSIDE_RUNS_DIR",
    "pose_weights": "OFFSIDE_POSE_WEIGHTS",
    "dataset_dir": "OFFSIDE_DATASET_DIR",
    "calibration_repo": "OFFSIDE_CALIB_REPO",
    "broadcast_dir": "OFFSIDE_BROADCAST_DIR",
    "output_dir": "OFFSIDE_OUTPUT_DIR",
}

_values = None


def path(key):
    """Absolute path for a configuration key.

    Args:
        key: One of the keys in configs/paths.yaml.

    Returns:
        The environment override if set, else the YAML value resolved against the repository root.
        A bare file name (no directory) is returned unchanged so Ultralytics can download it.
    """
    global _values
    if _values is None:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            _values = yaml.safe_load(f) or {}
    value = os.environ.get(ENV[key]) or _values[key]
    if os.path.dirname(value) == "" and os.path.splitext(value)[1]:
        return value
    return os.path.abspath(os.path.join(ROOT, os.path.expanduser(value)))
