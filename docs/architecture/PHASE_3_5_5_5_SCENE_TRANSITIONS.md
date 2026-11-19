# Phase 3.5.5.5 — Scene Transitions & Crossfade Rendering

## Scope

This phase extends the opt-in multi-scene motion renderer with frame-accurate scene crossfades. It reuses the immutable composition timeline, per-scene motion raster renderer, numbered frame-sequence encoder, and existing Studio audio mixer/muxer.

## Runtime behavior

1. The approved composition timeline determines each scene's slot and outgoing segment end.
2. The motion plan binds a SceneMotion to each scene's full rendered segment, including its outgoing overlap frames.
3. Each scene is rendered independently to a PNG sequence.
4. The coordinator walks the final output frame range. Frames with one active scene are copied to the output canvas; frames with two adjacent active scenes are alpha blended.
5. Each transition's overlap is derived from the frame-quantized timeline boundaries independently. This avoids assuming that tick-to-frame rounding produces an identical frame count for every transition.
6. The completed frame sequence is encoded as one constant-frame-rate H.264 MP4.
7. The existing audio muxer places the already-assembled narration and configured Studio music mix against the exact final video duration and validates the final MP4 streams.

## Safety and validation

- Only cut and crossfade are accepted.
- Crossfade requires at least two scenes and at least one output frame of overlap for every outgoing transition.
- The final scene cannot have an outgoing overlap.
- Overlaps may involve only adjacent scenes; triple-active frames are rejected.
- Each scene motion duration must exactly match its timeline segment, including outgoing overlap frames. Motion is never silently stretched or truncated.
- Composition and motion fingerprints are revalidated before encoding and before audio mux.
- Cancellation, temporary-file cleanup, no-overwrite output behavior, and FFprobe validation remain in place.

## Boundaries

- This phase does not add per-scene audio, SFX tracks, or audio crossfades. Existing narration and global Studio music tracks remain continuous and are muxed to the exact final timeline duration.
- Crossfade is a visual pixel blend; it does not add a transition editor or new UI.
- Motion remains caller-supplied and is not yet persisted into project files.
- Narration WAV must already be assembled and aligned to the approved composition timeline.
- Legacy ProductionJob behavior is unchanged.
