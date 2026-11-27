"""Calibration of a frame with the trained calibration HRNet (soccernet-calibration-sportlight).

The model runs in its Docker container (soccernet-calibration:0.0.2) with
scripts/inference/hrnet_keypoints_container.py. Of its 57 points, the grass points with enough
confidence that fit a single homography (RANSAC) are used, converted to this project's pitch frame.
"""
import glob
import json
import os
import subprocess
import tempfile

import cv2
import numpy as np

from . import config

CALIB_REPO = config.path("calibration_repo")
DOCKER_IMAGE = "soccernet-calibration:0.0.2"
SCRIPTS = os.path.join(config.ROOT, "scripts", "inference")
CONTAINER_SCRIPT = "hrnet_keypoints_container.py"
# Fixed pitch points used by Sportlight for calibration (prediction.py, keep_points) plus the centre
# circle points at 45° and on the axis (34-39), which are also fixed and needed in midfield shots.
# Tangency points to the circles are left out because they depend on where the camera is
KEEP = set(range(29)) | set(range(34, 40)) | {40, 41, 42, 44, 45, 48, 51, 52, 55}


def best_checkpoint():
    """The evalai-*.pth with the best val_evalai across all experiments (the value is in the file name)."""
    files = glob.glob(os.path.join(CALIB_REPO, "data", "experiments", "*", "evalai-*.pth"))
    if not files:
        raise FileNotFoundError("No hay ningún HRNet de calibración entrenado")
    return max(files, key=lambda p: float(os.path.basename(p)[:-4].rsplit("-", 1)[1]))


def _docker_args(checkpoint, image_dir):
    return ["docker", "run", "--rm", "--gpus", "all", "-u", f"{os.getuid()}:{os.getgid()}",
            "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{CALIB_REPO}:/workdir:ro", "-v", f"{SCRIPTS}:/scripts:ro",
            "-v", f"{image_dir}:/imagenes:ro", "-w", "/workdir", DOCKER_IMAGE,
            "python", f"/scripts/{CONTAINER_SCRIPT}"], "/workdir/" + os.path.relpath(checkpoint, CALIB_REPO)


def predict_keypoints(image_path, checkpoint):
    """The 57 HRNet points for one image, starting the container just for it."""
    image_path = os.path.abspath(image_path)
    with tempfile.TemporaryDirectory() as tmp:
        args, ckpt = _docker_args(checkpoint, os.path.dirname(image_path))
        args[args.index("-w"):args.index("-w")] = ["-v", f"{tmp}:/salida"]
        # Standard output only carries the NVIDIA image licence notice
        subprocess.run(args + [ckpt, "/salida/puntos.json", "/imagenes/" + os.path.basename(image_path)],
                       check=True, stdout=subprocess.DEVNULL)
        with open(os.path.join(tmp, "puntos.json")) as f:
            return next(iter(json.load(f).values()))


class HrnetServer:
    """HRNet container kept open for the whole session.

    The first image takes as long as the container start-up (~10 s) and the following ones less than
    a second. Images must be inside image_dir, which is mounted in the container.
    """

    def __init__(self, image_dir, checkpoint=None):
        self.image_dir = os.path.abspath(image_dir)
        self.checkpoint = checkpoint or best_checkpoint()
        self.name = f"hrnet_sesion_{os.getpid()}"
        self.process = None

    def _start(self):
        args, ckpt = _docker_args(self.checkpoint, self.image_dir)
        args[3:3] = ["-i", "--name", self.name]
        self.process = subprocess.Popen(args + ["--servidor", ckpt], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._read_reply(expect_ready=True)

    def _read_reply(self, expect_ready=False):
        for line in self.process.stdout:
            if not line.startswith("@@"):
                continue  # container licence notice
            body = line[2:].strip()
            if expect_ready:
                if body == "LISTO":
                    return None
                continue
            return json.loads(body)
        raise RuntimeError("El contenedor del HRNet se ha cerrado (¿Docker o la GPU no están disponibles?)")

    def keypoints(self, image_path):
        if self.process is None or self.process.poll() is not None:
            self._start()
        rel = os.path.relpath(os.path.abspath(image_path), self.image_dir)
        if rel.startswith(".."):
            raise ValueError(f"{image_path} no está en {self.image_dir}")
        self.process.stdin.write(f"/imagenes/{rel}\n")
        self.process.stdin.flush()
        reply = self._read_reply()
        if "error" in reply:
            raise RuntimeError(f"HRNet: {reply['error']}")
        return reply["points"]

    def close(self):
        if self.process is None or self.process.poll() is not None:
            return
        # Closing stdin ends the server and Docker removes the container (--rm)
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "stop", "-t", "2", self.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ground_points(keypoints, min_conf=0.5):
    """Grass points with enough confidence, converted to this project's pitch frame.

    SoccerNet has the far touchline at Y = -34 and Z pointing down; here the far touchline is +Y.
    """
    out = []
    for k in keypoints:
        if k["index"] in KEEP and k["pitch"] is not None and abs(k["pitch"][2]) < 1e-6 and k["conf"] >= min_conf:
            out.append({"field": [round(k["pitch"][0], 3), round(-k["pitch"][1], 3)],
                        "image": [round(k["image"][0], 1), round(k["image"][1], 1)],
                        "hrnet": k["name"], "conf": round(k["conf"], 3)})
    return out


def fit_homography(points, ransac_px=8.0):
    """Pitch -> image homography with RANSAC: (H or None, [whether each point fits])."""
    if len(points) < 4:
        return None, [False] * len(points)
    field = np.array([p["field"] for p in points], np.float64)
    image = np.array([p["image"] for p in points], np.float64)
    H, mask = cv2.findHomography(field, image, cv2.RANSAC, ransac_px)
    if H is None:
        return None, [False] * len(points)
    return H, mask.ravel().astype(bool).tolist()
