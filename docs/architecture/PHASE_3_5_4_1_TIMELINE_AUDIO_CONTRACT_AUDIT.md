# Phase 3.5.4.1 — Existing Timeline & Audio Contract Audit

Status: repository contract audit completed; no production behavior changed.

## Audited implementation

The following current-main files were inspected directly:

- `app/core/timebase.py`
- `app/studio/models.py`
- `app/studio/timing.py`
- `app/audio/mixer.py`
- `app/audio/assembler.py`
- `app/video/render.py`
- `app/workers/production.py`
- `app/universal/frame_sequence.py`
- `app/universal/adapters/ffmpeg.py`

## Canonical time model

- The canonical clock is `141,120,000` integer ticks per second (`TICKS_PER_SECOND`).
- Timebase conversion functions use explicit rounding policies and rational arithmetic.
- Audio sample boundaries use `ticks_to_samples`; video frame boundaries use `ticks_to_frames` and `frames_to_ticks`.
- Existing production deliberately keeps narration placement on the audio sample grid and video segments on the frame grid. It does not round each scene's audio duration to video frames.
- `StudioState` stores compatibility-facing seconds and serialized tick fields for music trims/fades/offsets and scene video duration. Unknown fields are preserved; newer/invalid Studio state can become read-only.

## Scene timeline and narration behavior

`ProductionJob._produce` is the current end-to-end orchestration entry point.

1. Narration is produced/reused by the existing `NarrationJob`.
2. For video, one `SceneTimingInput` is built for every project scene in script order.
3. Each input carries scene ID, measured narration duration (when narration exists), configured per-scene video duration, and narration pause duration.
4. `compute_timeline` receives the ordered inputs, configured transition type/duration, and default scene duration.
5. If narration is longer than configured visual duration, the slot is extended and a warning is emitted.
6. Scene video segments are quantized to frame boundaries. Narration audio placement uses sample-grid boundaries independently.
7. A narration-aligned WAV is assembled in scene order. Existing scene WAVs are appended, and silence fills unused slot duration; final silence extends audio through the final video frame when frame quantization makes video slightly longer.

The full timing contract is defined by `app/studio/timing.py`; future integration must use `compute_timeline` and its `VideoTimeline`/slot tick fields rather than implementing a parallel scene clock.

## Existing audio contract

### Studio data model

- `AudioSettings` contains narration volume, limiter, and music tracks.
- `MusicTrack` includes enabled state, volume percentage, trim start/end, offset, loop, fade-in, and fade-out.
- `AudioSettings.active_tracks()` returns enabled music tracks only.
- The audited `StudioState` audio model does not expose a dedicated SFX-track collection. Do not invent an SFX API or claim SFX are currently integrated into this mixer.

### Mixer

`app/audio/mixer.py::build_mix_args`:

- Uses narration as the timing reference.
- Adds enabled music tracks as separate FFmpeg inputs.
- Applies resampling, stereo channel layout, trim, loop, volume, fade-in, fade-out, and offset.
- Mixes with `amix normalize=0`, preserving configured gain rather than automatically normalizing.
- Optionally applies the configured limiter.
- Trims the final mix to the requested total timeline duration.
- Uses integer ticks for internal time calculations and formats seconds only at the FFmpeg filter boundary.

`has_mixing_work` currently returns true when enabled music tracks exist or narration volume differs from 100%.

### Audio assembly

`app/audio/assembler.py::WavBuilder`:

- Streams mono 16-bit PCM WAV data in fixed-size blocks.
- Supports exact silence insertion by canonical ticks when the requested duration maps to whole samples.
- Exposes exact duration derived from written sample count.
- Writes to a temporary `.part` file and atomically replaces the destination on success.
- Existing production uses it to assemble scene narration and silence; it is not a replacement for the FFmpeg music mixer.

## Existing video join and mux contract

`app/video/render.py` provides:

- Silent per-scene H.264 segment generation (`-an`).
- Cut/concat and crossfade joining.
- `build_mux_args`, which maps the joined video stream and one mixed audio stream, copies video without re-encoding, encodes audio as AAC, sets the output duration/frame count, uses `-shortest`, and enables fast-start MP4 layout.

The current `ProductionJob` then validates the final MP4 using FFmpeg/FFprobe-backed probes:

- video kind and audio presence;
- decoded frame count and timestamp continuity;
- video/audio stream durations;
- audio/video stream start alignment and zero-based timeline origin;
- duration tolerances based on frame rate and AAC access-unit size.

The final video is first written to a `.part` destination and atomically published only after validation. Cancellation is checked before publication.

## New Phase 3.5 visual path boundary

- `RasterCompositionRenderer` produces a single PNG still image from a scene composition.
- `FFmpegFrameSequenceEncoder` consumes a validated numbered PNG sequence and produces a **silent** H.264 MP4.
- `FFmpegFrameSequenceAdapter` is a frame-sequence encoder adapter, not an audio mixer or project timeline coordinator.
- `FFmpegSegmentAdapter` delegates to the existing legacy segment renderer and explicitly does not own joining, audio mixing, muxing, caching, or timeline calculation.

Therefore the new frame-sequence encoder must not be presented as audio-capable. The integration layer must explicitly hand off to the existing audio/mux contract or add a separately validated mux step. No silent automatic fallback between the composition and legacy scene paths is permitted.

## Gaps and constraints for the next increments

1. **Composition duration mapping:** existing composition data is associated with scenes, while timeline duration comes from `compute_timeline`. A future immutable render plan must bind each composition snapshot to the corresponding timeline slot and scene fingerprint.
2. **Still-hold scheduling:** one raster PNG is not an animation. Frame scheduling must repeat/hold the still for the approved slot duration at the selected FPS, using deterministic frame-boundary rounding.
3. **Audio reuse:** narration alignment and music mixing should be reused from `ProductionJob` behavior. Do not run a second independent mixer.
4. **SFX:** no dedicated SFX collection was found in the audited `StudioState`/mixer contract. SFX support requires a separately designed, explicit model/API increment and must not be smuggled into music tracks.
5. **Orchestration boundary:** the existing `ProductionJob` owns narration, timing, audio assembly/mix, segment cache, joining, mux, progress, cancellation, and final validation. Future work must integrate deliberately with this coordinator or extract a tested shared service; do not create a second parallel production coordinator.
6. **Schema compatibility:** keep new composition/timeline metadata additive in Universal state or immutable runtime snapshots. Do not migrate Project/Scene schemas or rewrite existing .voxora scene content.
7. **Testing:** preserve existing production tests and add focused characterization/integration tests for composition slot mapping, sample/frame boundary conservation, mux audio presence, cancellation, stale snapshots, and final output validation.

## Acceptance result

- The actual canonical timebase and rounding helpers are identified.
- Existing scene timing, narration alignment, BGM mixing, audio assembly, video join, mux, cancellation, and output validation contracts are identified.
- The lack of a dedicated SFX track in the audited audio model is documented.
- No production files, project data, render defaults, or legacy audio/video behavior were changed in this audit.
- Phase 3.5.4.2 can now define an immutable composition-to-scene timeline snapshot against these verified contracts.
