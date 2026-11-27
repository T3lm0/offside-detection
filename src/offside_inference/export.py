"""Writes the analysis in the offside-analysis format read by the 3D viewer."""
import json

import numpy as np

from .offside import ARM_JOINTS
from .pose import COCO_JOINTS

J = {n: i for i, n in enumerate(COCO_JOINTS)}
JOINT_RADIUS = {"nose": 0.025, "left_eye": 0.015, "right_eye": 0.015, "left_ear": 0.02, "right_ear": 0.02,
                "left_shoulder": 0.06, "right_shoulder": 0.06, "left_elbow": 0.045, "right_elbow": 0.045,
                "left_wrist": 0.038, "right_wrist": 0.038, "left_hip": 0.065, "right_hip": 0.065,
                "left_knee": 0.058, "right_knee": 0.058, "left_ankle": 0.048, "right_ankle": 0.048}
BONES = [("left_shoulder", "right_shoulder", 0.06), ("left_hip", "right_hip", 0.065),
         ("left_shoulder", "left_hip", 0.085), ("right_shoulder", "right_hip", 0.085),
         ("left_shoulder", "left_elbow", 0.045), ("left_elbow", "left_wrist", 0.037),
         ("right_shoulder", "right_elbow", 0.045), ("right_elbow", "right_wrist", 0.037),
         ("left_hip", "left_knee", 0.065), ("left_knee", "left_ankle", 0.05),
         ("right_hip", "right_knee", 0.065), ("right_knee", "right_ankle", 0.05)]


def hex_color(bgr):
    b, g, r = bgr
    return f"#{r:02x}{g:02x}{b:02x}"


def skeleton():
    return {
        "name": "coco17",
        "joints": COCO_JOINTS,
        "joint_radius": [JOINT_RADIUS[n] for n in COCO_JOINTS],
        "offside_valid": [n not in ARM_JOINTS for n in COCO_JOINTS],
        "bones": [[J[a], J[b], r] for a, b, r in BONES],
        "head": {"joints": [J["left_ear"], J["right_ear"]], "radius": 0.115},
    }


def write_analysis(path, *, title, source_info, fps, frames, entities, team_colors, keeper_colors,
                   attack_direction, events, warnings):
    """Writes the analysis file.

    Args:
        frames: [{frame, time, players: [{id, ground, conf, joints}], ball: (x, y) or None}].
    """
    teams = []
    for i in (0, 1):
        direction = 0 if attack_direction is None else (attack_direction if i == events_attacking(events) else -attack_direction)
        teams.append({"id": f"team{i}", "name": f"Equipo {'AB'[i]}", "color": hex_color(team_colors[i]),
                      "goalkeeper_color": hex_color(keeper_colors[i]), "attack_direction": direction})
    teams.append({"id": "officials", "name": "Árbitros", "color": "#202020", "goalkeeper_color": "#202020",
                  "attack_direction": 0})

    out_frames = []
    for f in frames:
        players = []
        for p in f["players"]:
            entry = {"id": p["id"], "position": [round(float(p["ground"][0]), 3), round(float(p["ground"][1]), 3)],
                     "confidence": round(float(p["conf"]), 2)}
            if p.get("joints") is not None:
                entry["coord_type"] = "pose3d_estimated"
                entry["pose"] = [None if c <= 0 or not np.isfinite(x) else
                                 [round(float(x), 3), round(float(y), 3), round(float(z), 3), round(float(c), 2)]
                                 for x, y, z, c in p["joints"]]
            else:
                entry.update({"coord_type": "ground_xy", "pose": None})
            # Detector box and the 2D pose the 3D one comes from (video pixels), to review it and to
            # recognise the same player if the analysis is repeated with other models
            if p.get("box") is not None:
                entry["box"] = [round(float(v), 1) for v in p["box"]]
            if p.get("kp2d") is not None:
                entry["pose2d"] = [[round(float(u), 1), round(float(v), 1), round(float(c), 2)] for u, v, c in p["kp2d"]]
            players.append(entry)
        ball = None
        if f.get("ball") is not None:
            bx, by, bc = f["ball"]
            ball = {"position": [round(float(bx), 3), round(float(by), 3), 0.11], "confidence": round(float(bc), 2)}
        out_frames.append({"frame": f["frame"], "time": round(f["time"], 3), "players": players, "ball": ball})

    data = {
        "format": "offside-analysis", "version": 1,
        "source": dict(type="pipeline", **source_info),
        "match": {"id": source_info.get("input", ""), "name": title},
        "sequence": {"id": title, "fps": fps, "frame_count": len(frames), "video": source_info.get("input")},
        "pitch": {"length": 105.0, "width": 68.0},
        "coordinate_system": {"units": "m", "origin": "centro del campo", "x": "a lo largo del campo",
                              "y": "a lo ancho", "z": "vertical"},
        "skeleton": skeleton(),
        "teams": teams,
        "entities": entities,
        "frames": out_frames,
        "events": events,
        "warnings": warnings,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))


def events_attacking(events):
    for e in events:
        team = e.get("attacking_team")
        if team is not None:
            return int(team.replace("team", ""))
    return 0
