"""Team of each player from the shirt colour (two-cluster grouping per play)."""
import cv2
import numpy as np


def jersey_color(frame, box):
    """Median Lab colour of the torso (grass excluded); None if the box is too small."""
    x1, y1, x2, y2 = box
    h, w = y2 - y1, x2 - x1
    if h < 20 or w < 8:
        return None
    crop = frame[int(y1 + 0.15 * h):int(y1 + 0.5 * h), int(x1 + 0.25 * w):int(x2 - 0.25 * w)]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
    grass = (hsv[:, 0] > 30) & (hsv[:, 0] < 90) & (hsv[:, 1] > 50)
    keep = lab[~grass]
    return np.median(keep, axis=0) if len(keep) >= 10 else None


def assign_teams(colors_by_track, roles, min_samples=3, min_outlier_dist=0.0):
    """K-means (k=2) on the median colour of each outfield player.

    Goalkeepers and referees are left out: they dress differently and the goalkeeper is assigned
    later by position. A "player" whose colour is far from both teams is usually a referee
    misclassified by the detector, and is set aside.

    Args:
        min_samples: colours needed per track (3 in a sequence, 1 in a single frame).
        min_outlier_dist: minimum Lab distance to set someone aside. In a single frame lighting
            changes colour a lot (a red shirt in the sun ends up ~30 from its team), so ~40 is safer.

    Returns:
        ({track: team 0/1}, [BGR colour of each team], {tracks whose colour matches neither team}).
    """
    tracks, colors, weights = [], [], []
    for t, cs in colors_by_track.items():
        if roles.get(t) == "player" and len(cs) >= min_samples:
            tracks.append(t)
            colors.append(np.median(np.array(cs), axis=0))
            weights.append(len(cs))
    if len(tracks) < 2:
        return {}, [(0, 0, 255), (255, 0, 0)], set()
    colors = np.array(colors, np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    outliers = set()
    for _ in range(2):
        keep = [i for i, t in enumerate(tracks) if t not in outliers]
        data = np.repeat(colors[keep], np.minimum(np.array(weights)[keep], 20), axis=0)
        _, _, centers = cv2.kmeans(data, 2, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
        all_dist = np.linalg.norm(colors[:, None] - centers[None], axis=2)
        group, dist = all_dist.argmin(axis=1), all_dist.min(axis=1)
        # Per cluster, the "normal" distance to the centre (median) and its spread (MAD): someone far
        # above both belongs to neither team
        outliers = set()
        for g in (0, 1):
            members = [i for i in keep if group[i] == g]
            if len(members) < 3:
                continue
            med = np.median(dist[members])
            mad = np.median(np.abs(dist[members] - med))
            limit = max(med + 4 * max(mad, 3.0), 2 * med, min_outlier_dist)
            outliers |= {tracks[i] for i in range(len(tracks)) if group[i] == g and dist[i] > limit}
    teams = {t: int(np.argmin(np.linalg.norm(centers - c, axis=1))) for t, c in zip(tracks, colors) if t not in outliers}
    bgr = [tuple(int(v) for v in cv2.cvtColor(np.uint8([[c]]), cv2.COLOR_LAB2BGR)[0, 0]) for c in centers]
    return teams, bgr, outliers


def keeper_colors(teams, roles, colors, team_bgr):
    """Goalkeeper kit colour of each team (the team colour if the goalkeeper is not visible)."""
    keeper_bgr = list(team_bgr)
    for t, role in roles.items():
        if role == "goalkeeper" and colors.get(t) and teams.get(t) is not None:
            lab = np.median(np.array(colors[t]), axis=0).astype(np.uint8)
            keeper_bgr[teams[t]] = tuple(int(v) for v in cv2.cvtColor(np.uint8([[lab]]), cv2.COLOR_LAB2BGR)[0, 0])
    return keeper_bgr
