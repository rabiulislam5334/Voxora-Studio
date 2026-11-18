# Phase 3.5.3 — Frame Sequence & FFmpeg Encoding Bridge

## Goal

Turn a validated, numbered PNG frame sequence into a real silent H.264 MP4 file using the installed FFmpeg executable. This is the first video artifact bridge for the layered raster pipeline; it does not itself animate scenes or generate artwork.

## Delivered contracts

- `FrameSequence`: contiguous, consistently named PNG files with a constant integer frame rate.
- `FrameSequenceLimits`: configurable bounds for frame count, dimensions, pixels, per-frame bytes, and total bytes.
- `FFmpegFrameSequenceEncoder`: validates image content and dimensions, invokes FFmpeg without a shell, reports progress, supports cancellation, validates the resulting video with FFprobe when available, and atomically publishes the MP4.
- `FFmpegFrameSequenceAdapter`: explicit adapter metadata for CPU-only MP4 encoding; no automatic selection or fallback.
- Output is silent H.264/yuv420p MP4. Audio muxing remains a later timeline/audio integration step.

## Safety and compatibility

- Input paths must be regular local PNG files; symbolic-link frames are rejected.
- Frame numbering must be contiguous and share one prefix and numeric width.
- All frames must have identical, even dimensions for yuv420p output.
- Resource limits are checked before launching FFmpeg.
- Output must use `.mp4`; existing files are preserved unless overwrite is explicitly requested.
- Encoding uses an isolated temporary file and only publishes after successful encoding and validation.
- Cancellation terminates the FFmpeg process and removes the temporary output.
- No project schema, `.voxora` persistence, legacy segment renderer, TTS, audio mixing, or timeline behavior is changed.
- No network, AI model, GPU, or automatic engine fallback is used.

## Explicit limitations

The encoder consumes an already-rendered frame sequence. It does not create per-frame scene motion, camera movement, transitions, characters, or artwork. The current raster composition renderer still produces a single still PNG; frame generation and timeline-driven animation are separate follow-up work. If FFprobe is unavailable, FFmpeg performs a decode check, but exact frame-count metadata verification is not available.

## Validation

The test suite covers deterministic input-pattern construction, frame naming and sequence validation, resource limits, dimensions, format restrictions, cancellation, output preservation, and a real FFmpeg encode to H.264 MP4 when FFmpeg is installed.
