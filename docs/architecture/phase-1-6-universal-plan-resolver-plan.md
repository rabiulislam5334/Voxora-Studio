# Phase 1.6 — Universal Scene Plan Resolver

**Status:** Planning document only  
**Base:** `main` after Phase 1.5 runtime contract merge (`65c74210d44e9f7b08aee33f7e687255b86841e3`)  
**Scope:** Convert one existing `ScenePlan` into a deterministic, reviewable engine-resolution result using metadata only. Do not execute an engine or change production rendering.

## 1. Why this phase is needed

The Universal Core now has the required building blocks:

- `ScenePlan`, `EngineChoice`, `AssetRef`, and `UniversalState` in `app/universal/models.py`.
- `EngineCapabilities`, `EngineDescriptor`, and metadata-only `EngineRegistry` in `app/universal/engines.py`.
- `EngineRenderRequest` and `RawEngineOutput` in `app/universal/requests.py`.
- `EngineAdapter` and lazy `EngineRuntimeRegistry` in `app/universal/runtime.py`.
- `SegmentNormalizer` in `app/universal/normalizer.py`.

What is still missing is a small domain layer that reads a scene's visual intent and explains whether its explicitly requested engine is compatible, unavailable, unknown, or still needs a human/director decision.

## 2. Phase 1.6 objective

Introduce a pure, deterministic `EnginePlanResolver` that:

1. Accepts one existing `ScenePlan` and an `EngineRegistry`.
2. Derives the engine requirements from the plan's existing fields.
3. Checks an explicitly selected `engine_choice.engine_id` against registered metadata.
4. Returns a typed resolution result with a clear status and useful reason.
5. Lists compatible alternatives when selection is missing or the requested engine cannot be used.
6. Preserves the explicit fallback chain as reviewable suggestions, never as silent permission to switch engines.

This phase answers **“Which registered engines satisfy this scene's declared requirements, and what decision is still needed?”** It does not answer **“Which engine should AI automatically choose?”**

## 3. Requirement mapping

Use only data already represented by the current model and capability schema:

| ScenePlan source | Resolver requirement |
|---|---|
| `ScenePlan.kind` | `scene_kind` |
| `ScenePlan.style_tags` | Required style tags |
| `ScenePlan.asset_refs[*].kind` | Required asset kinds |
| `ScenePlan.requirements["output_format"]` | Required output format, when present |
| `ScenePlan.engine_choice.engine_id` | Exact requested engine ID |
| `ScenePlan.engine_choice.fallback_chain` | Explicit fallback IDs to inspect and report, in declared order |

For Phase 1.6, `requirements["asset_kinds"]` is not an additional source of truth because asset kinds are already derived from `asset_refs`. If supplied, it must be validated for consistency or reported as an unsupported/contradictory requirement; do not silently merge conflicting declarations.

Unknown requirement keys must be surfaced in the result as unsupported requirements. Do not silently ignore constraints the resolver does not understand.

## 4. Proposed module boundaries

Add only:

- `app/universal/plan_resolver.py`
  - Typed immutable resolution result.
  - Resolver status constants or a small enum.
  - `EnginePlanResolver`, depending on `ScenePlan` and metadata-only `EngineRegistry`.
- `tests/test_universal_plan_resolver.py`
  - Deterministic tests using synthetic descriptors and no real renderer.

Export the public resolver/result types from `app/universal/__init__.py` only if the API is stable and consistent with the existing package exports.

Do not modify the existing model schema merely to make the resolver convenient. If a real model gap is discovered, document it and propose a separate narrowly-scoped change.

## 5. Resolution behavior

### 5.1 Explicit engine selection

When `engine_choice.engine_id` is present:

- Resolve that exact ID using `EngineRegistry.resolve`.
- Pass scene kind, style tags, asset kinds, and optional output format.
- If compatible, return a `compatible` result containing that exact descriptor.
- If unknown, unavailable, or incompatible, return the corresponding explicit status and explanation.
- Never silently replace it with another engine.

### 5.2 Missing engine selection

When `engine_choice.engine_id` is absent:

- Return `selection_required`.
- Include all metadata-compatible candidates in deterministic registry order.
- Do not select the first candidate, rank by engine ID, or infer a preferred engine from channel/profile names.

### 5.3 Explicit fallback chain

- Inspect only IDs explicitly listed in `fallback_chain`.
- Preserve their declared order in the result.
- Include only known, available, capability-compatible fallback descriptors as eligible suggestions; report missing/unavailable/incompatible entries as diagnostics.
- Return a review-required status when a fallback could be used.
- Do not mutate `EngineChoice`, rewrite the primary engine ID, or execute a fallback.
- A future approval workflow must explicitly record the accepted engine choice before execution.

### 5.4 Metadata only

The resolver must use `EngineRegistry`, not instantiate or call `EngineRuntimeRegistry` adapters. It must not import optional renderer packages, touch the filesystem, create render requests, normalize media, or run subprocesses.

A compatible metadata result is **not** proof that an adapter is installed, initialized, or capable of successfully rendering a particular asset. Runtime checks remain the responsibility of Phase 1.5's runtime layer.

### 5.5 Plan status

Preserve and report the plan's current `plan_status`. Do not automatically promote `draft` or `proposed` plans to `approved`. This phase does not authorize rendering or change approval state.

## 6. Result contract and statuses

The immutable result should include, at minimum:

- `scene_id`
- `requested_engine_id` (nullable)
- `plan_status`
- `status`
- `selected_descriptor` (present only when the exact requested engine is compatible; never inferred)
- `compatible_candidates`
- `fallback_candidates` (explicit fallback IDs only)
- `diagnostics` for unknown, unavailable, incompatible, contradictory, or unsupported requirements

Suggested statuses:

- `compatible`
- `selection_required`
- `fallback_review_required`
- `unknown_engine`
- `engine_unavailable`
- `engine_incompatible`
- `invalid_plan`
- `unsupported_requirements`

Keep statuses mutually understandable and avoid a generic success/failure boolean that hides the reason a decision is needed.

## 7. Explicit non-goals

Phase 1.6 does not:

- Add an AI/LLM Production Director or automatic engine ranking.
- Choose or silently activate a fallback engine.
- Instantiate adapters or call `EngineRuntimeRegistry.render()`.
- Connect to the production render button, scheduler, UI, or project save flow.
- Change `ScenePlan`, `EngineChoice`, project serialization, or format version unless a separate justified model change is reviewed.
- Add channel profiles, style taxonomies, scene generation, or prompt generation.
- Add GPU/VRAM detection, resource scheduling, concurrency, cost estimation, or performance scoring.
- Install or benchmark Remotion, HyperFrames, Motion Canvas, Three.js, map renderers, or other engines.
- Modify FFmpeg rendering, cache keys, normalizer, join/mux, audio, captions, or timeline behavior.

## 8. Implementation sequence

### Step A — Contract characterization

- Add focused tests for requirement extraction and each resolution status.
- Cover empty/missing engine selection, unknown IDs, unavailable descriptors, and capability mismatches.
- Cover duplicate/contradictory requirement declarations and unknown requirement keys.
- Verify the resolver does not mutate the input `ScenePlan` or registry.

### Step B — Pure resolver implementation

- Implement the smallest typed result and deterministic resolver.
- Reuse `EngineRegistry.resolve()` and `find_compatible()`; do not duplicate capability matching.
- Keep fallback inspection separate from primary selection.
- Keep metadata resolution separate from runtime adapter initialization.

### Step C — Regression verification

Run focused tests first, then the full suite:

```powershell
python -m pytest -q tests/test_universal_plan_resolver.py tests/test_universal_engines.py tests/test_universal_runtime.py
python -m pytest -q tests
```

Record the actual baseline at implementation time. The latest user-reported baseline after Phase 1.5 is **363 passed, 2 xfailed**. The existing pending asyncio task warning is known and should be tracked separately; do not hide it or weaken tests to remove it.

## 9. Acceptance criteria

Phase 1.6 is complete only when:

- A scene's requirements are derived consistently from the existing `ScenePlan`.
- Explicit engine IDs are checked exactly through the metadata registry.
- Missing selections produce candidate lists without auto-selection.
- Explicit fallback IDs are only surfaced as reviewable candidates and are never silently activated.
- Unknown, unavailable, incompatible, unsupported, and contradictory requirements are clearly diagnosed.
- The resolver is deterministic, side-effect-free, and does not mutate plans or registry state.
- No runtime adapter, renderer dependency, subprocess, filesystem operation, or production render path is invoked.
- Focused and full test suites pass without reducing existing coverage.

## 10. Follow-up boundary

After Phase 1.6 is implemented and verified, a later phase can define an explicit approval/selection boundary between a resolved plan and a runtime render request. Only after that boundary is tested should Voxora consider opt-in orchestration. AI-based scene/engine recommendations, channel-profile preferences, and hardware-aware scheduling should remain separate layers rather than being embedded in this resolver.

## 11. Repository safety rules

- Work on a dedicated feature branch; never commit implementation directly to `main`.
- Preserve untracked local files; do not run `git clean` or broad reset commands.
- Keep implementation changes small and phase-scoped.
- Do not merge a PR until the user explicitly approves it.
