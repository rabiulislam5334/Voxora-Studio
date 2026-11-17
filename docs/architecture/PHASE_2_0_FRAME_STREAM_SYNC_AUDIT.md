# Phase 2.0 — Frame and Stream Synchronization Audit

**Baseline:** `main` after PR #21 (2026-11-17)  
**Audit branch:** `audit/phase-2-0-frame-stream-sync`  
**Scope:** Read-only audit of the current video production, muxing, and media-probe paths. No runtime behavior is changed by this report.

## Executive finding

The pipeline already makes several important timing decisions deterministic: the canonical integer timebase is used for timeline calculations; scene video segments receive explicit frame counts; narration placement uses the audio sample grid; and the final mux receives both an expected frame count and a frame-aligned duration.

However, the final-output validator still cannot prove that the resulting MP4 contains the expected number of decoded video frames or that its individual audio and video streams start and end on the intended timeline. The current probe API exposes only container-level duration and basic stream-presence/dimension information.

## Existing protections verified in code

- `app/core/timebase.py` uses an integer canonical clock (141,120,000 ticks/second) and explicit rounding policies.
- `app/workers/production.py` derives `total_frames` from the canonical timeline and computes the final video duration from that frame count.
- Narration scene placement is performed on the audio sample grid through `_slot_sample_bounds`; it is not rounded to video frames.
- The aligned narration WAV is padded to the final frame-aligned video duration.
- `app/video/render.py` passes explicit `-frames:v` limits when rendering scene segments and in the final mux. It also passes the exact frame-derived duration to `-t`.
- Source video scenes are normalized through an `fps=<project fps>` filter when rendered as segments.
- PR #21 requires a valid video result, an audio stream, and a container duration within one frame plus 30 ms of the expected duration.

## Gaps found

### 1. Decoded video frame count is not validated

The final mux is instructed to write `total_frames`, but after muxing the application does not count decoded frames. The existing `MediaInfo` model has no frame-count field, and `FFmpegTool.probe()` does not run a frame-count inspection.

**Risk:** A file can pass container-duration validation while containing a missing, duplicated, or otherwise unexpected decoded frame count.

### 2. Per-stream durations are not available

`MediaInfo.duration_s` is parsed from the FFmpeg input banner and represents the reported media/container duration. The parser does not retain separate audio and video stream durations.

**Risk:** A container can have the expected overall duration while one stream ends early or extends beyond the intended timeline.

### 3. Stream start timestamps and offsets are not validated

The current parser records neither stream `start_time` nor stream time bases / start timestamps.

**Risk:** Equal overall durations do not prove that audio and video begin together. A non-zero start offset can create an audible/visible lead or lag.

### 4. Timestamp continuity and VFR characteristics are not inspected

The current probe does not expose packet/frame timestamps, timestamp discontinuities, or the distinction between nominal and average frame rate.

**Risk:** Container duration and stream presence alone cannot establish constant-frame-rate output or prove that timestamps are monotonic and continuous.

### 5. Current probe mechanism is insufficient for these checks

`FFmpegTool.probe()` invokes `ffmpeg -i` and parses human-readable stderr via `parse_probe_output()`. That is adequate for the current lightweight media classification and basic metadata, but it is not a structured source for per-stream timing, decoded frame counts, or packet timestamp analysis.

## Recommended incremental implementation plan

1. **Structured inspection foundation (next PR):** add an optional, structured FFprobe inspection path that can report stream type, stream duration, start time, time base, frame-rate metadata, and format duration. Keep the existing lightweight `probe()` behavior backward compatible. Detect FFprobe explicitly and return a clear capability error when unavailable; do not silently fabricate missing timing fields.
2. **Decoded-frame validation:** count decoded video frames for the final MP4 and compare against the frame count calculated by the production timeline. Add deterministic synthetic-media tests.
3. **Per-stream duration validation:** compare audio/video stream durations against the expected frame-aligned output duration using codec-aware tolerances; keep container duration as a separate check.
4. **A/V start alignment:** inspect stream start timestamps and reject material offsets, with tests for intentionally offset audio.
5. **Timestamp/VFR audit:** inspect decoded frame or packet timestamps for monotonicity and discontinuities; characterize VFR inputs and verify that the segment-rendering normalization produces the intended CFR output.

## Non-goals for this audit

- No changes to project schema, timeline policy, frame allocation, audio sample placement, mux command, or cache keys.
- No parallel rendering, scheduler, retry policy, or UI changes.
- No claim that all A/V synchronization defects are currently present; the gaps above describe what the existing validator cannot prove.

## Test baseline

The repository's current test suite passed locally on the user's machine after PR #21: **574 passed in 49.76s** (reported 2026-11-17). This audit itself has not been run as a code change because it only documents the inspected implementation.
