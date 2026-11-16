# Phase 1.5 — Runtime Engine Adapter Contract & Binding

**Status:** Planning document only  
**Base:** `main` at `9743c8a8eb8c35ef919da04cee3344cea9fcdd56`  
**Scope:** Define and test the runtime boundary between engine metadata and executable adapters. Do not route production rendering through this layer in Phase 1.5.

## 1. Why this phase is needed

The Universal Core already contains:

- `EngineCapabilities`, `EngineDescriptor`, and metadata-only `EngineRegistry` in `app/universal/engines.py`.
- Versioned `AssetRef`, `EngineChoice`, `ScenePlan`, and `UniversalState` models in `app/universal/models.py`.
- `FFmpegSegmentAdapter` in `app/universal/adapters/ffmpeg.py`, which delegates to the existing `SegmentSpec` and `build_segment_args`.
- `SegmentNormalizer` in `app/universal/normalizer.py`, which converts raw renderer output into the shared silent MP4 segment contract.

Therefore Phase 1.5 must **not recreate** the engine registry, scene-plan models, FFmpeg adapter, or segment normalizer. The missing boundary is the runtime binding that maps a registered engine ID to a lazily-created executable adapter while keeping metadata discovery separate from renderer execution.

## 2. Phase 1.5 objective

Introduce a small, renderer-independent runtime contract that can:

1. Accept a validated render request for one scene.
2. Resolve the explicitly requested engine ID to an executable adapter.
3. Verify requested scene/style/asset/output capabilities against the adapter descriptor.
4. Execute with progress and cancellation forwarding.
5. Return a clearly defined raw engine-output result for a later normalization step.
6. Fail explicitly for unknown, unavailable, incompatible, or failed engines.

The runtime must never silently switch engines. Any fallback must be an explicit, user/director-approved choice represented in the scene's `EngineChoice`.

## 3. Proposed module boundaries

Keep the existing modules and add only the minimum required files:

- `app/universal/runtime.py`
  - Runtime adapter protocol.
  - Runtime registry / binding object.
  - Typed runtime errors only if existing registry errors cannot express the failure.
- `app/universal/requests.py`
  - Immutable render request and raw engine-output result contracts, if these do not fit cleanly in `runtime.py`.
- `tests/test_universal_runtime.py`
  - Contract, binding, compatibility, progress, cancellation, and failure tests.

Do not create a large generic plugin framework, dependency-injection container, event bus, or scheduler in this phase.

## 4. Contract design requirements

### 4.1 Render request

The request should carry only data needed to render one scene:

- Stable `scene_id`.
- Scene kind and requested style tags.
- Asset references (reuse the existing `AssetRef` model).
- Output specification (reuse `SegmentOutputSpec` where its semantics fit).
- Engine-specific parameters in a clearly namespaced mapping.
- Destination/work directory.
- Optional progress callback and cancellation token passed at execution time, not serialized into project settings.

Validate required identifiers and output properties before calling an adapter. Do not pass mutable project/UI objects into an engine.

### 4.2 Adapter protocol

An executable adapter should expose:

- A stable `EngineDescriptor` (the existing descriptor; do not duplicate it).
- One render operation accepting the request and optional progress/cancellation controls.
- A typed raw-output result identifying the produced file and any trustworthy measured metadata.

The adapter contract must not own timeline assembly, narration, audio mixing, final muxing, captions, or project persistence.

### 4.3 Runtime registry

Keep `EngineRegistry` as metadata-only discovery and compatibility lookup. Add a separate runtime binding layer that:

- Binds an engine ID to an adapter instance or lazy factory.
- Rejects duplicate bindings unless replacement is explicitly requested.
- Confirms the adapter's descriptor ID matches the binding key.
- Resolves the requested ID exactly and checks declared capabilities.
- Distinguishes unknown, unavailable, and incompatible engines.
- Does not import optional renderer packages during `import app.universal`.
- Does not instantiate all engines during application startup.
- Does not choose an alternative when the requested engine is unavailable.

### 4.4 Output normalization boundary

The adapter returns raw engine output. The shared `SegmentNormalizer` remains the single normalization boundary for engines that need conversion to Voxora's silent MP4 segment format.

Do not normalize an output twice. If a future adapter already produces a verified normalized segment, that behavior must be explicit in its result contract and validated without running a second encode.

### 4.5 Existing FFmpeg compatibility

The current `FFmpegSegmentAdapter.render_segment(SegmentSpec, destination, ...)` must remain behaviorally unchanged in this phase.

Do not replace `app.video.render`, `build_segment_args`, the existing FFmpeg production path, join/mux, cache, or timeline logic. If adapting the legacy FFmpeg adapter to the new protocol would require changing its semantics, defer that bridge to a separately tested follow-up phase.

## 5. Explicit non-goals

Phase 1.5 does not:

- Connect the Universal Core to the production render button or scheduler.
- Change existing FFmpeg rendering, cache keys, join/mux, audio, captions, or timeline behavior.
- Install Remotion, HyperFrames, Motion Canvas, Three.js, map renderers, browsers, or other engines.
- Add GPU detection, resource scheduling, concurrency management, or automatic quality selection.
- Implement a Production Director, scene planner, channel profile manager, or UI.
- Add automatic fallback or retry with a different engine.
- Run real renderer benchmarks or full video renders.

## 6. Implementation sequence

### Step A — Contract characterization

- Read current engine/model/normalizer/adapter contracts before coding.
- Add tests describing request validation and raw-output semantics.
- Confirm imports remain lightweight and optional renderer packages are not imported.

### Step B — Runtime adapter protocol

- Add the smallest typed protocol and request/result models.
- Keep callbacks and cancellation outside serialized project state.
- Ensure adapter results identify raw output without falsely claiming normalized properties.

### Step C — Runtime binding registry

- Add deterministic registration, lookup, and exact resolution.
- Verify descriptor/binding identity and capability compatibility.
- Keep metadata-only `EngineRegistry` API backward-compatible.

### Step D — Fake-adapter integration tests

Test at minimum:

- Successful registration and deterministic lookup.
- Duplicate registration and explicit replacement.
- Descriptor ID mismatch.
- Unknown, unavailable, and incompatible engine failures.
- No implicit fallback.
- Progress and cancellation forwarding.
- Adapter exceptions propagate with useful context.
- Raw output path/result validation.
- Lazy factory is not called until the engine is resolved/executed.
- Importing Universal Core does not import optional rendering packages.

### Step E — Regression verification

Run focused tests first, then the full suite:

```powershell
python -m pytest -q tests/test_universal_runtime.py tests/test_universal_engines.py tests/test_universal_ffmpeg_adapter.py tests/test_universal_segment_normalizer.py
python -m pytest -q tests
```

Keep the current baseline of **343 passed, 2 xfailed** as the regression reference. Any changed baseline must be explained by an intentional test change, not hidden or casually updated.

## 7. Acceptance criteria

Phase 1.5 is complete only when:

- Runtime contracts are typed, small, and documented.
- Runtime binding is separate from metadata discovery.
- Engine selection is exact; no silent fallback exists.
- Adapter creation is lazy and optional dependencies remain optional.
- Progress and cancellation are forwarded unchanged.
- Raw outputs and normalized outputs cannot be confused.
- Existing FFmpeg adapter and production rendering behavior remain unchanged.
- Focused and full test suites pass.
- No renderer dependency is installed and no real video benchmark is run.

## 8. Follow-up boundary

After Phase 1.5 is merged and verified, a later phase may add a **non-production bridge** from the existing FFmpeg adapter to the runtime protocol, followed by an independently reviewed opt-in render orchestration path. Only after that path is proven should additional engines (2D, 2.5D, 3D/scientific, map/geography, documentary/infographic) be added one at a time.

## 9. Repository safety rules

- Work on a dedicated feature branch; never commit implementation directly to `main`.
- Preserve untracked local files; do not run `git clean` or broad reset commands.
- Keep each implementation PR small and phase-scoped.
- Do not merge a PR until the user explicitly approves it.
