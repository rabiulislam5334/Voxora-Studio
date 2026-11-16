# Phase 1.7 — Universal Scene Execution Coordinator Plan

## Status
Planning proposal only. This phase must not be implemented until this plan is reviewed and approved.

## Base
- Base branch: `main`
- Base commit at plan creation: `516419cd29d888393a7d3bc5864f786e2bb1a60c`
- Prerequisites: Phase 1.4 SegmentNormalizer, Phase 1.5 EngineRuntimeRegistry, Phase 1.6 EnginePlanResolver.

## Objective
Introduce a small, renderer-independent orchestration boundary that takes an already-authored `ScenePlan`, resolves its explicitly selected engine, constructs a validated `EngineRenderRequest` from explicit execution inputs, invokes exactly that runtime adapter, and normalizes its raw artifact through the existing `SegmentNormalizer`.

The coordinator is the first place where the metadata resolver, runtime adapter contract, and shared segment normalizer are composed. It must remain opt-in and must not replace or alter the current production FFmpeg rendering path.

## Proposed public API

Names below are proposals; implementation may adjust names to match repository conventions without expanding scope.

- `SceneExecutionContext` (immutable): execution-only values not currently owned by `ScenePlan`:
  - `output_spec: SegmentOutputSpec`
  - `destination: Path` for the normalized shared segment
  - `engine_params: Mapping[str, Any]`, default empty
- `SceneExecutionResult` (immutable): scene ID, exact engine ID, `EnginePlanResolution`, `RawEngineOutput`, and `NormalizedSegment`.
- `SceneExecutionCoordinator`: receives an `EnginePlanResolver`, `EngineRuntimeRegistry`, and `SegmentNormalizer`; exposes one synchronous `execute(plan, context, *, on_progress=None, cancel=None)` method.

The coordinator should derive scene kind, style tags, asset references, and output format from the validated `ScenePlan`. It must derive duration/dimensions/FPS and destination only from the explicit context. It must not infer missing render settings from channel profiles, project globals, hardware, or hidden defaults.

## Required execution flow

1. Validate the input types and required execution context.
2. Resolve the plan with `EnginePlanResolver` before initializing any adapter.
3. Continue only when the resolution is `COMPATIBLE` and has the exact selected descriptor. For all other statuses, raise a typed coordinator error carrying the resolution and diagnostics.
4. Construct `EngineRenderRequest` from the plan plus explicit context. Use `plan.requirements.output_format`; if it is absent, fail with a clear validation error rather than silently assuming a format.
5. Call `EngineRuntimeRegistry.render` using the exact `plan.engine_choice.engine_id`. Never auto-select a candidate or execute a fallback suggestion.
6. Pass the same cancellation token through runtime rendering and normalization.
7. Pass progress through a documented monotonic stage mapping: renderer occupies the first 80% and normalization the final 20%. Validate/handle callback values defensively; never allow progress reporting to change render correctness.
8. Normalize the raw engine output with the existing `SegmentNormalizer` and explicit `SegmentOutputSpec`.
9. Return a result containing both raw and normalized output metadata.

## Errors and cancellation
- Add a small coordinator-specific exception hierarchy (base execution error plus plan-resolution/validation errors) or an equivalently clear typed error contract.
- Preserve the original cause when wrapping adapter or normalizer exceptions.
- Do not swallow cancellation. Propagate the repository's existing `CancelToken` behavior and cleanup guarantees.
- Do not delete the raw renderer output: ownership and retention policy are not defined in this phase.
- Do not publish a successful result until normalization has completed successfully.
- Do not add automatic retry, engine fallback, or partial-success semantics.

## Progress contract
- Document callback values as normalized floats in the inclusive range 0.0–1.0.
- Map renderer progress `p` to `0.8 * p`; map normalizer progress `p` to `0.8 + 0.2 * p`.
- Clamp finite numeric progress to the valid range and ignore invalid/non-finite callback values rather than failing the render.
- Ensure the final callback is 1.0 only after successful normalization. Callback exceptions should be isolated from execution (or explicitly documented if repository conventions require propagation); they must not corrupt or cancel the render.

## Tests
Use synthetic descriptors, fake adapters, and a fake normalizer/FFmpeg boundary. Tests must not invoke real renderers or perform heavyweight media encoding.

Required coverage:
- Compatible plan executes only its explicitly selected engine.
- Resolver failure statuses prevent adapter factory initialization and rendering.
- Unknown, unavailable, incompatible, missing selection, unsupported requirements, and invalid plan errors preserve useful diagnostics.
- No compatible candidate or fallback is silently selected.
- Request construction uses plan-owned scene/style/assets/output format and context-owned output spec/destination/engine params.
- Missing output format is rejected explicitly.
- Runtime render receives the expected request, progress callback, and cancellation token.
- Normalizer receives the raw path, exact destination/spec, progress callback, and same cancellation token.
- Progress mapping is monotonic and reaches 1.0 only on success; invalid callback values and callback exceptions cannot break rendering.
- Adapter and normalizer failures preserve causes; cancellation propagates; no success result is returned on failure.
- Raw output is not deleted by the coordinator.
- Input plan, registry metadata, and caller-provided context mappings are not mutated.
- Existing resolver/runtime/normalizer tests and the full suite remain green.

## Non-goals and safety boundaries
- No integration with the current production renderer, UI, project lifecycle, or channel profiles.
- No changes to existing FFmpeg render commands, segment cache keys, assembler, audio pipeline, or current rendering behavior.
- No scheduler, job queue, parallel scene execution, resource manager, GPU detection, memory budgeting, or retry policy.
- No automatic engine selection, fallback execution, or engine installation.
- No new renderer/provider dependencies and no heavyweight media benchmarks.
- No deletion/retention policy for raw engine artifacts.
- No schema migration or changes to `ScenePlan`, `EngineRenderRequest`, or `RawEngineOutput` unless a concrete compatibility issue is demonstrated and separately approved.

## Acceptance criteria
- The coordinator composes resolver → exact runtime engine → normalizer in one deterministic synchronous call.
- Adapter factories are not initialized before plan resolution succeeds.
- Only explicit user/director engine selection is executed; fallback remains review-only.
- A successful return always contains a verified `NormalizedSegment`.
- Cancellation, error causes, progress, and artifact ownership are explicit and tested.
- No production rendering path or cache behavior changes.
- Focused tests and the full existing test suite pass locally before merge.
