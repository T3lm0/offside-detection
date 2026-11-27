"""Detection and tracking of players, goalkeepers, referees and the ball with YOLO + ByteTrack."""
import glob
import os
from collections import Counter, defaultdict

import numpy as np
from ultralytics import YOLO

from . import config
from .camera import HALF_LENGTH, HALF_WIDTH
from .lap_shim import install as _install_lap

_install_lap()

DEFAULT_POSE = config.path("pose_weights")


def default_detector():
    """Best available detector: the newest 4-class run, else the older 6-class model."""
    runs = os.path.join(config.path("runs_dir"), "detect")
    for pattern in ("det1280_*", "det640_*", "detector_4cls_*", "football_player_detection_v12"):
        candidates = sorted(glob.glob(os.path.join(runs, pattern, "weights", "best.pt")), key=os.path.getmtime)
        if candidates:
            return candidates[-1]
    raise FileNotFoundError("No hay ningún detector entrenado")


def role_of(class_name):
    """Role from the class name; works for both the 4-class and the 6-class detector."""
    name = class_name.lower()
    for role in ("ball", "goalkeeper", "referee"):
        if role in name:
            return role
    return "player"


class Tracker:
    def __init__(self, weights, device="cpu", imgsz=1280, conf=0.15):
        self.model = YOLO(weights)
        self.device, self.imgsz, self.conf = device, imgsz, conf
        self.roles = {i: role_of(n) for i, n in self.model.names.items()}

    def __call__(self, frame):
        """People with a track id and the most likely ball in the frame."""
        # Class-agnostic NMS: if the detector hesitates between two classes for the same person (left/right
        # team in the old model) there must not be two boxes or two tracks
        r = self.model.track(frame, persist=True, tracker="bytetrack.yaml", imgsz=self.imgsz,
                             conf=self.conf, device=self.device, verbose=False, agnostic_nms=True)[0]
        people, balls = [], []
        if r.boxes is None or len(r.boxes) == 0:
            return people, None
        boxes = r.boxes.xyxy.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy().astype(int)
        confs = r.boxes.conf.cpu().numpy()
        ids = r.boxes.id.cpu().numpy().astype(int) if r.boxes.id is not None else [None] * len(boxes)
        for box, c, p, tid in zip(boxes, classes, confs, ids):
            role = self.roles[c]
            if role == "ball":
                balls.append({"box": box, "conf": float(p)})
            elif tid is not None:
                people.append({"track": int(tid), "role": role, "box": box, "conf": float(p)})
        return people, _best_ball(balls)


class FrameDetector:
    """Single-frame detection without tracking: people numbered from left to right.

    Without tracking, which drops weak detections, distant players get several near-identical boxes,
    so the threshold is raised and boxes overlapping a more confident one are removed.
    """

    def __init__(self, weights, device="cpu", imgsz=1280, conf=0.25, iou=0.5):
        self.model = YOLO(weights)
        self.device, self.imgsz, self.conf, self.iou = device, imgsz, conf, iou
        self.roles = {i: role_of(n) for i, n in self.model.names.items()}

    def __call__(self, frame):
        r = self.model.predict(frame, imgsz=self.imgsz, conf=self.conf, iou=self.iou, device=self.device,
                               verbose=False, agnostic_nms=True)[0]
        people, balls = [], []
        if r.boxes is not None and len(r.boxes):
            for box, c, p in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy().astype(int),
                                 r.boxes.conf.cpu().numpy()):
                if self.roles[c] == "ball":
                    balls.append({"box": box, "conf": float(p)})
                elif not any(_overlap(box, q["box"]) > 0.6 for q in people):  # sorted by confidence
                    people.append({"role": self.roles[c], "box": box, "conf": float(p)})
        people.sort(key=lambda q: (q["box"][0] + q["box"][2]) / 2)
        for i, q in enumerate(people, 1):
            q["id"] = i
        return people, _best_ball(balls)


def _best_ball(balls):
    """The most confident ball plus every candidate: the most confident one is sometimes in the stand
    or on an advertising board, and choose_ball decides with the calibration.
    """
    if not balls:
        return None
    balls = sorted(balls, key=lambda b: -b["conf"])
    return {**balls[0], "candidates": balls}


FEET_CROP_FACTOR = 3.0  # side of the crop around the feet, in player heights
FEET_CROP_MIN_PX = 160
FEET_CROP_IMGSZ = 640


def ball_near_feet(model, frame, boxes, device, roles, conf=0.15):
    """Balls found in enlarged crops around each player's feet.

    The pass is where the detector fails most: the ball, about 13 px, is stuck to a foot or half
    occluded. In a crop three player heights wide resized to 640 px it appears about twice as large.

    Returns:
        Candidates {box, conf, source: "pies"} in frame pixels.
    """
    h, w = frame.shape[:2]
    crops, origins = [], []
    for x1, y1, x2, y2 in boxes:
        side = max(FEET_CROP_MIN_PX, FEET_CROP_FACTOR * (y2 - y1))
        cx, cy = (x1 + x2) / 2, y2 - 0.2 * (y2 - y1)
        a, b = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        c, d = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
        if c - a > 16 and d - b > 16:
            crops.append(frame[b:d, a:c])
            origins.append((a, b))
    found = []
    if not crops:
        return found
    for r, (a, b) in zip(model.predict(crops, imgsz=FEET_CROP_IMGSZ, conf=conf, device=device, verbose=False), origins):
        if r.boxes is None:
            continue
        for box, cl, p in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy().astype(int), r.boxes.conf.cpu().numpy()):
            if roles[cl] == "ball":
                found.append({"box": box + [a, b, a, b], "conf": float(p), "source": "pies"})
    # The same ball seen from two players' crops: keep the most confident
    found.sort(key=lambda f: -f["conf"])
    unique = []
    for f in found:
        centre = (f["box"][:2] + f["box"][2:]) / 2
        if all(np.linalg.norm(centre - (u["box"][:2] + u["box"][2:]) / 2) > 10 for u in unique):
            unique.append(f)
    return unique


BALL_PITCH_MARGIN_M = 1.0
BALL_NEAR_PLAYER_M = 2.5


def choose_ball(candidates, feet_xy, cam):
    """Picks the frame's ball among the detector candidates (full frame and foot crops).

    Candidates outside the pitch (stand, boards, bench) are dropped and, among the rest, one within
    2.5 m of a player's feet is preferred: at the pass the ball is at the passer's foot. Within each
    group the most confident wins. Without calibration nothing can be checked and the most confident
    one is kept.

    Returns:
        {box, conf, ground, near_player} or None.
    """
    if not candidates:
        return None
    if cam is None:
        return max(candidates, key=lambda b: b["conf"])
    feet = np.asarray(feet_xy, float).reshape(-1, 2)
    best = None
    for b in candidates:
        g = cam.to_ground([box_bottom(b["box"])])[0][:2]
        if abs(g[0]) > HALF_LENGTH + BALL_PITCH_MARGIN_M or abs(g[1]) > HALF_WIDTH + BALL_PITCH_MARGIN_M:
            continue
        near = bool(len(feet)) and float(np.min(np.linalg.norm(feet - g, axis=1))) <= BALL_NEAR_PLAYER_M
        key = (near, b["conf"])
        if best is None or key > best[0]:
            best = (key, {"box": b["box"], "conf": b["conf"], "ground": g, "near_player": near,
                          "source": b.get("source", "fotograma")})
    return None if best is None else best[1]


def _overlap(a, b):
    """Intersection over the smaller box's area: 1 if one box contains the other."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


def track_roles(detections):
    """Majority role of each track (the detector may hesitate between player and goalkeeper)."""
    votes = defaultdict(Counter)
    for frame_people in detections.values():
        for p in frame_people:
            votes[p["track"]][p["role"]] += p["conf"]
    return {t: v.most_common(1)[0][0] for t, v in votes.items()}


def box_bottom(box):
    x1, y1, x2, y2 = box
    return np.array([(x1 + x2) / 2, y2])
