"""Helps create a clip keyframe by hand: detects the white pitch lines in a frame, draws them
numbered and writes a keyframe template with all of them.

Then open the image, decide which pitch line each one is (names in offside_inference/camera.py,
FIELD_LINES), put that name in "field" and delete the ones that are not useful (running track,
players...). At least 4 non-parallel lines are needed, or lines plus points (FIELD_POINTS). The
intersections of the penalty arc with the box line help a lot.

Usage:
    python3 detect_pitch_lines.py --image .../img1/000526.jpg --frame 526 --out keyframes/my_clip.json
"""
import argparse
import json
import os

import cv2
import numpy as np


def detect_lines(image, min_length=120):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, (30, 40, 40), (90, 255, 255))
    near_grass = cv2.dilate(grass, np.ones((25, 25), np.uint8)) > 0
    white = ((hsv[..., 1] < 70) & (hsv[..., 2] > 175) & near_grass).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    segs = cv2.HoughLinesP(white, 1, np.pi / 720, threshold=60, minLineLength=min_length, maxLineGap=25)
    if segs is None:
        return []
    # Group segments of the same line (similar angle and distance to the origin)
    groups = []
    for x1, y1, x2, y2 in segs[:, 0, :].astype(float):
        a = np.arctan2(y2 - y1, x2 - x1) % np.pi
        rho = np.array([-np.sin(a), np.cos(a)]) @ [x1, y1]
        for g in groups:
            if abs(g["a"] - a) < 0.03 and abs(g["rho"] - rho) < 12:
                g["pts"] += [(x1, y1), (x2, y2)]
                break
        else:
            groups.append({"a": a, "rho": rho, "pts": [(x1, y1), (x2, y2)]})
    lines = []
    for g in sorted(groups, key=lambda g: -len(g["pts"])):
        P = np.array(g["pts"], np.float32)
        vx, vy, x0, y0 = cv2.fitLine(P, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        t = (P - [x0, y0]) @ [vx, vy]
        lines.append([[round(float(x0 + vx * t.min()), 1), round(float(y0 + vy * t.min()), 1)],
                      [round(float(x0 + vx * t.max()), 1), round(float(y0 + vy * t.max()), 1)]])
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--frame", type=int, required=True, help="Número de fotograma de esa imagen en el clip")
    ap.add_argument("--out", required=True, help="Plantilla de keyframe (JSON)")
    args = ap.parse_args()

    image = cv2.imread(args.image)
    lines = detect_lines(image)
    overlay = image.copy()
    for i, (p1, p2) in enumerate(lines):
        cv2.line(overlay, tuple(map(int, p1)), tuple(map(int, p2)), (255, 0, 255), 3)
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        cv2.putText(overlay, str(i), (int(mid[0]), int(mid[1]) - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 255), 3)
    preview = os.path.splitext(args.out)[0] + "_lineas.jpg"
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cv2.imwrite(preview, overlay)
    template = {
        "descripcion": "Sustituye cada '?' por el nombre de la línea del campo (FIELD_LINES) y borra las que no sirvan",
        "frame": args.frame,
        "lines": [{"field": "?", "id": i, "image": l} for i, l in enumerate(lines)],
        "points": [],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
    print(f"{len(lines)} líneas detectadas. Imagen: {preview}. Plantilla: {args.out}")


if __name__ == "__main__":
    main()
