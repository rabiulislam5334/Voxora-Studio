# Phase 3.5.4.3 — Composition Audio Mixer & MP4 Mux Integration

## Purpose

Connect the silent MP4 produced by the composition/frame-sequence path to Voxora's existing Studio audio pipeline. This phase reuses `AudioSettings`, `build_mix_args`, `probe_track_durations`, `FFmpegTool`, and the existing `build_mux_args` implementation. It does not create a second mixer and does not modify the legacy `ProductionJob`.

## Runtime contract

`CompositionAudioMuxer.render(...)` accepts:

- A silent H.264 MP4 whose dimensions, FPS, and packet count match the immutable `CompositionTimelinePlan`.
- A narration WAV already aligned to the frame-quantized timeline duration. Scene-level narration assembly remains the caller's responsibility.
- Existing Studio `AudioSettings` (narration gain, limiter, enabled music tracks, offsets, trims, loops, and fades).
- An output MP4 path that does not already exist.

The muxer derives duration from `plan.total_frames / plan.fps`, not the unquantized timeline tick total. If mixing is needed, it calls the existing mixer at `VIDEO_AUDIO_SAMPLE_RATE`; otherwise it uses the aligned narration WAV directly. It then reuses the existing video-copy/AAC mux command, validates streams, frame count, CFR timestamps, durations, and zero-based stream starts, and atomically publishes the MP4.

## Safety and compatibility

- Invalid timeline diagnostics block export.
- Silent input must contain exactly one H.264 video stream matching the plan.
- Final output must contain exactly one H.264 video stream and one AAC audio stream.
- Existing destination files and symlink destinations are never overwritten.
- Temporary mix and partial MP4 files are cleaned on failure/cancellation.
- The legacy production coordinator and its existing render path are unchanged.
- The caller must revalidate the immutable plan against the current project with `assert_composition_timeline_plan_current` immediately before execution and must obtain the user's explicit render approval.
- Music/SFX effects are limited to capabilities already represented by `AudioSettings`; this phase does not add a dedicated SFX track model.

## Current boundary

This phase performs audio mix + mux only. It does not render compositions into animated frame sequences, generate narration, create SFX, or introduce a new UI/workflow coordinator. The narration WAV must already contain the correctly placed scene narration and silence for the plan duration.
