"""Main camera position of each match, from frames of all its clips.

The main camera stays fixed in the stand for the whole match (it only pans and zooms): frames from
many clips are calibrated, those that calibrate well (HRNet + lines) are kept and the position is
the median of those that agree with the majority. It is saved in partidos.json ("camara") and in
clips/<match>/camara.json; the bench and the application use it to calibrate only orientation and
zoom.

Usage: python3 stadium_camera.py [--partidos RM-PSG ...] [--por-clip 2]
"""
import argparse
import csv
import json
import os

import numpy as np

from offside_inference import config
from offside_inference.detection import FrameDetector
from offside_inference.session import CENTER_AGREE_M, Session, _good

HERE = config.path("broadcast_dir")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--partidos", nargs="+", default=None)
    ap.add_argument("--por-clip", type=int, default=2, help="Fotogramas por clip")
    args = ap.parse_args()
    path = os.path.join(HERE, "partidos.json")
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    with open(os.path.join(HERE, "clips", "clips.csv"), encoding="utf-8") as f:
        clips = list(csv.DictReader(f))

    session = Session()
    session._detector = FrameDetector(session.detector_path, session.device)
    try:
        for match in config["partidos"]:
            name = match["partido"]
            if args.partidos and name not in args.partidos:
                continue
            centers = []
            mine = [c for c in clips if c["partido"] == name]
            for k, clip in enumerate(mine, 1):
                session.open([os.path.join(HERE, "clips", clip["clip"])])
                for j in np.linspace(0, session.source.count - 1, args.por_clip + 2)[1:-1].round().astype(int):
                    frame = session.source.read(int(j))
                    c = session._calibrate_frame(frame, int(j), [p["box"] for p in session._detector(frame)[0]],
                                                 use_center=False)
                    if _good(c):
                        centers.append(c["cam"].center)
                print(f"\r{name}: {k}/{len(mine)} clips, {len(centers)} fotogramas buenos", end="", flush=True)
            centers = np.array(centers)
            med = np.median(centers, axis=0)
            agree = centers[np.linalg.norm(centers - med, axis=1) <= CENTER_AGREE_M]
            center = np.median(agree, axis=0)
            spread = np.linalg.norm(agree - center, axis=1)
            match["camara"] = {"centro": [round(float(v), 2) for v in center], "fotogramas": int(len(agree)),
                               "descartados": int(len(centers) - len(agree)),
                               "dispersion_mediana_m": round(float(np.median(spread)), 2)}
            print(f"\n{name}: cámara en {match['camara']['centro']} con {len(agree)} fotogramas "
                  f"(descartados {len(centers) - len(agree)}, dispersión {np.median(spread):.2f} m)")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            # Also next to its clips, so the application uses it when opening any of them
            with open(os.path.join(HERE, "clips", name, "camara.json"), "w", encoding="utf-8") as f:
                json.dump({"partido": name, **match["camara"]}, f, ensure_ascii=False, indent=2)
    finally:
        session.close()


if __name__ == "__main__":
    main()
