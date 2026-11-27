"""Cuts one clip per event of eventos/eventos.csv for manual labelling.

The window depends on the event type: ESPN timestamps the moment of the event (the flag for an
offside, the ball in the net for a goal), so the preceding pass is a few seconds earlier. For a
corner it marks when it is awarded and for an inferred goal kick the previous shot: the restart
comes later.

Clips are re-encoded (h264_nvenc, no audio) so they start at the exact frame: clips.csv stores the
frame of the original video where each clip starts, so clip frame i is start_frame + i in the
original.

Output: clips/<match>/parte_<n>/<type>/<match>_p<n>_<mm-ss>_<type>_<n>.mp4 and clips/clips.csv

Usage:
  python3 cut_clips.py --dry-run          # how many clips and how much video
  python3 cut_clips.py --limit 3          # test
  python3 cut_clips.py --jobs 3           # all
"""
import argparse
import csv
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from offside_inference import config

HERE = config.path("broadcast_dir")
OUT = os.path.join(HERE, "clips")

# Seconds before and after the ESPN timestamp
VENTANAS = {
    "fuera_de_juego": (-12, 4),
    "gol": (-15, 5),
    "gol_anulado": (-15, 5),
    "penalti": (-10, 5),
    "saque_centro": (-3, 10),
    "saque_esquina": (-3, 45),
    "saque_puerta": (5, 40),
    "disparo": (-8, 4),
    "falta": (-5, 5),
    "revision_var": (-60, 5),
}
# By default cut the useful types (not the discarded ones: substitutions, cards...)
CAMPOS = ["clip", "partido", "parte", "tipo", "minuto", "seg_juego", "equipo", "jugadores", "uso",
          "origen", "sync_confianza", "video", "inicio_s", "fin_s", "fps", "fotograma_inicio",
          "fotograma_evento", "evento_en_clip_s", "x", "y", "x2", "y2", "texto"]


def plan(config, tipos=None):
    durations = {p["video"]: p["duracion_video_s"] for m in config["partidos"] for p in m["partes"].values()}
    with open(os.path.join(HERE, "eventos", "eventos.csv"), encoding="utf-8") as f:
        events = [r for r in csv.DictReader(f) if r["en_video"] == "1" and r["tipo"] in VENTANAS
                  and (tipos is None or r["tipo"] in tipos)]
    clips, used = [], {}
    for r in events:
        before, after = VENTANAS[r["tipo"]]
        t, fps = float(r["video_s"]), int(r["fps"])
        start = max(0.0, t + before)
        end = min(durations[r["video"]], t + after)
        if end - start < 2:
            continue
        # Name with the game clock (mm-ss) to find it by eye in the broadcast
        secs = int(r["seg_juego"])
        stem = f"{r['partido']}_p{r['parte']}_{secs // 60:02d}-{secs % 60:02d}_{r['tipo']}"
        used[stem] = used.get(stem, 0) + 1
        name = f"{stem}_{used[stem]}.mp4"
        first = int(round(start * fps))
        clips.append({
            "clip": os.path.join(r["partido"], f"parte_{r['parte']}", r["tipo"], name),
            "partido": r["partido"], "parte": r["parte"], "tipo": r["tipo"], "minuto": r["minuto"],
            "seg_juego": r["seg_juego"], "equipo": r["equipo"], "jugadores": r["jugadores"], "uso": r["uso"],
            "origen": r["origen"], "sync_confianza": r["sync_confianza"], "video": r["video"],
            "inicio_s": round(first / fps, 3), "fin_s": round(end, 3), "fps": fps,
            "fotograma_inicio": first, "fotograma_evento": r["fotograma"],
            "evento_en_clip_s": round(t - first / fps, 2),
            "x": r["x"], "y": r["y"], "x2": r["x2"], "y2": r["y2"], "texto": r["texto"],
        })
    return clips


def cut(clip, folder):
    out = os.path.join(OUT, clip["clip"])
    if os.path.exists(out):
        return out, "ya existía"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    frames = int(round((clip["fin_s"] - clip["inicio_s"]) * clip["fps"]))
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{clip['inicio_s']:.3f}",
           "-i", os.path.join(folder, clip["video"]), "-frames:v", str(frames), "-an",
           "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", out + ".part.mp4"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return out, "error: " + result.stderr.strip()[-300:]
    os.replace(out + ".part.mp4", out)
    return out, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tipos", nargs="+", default=None, help=f"Solo estos tipos: {', '.join(VENTANAS)}")
    ap.add_argument("--jobs", type=int, default=3)
    args = ap.parse_args()

    with open(os.path.join(HERE, "partidos.json"), encoding="utf-8") as f:
        config = json.load(f)
    clips = plan(config, args.tipos)
    total = sum(c["fin_s"] - c["inicio_s"] for c in clips)
    counts = {}
    for c in clips:
        counts[c["tipo"]] = counts.get(c["tipo"], 0) + 1
    print(f"{len(clips)} clips, {total / 60:.0f} min de vídeo:", dict(sorted(counts.items(), key=lambda kv: -kv[1])))
    if args.dry_run:
        return
    if args.limit:
        # Varied test: one of each type
        seen, sample = set(), []
        for c in clips:
            if c["tipo"] not in seen:
                seen.add(c["tipo"])
                sample.append(c)
        clips = sample[:args.limit]

    os.makedirs(OUT, exist_ok=True)
    errors = 0
    with ThreadPoolExecutor(args.jobs) as pool:
        for i, (out, status) in enumerate(pool.map(lambda c: cut(c, config["carpeta_videos"]), clips), 1):
            if status.startswith("error"):
                errors += 1
                print(f"[{i}/{len(clips)}] {os.path.relpath(out, OUT)}: {status}", flush=True)
            elif i % 25 == 0 or i == len(clips):
                print(f"[{i}/{len(clips)}] {os.path.relpath(out, OUT)}", flush=True)

    # The index lists every planned clip that exists on disk (tests included)
    path = os.path.join(OUT, "clips.csv")
    existing = [c for c in plan(config) if os.path.exists(os.path.join(OUT, c["clip"]))]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(existing)
    print(f"{len(existing)} clips en {path}; errores: {errors}")


if __name__ == "__main__":
    main()
