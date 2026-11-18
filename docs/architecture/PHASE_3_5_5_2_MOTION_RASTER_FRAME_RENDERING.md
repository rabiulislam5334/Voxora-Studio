# Phase 3.5.5.2 — Motion-Aware Raster Frame Rendering

## Purpose

Connect the renderer-independent motion contracts from Phase 3.5.5.1 to the
existing CPU raster composition renderer. For a requested integer frame, the
renderer evaluates the scene's motion tracks, applies animated element values,
renders the composition to real PNG pixels, then applies the camera transform.

This is an implementation slice: it renders actual frames and complete PNG
sequences, but it does not yet encode those sequences to MP4 or integrate motion
into the existing composition video coordinator.

## Implemented

- `MotionRasterRenderer.render_frame(...)` evaluates one `SceneMotion` frame
  with `evaluate_scene_motion` and verifies composition/scene identity.
- Element tracks update normalized position, dimensions, anchor, rotation and
  opacity on an ephemeral immutable composition. The persisted source
  composition is never mutated.
- Camera tracks apply canvas rotation, center-based zoom and normalized pan to
  the rendered pixels. A pan value of 1 moves the image by one full canvas
  dimension on that axis.
- `render_sequence(...)` renders frames sequentially as
  `frame_000000.png`, `frame_000001.png`, etc.
- Sequence output is staged in a temporary sibling directory and published
  only after every frame succeeds. Cancellation or a frame failure removes
  staged output.
- Existing destination files/directories are not overwritten implicitly.
- Sequence length is bounded (900 frames by default) to avoid unbounded CPU and
  disk work. The limit can be lowered or raised explicitly at construction.
- The existing raster renderer continues to enforce image decode, canvas,
  asset-path and resource limits.

## API sketch

```python
from app.universal.motion_raster_renderer import MotionRasterRenderer

renderer = MotionRasterRenderer()
result = renderer.render_frame(
    composition,
    scene_motion,
    frame=12,
    asset_paths={"asset-id": image_path},
    destination=output_png,
)

sequence = renderer.render_sequence(
    composition,
    scene_motion,
    asset_paths={"asset-id": image_path},
    destination_dir=output_directory,
)
```

## Deliberate boundaries

- No MP4 encoding, audio muxing, crossfade, transition or timeline integration.
- No camera easing beyond the interpolation already represented by motion tracks.
- No generated artwork, AI model, TTS, SFX or BGM generation.
- No UI controls or project persistence/schema migration for motion.
- No parallel rendering; frames are rendered sequentially for predictable CPU
  and memory use on modest hardware.
- Camera pan uses canvas-width/canvas-height units; zoom is centered on the
  canvas midpoint. Camera effects are applied after all composition layers.

## Verification scope

Tests cover pixel-level element movement and opacity, camera pan/zoom/rotation,
numbered sequence output, cancellation cleanup, frame limits, and invalid
scene/frame rejection. Full repository CI remains the merge gate.
