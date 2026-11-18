# Phase 3.5.5.1 — Motion & Camera Domain Contracts

## Purpose

Introduce deterministic, renderer-independent motion data as the first slice of motion, camera, and transition rendering. Motion is expressed in integer output frames and can target either a composition element or the scene camera.

## Domain contracts

- `MotionKeyframe`: non-negative integer frame, finite scalar value, and outgoing interpolation mode.
- `MotionTrack`: one allowlisted scalar property on one element or the scene camera; keyframes are strictly ordered and unique.
- `SceneMotion`: versioned scene-level motion data with a fixed positive frame duration and unique tracks/target properties.
- `EvaluatedMotionFrame`: immutable, deterministically ordered values for one requested frame.

Supported element properties: normalized `x`, `y`, `width`, `height`, `anchor_x`, `anchor_y`, `opacity`, and bounded `rotation_degrees`.

Supported camera properties: bounded `pan_x`, `pan_y`, positive `zoom`, and bounded `rotation_degrees`.

Supported interpolation: hold, linear, ease-in, ease-out, and ease-in-out. Values before the first keyframe and after the last keyframe hold the nearest endpoint. The interpolation mode belongs to the left keyframe and controls the segment leading to the next keyframe.

## Safety and compatibility

- Evaluation uses integer frames and deterministic pure calculations.
- Unknown target properties are rejected; no arbitrary attribute access, callbacks, or code execution.
- Optional composition validation rejects missing element targets and mismatched scene IDs.
- Source compositions and project state are never mutated.
- Unknown JSON fields are preserved when round-tripping track and scene-motion records.
- This phase does not yet render animated frames, apply camera transforms to pixels, or implement transitions. Those are subsequent 3.5.5 slices.
- No project schema migration, UI wiring, AI generation, or legacy ProductionJob changes.
