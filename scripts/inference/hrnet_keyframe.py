"""Automatic keyframe: pitch points are predicted by the trained calibration HRNet
(soccernet-calibration-sportlight) instead of being marked by hand with detect_pitch_lines.py.

Keeps the grass points with enough confidence, drops with RANSAC those that do not fit a single
homography and writes a keyframe that run_inference.py uses as is. It also writes a review image:
the points (green if they fit, red if not) and the projected pitch lines.

The model runs in its Docker container (soccernet-calibration:0.0.2) with hrnet_keypoints_container.py.

Usage:
    python3 hrnet_keyframe.py --image .../SNMOT-134/img1/000600.jpg --frame 600 --out keyframes/SNMOT-134.json
"""
import argparse
import json
import os

import cv2
import numpy as np

from offside_inference import camera as camlib
from offside_inference.hrnet import CALIB_REPO, best_checkpoint, fit_homography, ground_points, predict_keypoints


def draw_preview(image, points, inliers, H, path):
    overlay = image.copy()
    if H is not None:
        h, w = image.shape[:2]
        for poly in camlib.pitch_polylines():
            dense = np.concatenate([np.linspace(a, b, 20) for a, b in zip(poly[:-1], poly[1:])])
            uv = camlib.project_h(H, dense)
            inside = (np.abs(uv[:, 0] - w / 2) < 2 * w) & (np.abs(uv[:, 1] - h / 2) < 2 * h)
            cv2.polylines(overlay, [uv[inside].astype(np.int32).reshape(-1, 1, 2)], False, (255, 0, 255), 2)
    for p, ok in zip(points, inliers):
        u, v = map(int, p["image"])
        cv2.circle(overlay, (u, v), 9, (0, 220, 0) if ok else (0, 0, 255), 3)
        cv2.putText(overlay, p["hrnet"].lower(), (u + 10, v - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.imwrite(path, overlay)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--frame", type=int, required=True, help="Número de fotograma de esa imagen en el clip")
    ap.add_argument("--out", required=True, help="Keyframe (JSON) para run_inference.py")
    ap.add_argument("--checkpoint", help="HRNet de calibración (por defecto, el de mejor val_evalai)")
    ap.add_argument("--min-conf", type=float, default=0.5, help="Confianza mínima de un punto (0,5 en Sportlight)")
    ap.add_argument("--ransac-px", type=float, default=8.0, help="Error máximo en píxeles para que un punto encaje")
    args = ap.parse_args()

    checkpoint = args.checkpoint or best_checkpoint()
    points = ground_points(predict_keypoints(args.image, checkpoint), args.min_conf)
    H, inliers = fit_homography(points, args.ransac_px)
    good = [p for p, ok in zip(points, inliers) if ok]

    image = cv2.imread(args.image)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    preview = os.path.splitext(args.out)[0] + "_hrnet.jpg"
    draw_preview(image, points, inliers, H, preview)
    keyframe = {
        "descripcion": f"Puntos del campo predichos por el HRNet de calibración "
                       f"({os.path.relpath(checkpoint, CALIB_REPO)}) en el fotograma {args.frame}, "
                       f"filtrados con RANSAC ({args.ransac_px:g} px)",
        "frame": args.frame,
        "lines": [],
        "points": good,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(keyframe, f, indent=2, ensure_ascii=False)
    print(f"{len(points)} puntos del césped con confianza ≥ {args.min_conf:g}; encajan {len(good)}. "
          f"Keyframe: {args.out}. Imagen: {preview}")
    if len(good) < 4:
        raise SystemExit("Menos de 4 puntos fiables: hay que marcar este fotograma a mano (detect_pitch_lines.py)")


if __name__ == "__main__":
    main()
