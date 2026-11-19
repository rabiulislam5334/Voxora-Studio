# Phase 3.5.5.3 — Motion-to-MP4 Rendering Pipeline

## Purpose

Connect the motion-aware PNG sequence renderer to the existing validated
FFmpeg frame-sequence encoder. This produces a real H.264 MP4 from evaluated
scene motion without replacing the legacy production pipeline.

## Implemented

- `MotionVideoRenderCoordinator` orchestrates sequential motion frame rendering
  and MP4 encoding.
- Reuses `MotionRasterRenderer` for element and camera animation.
- Reuses `FrameSequence` validation and `FFmpegFrameSequenceEncoder` for
  H.264 encoding, output verification and atomic publication.
- Requires an explicit integer frame rate from 1 to 120 FPS.
- Reports progress across the raster-render and encode stages.
- Supports cancellation, including the existing `CancelToken` contract.
- Uses a temporary work directory for PNG frames and cleans it on success,
  failure or cancellation.
- Refuses to overwrite existing MP4 destinations.
- Returns frame count, frame rate, dimensions, duration, codec and SHA-256.

## API

```python
from app.universal import MotionVideoRenderCoordinator

coordinator = MotionVideoRenderCoordinator()
result = coordinator.run(
    composition,
    scene_motion,
    asset_paths={"asset-id": image_path},
    destination=output_mp4,
    fps=30,
)
```

## Deliberate boundaries

- Output is currently silent; no audio muxing is performed here.
- No scene timeline orchestration, transition rendering or cross-scene motion.
- No UI integration or motion persistence/schema migration.
- No change to the legacy `ProductionJob` pipeline.
- Frame rendering remains sequential and CPU-first.
- H.264 `yuv420p` encoding requires even frame dimensions; the existing
  encoder validates dimensions and every PNG before encoding.

## Verification

Tests exercise a real FFmpeg render when FFmpeg is available, MP4 metadata and
frame-count verification, progress completion, existing-output protection,
frame-rate validation and pre-cancelled `CancelToken` handling. Full
repository CI on Windows and Ubuntu remains the merge gate.
