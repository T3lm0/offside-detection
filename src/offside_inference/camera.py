"""Camera geometry relative to the pitch.

Pitch frame (same as the viewer and the offside-analysis format): metres, origin at the centre spot,
X along the pitch (goals at ±52.5), Y across (+Y = touchline opposite the main camera), Z up.

  - pitch -> image homography from pitch points and/or lines
  - full camera (K, R, t) from the homography, assuming square pixels and the principal point at
    the image centre
  - rays: image point -> ground (Z = 0) or -> vertical plane containing the player
"""
from dataclasses import dataclass

import numpy as np

HALF_LENGTH, HALF_WIDTH = 52.5, 34.0

# Named pitch lines: (point, direction) on the grass plane
FIELD_LINES = {
    "touchline_far": ((0, HALF_WIDTH), (1, 0)),
    "touchline_near": ((0, -HALF_WIDTH), (1, 0)),
    "halfway": ((0, 0), (0, 1)),
    "goal_line_right": ((HALF_LENGTH, 0), (0, 1)),
    "goal_line_left": ((-HALF_LENGTH, 0), (0, 1)),
    "box_front_right": ((HALF_LENGTH - 16.5, 0), (0, 1)),
    "box_front_left": ((-HALF_LENGTH + 16.5, 0), (0, 1)),
    "box_side_far_right": ((0, 20.16), (1, 0)),  # far side of the penalty areas (y = +20.16)
    "box_side_near_right": ((0, -20.16), (1, 0)),
    "box_side_far_left": ((0, 20.16), (1, 0)),
    "box_side_near_left": ((0, -20.16), (1, 0)),
    "goal_area_front_right": ((HALF_LENGTH - 5.5, 0), (0, 1)),
    "goal_area_front_left": ((-HALF_LENGTH + 5.5, 0), (0, 1)),
    "goal_area_side_far": ((0, 9.16), (1, 0)),
    "goal_area_side_near": ((0, -9.16), (1, 0)),
}

# Named points (for hand-written keyframes)
ARC_HALF = float(np.sqrt(9.15 ** 2 - (16.5 - 11.0) ** 2))  # half chord of the penalty arc on the box line
FIELD_POINTS = {
    "corner_far_right": (HALF_LENGTH, HALF_WIDTH), "corner_near_right": (HALF_LENGTH, -HALF_WIDTH),
    "corner_far_left": (-HALF_LENGTH, HALF_WIDTH), "corner_near_left": (-HALF_LENGTH, -HALF_WIDTH),
    "center": (0, 0), "halfway_far": (0, HALF_WIDTH), "halfway_near": (0, -HALF_WIDTH),
    "penalty_spot_right": (HALF_LENGTH - 11, 0), "penalty_spot_left": (-HALF_LENGTH + 11, 0),
    "box_far_right": (HALF_LENGTH - 16.5, 20.16), "box_near_right": (HALF_LENGTH - 16.5, -20.16),
    "box_goal_far_right": (HALF_LENGTH, 20.16), "box_goal_near_right": (HALF_LENGTH, -20.16),
    "box_far_left": (-HALF_LENGTH + 16.5, 20.16), "box_near_left": (-HALF_LENGTH + 16.5, -20.16),
    "goal_area_far_right": (HALF_LENGTH - 5.5, 9.16), "goal_area_near_right": (HALF_LENGTH - 5.5, -9.16),
    "goal_area_far_left": (-HALF_LENGTH + 5.5, 9.16), "goal_area_near_left": (-HALF_LENGTH + 5.5, -9.16),
    "arc_far_right": (HALF_LENGTH - 16.5, ARC_HALF), "arc_near_right": (HALF_LENGTH - 16.5, -ARC_HALF),
    "arc_far_left": (-HALF_LENGTH + 16.5, ARC_HALF), "arc_near_left": (-HALF_LENGTH + 16.5, -ARC_HALF),
}


def _normalization(pts):
    """Hartley normalisation: centres the points and scales them to a mean distance of sqrt(2)."""
    pts = np.asarray(pts, float)
    c = pts.mean(axis=0)
    s = np.sqrt(2) / max(np.linalg.norm(pts - c, axis=1).mean(), 1e-9)
    return np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])


def homography_from_correspondences(points=(), lines=()):
    """DLT from points and lines.

    Args:
        points: [((X, Y), (u, v))] pitch point -> pixel.
        lines: [(FIELD_LINES name or ((X, Y), (dX, dY)), (a, b, c))] pitch line -> image line
            a·u + b·v + c = 0. Each line gives two equations: two points of the pitch line must lie
            on the image line.

    Returns:
        H (pitch -> image) normalised so that H[2, 2] = 1.
    """
    field_pts, image_pts = [], []
    for f, i in points:
        field_pts.append(f)
        image_pts.append(i)
    line_samples = []
    for spec, img_line in lines:
        (px, py), (dx, dy) = FIELD_LINES[spec] if isinstance(spec, str) else spec
        line_samples.append(([(px - 30 * dx, py - 30 * dy), (px + 30 * dx, py + 30 * dy)], np.asarray(img_line, float)))
        field_pts += line_samples[-1][0]
    # Normalisation: on the pitch with every point used; in the image with the points plus one point
    # per line (the one closest to the origin) so lines are scaled the same way
    Tf = _normalization(field_pts)
    img_ref = list(image_pts) + [(-l[0] * l[2] / (l[0] ** 2 + l[1] ** 2), -l[1] * l[2] / (l[0] ** 2 + l[1] ** 2))
                                 for _, l in line_samples]
    Ti = _normalization(img_ref)
    rows = []
    for (X, Y), (u, v) in points:
        p = Tf @ [X, Y, 1]
        q = Ti @ [u, v, 1]
        rows.append(np.concatenate([np.zeros(3), -q[2] * p, q[1] * p]))
        rows.append(np.concatenate([q[2] * p, np.zeros(3), -q[0] * p]))
    Ti_inv_t = np.linalg.inv(Ti).T
    for samples, l in line_samples:
        ln = Ti_inv_t @ l  # line in normalised image coordinates
        ln /= np.linalg.norm(ln[:2])
        for X, Y in samples:
            p = Tf @ [X, Y, 1]
            rows.append(np.concatenate([ln[0] * p, ln[1] * p, ln[2] * p]))
    _, _, vt = np.linalg.svd(np.asarray(rows))
    Hn = vt[-1].reshape(3, 3)
    H = np.linalg.inv(Ti) @ Hn @ Tf
    return H / H[2, 2]


def project_h(H, xy):
    p = H @ np.c_[np.asarray(xy, float), np.ones(len(xy))].T
    return (p[:2] / p[2]).T


def line_from_points(p1, p2):
    """Homogeneous line a·u + b·v + c = 0 through two pixels."""
    return np.cross([*p1, 1.0], [*p2, 1.0])


@dataclass
class Camera:
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray

    @property
    def center(self):
        return -self.R.T @ self.t

    @property
    def focal(self):
        return float(self.K[0, 0])

    def project(self, xyz):
        p = self.K @ (self.R @ np.asarray(xyz, float).T + self.t[:, None])
        return (p[:2] / p[2]).T

    def ray(self, uv):
        """Pitch-frame direction of the ray through each pixel."""
        uv = np.atleast_2d(np.asarray(uv, float))
        d = self.R.T @ np.linalg.inv(self.K) @ np.c_[uv, np.ones(len(uv))].T
        return (d / np.linalg.norm(d, axis=0)).T

    def to_ground(self, uv, height=0.0):
        """Intersection of the rays with the horizontal plane Z = height."""
        C = self.center
        d = self.ray(uv)
        s = (height - C[2]) / d[:, 2]
        return C + s[:, None] * d

    def to_vertical_plane(self, uv, anchor_xy):
        """Intersection with the vertical plane through anchor_xy that faces the camera.

        Monocular approximation for body points above the ground: the player is assumed to lie in that
        plane (typical error 20-30 cm along the camera direction, which barely affects X in a side view).
        """
        C = self.center
        n = np.array([anchor_xy[0] - C[0], anchor_xy[1] - C[1], 0.0])
        n /= np.linalg.norm(n)
        d = self.ray(uv)
        s = (n @ (np.array([anchor_xy[0], anchor_xy[1], 0.0]) - C)) / (d @ n)
        return C + s[:, None] * d


def visible_grid(H, image_size, step=2.0, margin=0.0):
    """Pitch grid points whose projection falls inside the image."""
    w, h = image_size
    X, Y = np.meshgrid(np.arange(-HALF_LENGTH, HALF_LENGTH + 0.01, step),
                       np.arange(-HALF_WIDTH, HALF_WIDTH + 0.01, step))
    xy = np.c_[X.ravel(), Y.ravel()]
    p = H @ np.c_[xy, np.ones(len(xy))].T
    ok = p[2] > 0
    uv = (p[:2] / np.where(ok, p[2], 1)).T
    ok &= (uv[:, 0] > -margin) & (uv[:, 0] < w + margin) & (uv[:, 1] > -margin) & (uv[:, 1] < h + margin)
    return xy[ok], uv[ok]


def camera_from_homography(H, image_size):
    """Camera (K, R, t) that best reproduces the homography over the visible part of the pitch.

    Assumes square pixels and the principal point at the centre (usual for broadcast). The closed-form
    decomposition of H is very sensitive to noise, so the focal length is searched with PnP and then
    focal length and pose are refined together by least squares.

    Returns:
        The camera and the mean error (px) with which it reproduces H; a large error means the
        homography is not consistent with a real camera.
    """
    import cv2
    from scipy.optimize import least_squares

    w, h = image_size
    cx, cy = w / 2.0, h / 2.0
    xy, uv = visible_grid(H, image_size)
    if len(xy) < 6:
        raise ValueError("Se ve demasiado poco campo para calibrar la cámara")
    obj = np.c_[xy, np.zeros(len(xy))].astype(np.float64)

    def solve(f):
        K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]])
        ok, rvec, tvec = cv2.solvePnP(obj, uv.astype(np.float64), K, None, flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            return np.inf, None, None
        proj, _ = cv2.projectPoints(obj, rvec, tvec, K, None)
        return np.sqrt(((proj[:, 0] - uv) ** 2).sum(1).mean()), rvec, tvec

    focals = np.geomspace(300, 30000, 160)
    errors = [solve(f)[0] for f in focals]
    f0 = float(focals[int(np.argmin(errors))])
    _, rvec, tvec = solve(f0)
    if rvec is None:  # no focal length gives a camera: the homography comes from mismatched points
        raise ValueError("La homografía no corresponde a ninguna cámara")

    def residuals(p):
        K = np.array([[p[0], 0, cx], [0, p[0], cy], [0, 0, 1]])
        proj, _ = cv2.projectPoints(obj, p[1:4], p[4:7], K, None)
        return (proj[:, 0] - uv).ravel()

    sol = least_squares(residuals, np.r_[f0, rvec.ravel(), tvec.ravel()], x_scale="jac")
    f = float(sol.x[0])
    R, _ = cv2.Rodrigues(sol.x[1:4])
    cam = Camera(np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]]), R, sol.x[4:7].copy())
    if cam.center[2] <= 0:
        raise ValueError("La homografía no corresponde a una cámara por encima del campo")
    rms = float(np.sqrt((sol.fun.reshape(-1, 2) ** 2).sum(1).mean()))
    return cam, rms


def _look_at(center, target):
    """Rotation of a camera at center looking at target without roll (level horizon)."""
    forward = np.asarray(target, float) - center
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    return np.vstack([right, down, forward])


def camera_with_fixed_center(field_xy, image_uv, center, image_size, ransac_px=8.0, iterations=300, seed=0):
    """Camera with a known position: only focal length and orientation (pan, tilt, roll).

    The main broadcast camera is fixed in the stand and only pans and zooms, so with its position
    (estimated from frames that calibrate well) two pitch points are enough. Without the position, few
    markings (e.g. only the centre circle) fit equally well a close camera with little zoom and a far
    one with a lot, and the latter distorts perspective away from those markings.

    RANSAC over point pairs.

    Returns:
        (camera or None, [whether each point fits]).
    """
    import cv2
    from scipy.optimize import least_squares

    xy = np.asarray(field_xy, float)
    uv = np.asarray(image_uv, float)
    C = np.asarray(center, float)
    w, h = image_size
    cx, cy = w / 2.0, h / 2.0
    obj = np.c_[xy, np.zeros(len(xy))]
    if len(xy) < 2:
        return None, [False] * len(xy)

    def build(p):
        R, _ = cv2.Rodrigues(p[1:4])
        return Camera(np.array([[p[0], 0, cx], [0, p[0], cy], [0, 0, 1]]), R, -R @ C)

    def fit(idx):
        # Start: looking at the centre of the points, focal length from the angle they span
        R0 = _look_at(C, obj[idx].mean(0))
        rays = (R0 @ (obj[idx] - C).T).T
        ang = np.arctan2(np.linalg.norm(rays[:, :2], axis=1), rays[:, 2])
        pix = np.linalg.norm(uv[idx] - [cx, cy], axis=1)
        ok = ang > 1e-3
        f0 = float(np.median(pix[ok] / np.tan(ang[ok]))) if ok.any() else 3000.0
        f0 = float(np.clip(f0, 300, 30000))
        rvec, _ = cv2.Rodrigues(R0)

        def residuals(p):
            q = build(p).project(obj[idx])
            return (q - uv[idx]).ravel()

        sol = least_squares(residuals, np.r_[f0, rvec.ravel()], x_scale="jac", max_nfev=200)
        cam = build(sol.x)
        if cam.focal <= 0 or np.any((cam.R @ (obj[idx] - C).T)[2] <= 0):  # points behind the camera
            return None
        return cam

    def errors(cam):
        depth = (cam.R @ (obj - C).T)[2]
        e = np.linalg.norm(cam.project(obj) - uv, axis=1)
        e[depth <= 0] = np.inf
        return e

    rng = np.random.default_rng(seed)
    n = len(xy)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(pairs) > iterations:
        pairs = [pairs[k] for k in rng.choice(len(pairs), iterations, replace=False)]
    best, best_inliers = None, None
    for i, j in pairs:
        if np.linalg.norm(xy[i] - xy[j]) < 2.0:  # too close together to fix the zoom
            continue
        cam = fit([i, j])
        if cam is None:
            continue
        inliers = errors(cam) < ransac_px
        if best_inliers is None or inliers.sum() > best_inliers.sum():
            best, best_inliers = cam, inliers
    if best is None or best_inliers.sum() < 2:
        return None, [False] * n
    cam = fit(np.flatnonzero(best_inliers))  # with every inlier
    if cam is None:
        return None, [False] * n
    inliers = errors(cam) < ransac_px
    return cam, inliers.tolist()


def homography_from_camera(cam):
    """Pitch -> image homography of the Z = 0 plane of a camera."""
    H = cam.K @ np.column_stack([cam.R[:, 0], cam.R[:, 1], cam.t])
    return H / H[2, 2]


def line_mask(frame_bgr, exclude_boxes=()):
    """Pixels of the white pitch markings (excluding players, who may also wear white).

    A marking is a thin strip brighter than the surrounding grass (top-hat of brightness), not an
    absolute brightness: with a fixed threshold, lines in shadow disappear in stadiums with strong
    shadows. A top-hat with a structuring element wider than a line ignores the shadow edge, which is a
    wide change.
    """
    import cv2
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, (30, 40, 30), (90, 255, 255))
    near_grass = cv2.dilate(grass, np.ones((15, 15), np.uint8)) > 0
    k = max(9, frame_bgr.shape[1] // 120) | 1
    tophat = cv2.morphologyEx(hsv[..., 2], cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    white = (tophat > 30) & (hsv[..., 1] < 110) & near_grass
    mask = white.astype(np.uint8) * 255
    for x1, y1, x2, y2 in exclude_boxes:
        pad = 0.15 * (y2 - y1)
        mask[max(0, int(y1 - pad)):int(y2 + pad), max(0, int(x1 - pad)):int(x2 + pad)] = 0
    return mask


def _marking_samples(spacing=0.5):
    pts = []
    for poly in pitch_polylines(samples=200):
        for a, b in zip(poly[:-1], poly[1:]):
            n = max(1, int(np.linalg.norm(b - a) / spacing))
            pts.append(a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None])
    return np.vstack(pts)


MARKINGS = None


def refine_camera(cam, frame_bgr, exclude_boxes=(), fix_center=True, max_dist=25.0):
    """Refines the camera so that projected markings fall on the white lines.

    With fix_center (broadcast camera on a tripod) only focal length and orientation are refined.

    Returns:
        (camera, mean distance in px from markings to lines, number of markings used).
    """
    import cv2
    from scipy.ndimage import map_coordinates
    from scipy.optimize import least_squares

    global MARKINGS
    if MARKINGS is None:
        MARKINGS = np.c_[_marking_samples(), np.zeros(len(_marking_samples()))]
    h, w = frame_bgr.shape[:2]
    mask = line_mask(frame_bgr, exclude_boxes)
    dist = cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5).astype(np.float32)
    dist = np.minimum(dist, max_dist)
    uv = cam.project(MARKINGS)
    depth = (cam.R @ MARKINGS.T + cam.t[:, None])[2]
    visible = (depth > 0) & (uv[:, 0] > 5) & (uv[:, 0] < w - 5) & (uv[:, 1] > 5) & (uv[:, 1] < h - 5)
    pts = MARKINGS[visible]
    if len(pts) < 30:
        return cam, float("inf"), len(pts)
    C = cam.center
    cx, cy = cam.K[0, 2], cam.K[1, 2]

    def build(p):
        R, _ = cv2.Rodrigues(p[1:4])
        t = -R @ C if fix_center else p[4:7]
        return Camera(np.array([[p[0], 0, cx], [0, p[0], cy], [0, 0, 1]]), R, t)

    def residuals(p):
        c = build(p)
        q = c.project(pts)
        return map_coordinates(dist, [np.clip(q[:, 1], 0, h - 1), np.clip(q[:, 0], 0, w - 1)], order=1, mode="nearest")

    rvec, _ = cv2.Rodrigues(cam.R)
    p0 = np.r_[cam.focal, rvec.ravel()] if fix_center else np.r_[cam.focal, rvec.ravel(), cam.t]
    sol = least_squares(residuals, p0, loss="soft_l1", f_scale=3.0, x_scale="jac", max_nfev=200)
    refined = build(sol.x)
    return refined, float(np.median(np.abs(sol.fun))), len(pts)


def predict_with_motion(cam, H_rel):
    """Camera for the next frame from the inter-frame homography (pan + zoom).

    With the camera fixed on its mount, K' R' = H_rel K R: K' (focal length) and R' are separated by RQ.
    """
    from scipy.linalg import rq
    M = H_rel @ cam.K @ cam.R
    K, R = rq(M)
    S = np.diag(np.sign(np.diag(K)))  # positive diagonal of K
    K, R = K @ S, S @ R
    if np.linalg.det(R) < 0:
        R = -R
    f = float((K[0, 0] + K[1, 1]) / 2 / K[2, 2])
    Kn = cam.K.copy()
    Kn[0, 0] = Kn[1, 1] = f
    return Camera(Kn, R, -R @ cam.center)


def frame_motion(prev_gray, gray, exclude_boxes=(), scale=0.5):
    """Homography between two consecutive frames with ORB (players masked out); None if unreliable."""
    import cv2
    small = [cv2.resize(g, None, fx=scale, fy=scale) for g in (prev_gray, gray)]
    mask = np.full(small[0].shape, 255, np.uint8)
    for x1, y1, x2, y2 in exclude_boxes:
        mask[int(y1 * scale):int(y2 * scale) + 1, int(x1 * scale):int(x2 * scale) + 1] = 0
    orb = cv2.ORB_create(3000)
    k1, d1 = orb.detectAndCompute(small[0], mask)
    k2, d2 = orb.detectAndCompute(small[1], mask)
    if d1 is None or d2 is None or len(k1) < 50 or len(k2) < 50:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    if len(matches) < 40:
        return None
    p1 = np.float32([k1[m.queryIdx].pt for m in matches]) / scale
    p2 = np.float32([k2[m.trainIdx].pt for m in matches]) / scale
    # Between consecutive frames a panning and zooming camera looks like a similarity (translation +
    # rotation + scale); a free homography fits the noise and adds shear
    A, inliers = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if A is None or inliers.sum() < 30:
        return None
    return np.vstack([A, [0, 0, 1]])


def pitch_polylines(samples=48):
    """Pitch markings as (X, Y) polylines, for drawing over the image."""
    hl, hw = HALF_LENGTH, HALF_WIDTH
    out = [np.array([[-hl, -hw], [hl, -hw], [hl, hw], [-hl, hw], [-hl, -hw]]), np.array([[0, -hw], [0, hw]])]
    t = np.linspace(0, 2 * np.pi, samples)
    out.append(np.c_[9.15 * np.cos(t), 9.15 * np.sin(t)])
    for s in (-1, 1):
        g = s * hl
        out.append(np.array([[g, -20.16], [g - s * 16.5, -20.16], [g - s * 16.5, 20.16], [g, 20.16]]))
        out.append(np.array([[g, -9.16], [g - s * 5.5, -9.16], [g - s * 5.5, 9.16], [g, 9.16]]))
        a = np.arccos(5.5 / 9.15)
        ang = np.linspace(-a, a, samples) + (np.pi if s > 0 else 0)
        out.append(np.c_[g - s * 11 + 9.15 * np.cos(ang), 9.15 * np.sin(ang)])
    return out
