"""Law 11: offside position in the pass frame.

An attacker is in an offside position if any part they can score with (head, torso, legs and feet;
not the arms) is in the opponents' half and nearer to the opponents' goal line than both the ball
and the second-last defender.
"""
import numpy as np

ARM_JOINTS = {"left_elbow", "right_elbow", "left_wrist", "right_wrist"}
HEAD_JOINTS = {"nose", "left_eye", "right_eye", "left_ear", "right_ear"}
TORSO_JOINTS = {"left_shoulder", "right_shoulder", "left_hip", "right_hip"}
MIN_JOINT_CONF = 0.3
MIN_HEAD_CONF = 0.5  # the head is small and the model confuses it with another player's
MAX_HEAD_OFFSET_M = 0.5  # maximum horizontal distance from the head to the torso centre
MAX_LIMB_OFFSET_M = 1.0  # ... and from hips, knees and ankles (a long stride fits)
MAX_HEAD_ABOVE_NOSE_M = 0.3
BOX_SLACK = 0.15  # slack around the detector box for 2D points
# Typical height of each joint for a 1.80 m player standing up (2D check)
STANDARD_HEIGHT_M = {"nose": 1.66, "left_eye": 1.69, "right_eye": 1.69, "left_ear": 1.67, "right_ear": 1.67,
                     "left_shoulder": 1.47, "right_shoulder": 1.47, "left_hip": 0.96, "right_hip": 0.96,
                     "left_knee": 0.50, "right_knee": 0.50, "left_ankle": 0.09, "right_ankle": 0.09}


def clean_joints(joints, joint_names, kp2d=None, box=None):
    """Removes (sets confidence to 0) joints that do not fit the rest of the player.

    A single badly estimated joint decides the line if it ends up "in front" (e.g. an ear 0.8 m away
    from the head). Arms are ignored (they do not count for offside). Discarded:
      - joints whose 2D point falls outside the player's box;
      - the head with low confidence, more than 0.5 m from the torso or far above the nose;
      - hips, knees and ankles more than 1 m from the torso.

    Returns:
        (joints, [name: reason]).
    """
    joints = np.array(joints, float)
    names = list(joint_names)
    J = {n: i for i, n in enumerate(names)}
    valid = joints[:, 3] >= MIN_JOINT_CONF
    reasons = {}
    if kp2d is not None and box is not None:
        x1, y1, x2, y2 = box
        mx, my = BOX_SLACK * (x2 - x1), BOX_SLACK * (y2 - y1)
        for j, (u, v) in enumerate(np.asarray(kp2d)[:, :2]):
            if valid[j] and not (x1 - mx <= u <= x2 + mx and y1 - my <= v <= y2 + my):
                reasons[j] = "fuera de su caja en la imagen"
    torso = [J[n] for n in TORSO_JOINTS if valid[J[n]] and J[n] not in reasons]
    if len(torso) < 2:
        torso = [j for j, n in enumerate(names) if valid[j] and j not in reasons and n not in ARM_JOINTS]
    center = np.median(joints[torso, :2], axis=0) if len(torso) >= 2 else None
    nose = J.get("nose")
    nose_z = joints[nose, 2] if nose is not None and valid[nose] and nose not in reasons else None
    for j, n in enumerate(names):
        if not valid[j] or j in reasons or n in ARM_JOINTS:
            continue
        offset = None if center is None else float(np.linalg.norm(joints[j, :2] - center))
        if n in HEAD_JOINTS:
            if joints[j, 3] < MIN_HEAD_CONF:
                reasons[j] = f"confianza {joints[j, 3]:.2f}"
            elif offset is not None and offset > MAX_HEAD_OFFSET_M:
                reasons[j] = f"a {offset:.1f} m del tronco"
            elif nose_z is not None and n != "nose" and joints[j, 2] - nose_z > MAX_HEAD_ABOVE_NOSE_M:
                reasons[j] = f"{joints[j, 2] - nose_z:.1f} m por encima de la nariz"
        elif offset is not None and offset > MAX_LIMB_OFFSET_M:
            reasons[j] = f"a {offset:.1f} m del tronco"
    for j in reasons:
        joints[j, 3] = 0.0
    return joints, [f"{names[j]}: {r}" for j, r in sorted(reasons.items())]


def parts_on_ground_2d(cam, kp2d, joints, joint_names, box_bottom_uv):
    """Ground point under each valid body part (arms excluded) using only the image.

    The ray of the 2D point is cut at the typical height of that joint (STANDARD_HEIGHT_M). Without a
    pose, the bottom of the box is used.

    Returns:
        [(name, (x, y))].
    """
    parts = []
    if kp2d is not None and joints is not None:
        for j, name in enumerate(joint_names):
            if name in ARM_JOINTS or joints[j, 3] < MIN_JOINT_CONF:
                continue
            parts.append((name, cam.to_ground([kp2d[j, :2]], height=STANDARD_HEIGHT_M[name])[0][:2]))
    if not parts:
        parts.append(("box_bottom", cam.to_ground([box_bottom_uv])[0][:2]))
    return parts


def check_2d(attacker_parts, defender_parts, ball_xy, direction, result):
    """Second decision without the 3D pose.

    Each body part (head, torso, legs) is taken to the grass from its 2D point assuming the typical
    height of that joint, and the most advanced part of each player is compared. The 3D method assumes
    the player lies in a vertical plane facing the camera; this one assumes a standing posture. They
    fail differently, so a disagreement means the decision must be reviewed.
    """
    d = direction
    a_name, a_xy = max(attacker_parts, key=lambda f: d * f[1][0])
    d_name, d_xy = max(defender_parts, key=lambda f: d * f[1][0])
    line = d * d_xy[0]
    if ball_xy is not None and d * ball_xy[0] > line:
        line = d * ball_xy[0]
    margin = d * a_xy[0] - line
    unc = result["uncertainty_m"]
    margin_3d = result["margin_m"]
    agrees = (margin > 0) == (margin_3d > 0) or abs(margin) <= unc or abs(margin_3d) <= unc
    return {"margin_m": round(float(margin), 3), "agrees": bool(agrees),
            "difference_m": round(float(margin - margin_3d), 3),
            "attacker_joint": a_name, "attacker_point": [round(float(v), 3) for v in a_xy],
            "defender_joint": d_name, "defender_point": [round(float(v), 3) for v in d_xy],
            "line_x": round(float(d * line), 3),
            "method": "Partes válidas 2D llevadas al césped a su altura típica (sin pose 3D)"}


def front_point(player, direction, joint_names):
    """Most advanced valid body part in the attacking direction: (value, name, 3D point)."""
    best = None
    joints = player.get("joints")
    if joints is not None:
        for j, name in enumerate(joint_names):
            x, y, z, c = joints[j]
            if name in ARM_JOINTS or c < MIN_JOINT_CONF or not np.isfinite(x):
                continue
            if best is None or direction * x > best[0]:
                best = (direction * x, name, [x, y, z])
    if best is None:
        # No pose: ground contact point
        gx, gy = player["ground"]
        best = (direction * gx, "ground", [gx, gy, 0.0])
    return best


def evaluate_selected(players, ball_xy, joint_names, attack_direction, attacker_id, defender_id, uncertainty_m=0.3):
    """Law 11 with the attacker and second-last defender chosen by the user in the pass frame.

    Args:
        players: [{id, role, team, ground: (x, y), joints: (J, 4) or None}].
        attack_direction: +1 if the attacker attacks towards +X.

    A warning is added if other visible defenders would act as the second-last one.
    """
    by_id = {p["id"]: p for p in players}
    if attacker_id not in by_id or defender_id not in by_id:
        return {"status": "not_evaluable", "warnings": ["El atacante o el defensor elegido no está en el fotograma"]}
    if attacker_id == defender_id:
        return {"status": "not_evaluable", "warnings": ["El atacante y el defensor son el mismo jugador"]}
    attacker, defender = by_id[attacker_id], by_id[defender_id]
    d = attack_direction
    warnings = []
    if attacker.get("team") is not None and attacker.get("team") == defender.get("team"):
        warnings.append("Por el color de la camiseta, atacante y defensor parecen del mismo equipo")

    a_value, a_joint, a_point = front_point(attacker, d, joint_names)
    d_value, d_joint, d_point = front_point(defender, d, joint_names)
    line_value, line_source = d_value, "second_last_defender"
    ball_value = d * ball_xy[0] if ball_xy is not None else None
    if ball_value is None:
        warnings.append("Balón no detectado en el fotograma del pase: la línea solo depende del defensor")
    elif ball_value > line_value:
        line_value, line_source = ball_value, "ball"

    # Other visible defenders closer to their goal than the chosen one: with one, it is the last
    # defender (usually the goalkeeper); with two or more, the chosen one is not the second-last
    defending_team = defender.get("team")
    others = [p for p in players if p["id"] not in (attacker_id, defender_id) and p["role"] != "referee"
              and p.get("team") is not None and p.get("team") == defending_team]
    deeper = [p["id"] for p in others if front_point(p, d, joint_names)[0] > d_value + 0.05]
    if len(deeper) >= 2:
        warnings.append(f"Hay {len(deeper)} defensores más cerca de su portería que el elegido "
                        f"({', '.join(map(str, deeper))}): el penúltimo sería otro")
    elif not deeper:
        warnings.append("No se ve a ningún defensor por detrás del elegido: se supone que el último (el portero) "
                        "está fuera del plano")
    if attacker.get("joints") is None:
        warnings.append(f"El atacante {attacker_id} no tiene pose: se usa su punto de apoyo")
    if defender.get("joints") is None:
        warnings.append(f"El defensor {defender_id} no tiene pose: se usa su punto de apoyo")

    margin = a_value - line_value
    in_opponent_half = a_value > 0
    if margin > 0 and not in_opponent_half:
        warnings.append("El atacante está en su propio campo: no puede estar en fuera de juego")
    status = "offside" if margin > 0 and in_opponent_half else "onside"
    within = abs(margin) <= uncertainty_m
    if within:
        warnings.append("El margen es menor que la incertidumbre: decisión no concluyente")
    return {
        "status": status, "within_uncertainty": bool(within), "margin_m": round(margin, 3),
        "uncertainty_m": round(uncertainty_m, 3), "attack_direction": d,
        "attacking_team": attacker.get("team"), "passer": None,
        "line": {"x": round(d * line_value, 3), "source": line_source},
        "ball_x": round(ball_xy[0], 3) if ball_xy is not None else None,
        "attacker": {"id": attacker_id, "joint": a_joint, "point": [round(v, 3) for v in a_point]},
        "defender": {"id": defender_id, "joint": d_joint, "point": [round(v, 3) for v in d_point]},
        "attackers": [{"id": attacker_id, "joint": a_joint, "x": round(d * a_value, 3), "margin_m": round(margin, 3),
                       "offside_position": status == "offside", "point": [round(v, 3) for v in a_point],
                       "has_pose": attacker.get("joints") is not None}],
        "selection": "user",
        "method": "Parte válida más adelantada (sin brazos) del atacante elegido frente a max(defensor elegido, balón)",
        "warnings": warnings,
    }


def evaluate(players, ball_xy, joint_names, attack_direction=None, passer=None, attacking_team=None,
             uncertainty_m=0.3):
    """Law 11 for every attacker in the pass frame.

    Args:
        players: [{id, role, team, ground: (x, y), joints: (J, 4) or None}] in the pass frame.

    The attacking team is the passer's; if the team is known but the passer has lost its track in this
    frame (id switch), attacking_team is enough.
    """
    warnings = []
    field = [p for p in players if p["role"] != "referee" and p.get("team") is not None]
    by_track = {p["id"]: p for p in field}
    if passer in by_track:
        attacking = by_track[passer]["team"]
    elif attacking_team is not None:
        attacking = attacking_team
    else:
        return {"status": "not_evaluable", "warnings": warnings + ["No se ha identificado al pasador"]}
    attackers = [p for p in field if p["team"] == attacking and p["role"] == "player" and p["id"] != passer]
    defenders = [p for p in field if p["team"] != attacking]
    if not attackers or not defenders:
        return {"status": "not_evaluable", "passer": passer,
                "warnings": warnings + ["Faltan atacantes o defensores en el plano"]}

    if attack_direction is None:
        diff = np.mean([p["ground"][0] for p in defenders]) - np.mean([p["ground"][0] for p in attackers])
        attack_direction = 1 if diff >= 0 else -1
        warnings.append(f"Dirección de ataque deducida de la posición de los equipos ({'+X' if attack_direction > 0 else '-X'})")

    defender_front = sorted(((front_point(p, attack_direction, joint_names), p) for p in defenders),
                            key=lambda fp: -fp[0][0])
    has_keeper = any(p["role"] == "goalkeeper" for _, p in defender_front)
    if has_keeper and len(defender_front) >= 2:
        second = defender_front[1]
    else:
        # The goalkeeper is often out of shot: assume it is the last defender
        second = defender_front[0]
        warnings.append("El portero defensor no está en el plano: se supone que es el último defensor")
    line_value, line_source = second[0][0], "second_last_defender"
    ball_value = attack_direction * ball_xy[0] if ball_xy is not None else None
    if ball_value is None:
        warnings.append("Balón no detectado en el fotograma del pase: la línea solo depende de los defensores")
    elif ball_value > line_value:
        line_value, line_source = ball_value, "ball"

    results = []
    for p in attackers:
        value, joint, point = front_point(p, attack_direction, joint_names)
        margin = value - line_value
        results.append({"id": p["id"], "joint": joint, "x": round(attack_direction * value, 3),
                        "margin_m": round(margin, 3), "offside_position": bool(margin > 0 and value > 0),
                        "point": [round(v, 3) for v in point], "has_pose": p.get("joints") is not None})
    worst = max(results, key=lambda r: r["margin_m"])
    if not worst["has_pose"]:
        warnings.append(f"El atacante {worst['id']} no tiene pose: se usa su punto de apoyo")
    status = "offside" if worst["offside_position"] else "onside"
    within = abs(worst["margin_m"]) <= uncertainty_m
    if within:
        warnings.append("El margen es menor que la incertidumbre: decisión no concluyente")
    (_, d_joint, d_point), d_player = second
    return {
        "status": status, "within_uncertainty": bool(within), "margin_m": worst["margin_m"],
        "uncertainty_m": round(uncertainty_m, 3), "attack_direction": attack_direction,
        "attacking_team": attacking, "passer": passer,
        "line": {"x": round(attack_direction * line_value, 3), "source": line_source},
        "ball_x": round(ball_xy[0], 3) if ball_xy is not None else None,
        "attacker": {"id": worst["id"], "joint": worst["joint"], "point": worst["point"]},
        "defender": {"id": d_player["id"], "joint": d_joint, "point": [round(v, 3) for v in d_point]},
        "attackers": results,
        "method": "Parte válida más adelantada (sin brazos) frente a max(penúltimo defensor, balón)",
        "warnings": warnings,
    }
