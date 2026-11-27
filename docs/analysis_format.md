# `offside-analysis` format (version 1)

JSON written by the Python pipeline (`offside_inference/export.py`) and read by the Qt viewer
(`app/src/analysisdata.cpp`). Pitch coordinates are in metres: X along the pitch, Y across, Z up,
origin at the centre spot (goals at X = ±52.5).

```jsonc
{
  "format": "offside-analysis", "version": 1,
  "source": {"type": "synthetic"},              // or "pipeline" (then also detector, pose, calibration...)
  "match": {"id": "...", "name": "Text shown in the header"},
  "sequence": {"id": "...", "fps": 25, "frame_count": 250, "video": null},
  "pitch": {"length": 105, "width": 68},
  "skeleton": {
    "name": "halpe26",
    "joints": ["nose", "left_eye", ...],        // joint order in every pose
    "joint_radius": [0.022, ...],               // m; 0 = not drawn
    "offside_valid": [true, ..., false, ...],   // false for elbows and wrists
    "bones": [[15, 13, 0.05], ...],             // [joint a, joint b, radius in m]
    "head": {"joints": [3, 4], "radius": 0.115} // head sphere between the ears
  },
  "teams": [{"id": "home", "name": "Local", "color": "#e63946",
             "goalkeeper_color": "#ffd166", "attack_direction": 1}, ...],
  "entities": [{"id": 9, "team": "home", "role": "player", "number": "9"}, ...],
  "frames": [{
    "frame": 120, "time": 4.8,
    "players": [
      {"id": 9, "position": [32.1, 0.2], "confidence": 0.93,
       "coord_type": "pose3d_estimated", "pose": [[x, y, z, confidence], ...]},
      {"id": 109, "position": [4.0, 2.0], "confidence": 0.55,
       "coord_type": "ground_xy", "pose": null}
    ],
    "ball": {"position": [18.4, -5.1, 0.11], "confidence": 0.9}   // or null if not visible
  }],
  "events": [{
    "id": "pase_1", "type": "pass", "frame": 120, "time": 4.8,
    "passer": 8, "receiver": 9, "attacking_team": "home",
    "offside": {
      "status": "offside",                      // offside | onside | not_evaluable
      "margin_m": 0.22, "uncertainty_m": 0.08, "within_uncertainty": false,
      "line": {"x": 32.04, "source": "second_last_defender"},   // or "ball"
      "ball_x": 18.4,
      "attacker": {"id": 9, "joint": "right_shoulder", "point": [32.26, -0.1, 1.42]},
      "defender": {"id": 104, "joint": "right_heel", "point": [32.04, -4.1, 0.03]},
      "attackers": [{"id": 9, "joint": "...", "x": 32.26, "margin_m": 0.22, "offside_position": true}],
      "method": "...", "warnings": ["..."]
    }
  }]
}
```

- A joint that was not estimated in a frame may be `null` inside `pose`.
- Files written by the pipeline use the COCO-17 skeleton and also store each player's detector box
  and 2D pose, so the same player can be recognised when an analysis is repeated.
- Human-readable texts inside the file (`method`, `warnings`, team names) are in Spanish.
