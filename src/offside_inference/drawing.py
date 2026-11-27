"""Image of the pass frame with the offside lines drawn over the video."""
import cv2
import numpy as np

from .export import BONES, J

SKELETON_2D = [(J[a], J[b]) for a, b, _ in BONES] + [(J["left_ear"], J["left_eye"]), (J["left_eye"], J["nose"]),
                                                    (J["nose"], J["right_eye"]), (J["right_eye"], J["right_ear"])]


def _ground_line(img, cam, x, color, thickness):
    ys = np.linspace(-34, 34, 50)
    uv = cam.project(np.c_[np.full(50, x), ys, np.zeros(50)])
    cv2.polylines(img, [uv.astype(np.int32)], False, color, thickness)


def _pose_2d(img, p, color):
    """2D pose of a player: joints used in white, discarded ones marked with an X."""
    kp, joints = p.get("kp2d"), p.get("joints")
    if kp is None or joints is None:
        return
    used = joints[:, 3] > 0
    for a, b in SKELETON_2D:
        if used[a] and used[b]:
            cv2.line(img, tuple(map(int, kp[a, :2])), tuple(map(int, kp[b, :2])), color, 2)
    for j, (u, v, c) in enumerate(kp):
        if used[j]:
            cv2.circle(img, (int(u), int(v)), 3, (255, 255, 255), -1)
        elif c >= 0.3:  # it had confidence but did not fit the rest of the body
            cv2.drawMarker(img, (int(u), int(v)), (0, 220, 255), cv2.MARKER_TILTED_CROSS, 14, 2)


def draw_pass_frame(frame, cam, players, teams_bgr, result, path):
    """Pass frame with boxes per team, the 2D pose of attacker and defender, and the offside lines
    (thick: 3D; thin: 2D check without the 3D pose).
    """
    img = frame.copy()
    for p in players:
        x1, y1, x2, y2 = map(int, p["box"])
        color = (40, 40, 40) if p["role"] == "referee" else teams_bgr[p["team"]] if p.get("team") is not None else (200, 200, 200)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, str(p["id"]), (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    if result.get("status") in ("offside", "onside"):
        by_id = {p["id"]: p for p in players}
        _pose_2d(img, by_id[result["attacker"]["id"]], (40, 40, 255))
        _pose_2d(img, by_id[result["defender"]["id"]], (255, 140, 40))
        for x, color in ((result["line"]["x"], (255, 140, 40)), (result["attacker"]["point"][0], (40, 40, 255))):
            _ground_line(img, cam, x, color, 3)
        for key, color in (("attacker", (40, 40, 255)), ("defender", (255, 140, 40))):
            u, v = cam.project([result[key]["point"]])[0]
            cv2.circle(img, (int(u), int(v)), 9, color, 3)
        if result.get("ball_xy") is not None:  # ball used for the line (from the detector or marked by hand)
            u, v = cam.project([[*result["ball_xy"], 0.0]])[0]
            cv2.circle(img, (int(u), int(v)), 12, (255, 255, 255), 2)
        check = result.get("check_2d")
        if check:
            for key, color in (("attacker_point", (120, 120, 255)), ("defender_point", (255, 200, 120))):
                x, y = check[key]
                _ground_line(img, cam, x, color, 1)
                u, v = cam.project([[x, y, 0.0]])[0]
                cv2.rectangle(img, (int(u) - 5, int(v) - 5), (int(u) + 5, int(v) + 5), color, 2)
        text = f"{'FUERA DE JUEGO' if result['status'] == 'offside' else 'POSICION LEGAL'}  margen {100 * result['margin_m']:+.0f} cm (+-{100 * result['uncertainty_m']:.0f})"
        lines = [text]
        if check:
            lines.append(f"2D: {100 * check['margin_m']:+.0f} cm ({check['attacker_joint']} / {check['defender_joint']})  "
                         f"{'coincide' if check['agrees'] else 'NO COINCIDE'}")
        cv2.rectangle(img, (20, 20), (20 + 16 * max(map(len, lines)), 30 + 42 * len(lines)), (20, 20, 20), -1)
        for i, line in enumerate(lines):
            cv2.putText(img, line, (30, 56 + 42 * i), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    cv2.imwrite(path, img)
