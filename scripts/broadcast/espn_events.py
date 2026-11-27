"""Events of the 2025 Club World Cup matches (partidos.json) taken from ESPN's match commentary
(public API at site.api.espn.com), with each event's use in the pipeline and its video frame.

Each event has the game-clock second, the real UTC time (wallclock) and often the normalised pitch
position (0-1). Synchronisation is per half: the video second where each half starts is in
partidos.json (checked against the on-screen clock), and the time elapsed since that half's
kick-off, measured with the UTC time, is added to it. This handles stoppage time correctly, which
ESPN leaves at 45:00 / 90:00 on the game clock.

ESPN does not record goal kicks: they are inferred (origin "inferido") after a shot wide with no
corner in the next 40 s.

Usage: python3 espn_events.py            -> eventos/raw/<id>.json and eventos/eventos.csv
"""
import csv
import json
import os
import urllib.request
from datetime import datetime

from offside_inference import config

HERE = config.path("broadcast_dir")
OUT = os.path.join(HERE, "eventos")
URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.cwc/summary?event={}"

# Videos and start of each half. The train/val/test split is always by match
with open(os.path.join(HERE, "partidos.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)

# ESPN type -> (own type, use in the pipeline)
TIPOS = {
    "Offside": ("fuera_de_juego", "regla11"),
    "Goal": ("gol", "regla11+deteccion"),
    "Goal - Header": ("gol", "regla11+deteccion"),
    "Goal - Free-kick": ("gol", "regla11+deteccion"),
    "Penalty - Scored": ("penalti", "calibracion+deteccion"),
    "Penalty - Missed": ("penalti", "calibracion+deteccion"),
    "Penalty - Saved": ("penalti", "calibracion+deteccion"),
    "Kickoff": ("saque_centro", "sincronizacion+calibracion"),
    "Start 2nd Half": ("saque_centro", "sincronizacion+calibracion"),
    "Start Extra Time": ("saque_centro", "sincronizacion+calibracion"),
    "Corner Awarded": ("saque_esquina", "calibracion+deteccion"),
    "Shot On Target": ("disparo", "calibracion+deteccion"),
    "Shot Off Target": ("disparo", "calibracion+deteccion"),
    "Shot Blocked": ("disparo", "deteccion"),
    "Foul": ("falta", "deteccion"),
    "Handball": ("falta", "deteccion"),
    "Halftime": ("descanso", "sincronizacion"),
    "End Regular Time": ("final", "sincronizacion"),
}
# Not useful for frame sampling (usually close-ups): kept, but flagged
DESCARTE = "descartar"

CAMPOS = ["partido", "espn_id", "parte", "seg_juego", "minuto", "wallclock_utc", "tipo", "tipo_espn",
          "equipo", "jugadores", "x", "y", "x2", "y2", "uso", "origen", "video", "video_s", "fotograma",
          "fps", "en_video", "sync_confianza", "texto"]


def fetch(gid):
    path = os.path.join(OUT, "raw", f"{gid}.json")
    if not os.path.exists(path):
        req = urllib.request.Request(URL.format(gid), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    with open(path) as f:
        return json.load(f)


def utc(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def add_video_time(rows, match):
    """Video second and frame of each event, using the half from partidos.json."""
    starts = {r["parte"]: utc(r["wallclock_utc"]) for r in rows
              if r["tipo"] == "saque_centro" and r["wallclock_utc"]}
    for r in rows:
        part = match["partes"].get(str(r["parte"]))
        if part is None or r["parte"] not in starts:
            r.update(video="", video_s="", fotograma="", fps="", en_video=0, sync_confianza="")
            continue
        if r["wallclock_utc"]:
            elapsed = (utc(r["wallclock_utc"]) - starts[r["parte"]]).total_seconds()
        else:  # no UTC time: game clock (minute precision)
            elapsed = r["seg_juego"] - (0 if r["parte"] == 1 else 2700)
        t = part["inicio_s"] + elapsed
        r.update(video=part["video"], video_s=round(t, 1), fotograma=int(round(t * match["fps"])),
                 fps=match["fps"], en_video=int(0 <= t <= part["duracion_video_s"]),
                 sync_confianza=part["confianza"] if r["wallclock_utc"] else "baja (solo minuto)")


def rows_for(match):
    partido, gid = match["partido"], match["espn_id"]
    data = fetch(gid)
    rows = []
    # Kick-offs and some offsides have no "play" in the commentary: they are completed from keyEvents
    # (which do have the UTC time) and from the text
    seen = {c["play"]["id"] for c in data.get("commentary", []) if c.get("play")}
    entries = list(data.get("commentary", []))
    entries += [{"time": k["clock"], "text": k.get("text", k["type"]["text"]), "play": k}
                for k in data.get("keyEvents", []) if k["id"] not in seen]
    for c in entries:
        play = c.get("play")
        if not play:
            if not c["text"].startswith("Offside, "):
                continue
            # No UTC time: game minute only
            team = c["text"].split(",")[1].split(".")[0].strip()
            minute = int(c["time"]["displayValue"].split("'")[0])
            play = {"type": {"text": "Offside"}, "team": {"displayName": team},
                    "period": {"number": 1 if minute <= 45 else 2}}
            c = {**c, "time": {"value": minute * 60 - 30, "displayValue": c["time"]["displayValue"]}}
        tipo_espn = play["type"]["text"]
        tipo, uso = TIPOS.get(tipo_espn, (tipo_espn.lower().replace(" ", "_"), DESCARTE))
        # ESPN sometimes gives a generic type ("Free Kick") to an offside or a shot: the text decides
        text = c["text"]
        if text.startswith("Offside, "):
            tipo, uso = TIPOS["Offside"]
        elif text.startswith("GOAL OVERTURNED BY VAR"):
            tipo, uso = "gol_anulado", "regla11"
        elif text.startswith("VAR Decision"):
            tipo, uso = "revision_var", "deteccion"
        elif text.startswith("Attempt") or "hits the bar" in text or "hits the" in text and "post" in text:
            tipo, uso = "disparo", TIPOS["Shot On Target"][1]
        pos = [play.get(k) or "" for k in ("fieldPositionX", "fieldPositionY", "fieldPosition2X", "fieldPosition2Y")]
        players = "; ".join(p["athlete"]["displayName"] for p in play.get("participants", []))
        if tipo == "fuera_de_juego":
            # For offsides the ESPN participant is the passer; the player caught offside only appears in the
            # text ("X is caught offside")
            caught = c["text"].split(". ", 1)[1].replace(" is caught offside.", "").strip()
            players = f"en fuera de juego: {caught}" + (f"; pase: {players}" if players else "")
        rows.append({
            "partido": partido, "espn_id": gid,
            "parte": play.get("period", {}).get("number", ""),
            "seg_juego": int(c["time"]["value"]), "minuto": c["time"]["displayValue"],
            "wallclock_utc": play.get("wallclock", ""), "tipo": tipo, "tipo_espn": tipo_espn,
            "equipo": play.get("team", {}).get("displayName", ""),
            "jugadores": players,
            "x": pos[0], "y": pos[1], "x2": pos[2], "y2": pos[3],
            "uso": uso, "origen": "espn" if play.get("wallclock") else "espn_sin_hora", "texto": c["text"],
        })
    rows.sort(key=lambda r: (r["parte"], r["seg_juego"]))

    # Inferred goal kicks: shot wide with no corner in the next 40 s
    inferred = []
    for i, r in enumerate(rows):
        if r["tipo_espn"] != "Shot Off Target":
            continue
        later = [n for n in rows[i + 1:] if n["parte"] == r["parte"] and n["seg_juego"] - r["seg_juego"] <= 40]
        if not any(n["tipo"] == "saque_esquina" for n in later):
            inferred.append({**r, "tipo": "saque_puerta", "tipo_espn": "", "uso": "calibracion",
                             "origen": "inferido", "x": "", "y": "", "x2": "", "y2": "",
                             "texto": f"Saque de puerta probable tras: {r['texto']}"})
    rows += inferred
    rows.sort(key=lambda r: (r["parte"], r["seg_juego"], r["origen"]))
    add_video_time(rows, match)
    return rows


def main():
    rows = []
    for match in CONFIG["partidos"]:
        rows += rows_for(match)
    path = os.path.join(OUT, "eventos.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} eventos en {path}")
    for match in CONFIG["partidos"]:
        mine = [r for r in rows if r["partido"] == match["partido"]]
        counts = {}
        for r in mine:
            if r["en_video"]:
                counts[r["tipo"]] = counts.get(r["tipo"], 0) + 1
        print(match["partido"], f"{sum(r['en_video'] for r in mine)}/{len(mine)} en el vídeo",
              dict(sorted(counts.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    main()
