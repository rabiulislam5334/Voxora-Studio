# Phase 2.1 — Visual Production Foundation Audit

**Branch:** `audit/phase-2-1-visual-production-foundation`  
**Base:** `main` at `71a96ddccdf4ee72286bd606a8e9be31167ad675`  
**Scope:** Read-only source audit and implementation plan. No runtime code, project schema, cache format, or UI behavior is changed in this PR.

## Executive summary

Voxora already has a working, deterministic, scene-based FFmpeg video pipeline. It is not starting from zero: scenes can use a still image, a source video, or a blank frame; still images support five simple motion modes; scenes can be cut or crossfaded; audio is mixed and muxed; scene clips are cached; and the final MP4 is validated for frame count, timestamps, stream durations, and stream origins.

The next step should therefore **extend the existing renderer and Universal Core contracts**, not replace the production pipeline or introduce a second video-rendering stack.

The current implementation is best described as a reliable *single-visual-per-scene renderer*. It is not yet a layered visual-composition or motion-graphics system. Prompt-based image generation, sketch/infographic composition, maps, 2D/3D animation, keyframed camera control, and a multi-layer visual timeline are not part of the current production path.

## 1. Existing visual production capabilities

### 1.1 Scene media model

- Each project scene has a stable scene ID, title, narration text, notes, and a `visual_prompt` string.
- Studio video settings are stored separately under the existing `studio` settings namespace.
- Per-scene video settings currently include a media path, optional duration, optional motion, and optional fit mode.
- Project-level video settings include aspect ratio, resolution, FPS, transition type/duration, default scene duration, default image motion, and default fit.
- The supported aspect ratios are 16:9 and 9:16. Resolutions include 360p draft, 720p, and 1080p. FPS is constrained to 12–60.
- The generic project model already has additive `profile`, `assets`, and `director` containers. These are forward-compatible data containers, not by themselves a complete typed asset library or channel-profile implementation.

### 1.2 Existing renderer

The current renderer is `app/video/render.py` and produces one silent H.264 MP4 segment per scene.

| Scene input | Current behavior |
|---|---|
| Image | Static image or FFmpeg zoom/pan animation |
| Video | Source video normalized to project FPS and fitted/cropped; source loops to fill the scene segment |
| Blank / no media | Black segment |
| Motion | none, zoom_in, zoom_out, pan_left, pan_right |
| Fit | fill (crop to cover) or fit (letterbox) |
| Scene transition | cut or crossfade |

The image motion implementation uses FFmpeg `zoompan`; it is a small set of deterministic camera moves, not a general keyframe system. Scene clips are joined or crossfaded, then muxed with the narration/music audio.

### 1.3 Existing production pipeline

`app/workers/production.py` owns the end-to-end flow:

1. Generate/reuse narration.
2. Calculate the scene timeline from real narration durations and configured scene durations.
3. Build the aligned narration track and optional music mix.
4. Render or reuse cached scene MP4 segments.
5. Join/crossfade the scene segments.
6. Mux video and audio.
7. Validate the temporary final MP4 before publishing it.

The production worker already uses cancellation, per-job temporary files, scene cache validation, and the Universal FFmpeg segment adapter. Phase 2.0 reliability work must remain intact.

## 2. Existing Universal Core foundations

The repository already contains useful extension points:

- `app/universal/models.py` defines versioned scene visual plans, open-ended scene kinds and style tags, engine choices, asset references, camera metadata, and plan status.
- `AssetRef` can carry a stable asset ID, kind, path, identity, license, and metadata.
- `ScenePlan` can carry scene kind, style tags, requirements, camera information, asset references, complexity estimate, and approval/review status.
- `app/universal/engines.py` provides engine descriptors, declared capabilities, compatibility checks, and an explicit registry. The registry does not silently substitute an engine.
- `app/universal/requests.py` defines immutable renderer-independent scene render requests.
- `app/universal/adapters/ffmpeg.py` adapts the existing FFmpeg segment renderer instead of replacing it.
- `app/workers/production.py` currently constructs an engine registry containing the FFmpeg adapter and resolves that adapter for the existing image/video/blank segment kinds.

### Important integration gap

The Universal Core has richer intent and asset contracts than the current production path uses. The production path still builds a legacy `SegmentSpec` from the scene and Studio settings. The current FFmpeg adapter advertises only blank/image/video scene kinds and MP4 output; it does not declare sketch, infographic, map, layered composition, or other motion-graphics capabilities.

This is the key foundation gap: **visual plans, style tags, camera metadata, and asset references are not yet a complete end-to-end authoring-to-rendering workflow.**

## 3. Current limitations confirmed in the production path

The following capabilities are not implemented as part of the current production renderer:

- Multiple independently positioned visual layers within one scene.
- Text, caption, shape, vector, diagram, or infographic overlays as first-class visual elements.
- A reusable sketch/whiteboard drawing engine.
- Map composition and animated map routes.
- General keyframes for position, scale, rotation, opacity, and camera movement.
- 2D character animation, 2.5D parallax layers, or 3D scene rendering.
- Prompt-to-image generation or an image-provider workflow.
- A channel-profile system that automatically maps a channel identity to approved visual rules and scene treatments.
- A dedicated visual asset browser/library with provenance, license checks, and reusable project-level asset management.
- A visual timeline editor for arranging and adjusting multiple layers and transitions.

The current scene `visual_prompt` field is not consumed by the inspected production render path to create or select visual assets. It should not be treated as an implemented prompt-to-visual feature.

## 4. Architectural constraints for Phase 2.1

These constraints are carried forward from the existing project direction:

1. **Preserve the working renderer.** Extend `SegmentSpec`, adapters, or composition stages incrementally; do not replace the FFmpeg production path.
2. **Keep Universal Core renderer-independent.** Core contracts describe intent and capabilities; concrete renderers remain behind adapters.
3. **No silent engine fallback.** A different engine/provider must be explicitly selected or approved.
4. **Local-first and provider-flexible.** The base workflow must remain usable without paid API keys. Optional external AI providers must not become mandatory runtime dependencies.
5. **Hardware-aware.** The initial implementation must run on CPU and provide draft-quality output. GPU support is optional, not a hard requirement. Avoid designs that assume more than the user's 8 GB RAM / NVIDIA 940MX 4 GB system can provide.
6. **Sequential by default.** Do not add parallel scene rendering or a scheduler in this phase. Existing cache and process-safety boundaries remain in force.
7. **Preserve project compatibility.** Prefer using the existing `Project.profile`, `Project.assets`, `Project.director`, and Universal Core format-versioned containers. Any schema change needs a separate compatibility/migration review.
8. **Deterministic and testable.** Rendering requests must be immutable and explicit; outputs must remain cancellable, cache-aware, and validated.
9. **No destructive cleanup.** Never introduce a global cache/temp sweep that could delete another active job's files.

## 5. Recommended incremental roadmap

This audit does not authorize a broad rewrite. The recommended sequence is a series of small, testable vertical slices.

### 2.1-A — Visual plan and asset contract integration

- Trace the existing Universal Core serialization, plan resolver, execution coordinator, and render-request lifecycle end to end.
- Define how a project scene maps to exactly one stable `ScenePlan` without duplicating the existing scene model.
- Define asset resolution/validation behavior for local images and videos, including missing files and changed source identity.
- Define how channel/profile defaults influence style tags and scene requirements while keeping explicit scene-level overrides.
- Keep current project files readable and round-trippable. Do not introduce a schema migration until a concrete incompatibility is demonstrated.

**Exit criteria:** documented data flow, deterministic plan resolution, explicit validation errors, and tests proving old projects still load/save unchanged.

### 2.1-B — First compositing-capable scene renderer

- Add a renderer capability behind the existing adapter/registry boundary.
- Start with a CPU-friendly composition of a background image/video plus simple text and vector/shape overlays.
- Preserve current image/video/blank rendering as the fallback only when explicitly selected or approved.
- Keep output as the same normalized silent scene segment contract so the existing timeline, cache, join, audio, mux, and final validation stages remain reusable.

**Exit criteria:** one scene can render a background plus at least one independently positioned overlay; deterministic output; cancellation; cache identity includes every visual input; integration tests cover final MP4 validation.

### 2.1-C — Reusable visual styles

- Build style primitives from reusable components rather than hard-coded channel-specific render paths.
- Initial candidate styles: documentary collage, sketch/hand-drawn accents, clean infographic, cinematic still-image motion.
- Keep style definitions data-driven and versioned; style presets must not silently rewrite scene assets or narration.

### 2.1-D — Optional visual providers and imports

- Add optional provider interfaces only after the local composition path works.
- Support user-supplied/generated image assets through a provider-neutral asset import contract.
- Record source/provenance/license metadata when known.
- Provider absence, network failure, or missing API keys must not break local rendering.

### 2.1-E — Advanced motion and specialized engines

- Consider keyframed 2D motion, parallax/2.5D, sketch drawing, map animation, and external animation/code imports as separate engines with explicit capabilities and resource estimates.
- Treat 3D and AI video generation as optional heavyweight engines, not baseline dependencies.

## 6. First implementation slice recommended after this audit

The first code PR should **not** attempt prompt-to-video, maps, 2.5D, or a complete timeline editor.

Recommended first slice:

1. Trace and test the existing Universal Core plan → resolver → immutable render request → adapter execution path.
2. Connect one scene's existing `ScenePlan` and `AssetRef` data to the current production worker without changing rendered output.
3. Add compatibility tests proving that projects with no Universal Core plan continue to render exactly as they do now.
4. Add explicit tests for missing/invalid asset references and unsupported engine capability.
5. Keep FFmpeg as the only active production engine until a second renderer is implemented and tested.

This creates a safe seam for later sketch, infographic, 2D/2.5D, map, and provider-based engines without destabilizing the current MP4 workflow.

## 7. Non-goals of this audit

- No runtime code changes.
- No project schema migration.
- No UI redesign.
- No new dependencies or API keys.
- No new concurrency, scheduler, or resource manager.
- No change to the current timeline, timebase, FFmpeg mux, audio mixing, or final MP4 validation policy.

## 8. Verification baseline

The user reported that the latest `main` branch passed the full suite after PR #32:

```
614 passed in 70.84s
```

This audit is documentation-only. No new test run is claimed for this branch.
