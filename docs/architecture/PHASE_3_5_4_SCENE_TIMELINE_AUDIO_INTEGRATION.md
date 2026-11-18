# Phase 3.5.4 — Scene Timeline & Audio Integration

## Goal

Connect the new composition-backed visual output path to Voxora's established scene/timeline and audio-rendering foundations without replacing or changing the legacy production path. The first deliverable is a deterministic, reviewable render plan that maps approved still compositions to explicit scene intervals and preserves the existing narration, BGM, SFX, and synchronization semantics.

This phase must not imply animation: a still composition is held for its approved scene interval. Motion, camera movement, and transitions remain Phase 3.5.5.

## Current foundation

- SceneComposition and composition preview/apply are additive Universal-state data; existing Project/Scene schemas remain unchanged.
- RasterCompositionRenderer produces a real PNG still from bound local assets.
- FFmpegFrameSequenceEncoder produces a silent H.264/yuv420p MP4 from a validated numbered PNG sequence.
- The legacy scene renderer and audio mixing pipeline already exist and remain the compatibility baseline.
- The frame-sequence encoder is currently a silent encoder. Audio muxing and timeline-wide orchestration are not implemented by it.

## Design principles

1. **Reuse, do not replace:** integrate with existing timeline, narration, audio mixer, render coordinator, and FFmpeg tool contracts after inspecting their actual APIs. Do not create a parallel audio mixer or a second source of timeline truth.
2. **Explicit timing provenance:** distinguish measured timings from approved estimates. Never invent precise durations from narration text or silently reinterpret existing scene timing.
3. **One timeline clock:** use the repository's established time unit and conversion rules. If a boundary adapter is required, convert once and preserve integer precision.
4. **Still means still:** composition-backed scenes render a still hold for their interval until Phase 3.5.5 adds tested motion.
5. **Audio remains authoritative:** narration, BGM, and SFX retain existing offsets, trims, fades, gain, and mix behavior. No implicit audio regeneration or destructive edits.
6. **Snapshot and approval:** render from immutable snapshots of project, composition, scene timing, and asset fingerprints. Require explicit approval and reject stale inputs before expensive work.
7. **Bounded local execution:** CPU-first, offline-first; stream/process incrementally and enforce frame count, duration, memory, and temporary-disk limits.
8. **Backward compatibility:** do not migrate Project/Scene schemas, rewrite .voxora files, or alter legacy rendering defaults.

## Target flow

Approved Project + Scene/ScenePlan + SceneComposition + bound asset snapshot
→ inspect and resolve existing scene/timeline timing
→ immutable visual/audio render plan
→ raster still frame(s) held over the required scene interval
→ existing narration/BGM/SFX mix path with preserved timing
→ FFmpeg video/audio mux or the established render coordinator
→ output validation (video dimensions, frame rate/count, duration, audio streams, decodability)
→ render manifest with source fingerprints and timing provenance

The implementation must select one compatible path explicitly. It must not silently fall back between the new composition path and legacy renderer.

## Planned increments

### 3.5.4.1 — Existing Timeline & Audio Contract Audit

- Map the actual Project, Scene, ScenePlan, timeline, narration, BGM, SFX, audio mixer, and render coordinator APIs.
- Record their time units, interval semantics, trim/fade/gain behavior, cancellation, progress, and output validation contracts.
- Identify which existing audio artifact can be reused without re-rendering or changing its timing.
- Add characterization tests before connecting the new visual path.
- No production behavior changes in this increment.

### 3.5.4.2 — Immutable Scene Render Timeline

- Define a renderer-independent snapshot/plan using existing domain types and established clock units.
- Map each approved composition to a scene interval and explicit still-hold behavior.
- Validate gaps, overlaps, missing/ambiguous durations, unsupported timing provenance, and stale scene/composition/asset fingerprints.
- Preserve source ordering and exact existing narration intervals.
- Preview only; no project mutation or encoding.

### 3.5.4.3 — Visual Frame Scheduling

- Derive frame count and frame boundaries from approved scene timing and a declared output frame rate.
- Define deterministic rounding at scene boundaries so total output duration is conserved and no scene silently gains/loses time.
- Reuse the raster renderer and frame-sequence contract; avoid holding all frames in memory.
- For still holds, reuse or safely replicate the rendered PNG according to the sequence contract; do not claim motion.

### 3.5.4.4 — Audio Timeline Assembly

- Adapt the existing audio mix result/artifacts into the visual render timeline without changing source audio.
- Preserve narration alignment, BGM looping/trimming/fades, SFX offsets, and mix levels as already defined by the existing mixer.
- Validate audio coverage and expected duration before muxing.
- Do not create a parallel mixer or alter existing audio project settings.

### 3.5.4.5 — Explicit Video/Audio Mux & Validation

- Add a separate mux operation or extend the existing coordinator only after its real contract is understood.
- Encode/mux to a unique temporary destination; validate video and audio streams, dimensions, frame rate, frame count, duration tolerance, and decodability.
- Preserve existing destination on failure/cancellation; publish atomically after validation.
- Report missing FFmpeg/FFprobe/audio stream capability clearly; no hidden fallback.

### 3.5.4.6 — Opt-in Render Coordinator Integration

- Add an explicit composition-backed render action with preview, diagnostics, approval, progress, and cancellation.
- Revalidate snapshot fingerprints immediately before execution.
- Keep the legacy render path unchanged and independently selectable.
- Add end-to-end tests using real PNG, MP4, and audio fixtures on Windows and Ubuntu.

## Timing and validation rules

- Reuse the established time unit from the existing timeline/audio APIs; do not introduce floating-point seconds as the canonical internal clock.
- Measured timings remain measured. Estimated timings must be clearly marked and approved before final rendering.
- Convert timeline intervals to frame boundaries using a documented deterministic rounding policy.
- The sum of scheduled frame durations must match the approved output duration within one frame; any larger mismatch is an error.
- Audio/video duration tolerance must be explicit and tested; never silently stretch narration or shift SFX to hide a mismatch.
- Reject missing audio/video streams, unexpected frame dimensions/rate/count, stale snapshots, and invalid output files.

## Non-goals

- No motion, keyframes, camera moves, transitions, character animation, or lip sync (Phase 3.5.5 or later).
- No new audio mixer, TTS engine, music/SFX generator, or audio asset download.
- No automatic engine selection/fallback, cloud API, AI generation, or arbitrary code execution.
- No Project/Scene schema migration or destructive .voxora rewrite.
- No replacement of the legacy render coordinator or FFmpeg single-source segment path.

## Acceptance gates

- First inspect and characterize the existing timeline/audio APIs; do not guess field names or semantics.
- Unit tests cover interval mapping, timing provenance, deterministic frame rounding, stale snapshots, and duration conservation.
- Integration tests create real MP4 output and verify audio/video stream metadata with FFprobe, then decode representative media.
- Tests must run on Windows and Ubuntu against the exact PR head SHA.
- No capability or UI action is advertised until the end-to-end output path is implemented and verified.
- Merge only after exact-head CI succeeds and explicit user approval.

