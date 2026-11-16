# Phase 1.8 — Multi-Scene Execution Orchestration Plan

## Status

**Proposal only — documentation and architecture review. No implementation is included in this phase plan.**

Base: `main` after Phase 1.7 merge.

## 1. Purpose

Phase 1.7 provides a reliable opt-in execution path for one explicitly planned scene:

`ScenePlan → EnginePlanResolver → EngineRuntimeRegistry → SegmentNormalizer → NormalizedSegment`

A video project contains many scenes. Phase 1.8 should define the smallest safe layer that executes an ordered collection of scenes through the existing single-scene coordinator, without turning that layer into a scheduler or changing the production renderer.

The proposed deliverable is a **Multi-Scene Execution Coordinator** with deterministic, sequential, fail-fast behavior.

## 2. Goals

- Execute an explicitly supplied ordered sequence of scene plans.
- Reuse the existing `SceneExecutionCoordinator` for every scene; do not duplicate engine resolution, rendering, or normalization logic.
- Require an explicit execution context for every scene.
- Preserve input order and produce an ordered collection of successful scene results.
- Aggregate per-scene progress into monotonic batch progress.
- Forward the same cancellation token to each scene execution and stop before starting another scene when cancellation is observed.
- Make partial completion and the failing scene identifiable when a batch fails.
- Keep the API independent of UI, project persistence, channel profiles, and the legacy FFmpeg production pipeline.

## 3. Non-goals

This phase must not introduce:

- Parallel or concurrent scene rendering.
- A scheduler, worker pool, queue, priority system, or resource manager.
- GPU/VRAM/CPU/RAM detection or admission control.
- Automatic engine selection, fallback execution, retries, or silent scene skipping.
- Cross-scene dependency graphs, dynamic reordering, or automatic stop reordering.
- New render engines or renderer-specific dependencies.
- A new UniversalState schema, project-settings migration, or persistent execution history.
- Cache policy changes, cache-key changes, or automatic deletion of raw engine outputs.
- UI integration or wiring into the current production rendering pipeline.

These capabilities may be considered in later phases after their requirements and resource constraints are separately designed.

## 4. Proposed public contracts

Names below are proposals and may be adjusted during implementation review.

### 4.1 MultiSceneExecutionRequest

An immutable request containing:

- An ordered tuple of `ScenePlan` objects.
- A mapping from each scene ID to its explicit `SceneExecutionContext`.
- Optional batch-level progress callback and cancellation token supplied to the coordinator method rather than persisted in the request.

Validation should reject an empty plan collection, duplicate/blank scene IDs, non-`ScenePlan` entries, missing contexts, unexpected context keys, and invalid context values before the first scene starts.

The caller owns ordering. The coordinator must never sort or infer scene order from IDs, script text, duration, channel profile, or engine capabilities.

### 4.2 MultiSceneExecutionResult

An immutable successful result containing:

- Ordered per-scene `SceneExecutionResult` values.
- The ordered scene IDs corresponding to those results.
- A final completed count equal to the request scene count.

A successful batch result is returned only when every requested scene has rendered and normalized successfully.

### 4.3 MultiSceneExecutionError

A batch-level error should identify:

- The failed scene ID and its zero-based position.
- The successfully completed results before the failure, in original order.
- The original scene-level exception as the chained cause.

The coordinator must fail fast. It must not continue to later scenes after a scene fails. Already completed normalized outputs are not rolled back or deleted.

Cancellation should remain distinguishable from ordinary execution failure. If cancellation occurs during a scene, propagate the existing `GenerationCancelled` behavior; if cancellation is already requested between scenes, do not start the next scene.

## 5. Execution semantics

1. Validate the entire batch request before executing any scene.
2. Iterate plans in caller-supplied order.
3. Before each scene, check cancellation when a token is supplied.
4. Execute the scene using the existing `SceneExecutionCoordinator.execute()` with its matching context.
5. Append a result only after that scene has completed normalization successfully.
6. Report aggregate progress after scene-level progress updates.
7. Stop immediately on cancellation or the first scene failure.
8. Return the batch result only after all scenes succeed.

No scene may execute with an implicit context, an inferred engine, or a substituted engine.

## 6. Progress model

Use a deterministic equal-scene weighting model for this phase:

`batch_progress = (completed_scene_count + current_scene_progress) / total_scene_count`

- Progress is monotonic and constrained to `[0.0, 1.0]`.
- Scene progress comes from the existing single-scene coordinator.
- A scene counts as completed only after normalization succeeds.
- Emit `1.0` only after every requested scene succeeds.
- Invalid/non-finite callback values and observer callback exceptions must not affect execution.
- Do not estimate or infer scene duration or computational cost for weighting in this phase.

Equal weighting is intentionally simple and deterministic. Duration- or resource-weighted progress can be reconsidered when reliable estimates exist.

## 7. Failure, cancellation, and artifact policy

- Fail-fast is the only batch failure policy in Phase 1.8.
- No automatic retry, skip, fallback engine, or rollback.
- Preserve successful normalized outputs from earlier scenes.
- Preserve raw engine outputs according to the existing single-scene contract.
- Do not clean up caller-owned inputs or previously completed artifacts.
- Forward the caller's cancellation token unchanged to each single-scene execution.
- Do not swallow `GenerationCancelled`.

## 8. Resource and concurrency policy

Execution is strictly sequential in Phase 1.8. This is a deliberate safety boundary, not a permanent limitation.

The current engine descriptors already expose optional metadata such as GPU requirements, maximum concurrent jobs, and estimated memory. Phase 1.8 must not pretend those fields are sufficient for safe resource scheduling. A future resource-management design must define measurement, reservations, release behavior, cancellation, and engine-specific constraints before concurrency is introduced.

Sequential execution also keeps the implementation suitable for Voxora's current low-memory development hardware and avoids destabilizing the existing FFmpeg pipeline.

## 9. Testing strategy

Use fake scene adapters and a fake normalizer. Tests must not invoke real FFmpeg, download models, initialize GPU engines, or create expensive media.

Required coverage:

- Ordered execution of multiple scenes through the existing single-scene coordinator.
- Correct context association by scene ID.
- Full-batch validation before any adapter is invoked.
- Empty input, duplicate IDs, missing/extra contexts, and invalid plan/context rejection.
- Monotonic aggregate progress across scene boundaries.
- Final progress of 1.0 only after all scenes succeed.
- Callback exceptions and invalid progress values do not fail execution.
- Cancellation before the first scene, between scenes, and during a scene.
- Fail-fast behavior and accurate failed-scene index/ID.
- Partial results retain only fully completed scenes.
- No fallback, retry, skip, reordering, or parallel execution.
- Raw and normalized artifact ownership remains consistent with Phase 1.7.

Run focused tests for the new coordinator and all related Universal Core tests, followed by the complete `python -m pytest -q tests` suite.

## 10. Acceptance criteria

Phase 1.8 implementation may be considered complete only when:

- The public batch contracts are documented and exported consistently.
- All batch inputs are validated before the first scene begins.
- Every scene is executed through the existing single-scene coordinator.
- Execution order is deterministic and sequential.
- Progress, cancellation, partial completion, and fail-fast semantics match this document.
- Focused and full test suites pass locally.
- Existing production rendering, project persistence, and cache behavior remain unchanged.
- No new third-party dependency is introduced.

## 11. Expected change boundary

Expected implementation scope, subject to review:

- A new focused module such as `app/universal/multi_execution.py`.
- Public exports in `app/universal/__init__.py`.
- Isolated tests such as `tests/test_universal_multi_execution.py`.

No existing production renderer, UI, project model, cache manager, or FFmpeg assembly module should be modified unless a separately reviewed requirement proves it necessary.

## 12. Review questions before implementation

1. Is ordered, sequential, fail-fast batch execution the correct first multi-scene abstraction?
2. Is equal-scene progress weighting acceptable until trustworthy duration/resource estimates exist?
3. Should a batch failure expose completed results through the exception, rather than returning a partially successful result type?
4. Are there any existing project-level ordering or cancellation contracts that must be reflected before implementation?

**Implementation must not begin until the plan is reviewed and approved.**
