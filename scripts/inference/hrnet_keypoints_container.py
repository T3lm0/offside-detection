"""Pitch points with Sportlight's calibration HRNet. Runs inside its Docker container (started by
offside_inference.hrnet) and writes, for each image, the 57 points in original image pixels with
their confidence and their pitch position in the SoccerNet frame.

Usage (inside the container):
    python hrnet_keypoints_container.py CHECKPOINT OUTPUT.json IMAGE [IMAGE...]
    python hrnet_keypoints_container.py --servidor CHECKPOINT

With --servidor the model is loaded once and, for each image path read from stdin, it answers with
a line "@@" + JSON of its points (it first writes "@@LISTO"). The prefix separates the answers from
the licence notice the NVIDIA image prints on start-up.
"""
import json
import sys

import cv2
import torch

sys.path.insert(0, "/workdir")
from argus import load_model  # noqa: E402
from src.datatools.ellipse import INTERSECTON_TO_PITCH_POINTS, PITCH_POINTS  # noqa: E402
from src.models.hrnet.metamodel import HRNetMetaModel  # noqa: E402,F401  (argus looks it up by name)

INPUT_W, INPUT_H = 960, 540


def keypoints_of(model, path):
    image = cv2.imread(path, cv2.IMREAD_COLOR)  # BGR and not normalised, as in training
    h, w = image.shape[:2]
    x = torch.from_numpy(cv2.resize(image, (INPUT_W, INPUT_H), interpolation=cv2.INTER_AREA))
    x = x.permute(2, 0, 1).float().div(255).unsqueeze(0)
    keypoints = model.predict(x)[0].cpu().numpy()  # (57, 3): x, y at 960x540 and confidence
    points = []
    for i, (u, v, conf) in enumerate(keypoints):
        name = INTERSECTON_TO_PITCH_POINTS[i]
        pitch = PITCH_POINTS.get(name)
        points.append({"index": i, "name": name,
                       "image": [float(u) * w / INPUT_W, float(v) * h / INPUT_H], "conf": float(conf),
                       "pitch": None if pitch is None else [float(c) for c in pitch]})
    return points


def serve(checkpoint):
    model = load_model(checkpoint, device="cuda:0")
    print("@@LISTO", flush=True)
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            reply = {"points": keypoints_of(model, path)}
        except Exception as e:  # the image may not exist or be unreadable: answer anyway
            reply = {"error": f"{type(e).__name__}: {e}"}
        print("@@" + json.dumps(reply), flush=True)


def main():
    if sys.argv[1] == "--servidor":
        serve(sys.argv[2])
        return
    checkpoint, out_path, *images = sys.argv[1:]
    model = load_model(checkpoint, device="cuda:0")
    result = {path: keypoints_of(model, path) for path in images}
    with open(out_path, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
