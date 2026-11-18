# Phase 3.5 — Actual Visual Rendering Pipeline

## Purpose

Phase 3.5 turns the existing renderer-independent scene composition model into a production-capable, deterministic visual rendering pipeline. The first deliverable is real pixels and verifiable media files from user-provided/local visual assets—not another preview-only abstraction.

The implementation must remain local-first, offline-first, CPU-capable, and compatible with the existing .voxora project format. GPU acceleration and external AI services are optional capabilities, never baseline requirements.

## Current foundation

The repository already has:
- Universal Project, Scene, ScenePlan, Timeline, and render coordination foundations.
- Channel Profile and workflow registries with explicit engine compatibility.
- Visual asset and character domain contracts, local asset library/import, scene asset bindings, and continuity diagnostics.
- Renderer-independent SceneComposition contracts, deterministic preview/diagnostics, explicit apply and persistence.
- Desktop Composition Editor.
- An explicit composition-render capability bridge.

The current FFmpegSegmentAdapter renders single-source scene segments and does **not** implement layered composition rendering. The composition capability bridge correctly reports that limitation. Phase 3.5 must not advertise a capability until an implementation actually produces and validates the promised output.

## Product principles

1. **Real output over simulated support:** every render capability must be backed by integration tests that inspect actual generated media.
2. **CPU-first:** baseline rendering must work without NVIDIA/CUDA or a discrete GPU.
3. **Offline-first:** imported/local assets and local renderers work without network access or API keys.
4. **Bounded resource use:** enforce canvas, pixel, frame, memory, duration, and temporary-disk limits; stream or process frames incrementally.
5. **Deterministic where possible:** identical inputs, renderer version, and settings should produce equivalent frame pixels and stable metadata.
6. **Explicit user control:** no implicit engine switching, fallback, destructive asset edits, or silent project mutation.
7. **Backward compatibility:** no breaking changes to legacy .voxora projects, Scene/Project schemas, existing TTS/audio/render behavior, or existing single-source FFmpeg rendering.
8. **Honest capability reporting:** distinguish composition preview, raster frame rendering, encoded video rendering, animation, and AI asset generation.

## Target pipeline

Scene + ScenePlan + SceneComposition + bound local assets
→ validated immutable render request
→ composition renderer
→ rendered frame(s) / intermediate image sequence
→ optional FFmpeg encoding and audio mux
→ output validation
→ render manifest and provenance

The renderer consumes an explicit snapshot. It must not reach into mutable UI state or silently modify Project, Scene, ScenePlan, asset catalog, or composition persistence.

## Planned subphases

### 3.5.1 — Raster Composition Renderer

Build the first real CPU-capable renderer for a single composition frame.

- Resolve each composition element only through the approved scene bindings and local asset catalog.
- Decode supported raster formats safely; define explicit behavior for unsupported/corrupt assets.
- Composite in deterministic layer order.
- Implement declared fit modes (contain, cover, stretch), normalized transforms, anchors, rotation, opacity, and visibility.
- Render to a concrete pixel buffer and PNG output at the declared canvas dimensions.
- Keep source assets immutable; use bounded decoded-image caches and deterministic cleanup.
- Add pixel-level and integration tests using generated fixture images.
- Report unsupported features instead of silently approximating them.

Initial scope is still-image raster layers. It does not claim text/vector authoring, character animation, 3D, AI image generation, or video encoding.

### 3.5.2 — Composition Renderer Adapter & Capability Registration

Connect the real raster renderer to the existing engine/capability contracts.

- Implement the composition renderer protocol and exact-ID adapter binding.
- Declare supported formats, fit modes, transforms, alpha, rotation, canvas limits, and resource estimates.
- Validate input snapshot, local asset set, output destination, and capability requirements before work begins.
- Forward progress and cancellation; clean partial outputs on failure.
- Keep registry discovery metadata-only and avoid expensive work during application startup.
- No automatic engine selection or fallback.

### 3.5.3 — Frame Sequence & FFmpeg Encoding Bridge

Turn rendered frames into actual playable video using the existing FFmpeg toolchain.

- Define a bounded frame-sequence contract with explicit frame rate, dimensions, ordering, and duration.
- Stream frames to a unique temporary workspace; do not hold an entire video in RAM.
- Encode an MP4 using verified FFmpeg/FFprobe capabilities and explicit codec/pixel-format settings.
- Validate output existence, dimensions, duration, frame rate, stream metadata, and decodability.
- Preserve the legacy single-source segment path and its behavior.
- Ensure cancellation, timeout, disk-space errors, and FFmpeg failures clean temporary artifacts safely.

### 3.5.4 — Scene Timeline & Audio Integration

Integrate composition-backed scene visuals with the existing timeline/render coordinator.

- Derive frame timing from explicit measured or approved estimated scene timing.
- Preserve narration timing and existing audio mixing/synchronization behavior.
- Support still composition holds first; do not imply motion where none exists.
- Produce a render manifest tying output segments to scene, composition fingerprint, asset fingerprints, renderer version, and settings.
- Require explicit render approval and reject stale composition/asset snapshots.

### 3.5.5 — Motion, Camera & Transition Rendering

Add controlled motion only after still composition and encoding are reliable.

- Define deterministic keyframe/animation contracts for position, scale, rotation, opacity, and camera framing.
- Add a small tested set of transitions and camera moves.
- Use bounded frame sampling and interpolation; avoid unbounded frame generation.
- Keep animation optional and preserve still-scene behavior.
- Test continuity, frame timing, cancellation, and output validation.

### 3.5.6 — Procedural 2D Graphics & Workflow Integration

Expand beyond imported raster images with safe, deterministic procedural primitives.

- Add supported vector-like primitives (shapes, paths, lines, and text) through declarative data contracts, not arbitrary Python execution.
- Integrate reusable 2D storytelling, stickman, infographic, and documentary workflows only where their declared visual features are actually implemented.
- Keep channel profiles as defaults/presets, not hard-coded renderer branches.
- Add character pose/gesture support only with an explicit tested representation and continuity rules.
- Distinguish procedural graphics from AI-generated artwork.

### 3.5.7 — Optional AI Asset Generation Adapters (separate capability track)

Only after the deterministic local pipeline is stable, evaluate optional local/external image-generation adapters.

- AI services must be opt-in, provider/model-specific, and isolated behind an adapter.
- No API key, network, model download, or cloud account is required for baseline rendering.
- Clearly label generated assets and record model/provider provenance and licensing metadata where available.
- Require user review before generated assets enter a project.
- Do not claim prompt-to-video from prompt planning alone.

## Resource and safety constraints

- CPU fallback is mandatory for the baseline.
- Set configurable maximum canvas dimensions, total pixels, frame count, duration, decoded image memory, and temporary disk usage.
- Decode untrusted image files with bounded dimensions and safe failure handling.
- Use temporary directories unique to a render job; never overwrite source assets.
- Check cancellation at bounded intervals and remove partial outputs on cancellation/failure.
- Avoid arbitrary code execution, untrusted plugins, automatic downloads, and hidden subprocesses.
- Treat GPU acceleration as an optional declared capability with a tested CPU fallback, not as a prerequisite.

## Compatibility and non-goals

- No Project/Scene schema migration is planned.
- Existing .voxora data and additive Universal composition persistence remain compatible.
- No rewrite of existing TTS, narration parsing, audio mixing, cache, or legacy FFmpeg segment rendering.
- No claim that the first raster renderer generates original artwork; it composes existing local assets.
- No promise of real 3D/4D rendering in this phase. A future 3D engine must be a separately declared and tested adapter.
- No automatic engine fallback or channel-specific renderer fork.

## Acceptance gates

Each subphase must include focused unit tests plus integration tests for real files where applicable. CI must pass on the exact PR head SHA on Windows and Ubuntu. For media-producing phases, tests must inspect the generated output with Pillow and/or FFprobe and decode representative frames; a mocked adapter alone is insufficient.

A capability may be exposed in the UI only after its real output path passes these acceptance gates. Each increment should be independently reviewable and merged only after explicit user approval.

## Recommended execution order

Implement 3.5.1 first, then 3.5.2 and 3.5.3 before attempting timeline-wide integration. This delivers a narrow, verifiable milestone—one actual composition frame and then a playable encoded scene—before adding motion, procedural graphics, or AI.
