"""2D pose of each player (17 COCO keypoints) with YOLO-pose on the crop of their box.

In a broadcast players are 60-200 px tall: cropping and enlarging each one gives a much more
stable pose than running on the full image.
"""
import numpy as np
from ultralytics import YOLO

COCO_JOINTS = ["nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder", "right_shoulder",
               "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip",
               "left_knee", "right_knee", "left_ankle", "right_ankle"]


class PoseEstimator:
    def __init__(self, weights, device="cpu", imgsz=320, pad=0.25):
        self.model = YOLO(weights)
        self.device, self.imgsz, self.pad = device, imgsz, pad

    def __call__(self, frame, boxes):
        """List with one (17, 3) array [u, v, confidence] per box, or None if no pose is found."""
        if len(boxes) == 0:
            return []
        h, w = frame.shape[:2]
        crops, offsets, targets = [], [], []
        for x1, y1, x2, y2 in boxes:
            bw, bh = x2 - x1, y2 - y1
            side = max(bh, bw) * (1 + 2 * self.pad)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            ox, oy = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
            ex, ey = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
            crops.append(frame[oy:ey, ox:ex])
            offsets.append((ox, oy))
            targets.append(np.array([x1 - ox, y1 - oy, x2 - ox, y2 - oy]))
        results = self.model(crops, imgsz=self.imgsz, device=self.device, verbose=False, conf=0.2)
        poses = []
        for r, (ox, oy), target in zip(results, offsets, targets):
            if r.keypoints is None or len(r.boxes) == 0:
                poses.append(None)
                continue
            # The person in the crop that best matches the tracked box
            ious = [_iou(b, target) for b in r.boxes.xyxy.cpu().numpy()]
            best = int(np.argmax(ious))
            if ious[best] < 0.3:
                poses.append(None)
                continue
            kp = r.keypoints.data[best].cpu().numpy().copy()
            kp[:, 0] += ox
            kp[:, 1] += oy
            poses.append(kp)
        return poses


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
