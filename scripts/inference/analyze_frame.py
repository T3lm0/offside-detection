"""Single-frame analysis from the terminal, same as in the application.

Without --attacker/--defender it calibrates the frame, detects the players and writes an image with
each one numbered so they can be chosen. With them, it applies Law 11 and writes the viewer JSON and
the pass image to <output_dir>/app/ (configs/paths.yaml).

    python3 analyze_frame.py --input clip.mp4 --frame 579
    python3 analyze_frame.py --input clip.mp4 --frame 579 --goal right --attacker 12 --defender 9

--frame is the number shown in the application (for a folder such as 000579.jpg, 579).
--goal is the attacked goal: left (-X) or right (+X), according to the pitch calibration.
"""
import argparse
import os

import cv2

from offside_inference.session import Session


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, nargs="+", help="Vídeo, imagen, varias imágenes o carpeta")
    ap.add_argument("--frame", type=int, default=None, help="Número del fotograma del pase (por defecto, el primero)")
    ap.add_argument("--goal", choices=["left", "right"], help="Portería atacada")
    ap.add_argument("--attacker", type=int)
    ap.add_argument("--defender", type=int, help="Penúltimo defensor (si falta, se propone)")
    args = ap.parse_args()

    session = Session()
    try:
        info = session.open(args.input)
        index = 0 if args.frame is None else session.index_of(args.frame)
        print(f"{info['name']}: {info['count']} fotograma{'' if info['count'] == 1 else 's'}, {info['width']}x{info['height']}")
        prep = session.prepare(index, print)
        print(prep["calibration"]["message"])
        for p in prep["players"]:
            where = "" if p["ground"] is None else f" en ({p['ground'][0]:.1f}, {p['ground'][1]:.1f}) m"
            print(f"  {p['id']:>2}  {p['role']:<10} equipo {p['team']}{where}")
        if not prep["calibration"]["ok"]:
            return
        if args.attacker is None or args.goal is None:
            frame = session.prepared[index]["frame"].copy()
            for p in prep["players"]:
                x1, y1, x2, y2 = map(int, p["box"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(frame, str(p["id"]), (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            os.makedirs(session.out_dir, exist_ok=True)
            path = os.path.join(session.out_dir, f"{info['name']}_f{prep['number']}_jugadores.jpg")
            cv2.imwrite(path, frame)
            print(f"Elige --goal, --attacker y --defender. Jugadores numerados en {path}")
            return
        direction = 1 if args.goal == "right" else -1
        defender = args.defender
        if defender is None:
            proposal = session.propose(index, direction, args.attacker)
            defender = proposal["defender"]
            print(f"Defensor propuesto: {defender} ({proposal['reason']})")
            if defender is None:
                return
        result = session.analyze(index, args.attacker, defender, direction, print)
        margin = "" if result["margin_m"] is None else f", margen {100 * result['margin_m']:+.1f} cm ±{100 * result['uncertainty_m']:.0f}"
        print(f"{result['status']}{margin} ({result['attacker_joint']} frente a {result['defender_joint']}, "
              f"línea por {result['line_source']})")
        for w in result["warnings"]:
            print(f"  aviso: {w}")
        print(f"Visor: {result['json']}\nImagen: {result['image']}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
