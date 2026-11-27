# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (0.x: work in progress, anything may change).

## [Unreleased]

### Planned
- Integrate the ball-only detector (sliding 640 px windows) into the analysis session.
- Mark a decision as "not evaluable" when the receiver or the defensive line are out of shot.
- Detect goalkeepers that the detector labels as outfield players.
- Automatic suggestion of the pass frame.
- Unit tests for the geometry (`camera.py`) and the Law 11 logic (`offside.py`).
- Validate the reported uncertainty against annotated plays.
- Play the original video in sync inside the 3D viewer.

## [0.2.0] - 2026-11-27

First public version. Semi-automatic: a person chooses the pass frame, the attacked goal, the
attacker and the second-last defender.

### Added
- `offside_inference` library: 4-class YOLO detection and ByteTrack tracking, camera calibration
  from HRNet pitch keypoints refined on the white lines (with a fixed camera position per stadium),
  team assignment by shirt colour, YOLO11-pose on player crops lifted to 3D, Law 11 evaluation with
  a 2D cross-check, and export to the `offside-analysis` JSON format.
- Single-frame analysis CLI (`analyze_frame.py`), sequence pipeline (`run_inference.py`) and a JSON
  lines backend for the Qt application.
- Qt 6 / Quick 3D viewer with an analysis tab and a 3D view of the result, synthetic play
  generator and scripted demo recording.
- Data tools: SoccerNet tracking to YOLO conversion, 4-class dataset split by sequence, ESPN
  match-commentary synchronisation with broadcast recordings, per-event clips, stadium camera
  position, CVAT pre-labelling, fine-tuning and ball-crop training scripts, and a Law 11 bench.
- Single path configuration in `configs/paths.yaml` with environment overrides.

### Known limitations
- No trained weights or data are distributed; models must be trained by the user.
- Camera calibration needs an external, unlicensed repository (Sportlight's SoccerNet calibration
  solution) running in Docker.
- The ball is the weakest detection class.
- No automated tests.
