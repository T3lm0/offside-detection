# Inference pipeline

From a broadcast frame (or a short clip) to a Law 11 decision and a 3D reconstruction that the
[viewer](app.md) can show. The library is `src/offside_inference/`; the entry points are in
`scripts/inference/`.

All paths (trained detector, pose model, calibration repository, outputs) come from
`configs/paths.yaml` and can be overridden with environment variables. No weights are included in
this repository: see [data/README.md](../data/README.md).

## Single-frame analysis (what the app uses)

The user picks the pass frame, the attacked goal, the attacker and the second-last defender. That
frame is calibrated with the HRNet, players are detected, their pose is lifted to 3D and Law 11 is
applied. This is the *Análisis* tab of the app, which talks to `offside_backend.py` (protocol in its
docstring). The logic lives in `offside_inference/session.py` and can also be run from a terminal:

```bash
python3 scripts/inference/analyze_frame.py --input clip.mp4 --frame 579                 # calibrate and number the players
python3 scripts/inference/analyze_frame.py --input clip.mp4 --frame 579 --goal right --attacker 15
```

It accepts a video, an image, several images or a folder. If the pass frame shows few pitch
markings, a nearby frame (±2 s) is calibrated and the camera is followed to the pass frame. The
viewer JSON and a VAR-style image of the pass go to `<output_dir>/app/`.

### Design decisions

**Calibration with the camera in place.** The main broadcast camera is fixed in the stand; it only
pans and zooms. With few markings in view (e.g. only the centre circle), a close camera with little
zoom and a far one with a lot of zoom fit equally well, and the wrong one distorts perspective
where the players are. So the camera position is fixed first (median of the good calibrations of
12 frames of the video, or a `camara.json` next to the video) and the pass frame is calibrated
with orientation and zoom only (`camera_with_fixed_center`; 2-3 HRNet points are enough). A free
calibration that puts the camera more than 6 m away is flagged as doubtful (replay or another
camera). White lines are found by local contrast (top-hat), not absolute brightness, so the fit
survives strong shadows.

**Inconsistent joints.** Before looking for the most advanced part, joints that do not fit the rest
of the player are discarded (`clean_joints` in `offside_inference/offside.py`): 2D points outside the
box, a head with confidence < 0.5, more than 0.5 m from the torso or far above the nose, and legs
more than 1 m from the torso. The typical case is an occluded ear that the pose model places
~100 px away with confidence 0.3-0.5, which would move the line by almost a metre.

**2D cross-check.** Besides the 3D decision, a second one is made without the 3D pose (`check_2d`):
each valid part (head, torso, legs; not arms) is taken to the grass from its 2D point assuming the
typical height of that joint for a standing player (`STANDARD_HEIGHT_M`). The 3D method assumes the
body lies in a vertical plane facing the camera and the 2D one an upright posture; they fail
differently, so a disagreement raises a warning. The VAR image draws the 2D pose of attacker and
defender (discarded joints with an X), the 3D lines (thick) and the 2D lines (thin).

## Sequence analysis (`run_inference.py`)

Follows the play over several frames (for the viewer animation) and finds the passer by itself. It
needs a keyframe and, preferably, the attacking direction:

1. **Detection and tracking** of players, goalkeepers, referees and ball (YOLO + ByteTrack), with
   the newest trained detector found in `<runs_dir>/detect/`.
2. **Camera in every frame:** a keyframe is calibrated from pitch lines or points and the rest are
   followed by refining pan and zoom on the white lines.
3. **Teams** by shirt colour (two clusters). A "player" whose colour matches neither team is
   treated as a referee, and goalkeepers are assigned by position.
4. **2D pose** with YOLO11-pose on each player's crop, then **lifting to 3D**: feet to the ground,
   the rest of the body to a vertical plane through the player.
5. **Offside** (Law 11) in the pass frame: the attacker's most advanced valid part (arms excluded)
   against the further of the second-last defender and the ball.
6. **Output:** the `offside-analysis` JSON and an image of the pass frame with both lines.

```bash
IMG=<dataset_dir>/SoccerNet/tracking-2023/test/SNMOT-134/img1
python3 scripts/inference/hrnet_keyframe.py --image $IMG/000612.jpg --frame 612 --out keyframes/SNMOT-134.json
python3 scripts/inference/run_inference.py --input $IMG --keyframe keyframes/SNMOT-134.json \
    --start 566 --end 630 --pass-frame 579 --attack-direction 1 --output outputs/SNMOT-134.json --device 0
app/build/offside_viewer outputs/SNMOT-134.json --frame 579
```

| Option | Use |
|---|---|
| `--pass-frame N` | Pass frame, confirmed by a person; without it only positions are produced |
| `--passer ID` | Passer track. Default: the player closest to the last real ball detection (at most 0.8 s before) |
| `--attack-direction ±1` | Which goal is attacked. Default: inferred from the team positions (unreliable) |
| `--detector`, `--pose` | Weights to use |
| `--no-pose` | Ground positions only |
| `--device` | `cpu` (default) or a GPU index |

### Keyframe for a new clip

The quickest way is to let the calibration HRNet find it (it runs in its Docker container):

```bash
python3 scripts/inference/hrnet_keyframe.py --image clip/000612.jpg --frame 612 --out keyframes/my_clip.json
```

It keeps grass points with confidence ≥ 0.5 that fit a single homography (RANSAC) and writes
`keyframes/my_clip_hrnet.jpg` with the points and projected pitch lines for review. If fewer than
4 reliable points come out, mark the lines by hand:

```bash
python3 scripts/inference/detect_pitch_lines.py --image clip/000526.jpg --frame 526 --out keyframes/my_clip.json
```

It writes a template with the detected lines and an image with them numbered. In the template,
give each line its `FIELD_LINES` name (`offside_inference/camera.py`) and delete false ones
(running track, players). `FIELD_POINTS` can be added too. At least 4 non-parallel lines are needed.

## Known limitations

- **The pass instant, attacker and defender are chosen by a person.** There is no automatic pass
  detection.
- **Receiver out of shot.** With a long ball the camera follows the passer and neither the receiver
  nor the defensive line are visible in the pass frame. The program still gives a decision with the
  players it sees; it should say "not evaluable".
- **Goalkeeper detected as a player** in some clips: they count as an outfield defender and an
  invisible goalkeeper is assumed as well, so the line ends up too deep.
- **The inferred attacking direction is unreliable** when the attack is pushed forward; pass
  `--attack-direction`.
- **The ball** is the weakest class of the detector (small, blurred, stuck to a boot). Gaps of up
  to 1.2 s are filled by interpolation (confidence 0.3).
- **COCO-17 pose** has no toe keypoints, so the ankle is used. The 3D body is a monocular
  approximation: the error along the camera direction is about 20-30 cm.
- **Goalkeeper out of shot:** if the defending goalkeeper is not visible, they are assumed to be the
  last defender, and a warning is added.
- **The uncertainty (±)** is a simple estimate: calibration error in metres plus 15 cm of pose. It
  has not been validated against annotated plays.
- **One keyframe per shot** in `run_inference.py`: after a camera cut it must be calibrated again.
