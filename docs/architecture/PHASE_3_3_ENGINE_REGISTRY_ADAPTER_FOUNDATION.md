# Phase 3.3 — Engine Registry & Adapter Foundation

**Status:** Architecture plan  
**Parent architecture:** Universal Creative Production Architecture  
**Depends on:** Phase 3.1 scene-plan proposal and safe apply; Phase 3.2 Channel Profile System  
**Scope:** Engine metadata, adapter contracts, registration, capability resolution, and safe execution boundaries.

## 1. Objective

Make Voxora's production engines independently registerable and replaceable without coupling Channel Profiles, Universal Core, or the shared production pipeline to a specific visual style or channel.

A channel profile may express preferred engine IDs, but it must never create an engine, silently select an unavailable engine, or force an incompatible engine. Engine availability and compatibility are resolved by the engine registry and runtime layer. The user retains control over the final engine choice.

The registry must support future production families such as:

- Documentary and collage workflows
- Stickman and flat-vector explainers
- 2D cartoon storytelling
- 2.5D illustration and motion graphics
- 3D/4D scientific and technical visualization
- Real-map and geographic visualization
- Sketch and illustration workflows
- Character performance, expression, gesture, and lip-sync workflows

These are capability/workflow families, not channel-specific hard-coded branches. A single engine may support multiple families, and a family may have multiple engine implementations.

## 2. Current implementation inventory

The repository already contains meaningful parts of this foundation. Phase 3.3 must extend these components rather than create a competing registry.

| Existing component | Current responsibility |
|---|---|
| `app/universal/engines.py` | Immutable `EngineCapabilities` and `EngineDescriptor`; metadata-only `EngineRegistry`; deterministic listing, compatibility search, and exact-ID resolution |
| `app/universal/runtime.py` | `EngineAdapter` protocol; lazy adapter factories; runtime binding validation; execution and raw-output contract checks |
| `app/universal/requests.py` | Immutable render request and raw engine output contracts |
| `app/universal/plan_resolver.py` | Scene-plan engine choice and capability resolution; no silent fallback |
| `app/universal/execution.py` | Opt-in single-scene execution orchestration and shared normalization |
| `app/universal/multi_execution.py` | Opt-in multi-scene execution orchestration |
| `app/universal/adapters/ffmpeg.py` | Bridge to the existing FFmpeg segment renderer; currently exposes the legacy segment/request rendering methods |
| `app/universal/normalizer.py` | Shared normalized segment output contract |
| `tests/test_universal_engines.py`, `test_universal_runtime.py`, `test_universal_plan_resolver.py`, `test_universal_execution.py` | Existing contract and safety coverage |

Important integration gap: the runtime protocol expects an adapter with `render(request, ...)` returning `RawEngineOutput`, while the existing FFmpeg adapter currently exposes `render_request(...)` and `render_segment(...)` and returns a rendered path. The first implementation slice should resolve this boundary explicitly without changing the legacy renderer's output, timing, cancellation, cache, audio, or export behavior.

## 3. Architectural boundaries

### Engine descriptor and metadata registry

Owns stable, serializable metadata:

- Stable `engine_id`, display name, and implementation version.
- Declared scene kinds, style tags, asset kinds, and output formats.
- Runtime requirements such as GPU needs and resource estimates where known.
- Draft-render and concurrency declarations.
- Availability state and a human-readable unavailable reason.

Descriptors are declarations, not proof that an engine works. Runtime initialization and request validation remain separate.

### Runtime adapter registry

Owns the mapping from an exact engine ID to an adapter instance or lazy factory.

- Factories remain lazy; merely opening the app or listing engines must not initialize heavy dependencies.
- Adapter descriptor ID must match the registered ID.
- Missing, unavailable, or incompatible engines fail explicitly.
- No implicit fallback or substitution.
- Initialization failures must be reported with engine context.
- Runtime adapters must not mutate the project or rewrite scene plans.

### Adapter contract

An adapter receives one immutable `EngineRenderRequest`, optional progress callback, and cancellation token, then returns a `RawEngineOutput`.

The adapter must:
- Validate its own engine-specific parameters and inputs.
- Write only to the requested raw-output destination or a clearly declared safe output path.
- Report progress monotonically when possible; malformed observer callbacks must not corrupt execution.
- Honor cancellation where its underlying implementation permits.
- Avoid modifying the shared timeline, project, scene plan, or normalized output.
- Include enough metadata to identify the engine/version and relevant output properties.
- Raise typed, contextual errors rather than silently changing render modes.

The shared normalizer remains responsible for converting supported raw outputs to the common segment format. The shared FFmpeg production pipeline remains responsible for final assembly, audio mixing, synchronization, validation, and export.

### Channel Profile integration

Profile preferences are advisory metadata only. Resolution order must be explicit:

1. Validate the selected scene plan and its requirements.
2. Check the explicitly selected engine ID.
3. Check declared capabilities and current availability.
4. Return compatible alternatives as suggestions only, if requested.
5. Require a separate user decision to change the selected engine.

A preferred engine must never override a scene-level explicit selection.

## 4. Safety, portability, and resource policy

- No arbitrary Python source, shell commands, or untrusted executable plugin manifests.
- No automatic import of every installed Python package during registry discovery.
- No network download or model installation during engine listing or project opening.
- Optional engines must degrade to an explicit unavailable state when dependencies or hardware are missing.
- CPU fallback must be declared by the adapter; do not infer it from a GPU failure.
- GPU requirements, estimated memory, concurrency, and draft-render support are advisory resource declarations and must not be treated as guaranteed performance.
- On low-resource machines, default execution remains sequential unless a separately tested policy explicitly permits concurrency.
- External AI/model adapters are future optional integrations; local-first and offline-safe workflows remain available.
- Engine errors and logs must not expose API keys, credentials, or private prompt data.

## 5. Implementation slices

### 3.3a — Runtime Adapter Contract & FFmpeg Bridge

- Audit the existing request, runtime, normalizer, and FFmpeg adapter contracts.
- Implement the narrowest adapter bridge so the existing FFmpeg segment renderer can participate in the runtime contract.
- Preserve exact legacy segment rendering behavior and keep the bridge opt-in.
- Define raw output metadata and destination semantics.
- Add tests for success, invalid request, missing output, cancellation forwarding, progress forwarding, and output-path safety.
- Do not wire the new execution coordinator into the default Studio render path.

### 3.3b — Built-in Engine Registration

- Add an explicit built-in registration composition root.
- Register only adapters whose dependencies are available or expose them as unavailable with a reason.
- Keep registry construction deterministic and lightweight.
- Verify repeated initialization does not duplicate or unexpectedly replace bindings.
- Do not auto-discover/import arbitrary third-party code.

### 3.3c — Capability & Resource Resolution

- Extend resolution only where concrete missing requirements are identified by tests.
- Preserve exact engine selection and no-silent-fallback behavior.
- Return structured compatibility/unavailability diagnostics suitable for UI.
- Keep resource estimates advisory; no automatic parallel rendering.

### 3.3d — Profile Preference Resolution

- Read profile preferred-engine IDs as suggestions.
- Distinguish preferred, compatible, unavailable, and incompatible engines.
- Never mutate a scene plan or replace an explicit engine choice.
- Require explicit user confirmation for any engine-choice change.

### 3.3e — Engine Catalog & UI Integration

- Present engine name, availability, capabilities, and diagnostics.
- Show compatible alternatives without silently selecting them.
- Keep engine configuration separate from channel profile editing.
- Avoid adding UI until the underlying contracts and registration tests are stable.

### 3.3f — Workflow Engine Foundations

After the registry and adapter contracts are stable, introduce reusable workflow adapters/capability groups for 2D, 2.5D, 3D/4D, map, documentary, and character-performance production. Each workflow must be independently testable and must use the same Universal request/output boundaries.

## 6. Compatibility requirements

- No Project schema bump for registry/adapter metadata.
- No changes to legacy `.voxora` serialization unless a separate migration is designed and approved.
- No automatic scene, asset, narration, prompt, or render-setting rewrites.
- No change to the existing FFmpeg render pipeline, audio mixing, synchronization, cache identity, timeline timebase, or cancellation semantics.
- Existing projects without an explicit engine selection must continue to behave as they do today.
- New adapter execution remains opt-in until it has parity tests and an explicit integration decision.

## 7. Acceptance criteria

- An adapter can be registered by exact engine ID without editing Universal Core models or the renderer.
- Metadata discovery does not initialize adapters.
- Runtime factories are lazy and validated before execution.
- Engine capability checks are deterministic and explicit.
- No engine is silently substituted.
- The FFmpeg bridge passes the runtime contract while preserving legacy segment behavior.
- Cancellation, progress, output validation, and normalization boundaries are covered by tests.
- Optional engines can be unavailable without preventing the app from starting.
- Windows and Ubuntu CI remain green.
- No default render-path behavior changes in this phase.

## 8. Out of scope

- Building a full 2D cartoon, Stickman, 2.5D, or 3D renderer.
- Bundling large AI models or requiring paid API keys.
- Automatic model downloads or arbitrary plugin execution.
- Prompt-to-Video generation or an AI Director implementation.
- Parallel rendering by default.
- Changing the default Studio render pipeline or replacing FFmpeg.

## 9. Immediate next step

Implement **Phase 3.3a — Runtime Adapter Contract & FFmpeg Bridge** as a focused, test-first pull request. Before changing code, inspect the complete current `RawEngineOutput`, `EngineRenderRequest`, `FFmpegSegmentAdapter`, and runtime validation contracts. The implementation must remain additive and opt-in.
