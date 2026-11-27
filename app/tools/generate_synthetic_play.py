#!/usr/bin/env python3
"""Generates a synthetic play in the "offside-analysis" format read by the 3D viewer.

Used to test the C++ application without the vision models: players follow hand-defined
trajectories and their pose is synthesised with a simple running cycle. The offside decision is
computed from those poses with the same rule as the real pipeline: the attacker's most advanced
valid part (arms excluded) against the second-last defender and the ball, in the pass frame.

Usage:
    python3 generate_synthetic_play.py                      # offside by 22 cm
    python3 generate_synthetic_play.py --margin -0.15 -o ../sample_data/jugada_legal.json
"""
import argparse
import json
import math
import os

import numpy as np

FPS = 25
DURATION = 10.0
PASS_TIME = 4.8
RECEIVE_TIME = 7.0
BALL_RADIUS = 0.11
UNCERTAINTY_M = 0.08
PITCH_LENGTH, PITCH_WIDTH = 105.0, 68.0

# Halpe-26 skeleton: COCO-17 + head, neck, pelvis and feet (toes and heels)
JOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
    "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
    "head", "neck", "hip",
    "left_big_toe", "right_big_toe", "left_small_toe", "right_small_toe", "left_heel", "right_heel",
]
J = {name: i for i, name in enumerate(JOINTS)}
# Law 11: the arm (up to the armpit) does not count for offside
ARM_JOINTS = {"left_elbow", "right_elbow", "left_wrist", "right_wrist"}
VALID = np.array([name not in ARM_JOINTS for name in JOINTS])

JOINT_RADIUS = {
    "nose": 0.022, "left_eye": 0.016, "right_eye": 0.016, "left_ear": 0.02, "right_ear": 0.02,
    "left_shoulder": 0.06, "right_shoulder": 0.06, "left_elbow": 0.045, "right_elbow": 0.045,
    "left_wrist": 0.038, "right_wrist": 0.038, "left_hip": 0.065, "right_hip": 0.065,
    "left_knee": 0.058, "right_knee": 0.058, "left_ankle": 0.045, "right_ankle": 0.045,
    "head": 0.0, "neck": 0.055, "hip": 0.07,
    "left_big_toe": 0.03, "right_big_toe": 0.03, "left_small_toe": 0.025, "right_small_toe": 0.025,
    "left_heel": 0.032, "right_heel": 0.032,
}
BONES = [
    ("left_ankle", "left_knee", 0.05), ("left_knee", "left_hip", 0.065), ("left_hip", "hip", 0.06),
    ("right_ankle", "right_knee", 0.05), ("right_knee", "right_hip", 0.065), ("right_hip", "hip", 0.06),
    ("hip", "neck", 0.12), ("neck", "head", 0.045),
    ("neck", "left_shoulder", 0.055), ("left_shoulder", "left_elbow", 0.045), ("left_elbow", "left_wrist", 0.037),
    ("neck", "right_shoulder", 0.055), ("right_shoulder", "right_elbow", 0.045), ("right_elbow", "right_wrist", 0.037),
    ("left_ankle", "left_heel", 0.03), ("left_heel", "left_big_toe", 0.028), ("left_heel", "left_small_toe", 0.025),
    ("left_big_toe", "left_small_toe", 0.022), ("left_ankle", "left_big_toe", 0.03),
    ("right_ankle", "right_heel", 0.03), ("right_heel", "right_big_toe", 0.028), ("right_heel", "right_small_toe", 0.025),
    ("right_big_toe", "right_small_toe", 0.022), ("right_ankle", "right_big_toe", 0.03),
]

TEAMS = [
    {"id": "home", "name": "Local", "color": "#e63946", "goalkeeper_color": "#ffd166", "attack_direction": 1},
    {"id": "away", "name": "Visitante", "color": "#3a86ff", "goalkeeper_color": "#06d6a0", "attack_direction": -1},
    {"id": "officials", "name": "Árbitros", "color": "#2b2d42", "goalkeeper_color": "#2b2d42", "attack_direction": 0},
]

# (id, team, role, shirt number, style, [(t, x, y), ...]); the home team attacks towards +X
ENTITIES = [
    (1, "home", "goalkeeper", "1", "keeper", [(0, -46, 0), (5, -44, 1.5), (10, -42, 2)]),
    (2, "home", "player", "2", "run", [(0, 4, -26), (4.8, 11, -27), (10, 21, -26)]),
    (3, "home", "player", "3", "run", [(0, 2, 24), (4.8, 8, 26), (10, 15, 25)]),
    (4, "home", "player", "4", "run", [(0, -12, -8), (4.8, -6, -7), (10, 0, -6)]),
    (5, "home", "player", "5", "run", [(0, -12, 8), (4.8, -6, 7), (10, 0, 6)]),
    (6, "home", "player", "6", "run", [(0, 6, 2), (4.8, 10, 1), (10, 15, 0)]),
    (8, "home", "player", "8", "run", [(0, 12.5, -6.5), (2.5, 15.5, -5.8), (4.8, 18, -5), (5.6, 18.8, -4.6), (10, 24, -2)]),
    (10, "home", "player", "10", "run", [(0, 21, 8), (4.8, 28.5, 9), (7, 35, 7), (10, 39, 6)]),
    (7, "home", "player", "7", "run", [(0, 26, -22), (4.8, 29.5, -20), (7, 35, -17), (10, 39, -14)]),
    (11, "home", "player", "11", "run", [(0, 28, 20), (4.8, 30.0, 18), (7, 35, 15), (10, 38, 13)]),
    (9, "home", "player", "9", "run", [(0, 30.5, -1), (2.4, 31.6, -2.5), (4.0, 31.9, -1.2), (4.8, 32.6, 0.0),
                                       (5.8, 37.0, 2.5), (7.0, 43.5, 5.0), (8.2, 47.5, 5.8), (10, 49.0, 5.0)]),
    (101, "away", "goalkeeper", "1", "keeper", [(0, 49.5, 0), (4.8, 48.5, 0.5), (7, 46.5, 3.5), (10, 46, 4.5)]),
    (102, "away", "player", "2", "run", [(0, 33.2, 19), (4.8, 31.6, 18.5), (6, 33.5, 17), (10, 40, 12)]),
    (103, "away", "player", "3", "run", [(0, 33.0, -19), (4.8, 31.8, -18.5), (6, 33.5, -16), (10, 40, -10)]),
    (104, "away", "player", "4", "run", [(0, 33.8, -5), (4.8, 32.3, -4), (5.6, 33.8, -2), (7, 40.5, 2.5), (10, 46, 4)]),
    (105, "away", "player", "5", "run", [(0, 33.3, 6), (4.8, 31.7, 5), (6, 34, 5), (10, 42, 6)]),
    (106, "away", "player", "6", "run", [(0, 24, 0), (4.8, 22.5, -1), (10, 28, 0)]),
    (108, "away", "player", "8", "run", [(0, 22, -10), (4.8, 20.5, -8.5), (10, 26, -6)]),
    (110, "away", "player", "10", "run", [(0, 23, 10), (4.8, 21.5, 9), (10, 27, 8)]),
    (107, "away", "player", "7", "run", [(0, 12, -18), (4.8, 14, -17), (10, 19, -14)]),
    (111, "away", "player", "11", "run", [(0, 12, 18), (4.8, 14, 17), (10, 20, 14)]),
    (109, "away", "player", "9", "run", [(0, 2, 0), (4.8, 4, 2), (10, 7, 3)]),
    (201, "officials", "referee", "ÁRB", "run", [(0, 8, 7), (4.8, 14, 5), (10, 25, 4)]),
    (202, "officials", "referee", "AA1", "run", [(0, 33.8, -34.8), (4.8, 32.3, -34.8), (7, 40, -34.8), (10, 45, -34.8)]),
    (203, "officials", "referee", "AA2", "run", [(0, -18, 34.8), (10, -14, 34.8)]),
]
PASSER, RECEIVER = 8, 9
# This player only has a ground position at the start (no estimated 3D pose)
GROUND_ONLY = {109: (0, 70)}


def hermite_track(keys, times):
    """Interpolates the (t, x, y) keyframes with cubic Hermite splines."""
    kt = np.array([k[0] for k in keys], float)
    kp = np.array([k[1:] for k in keys], float)
    if len(kt) == 1:
        return np.repeat(kp, len(times), axis=0)
    tangents = np.zeros_like(kp)
    for i in range(len(kt)):
        a, b = max(i - 1, 0), min(i + 1, len(kt) - 1)
        tangents[i] = (kp[b] - kp[a]) / (kt[b] - kt[a])
    out = np.zeros((len(times), 2))
    for n, t in enumerate(times):
        i = int(np.clip(np.searchsorted(kt, t) - 1, 0, len(kt) - 2))
        h = kt[i + 1] - kt[i]
        u = np.clip((t - kt[i]) / h, 0, 1)
        h00, h10 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u
        h01, h11 = -2 * u**3 + 3 * u**2, u**3 - u**2
        out[n] = h00 * kp[i] + h10 * h * tangents[i] + h01 * kp[i + 1] + h11 * h * tangents[i + 1]
    return out


def smoothstep(u):
    u = np.clip(u, 0, 1)
    return u * u * (3 - 2 * u)


def synth_pose(root, heading, phase, speed, height, style, kick=None):
    """Returns the 26 joints (x, y, z) in metres for one instant."""
    H = height
    v = speed
    # Local axes: forward (f), left (l), up (z)
    f = np.array([math.cos(heading), math.sin(heading)])
    l = np.array([-math.sin(heading), math.cos(heading)])

    amp_hip = min(0.12 + 0.075 * v, 0.75)
    amp_knee = min(0.1 + 0.2 * v, 1.5)
    amp_arm = min(0.1 + 0.07 * v, 0.7)
    knee_base = 0.08 + 0.02 * v
    elbow = min(0.25 + 0.12 * v, 1.5)
    lean = min(0.035 * v, 0.28)
    abduction = 0.12
    if style == "keeper":
        knee_base, lean, abduction, elbow = 0.45, 0.22, 0.45, 0.7

    pts = {}  # local coordinates (forward, left, up) relative to the pelvis centre
    thigh, shin = 0.45 * H, 0.44 * H
    for side, sgn, ph in (("left", 1, phase), ("right", -1, phase + math.pi)):
        a = amp_hip * math.sin(ph)
        k = knee_base + amp_knee * max(0.0, math.cos(ph)) ** 1.5
        if style == "keeper":
            a = 0.28
        if kick is not None and side == "right":
            a, k = kick
        elif kick is not None:
            a, k = 0.15, 0.25
        hip = np.array([0.0, sgn * 0.10 * H, 0.0])
        knee = hip + np.array([math.sin(a), 0, -math.cos(a)]) * thigh
        shin_a = a - k
        ankle = knee + np.array([math.sin(shin_a), 0, -math.cos(shin_a)]) * shin
        q = 0.6 * shin_a if shin_a < 0 else 0.3 * shin_a  # foot pitch

        def foot(fwd, lat, up):
            return ankle + np.array([fwd * math.cos(q) - up * math.sin(q), sgn * lat, fwd * math.sin(q) + up * math.cos(q)])

        pts[f"{side}_hip"], pts[f"{side}_knee"], pts[f"{side}_ankle"] = hip, knee, ankle
        pts[f"{side}_heel"] = foot(-0.06 * H, 0.0, -0.055 * H)
        pts[f"{side}_big_toe"] = foot(0.17 * H, -0.01 * H, -0.065 * H)
        pts[f"{side}_small_toe"] = foot(0.14 * H, 0.04 * H, -0.065 * H)

    upper = {
        "neck": (0.0, 0.0, 0.55 * H), "head": (0.0, 0.0, 0.82 * H),
        "nose": (0.10 * H, 0.0, 0.69 * H), "left_eye": (0.085 * H, 0.033 * H, 0.72 * H),
        "right_eye": (0.085 * H, -0.033 * H, 0.72 * H), "left_ear": (0.0, 0.075 * H, 0.70 * H),
        "right_ear": (0.0, -0.075 * H, 0.70 * H),
    }
    for name, p in upper.items():
        pts[name] = np.array(p)
    for side, sgn, ph in (("left", 1, phase + math.pi), ("right", -1, phase)):
        b = amp_arm * math.sin(ph)
        ab = abduction if kick is None else 0.55
        shoulder = np.array([0.0, sgn * 0.19 * H, 0.51 * H])
        elbow_p = shoulder + np.array([math.sin(b) * math.cos(ab), sgn * math.sin(ab), -math.cos(b) * math.cos(ab)]) * 0.30 * H
        fa = b + elbow
        wrist = elbow_p + np.array([math.sin(fa) * math.cos(ab), sgn * math.sin(ab) * 0.6, -math.cos(fa) * math.cos(ab)]) * 0.27 * H
        pts[f"{side}_shoulder"], pts[f"{side}_elbow"], pts[f"{side}_wrist"] = shoulder, elbow_p, wrist
    pts["hip"] = np.zeros(3)

    # Forward lean of the torso (everything above the pelvis)
    for name in list(upper) + [f"{s}_{p}" for s in ("left", "right") for p in ("shoulder", "elbow", "wrist")]:
        fwd, lat, up = pts[name]
        pts[name] = np.array([fwd * math.cos(lean) + up * math.sin(lean), lat, -fwd * math.sin(lean) + up * math.cos(lean)])

    local = np.array([pts[n] for n in JOINTS])
    # The lowest foot touches the grass; running has a short flight phase
    foot_idx = [J[n] for n in ("left_heel", "right_heel", "left_big_toe", "right_big_toe", "left_small_toe", "right_small_toe")]
    flight = 0.05 * min(1.0, v / 6.0) * max(0.0, math.sin(2 * phase)) if style != "keeper" else 0.0
    lift = -local[foot_idx, 2].min() + 0.02 + flight
    world = np.zeros((len(JOINTS), 3))
    world[:, :2] = root + np.outer(local[:, 0], f) + np.outer(local[:, 1], l)
    world[:, 2] = local[:, 2] + lift
    return world


def angle_lerp(a, b, t):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--margin", type=float, default=0.22,
                        help="Margen deseado del receptor sobre la línea en metros (>0 fuera de juego)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("-o", "--output", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                             "..", "sample_data", "jugada_sintetica.json"))
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)

    n_frames = int(DURATION * FPS)
    times = np.arange(n_frames) / FPS
    pass_frame = int(round(PASS_TIME * FPS))
    team_of = {e[0]: e[1] for e in ENTITIES}
    tracks = {e[0]: hermite_track(e[5], times) for e in ENTITIES}

    # Ball before the pass: at the passer's feet (needed to orient the players)
    passer_track = tracks[PASSER]
    ball = np.full((n_frames, 3), np.nan)
    pass_dir = passer_track[pass_frame + 1] - passer_track[pass_frame - 1]
    pass_heading = math.atan2(pass_dir[1], pass_dir[0])
    for i in range(pass_frame + 1):
        d = passer_track[min(i + 1, n_frames - 1)] - passer_track[max(i - 1, 0)]
        h = math.atan2(d[1], d[0])
        reach = 0.45 + 0.2 * math.sin(2 * math.pi * 0.9 * times[i])
        if i > pass_frame - 10:
            h, reach = pass_heading, 0.35
        ball[i, :2] = passer_track[i] + reach * np.array([math.cos(h), math.sin(h)])
        ball[i, 2] = BALL_RADIUS

    # Poses
    poses, headings = {}, {}
    for eid, team, role, number, style, _ in ENTITIES:
        track = tracks[eid]
        height = 1.0 + rng.uniform(-0.05, 0.05)
        heading = 0.0 if team == "home" else math.pi
        phase = rng.uniform(0, 2 * math.pi)
        noise = np.zeros((len(JOINTS), 3))
        frames_pose, frames_conf, frames_heading = [], [], []
        # Window with poorly visible joints (occlusion), except for the players in the play
        occl = None
        if eid not in (PASSER, RECEIVER, 104) and rng.random() < 0.45:
            start = rng.uniform(0, DURATION - 2.5)
            parts = [["left_elbow", "left_wrist"], ["right_elbow", "right_wrist"],
                     ["left_knee", "left_ankle", "left_heel", "left_big_toe", "left_small_toe"],
                     ["right_shoulder", "right_elbow", "right_wrist"]]
            part = parts[rng.integers(len(parts))]
            occl = (start, start + rng.uniform(1.0, 2.5), [J[p] for p in part])
        for i, t in enumerate(times):
            vel = (track[min(i + 1, n_frames - 1)] - track[max(i - 1, 0)]) * FPS / (2 if 0 < i < n_frames - 1 else 1)
            speed = float(np.linalg.norm(vel))
            ball_xy = ball[min(i, pass_frame), :2]
            to_ball = math.atan2(ball_xy[1] - track[i, 1], ball_xy[0] - track[i, 0])
            if style == "keeper" or speed < 2.0:
                target = to_ball
            else:
                target = math.atan2(vel[1], vel[0])
            heading = angle_lerp(heading, target, 0.2) if i else target
            forward = float(np.dot(vel, [math.cos(heading), math.sin(heading)]))
            phase += 2 * math.pi * (0.9 + 0.17 * speed) / FPS * (1 if forward >= -0.2 else -1)

            kick = None
            if eid == PASSER:
                u = (t - (PASS_TIME - 0.4)) / 0.75
                if 0 <= u <= 1:
                    kick = (-0.6 + 1.7 * smoothstep(u / 0.6) - 0.6 * smoothstep((u - 0.6) / 0.4),
                            1.3 * (1 - smoothstep(u / 0.55)) + 0.15)
            pose = synth_pose(track[i], heading, phase, speed, height, style, kick)
            noise = 0.75 * noise + 0.25 * rng.normal(0, 0.03, noise.shape)
            conf = np.clip(0.93 + rng.normal(0, 0.025, len(JOINTS)), 0.7, 0.99)
            # Extra occlusion noise only goes to the output: if it entered the temporal noise state it would
            # accumulate frame after frame
            frame_noise = noise.copy()
            if occl and occl[0] <= t <= occl[1]:
                conf[occl[2]] = rng.uniform(0.25, 0.45, len(occl[2]))
                frame_noise[occl[2]] += rng.normal(0, 0.03, (len(occl[2]), 3))
            frames_pose.append(pose + frame_noise)
            frames_conf.append(conf)
            frames_heading.append(heading)
        poses[eid] = (np.array(frames_pose), np.array(frames_conf))
        headings[eid] = np.array(frames_heading)
        # No joint may end up far from the body or below the grass
        reach = np.linalg.norm(poses[eid][0][:, :, :2] - track[:, None, :], axis=2).max()
        z = poses[eid][0][:, :, 2]
        assert reach < 1.5 and z.min() > -0.15 and z.max() < 2.3, \
            f"Pose fuera de rango en la entidad {eid}: alcance {reach:.2f} m, z [{z.min():.2f}, {z.max():.2f}] m"

    attack_dir = 1  # the home team attacks towards +X

    def front_valid(eid, frame):
        """Most advanced valid part in the attacking direction: (value, joint index)."""
        p, c = poses[eid][0][frame], poses[eid][1][frame]
        values = np.where(VALID & (c > 0), p[:, 0] * attack_dir, -np.inf)
        j = int(np.argmax(values))
        return float(values[j]), j

    def evaluate():
        defenders = sorted(((front_valid(e[0], pass_frame), e[0]) for e in ENTITIES if team_of[e[0]] == "away"),
                           reverse=True)
        (second_val, second_joint), second_id = defenders[1]
        ball_val = float(ball[pass_frame, 0] * attack_dir)
        line_val, line_source = max((second_val, "second_last_defender"), (ball_val, "ball"))
        return defenders, second_id, second_joint, line_val, line_source, ball_val

    # Adjust the receiver's run so the margin is exactly the requested one
    _, _, _, line_val, _, _ = evaluate()
    current, _ = front_valid(RECEIVER, pass_frame)
    shift = (args.margin - (current - line_val)) * attack_dir
    poses[RECEIVER][0][:, :, 0] += shift
    tracks[RECEIVER][:, 0] += shift
    defenders, second_id, second_joint, line_val, line_source, ball_val = evaluate()

    # Ball after the pass: rolling towards the receiver's run and then at their feet
    recv_frame = int(round(RECEIVE_TIME * FPS))
    recv = tracks[RECEIVER]
    for i in range(pass_frame + 1, n_frames):
        h = headings[RECEIVER][i]
        at_feet = recv[i] + 0.5 * np.array([math.cos(h), math.sin(h)])
        if i < recv_frame:
            target = recv[recv_frame] + 0.5 * np.array([math.cos(headings[RECEIVER][recv_frame]),
                                                        math.sin(headings[RECEIVER][recv_frame])])
            u = (i - pass_frame) / (recv_frame - pass_frame)
            s = 1 - (1 - u) ** 1.6
            ball[i, :2] = ball[pass_frame, :2] + s * (target - ball[pass_frame, :2])
        else:
            ball[i, :2] = at_feet
        ball[i, 2] = BALL_RADIUS
    hidden_ball = set(range(pass_frame + 22, pass_frame + 26))  # brief occlusion during the pass

    attackers = []
    for eid, team, role, *_ in ENTITIES:
        if team != "home" or role == "goalkeeper":
            continue
        val, joint = front_valid(eid, pass_frame)
        margin = val - line_val
        attackers.append({"id": eid, "joint": JOINTS[joint], "x": round(val * attack_dir, 3),
                          "margin_m": round(margin, 3), "offside_position": bool(margin > 0 and val > 0)})
    recv_val, recv_joint = front_valid(RECEIVER, pass_frame)
    margin = recv_val - line_val
    within = abs(margin) <= UNCERTAINTY_M
    warnings = ["Datos sintéticos: trayectorias y poses generadas, no proceden de vídeo",
                f"Incertidumbre fijada a mano (±{UNCERTAINTY_M * 100:.0f} cm), no medida"]
    if within:
        warnings.append("El margen es menor que la incertidumbre: decisión no concluyente")

    def point(eid, joint):
        return [round(float(v), 3) for v in poses[eid][0][pass_frame][joint]]

    event = {
        "id": "pase_1", "type": "pass", "frame": pass_frame, "time": round(pass_frame / FPS, 3),
        "passer": PASSER, "receiver": RECEIVER, "attacking_team": "home",
        "offside": {
            "status": "offside" if margin > 0 and recv_val > 0 else "onside",
            "within_uncertainty": bool(within),
            "margin_m": round(margin, 3),
            "uncertainty_m": UNCERTAINTY_M,
            "line": {"x": round(line_val * attack_dir, 3), "source": line_source},
            "ball_x": round(ball_val * attack_dir, 3),
            "attacker": {"id": RECEIVER, "joint": JOINTS[recv_joint], "point": point(RECEIVER, recv_joint)},
            "defender": {"id": second_id, "joint": JOINTS[second_joint], "point": point(second_id, second_joint)},
            "attackers": attackers,
            "method": "Parte válida más adelantada (sin brazos) frente a max(penúltimo defensor, balón)",
            "warnings": warnings,
        },
    }

    frames = []
    for i in range(n_frames):
        players = []
        for eid, *_ in ENTITIES:
            p, c = poses[eid][0][i], poses[eid][1][i]
            ground = (p[J["left_ankle"], :2] + p[J["right_ankle"], :2]) / 2
            entry = {"id": eid, "position": [round(float(ground[0]), 3), round(float(ground[1]), 3)],
                     "confidence": round(float(c.mean()), 2)}
            if eid in GROUND_ONLY and GROUND_ONLY[eid][0] <= i < GROUND_ONLY[eid][1]:
                entry.update({"coord_type": "ground_xy", "pose": None, "confidence": 0.55})
            else:
                entry.update({"coord_type": "pose3d_estimated",
                              "pose": [[round(float(x), 3), round(float(y), 3), round(float(z), 3), round(float(cc), 2)]
                                       for (x, y, z), cc in zip(p, c)]})
            players.append(entry)
        if i in hidden_ball:
            ball_entry = None
        else:
            conf = 0.62 if pass_frame < i < recv_frame else 0.9
            ball_entry = {"position": [round(float(v), 3) for v in ball[i]], "confidence": conf}
        frames.append({"frame": i, "time": round(i / FPS, 3), "players": players, "ball": ball_entry})

    status = "FUERA DE JUEGO" if event["offside"]["status"] == "offside" else "POSICIÓN LEGAL"
    data = {
        "format": "offside-analysis",
        "version": 1,
        "source": {"type": "synthetic", "generator": "tools/generate_synthetic_play.py", "seed": args.seed},
        "match": {"id": "sintetico-01", "name": f"Jugada sintética ({status.lower()}, {margin * 100:+.0f} cm)"},
        "sequence": {"id": "pase_al_hueco", "fps": FPS, "frame_count": n_frames, "video": None},
        "pitch": {"length": PITCH_LENGTH, "width": PITCH_WIDTH},
        "coordinate_system": {"units": "m", "origin": "centro del campo",
                              "x": "a lo largo del campo", "y": "a lo ancho", "z": "vertical"},
        "skeleton": {
            "name": "halpe26",
            "joints": JOINTS,
            "joint_radius": [JOINT_RADIUS[n] for n in JOINTS],
            "offside_valid": [bool(v) for v in VALID],
            "bones": [[J[a], J[b], r] for a, b, r in BONES],
            "head": {"joints": [J["left_ear"], J["right_ear"]], "radius": 0.115},
        },
        "teams": TEAMS,
        "entities": [{"id": e[0], "team": e[1], "role": e[2], "number": e[3]} for e in ENTITIES],
        "frames": frames,
        "events": [event],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{args.output}: {n_frames} fotogramas, {len(ENTITIES)} entidades")
    print(f"Pase en el fotograma {pass_frame}: {status} | margen {margin * 100:+.1f} cm "
          f"(receptor: {JOINTS[recv_joint]}, defensor {second_id}: {JOINTS[second_joint]}, línea por {line_source})")
    for a in attackers:
        print(f"  atacante {a['id']:>2}: {a['joint']:<16} margen {a['margin_m'] * 100:+6.1f} cm")


if __name__ == "__main__":
    main()
