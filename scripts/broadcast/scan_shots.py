"""First pass over a stretch of video: one frame per second with cheap measurements to separate the
wide main shot (useful) from replays, close-ups and crowd shots, and to mark shot cuts.

Usage: python3 scan_shots.py VIDEO --start 300 --seconds 600 --out output/
"""
import argparse
import csv
import os

import cv2
import numpy as np


def features(frame):
    small = cv2.resize(frame, (320, 180))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    green = ((hsv[..., 0] > 35) & (hsv[..., 0] < 85) & (hsv[..., 1] > 60) & (hsv[..., 2] > 40))
    # White lines on grass: very bright, low-saturation pixels surrounded by green
    white = (hsv[..., 1] < 50) & (hsv[..., 2] > 200)
    top_green = green[:60].mean()
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    return {"green": float(green.mean()), "green_top": float(top_green),
            "white": float(white.mean())}, hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--start", type=float, default=0)
    ap.add_argument("--seconds", type=float, default=600)
    ap.add_argument("--step", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(os.path.join(args.out, "frames"), exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    rows, prev = [], None
    t = args.start
    while t < args.start + args.seconds:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
        ok, frame = cap.read()
        if not ok:
            break
        f, hist = features(frame)
        f["cut"] = float(cv2.compareHist(prev, hist, cv2.HISTCMP_BHATTACHARYYA)) if prev is not None else 0.0
        prev = hist
        f.update(t=round(t, 2), frame=int(round(t * fps)))
        rows.append(f)
        cv2.imwrite(os.path.join(args.out, "frames", f"{f['frame']:07d}.jpg"),
                    cv2.resize(frame, (320, 180)), [cv2.IMWRITE_JPEG_QUALITY, 80])
        t += args.step
    with open(os.path.join(args.out, "scan.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["t", "frame", "green", "green_top", "white", "cut"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} fotogramas, fps {fps}")


if __name__ == "__main__":
    main()
