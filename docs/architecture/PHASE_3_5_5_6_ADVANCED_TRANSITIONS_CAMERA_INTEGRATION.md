# Phase 3.5.5.6 — Advanced Transitions & Camera Movement Integration

## Status and intent

This phase extends the real motion-to-MP4 pipeline after Phase 3.5.5.5 added cut and adjacent-scene alpha crossfade rendering. The goal is to make transition behavior deterministic, renderer-independent where practical, and compatible with the existing per-scene camera-motion evaluator.

This document is an implementation plan only. It does not claim that the effects below are already implemented.

## Current foundation

- `CompositionTimelinePlan` provides immutable scene slots, frame boundaries, transition mode/duration, and stale-input fingerprints.
- `MotionTimelinePlan` binds caller-supplied `SceneMotion` to each scene and includes outgoing overlap frames.
- `MotionRasterRenderer` renders actual PNG frames with per-element and camera transforms.
- `MotionTimelineRenderCoordinator` renders scene motion sequentially, composites the timeline, encodes one H.264 MP4, and reuses the existing narration/global Studio music muxer.
- Cut and linear alpha crossfade are implemented. The legacy `ProductionJob` is intentionally unchanged.

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

### 3.5.5.6b — Transition frame compositor
- Extract transition compositing from the motion timeline coordinator into a focused component.
- Preserve existing crossfade pixels byte-for-byte where feasible.
- Implement four directional wipes and dip-to-color.
- Validate equal frame dimensions/modes and normalize only through the existing explicit frame-normalization policy.
- Add pixel-level tests for boundary frames, midpoint, odd/even frame counts, and complete pixel coverage.

### 3.5.5.6c — Camera-aware transition orchestration
- Bind the validated transition specification to the immutable motion timeline plan.
- Render each scene's own camera motion before compositing.
- Revalidate the plan before rendering and before final publish.
- Keep sequential execution, cancellation, progress reporting, temporary cleanup, and no-overwrite guarantees.
- Reject unsupported transition/camera combinations rather than silently falling back.

### 3.5.5.6d — Integration and regression validation
- Reuse the existing frame-sequence encoder and audio muxer.
- Verify exact output frame count, dimensions, codec, stream alignment, and duration.
- Add end-to-end FFmpeg tests for at least one wipe and dip-to-color transition with camera motion on both scenes.
- Run the full test suite on Windows and Ubuntu with FFmpeg/FFprobe available.

## Explicit non-goals

- No transition editor or timeline UI.
- No project schema migration or automatic persistence of motion.
- No per-scene audio tracks, SFX generation, or audio crossfade.
- No AI/cloud asset generation, GPU dependency, or parallel rendering.
- No changes to the legacy `ProductionJob`.
- No claim of full commercial readiness based on CI alone.

## Acceptance criteria

- Existing cut and crossfade behavior remains regression-tested.
- Every new transition is deterministic at the pixel level.
- Camera motion is independently applied to each scene before transition composition.
- Invalid transition data fails safely with actionable diagnostics.
- Cancellation leaves no partial published MP4 or temporary frame directory.
- Windows and Ubuntu full test suites pass on the exact PR head SHA, including FFmpeg/FFprobe checks.
