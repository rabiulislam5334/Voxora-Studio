# Phase 3.5.5.6 — Advanced Transitions & Camera Movement Integration

## Status and intent

This phase extends the real motion-to-MP4 pipeline after Phase 3.5.5.5 added cut and adjacent-scene alpha crossfade rendering. The goal is to make transition behavior deterministic, renderer-independent where practical, and compatible with the existing per-scene camera-motion evaluator.

This document tracks the implementation. The transition contract (3.5.5.6a), pixel compositor (3.5.5.6b), motion-timeline binding and camera-aware orchestration (3.5.5.6c), and FFmpeg frame-sequence regression coverage (part of 3.5.5.6d) are implemented in this PR. Full desktop UI and project persistence remain out of scope.

## Current foundation

- `CompositionTimelinePlan` provides immutable scene slots, frame boundaries, transition mode/duration, and stale-input fingerprints.
- `MotionTimelinePlan` binds caller-supplied `SceneMotion` to each scene and includes outgoing overlap frames.
- `MotionRasterRenderer` renders actual PNG frames with per-element and camera transforms.
- `MotionTimelineRenderCoordinator` renders scene motion sequentially, composites the timeline, encodes one H.264 MP4, and reuses the existing narration/global Studio music muxer.
- Cut, crossfade, four directional wipes, and dip-to-color are implemented for the motion timeline. Each scene's own camera motion is rendered before transition compositing. The legacy `ProductionJob` is intentionally unchanged.

## Design principles

1. Keep all timing on the canonical integer project clock and quantize to output frames exactly once per plan.
2. Preserve immutable plans, deterministic fingerprints, explicit approval, and stale-plan revalidation.
3. Apply each scene's camera motion to that scene's source frames before transition compositing. Never interpolate camera values across unrelated scene coordinate spaces.
4. Keep rendering sequential and CPU-first; do not introduce GPU requirements or parallel rendering.
5. Preserve existing cut/crossfade output and project compatibility.
6. Do not silently substitute unsupported effects or transition durations.
7. Existing narration and global music remain continuous; per-scene SFX/audio crossfades are out of scope.

## Proposed transition contract

Introduce a validated transition specification rather than adding unrelated string branches to the coordinator.

Initial supported effects:
- `cut`: zero overlap; existing behavior.
- `crossfade`: existing linear alpha blend.
- `wipe_left`, `wipe_right`, `wipe_up`, `wipe_down`: deterministic spatial reveal using a frame-derived boundary.
- `dip_to_color`: outgoing scene fades to a configured opaque color, then incoming scene fades from that color. The midpoint must be deterministic for odd and even transition frame counts.

The specification should carry only validated, serializable values: effect ID, duration in canonical ticks, easing/interpolation mode, and optional RGB color for `dip_to_color`. Unknown effects, invalid colors, non-positive durations, and sub-frame overlaps must produce clear blocking diagnostics.

## Transition progress and easing

- Compute transition progress from integer overlap-frame index and overlap-frame count; do not accumulate floating-point deltas.
- Support a small explicit easing set: `linear`, `ease_in`, `ease_out`, and `ease_in_out`.
- Clamp progress to [0, 1] and use stable rounding for pixel boundaries.
- For wipe effects, guarantee every output pixel is assigned exactly once, including the first and last transition frames.
- For dip-to-color, define the outgoing and incoming halves explicitly so odd frame counts do not create an undefined midpoint.

## Camera-motion integration

- Continue evaluating each scene's own `SceneMotion` over its exact planned source-frame interval.
- Render camera pan, zoom, and rotation independently for each scene before applying the transition mask/blend.
- During overlap, composite the already-rendered outgoing and incoming frames using the selected transition effect.
- Do not blend camera keyframes between scenes or reinterpret one scene's normalized coordinates in another scene's canvas.
- Add tests proving camera movement remains visible on both sides of an overlap and that transition output is deterministic for repeated renders.
- Camera interpolation remains governed by the existing motion domain contract; this phase does not add new camera keyframe semantics.

## Implementation stages

### 3.5.5.6a — Transition domain contract
- Add immutable/versioned transition specification and validation.
- Add deterministic progress/easing helpers and stable serialization/fingerprinting.
- Add tests for unknown effect, invalid parameters, duration bounds, and round-trip behavior.

### 3.5.5.6b — Transition frame compositor — implemented
- Added a focused Pillow compositor for crossfade, four directional wipes, and dip-to-color.
- Preserved the existing linear crossfade calculation and explicit RGBA normalization in the coordinator.
- Enforced matching dimensions/modes at the compositor boundary; only RGB/RGBA inputs are accepted.
- Added pixel-level endpoint, easing, direction, odd/even dip, and invalid-input tests.

### 3.5.5.6c — Camera-aware transition orchestration — implemented
- Bind per-outgoing-scene `TransitionSpec` values into the immutable `MotionTimelinePlan` fingerprint.
- Require each spec duration to equal the approved composition overlap; reject unknown scene IDs, cut-overlap mismatches, and invalid specs.
- Render each scene's own camera motion through `MotionRasterRenderer` before applying the transition compositor; camera values are never interpolated across scenes.
- Preserve pre-render and pre-publish stale-plan checks, sequential rendering, cancellation, progress, temporary cleanup, and no-overwrite guarantees.

### 3.5.5.6d — Integration and regression validation — implemented with a scoped boundary
- Reuse the existing numbered-PNG frame-sequence encoder and existing Studio audio muxer; no alternate audio path is introduced.
- Added FFmpeg/FFprobe integration tests that encode wipe and dip-to-color frame sequences and verify H.264 codec, dimensions, FPS, exact frame count, and duration.
- Existing audio-mux regression tests remain part of the full suite. A single full `MotionTimelineRenderCoordinator` test combining real asset-library setup, camera animation, advanced transition, narration, and global music is still a follow-up validation gap and must not be inferred from the frame-encoder test.

## Explicit non-goals

- No transition editor or timeline UI.
- No project schema migration or automatic persistence of motion.
- No per-scene audio tracks, SFX generation, or audio crossfade.
- No AI/cloud asset generation, GPU dependency, or parallel rendering.
- No changes to the legacy `ProductionJob`.
- No claim of full commercial readiness based on CI alone.

## Acceptance criteria

- Existing cut and crossfade behavior remains regression-tested.
- Every new transition is deterministic at the pixel level and has exact first/last-frame behavior.
- Camera motion is independently applied to each scene before transition composition.
- Invalid transition data fails safely with actionable diagnostics and is included in the plan fingerprint.
- Existing cancellation/no-overwrite/temp-cleanup guarantees are preserved by the coordinator.
- Windows and Ubuntu full test suites pass on the exact PR head SHA, including FFmpeg/FFprobe checks.
