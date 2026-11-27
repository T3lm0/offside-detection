"""Law 11 test bench with real Club World Cup plays.

  - Positives: offsides called by the referee (ESPN match commentary).
  - Negatives: goals that stood (there was no offside in the last pass).
  - The goal disallowed by VAR: the reason is not in the commentary, the annotator sets it.

A person marks each play once in the application (pass frame, goal, attacker and defender) and the
bench replays it with whatever models exist at the time, to measure whether a calibration or pose
change helps or hurts. Attacker and defender are recognised by their box in the image, not by their
number, which changes when the detector changes.

Usage:
  python3 bench.py crear                 # banco/jugadas.csv from clips/clips.csv
  python3 bench.py marcar                # opens the application play by play (in a terminal)
  python3 bench.py medir --etiqueta base # replays every marked play and writes the report
"""
import argparse
import csv
import glob
import json
import os
import subprocess
import time
from datetime import datetime

from offside_inference import config

HERE = config.path("broadcast_dir")
BANCO = os.path.join(HERE, "banco")
CLIPS = os.path.join(HERE, "clips")
APP_RESULTS = os.path.join(config.path("output_dir"), "app")
VIEWER = os.environ.get("OFFSIDE_VIEWER", os.path.join(config.ROOT, "app", "build", "offside_viewer"))
JUGADAS = os.path.join(BANCO, "jugadas.csv")
ANOTACIONES = os.path.join(BANCO, "anotaciones.json")

ESPERADO = {"fuera_de_juego": "offside", "gol": "onside", "gol_anulado": "desconocido"}
CAMPOS = ["jugada", "clip", "partido", "parte", "minuto", "tipo", "esperado", "evento_en_clip_s", "jugadores", "texto"]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def plays():
    with open(JUGADAS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def crear(_args):
    with open(os.path.join(CLIPS, "clips.csv"), encoding="utf-8") as f:
        clips = [c for c in csv.DictReader(f) if c["tipo"] in ESPERADO]
    os.makedirs(BANCO, exist_ok=True)
    rows = []
    for c in clips:
        stem = os.path.splitext(os.path.basename(c["clip"]))[0]
        rows.append({"jugada": stem, "clip": c["clip"], "partido": c["partido"], "parte": c["parte"],
                     "minuto": c["minuto"], "tipo": c["tipo"], "esperado": ESPERADO[c["tipo"]],
                     "evento_en_clip_s": c["evento_en_clip_s"], "jugadores": c["jugadores"], "texto": c["texto"]})
    with open(JUGADAS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["esperado"]] = counts.get(r["esperado"], 0) + 1
    print(f"{len(rows)} jugadas en {JUGADAS}: {counts}")


def last_result(stem, since):
    """Application JSON for this clip written after opening it (the latest if there are several)."""
    found = [p for p in glob.glob(os.path.join(APP_RESULTS, f"{stem}_f*.json")) if os.path.getmtime(p) >= since]
    return max(found, key=os.path.getmtime) if found else None


def annotation_from(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    event = data["events"][0]
    result = event["offside"]
    players = {p["id"]: p for p in data["frames"][0]["players"]}
    att, dfd = result["attacker"]["id"], result["defender"]["id"]
    return {"fotograma": event["frame"], "direccion": result["attack_direction"],
            "atacante": {"id": att, "box": players[att].get("box")},
            "defensor": {"id": dfd, "box": players[dfd].get("box")},
            # Ball: the detector's, none, or the image point marked by the person
            "balon": {"user": result.get("ball_uv"), "none": "none"}.get(result.get("ball_source"), "auto"),
            "resultado_al_marcar": {"status": result["status"], "margin_m": result.get("margin_m")},
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}


def marcar(args):
    notes = load_json(ANOTACIONES, {})
    # With --solo plays are marked again even if already marked (e.g. ones skipped due to a fixed bug)
    pending = [p for p in plays() if (p["jugada"] in args.solo if args.solo else p["jugada"] not in notes)]
    print(f"{len(pending)} jugadas por marcar ({len(notes)} ya marcadas).")
    print("En la aplicación: busca el último pase del equipo atacante, «Calibrar y detectar», portería,\n"
          "atacante, defensor y «Aplicar la Regla 11». Después cierra la ventana.\n")
    for i, p in enumerate(pending, 1):
        stem = p["jugada"]
        clip = os.path.join(CLIPS, p["clip"])
        start = max(0, int((float(p["evento_en_clip_s"]) - 3) * 30))
        print(f"[{i}/{len(pending)}] {p['partido']} {p['minuto']} {p['tipo']} — {p['jugadores']}")
        print(f"    {p['texto']}")
        while True:
            since = time.time()
            subprocess.run([VIEWER, "--input", clip, "--frame", str(start)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            path = last_result(stem, since)
            if path:
                note = annotation_from(path)
                break
            answer = input("    No has aplicado la Regla 11. [r] repetir, [s] saltar (no evaluable), [q] salir: ").strip().lower()
            if answer == "s":
                note = {"saltada": True, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}
                break
            if answer == "q":
                return
        if not note.get("saltada"):
            expected = p["esperado"]
            if expected == "desconocido":
                answer = input("    ¿Qué decidió el VAR? [o] fuera de juego, [l] legal (otro motivo): ").strip().lower()
                expected = "offside" if answer == "o" else "onside"
            note["esperado"] = expected
            got = note["resultado_al_marcar"]
            print(f"    Guardada: fotograma {note['fotograma']}, atacante {note['atacante']['id']}, "
                  f"defensor {note['defensor']['id']} → {got['status']} ({100 * (got['margin_m'] or 0):+.0f} cm)")
        note["nota"] = input("    Nota (opcional, Enter para seguir): ").strip()
        notes[stem] = note
        save_json(ANOTACIONES, notes)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(players, box):
    best = max(players, key=lambda p: iou(p["box"], box))
    return best["id"] if iou(best["box"], box) >= 0.3 else None


def medir(args):
    from offside_inference.session import Session

    notes = load_json(ANOTACIONES, {})
    by_id = {p["jugada"]: p for p in plays()}
    todo = [(k, v) for k, v in notes.items() if not v.get("saltada") and k in by_id]
    if not todo:
        print("No hay jugadas marcadas: primero python3 bench.py marcar")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    run = f"{stamp}_{args.etiqueta}"
    out_dir = os.path.join(BANCO, "ejecuciones", run)
    os.makedirs(out_dir, exist_ok=True)
    session = Session(out_dir=os.path.join(out_dir, "salidas"))
    # Main camera position of each match (stadium_camera.py); without it, it is estimated from the clip
    with open(os.path.join(HERE, "partidos.json"), encoding="utf-8") as f:
        centers = {m["partido"]: m.get("camara", {}).get("centro") for m in json.load(f)["partidos"]}
    rows = []
    try:
        for i, (stem, note) in enumerate(todo, 1):
            p = by_id[stem]
            row = {"jugada": stem, "partido": p["partido"], "minuto": p["minuto"], "tipo": p["tipo"],
                   "esperado": note["esperado"]}
            t0 = time.monotonic()
            try:
                session.set_camera_center(centers.get(p["partido"]) if args.camara_estadio else None)
                session.open([os.path.join(CLIPS, p["clip"])])
                index = session.index_of(note["fotograma"])
                prep = session.prepare(index)
                cal = prep["calibration"]
                row.update(calibrado=cal["ok"], error_px=cal.get("error_px"), dudosa=cal.get("dubious"),
                           ancla=cal.get("anchor"), metodo=cal.get("method"), camara=cal.get("camera"),
                           desvio_libre_m=cal.get("free_offset_m"))
                att = match(prep["players"], note["atacante"]["box"])
                dfd = match(prep["players"], note["defensor"]["box"])
                if not cal["ok"]:
                    row["obtenido"] = "no_evaluable"
                elif att is None or dfd is None:
                    row["obtenido"] = "jugador_no_detectado"
                else:
                    res = session.analyze(index, att, dfd, note["direccion"], ball=note.get("balon", "auto"))
                    check = res.get("check_2d") or {}
                    row.update(obtenido=res["status"], margen_cm=round(100 * res["margin_m"], 1),
                               incertidumbre_cm=round(100 * res["uncertainty_m"], 1),
                               concluyente=not res["within_uncertainty"],
                               margen_2d_cm=round(100 * check["margin_m"], 1) if check else None,
                               coincide_2d=check.get("agrees"),
                               parte_atacante=res.get("attacker_joint"), parte_defensor=res.get("defender_joint"),
                               descartadas=sum(len(v) for v in (res.get("discarded_joints") or {}).values()))
            except Exception as e:  # a failing play does not stop the bench
                row.update(obtenido="error", error=str(e)[:200])
            row["acierto"] = row.get("obtenido") == note["esperado"]
            row["segundos"] = round(time.monotonic() - t0, 1)
            rows.append(row)
            margin = "" if row.get("margen_cm") is None else f" ({row['margen_cm']:+.0f} cm)"
            print(f"[{i}/{len(todo)}] {stem}: esperado {row['esperado']}, obtenido {row.get('obtenido')}{margin}",
                  flush=True)
    finally:
        session.close()

    fields = ["jugada", "partido", "minuto", "tipo", "esperado", "obtenido", "acierto", "margen_cm",
              "incertidumbre_cm", "concluyente", "margen_2d_cm", "coincide_2d", "parte_atacante", "parte_defensor",
              "descartadas", "calibrado", "metodo", "error_px", "dudosa", "ancla", "camara", "desvio_libre_m",
              "segundos", "error"]
    with open(os.path.join(out_dir, "resultados.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    write_report(out_dir, run, rows)


def write_report(out_dir, run, rows):
    def share(n, d):
        return f"{n}/{d} ({100 * n / d:.0f} %)" if d else "—"

    lines = [f"# Banco de pruebas de la Regla 11 · {run}", ""]
    for label, subset in (("Todas", rows), ("Fuera de juego (pitados)", [r for r in rows if r["esperado"] == "offside"]),
                          ("Legales (goles válidos)", [r for r in rows if r["esperado"] == "onside"])):
        evaluated = [r for r in subset if r.get("obtenido") in ("offside", "onside")]
        lines.append(f"- **{label}:** aciertos {share(sum(r['acierto'] for r in subset), len(subset))}; "
                     f"evaluadas {share(len(evaluated), len(subset))}; "
                     f"concluyentes {share(sum(bool(r.get('concluyente')) for r in evaluated), len(evaluated))}")
    evaluated = [r for r in rows if r.get("obtenido") in ("offside", "onside")]
    errors = sorted(r["error_px"] for r in rows if r.get("error_px") is not None)
    lines += [f"- **2D y 3D coinciden:** {share(sum(bool(r.get('coincide_2d')) for r in evaluated), len(evaluated))}",
              f"- **Calibración:** {share(sum(bool(r.get('calibrado')) for r in rows), len(rows))} calibradas, "
              f"{sum(bool(r.get('dudosa')) for r in rows)} dudosas, "
              f"{sum(r.get('ancla') is not None for r in rows)} con un fotograma vecino; error mediano "
              f"{errors[len(errors) // 2]:.2f} px" if errors else "- **Calibración:** sin datos",
              f"- **Articulaciones descartadas:** {sum(r.get('descartadas') or 0 for r in evaluated)} en "
              f"{len(evaluated)} jugadas",
              f"- **Calibración con la posición de la cámara fija:** "
              f"{share(sum(r.get('metodo') == 'posición fija' for r in rows), len(rows))}", "",
              "| Jugada | Esperado | Obtenido | Margen 3D | Margen 2D | Calibración | |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        cal = "—" if r.get("error_px") is None else f"{r['error_px']:.1f} px" + (" dudosa" if r.get("dudosa") else "")
        m3 = "—" if r.get("margen_cm") is None else f"{r['margen_cm']:+.0f} ±{r['incertidumbre_cm']:.0f} cm"
        m2 = "—" if r.get("margen_2d_cm") is None else f"{r['margen_2d_cm']:+.0f} cm"
        lines.append(f"| {r['partido']} {r['minuto']} {r['tipo']} | {r['esperado']} | {r.get('obtenido')} | {m3} | {m2} "
                     f"| {cal} | {'✔' if r['acierto'] else '✘'} |")
    path = os.path.join(out_dir, "informe.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:7]))
    print(f"Informe: {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("crear")
    m = sub.add_parser("marcar")
    m.add_argument("--solo", nargs="+", help="Solo estas jugadas (por nombre), aunque ya estén marcadas")
    r = sub.add_parser("medir")
    r.add_argument("--etiqueta", default="prueba", help="Nombre de la ejecución (p. ej. base, rtmpose)")
    r.add_argument("--camara-estadio", action="store_true",
                   help="Usar la posición de la cámara de cada partido (partidos.json) en vez de estimarla con el clip")
    args = ap.parse_args()
    {"crear": crear, "marcar": marcar, "medir": medir}[args.cmd](args)


if __name__ == "__main__":
    main()
