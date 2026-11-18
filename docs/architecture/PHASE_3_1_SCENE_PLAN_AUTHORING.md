# Phase 3.1 — Universal Scene Plan Authoring

**Status:** Design proposal  
**Target:** First implementation slice of Phase 3  
**Base:** Phase 2 mainline after the real Windows render acceptance check  
**Principles:** local-first, deterministic, hardware-aware, reviewable, backward-compatible, sequential

## 1. Purpose

Phase 2 established versioned Universal Core contracts and a production bridge, but it deliberately deferred first-class plan authoring. Phase 3.1 introduces the first authoring workflow: turn an existing script or a set of authored project scenes into an editable, reviewable Universal Scene Plan without changing the proven FFmpeg production path.

The first slice must be useful without a cloud service, paid API key, or local AI model. It must not pretend that deterministic text splitting can understand visual semantics. Automatic creative visual direction and image generation belong to later slices.

## 2. Current architecture to preserve

- `Project.scenes` is the canonical ordered narration/script source. Each `Scene` already has a stable ID, title, text, notes, visual prompt, and order.
- Universal data is stored additively under `Project.settings["universal"]`, independently from legacy `Project.settings["studio"]`.
- `UniversalState`, `ScenePlan`, `AssetRef`, and `EngineChoice` are the existing versioned contracts in `app/universal/models.py`.
- `build_production_render_request()` bridges an explicit per-scene plan to the existing FFmpeg path. Legacy projects continue through the compatibility path.
- Project schema v4 and existing serialization/migration behavior must remain unchanged unless a separately reviewed migration is proven necessary.
- Existing rendering, audio timing, cache identity, timebase, and final MP4 validation must not be modified by this authoring slice.

## 3. User workflow

1. User opens or creates a project and supplies a script, or uses scenes already in the project.
2. User chooses a deterministic split strategy:
   - **Existing scenes:** use current project scene boundaries exactly.
   - **Paragraphs:** split on blank-line paragraph boundaries.
   - **Explicit marker:** split only on a documented marker supplied by the user.
   - **Manual:** create one scene from the supplied text; the user can split/edit scenes afterward.
3. Voxora presents a draft scene list. It does not silently replace existing scenes.
4. User reviews and edits scene title, narration text, visual prompt/notes, visual kind, style tags, and estimated duration.
5. User explicitly applies the proposal to the project.
6. The accepted plan is persisted under the Universal settings namespace and remains editable before production.

## 4. First-slice scope

### Included

- A pure, UI-independent authoring service that transforms script input or existing scenes into a deterministic proposal.
- Explicit split options and validation; no hidden AI or network calls.
- Stable scene ordering and fresh stable IDs for newly proposed scenes.
- Word-count-based duration estimates using an explicit configurable narration rate. Estimates must be labeled as estimates and must never overwrite measured/generated audio duration.
- A draft `ScenePlan` for each proposed scene, keyed by the corresponding scene ID, with conservative defaults:
  - `kind="unspecified"` unless the user explicitly chooses a supported kind.
  - no engine selection by default;
  - `plan_status="proposed"` until the user accepts it;
  - user-selected profile/style metadata only; no invented assets.
- A validation/report layer that explains empty scenes, duplicate IDs, invalid options, and unsupported values before apply.
- Explicit apply operation that updates project scenes and UniversalState together in memory, preserves unrelated project settings (especially `studio`), and prunes stale scene plans only as part of the same accepted operation.
- Focused unit tests for deterministic splitting, estimates, ID/key consistency, deep-copy behavior, invalid inputs, read-only future Universal payloads, and settings preservation.
- Documentation and a small integration seam for a later UI.

### Not included

- LLM-based script interpretation or automatic creative shot writing.
- Image generation, web image search, stock-media downloads, or asset licensing automation.
- New renderer providers, automatic engine fallback, parallel rendering, or scheduling.
- Timeline editing, preview playback, subtitles, or advanced audio mixing.
- Heavy local models or GPU workloads.
- Any change to the current FFmpeg render/export path.

## 5. Proposed data and service boundaries

Keep the existing `Scene` and `ScenePlan` contracts as the persisted domain model. Add a dedicated authoring module (proposed location: `app/universal/authoring.py`) containing small, testable types such as:

- `SceneAuthoringOptions`: split strategy, explicit marker, words-per-minute, and conservative defaults.
- `SceneDraft`: proposed scene content plus estimated duration metadata.
- `ScenePlanProposal`: ordered scene drafts, per-scene visual plans, validation diagnostics, and source fingerprint.
- `build_scene_plan_proposal(...)`: pure deterministic proposal builder.
- `apply_scene_plan_proposal(project, proposal)`: explicit, validated apply operation; never called implicitly during project open or render.

Before implementation, inspect the existing narration parser/chunker and project/UI mutation patterns. Reuse them only where their semantics match the explicit split options; do not introduce a second competing chunking policy.

### Timing representation

Use the project's canonical tick timebase for persisted timing values. The initial proposal may carry an estimated duration in proposal metadata or a separately named authoring field; do not overload renderer `requirements` or imply that estimated duration is authoritative render timing. The implementation review must settle the smallest additive representation and test round-trip preservation before writing it.

### IDs and atomicity

New scene IDs must be generated once when a proposal is created and remain stable while the proposal is reviewed. Applying the same proposal twice must be rejected or be explicitly idempotent; it must not duplicate scenes. Apply must validate all IDs and plan references before mutating the project. A failed apply must leave the original project and settings unchanged.

## 6. Compatibility and safety requirements

- Do not alter `Project.schema_version` or existing .voxora fixtures in the first slice.
- Preserve all unknown Universal payload fields. If UniversalState is read-only because it contains a future or malformed payload, authoring/apply must fail clearly and must not overwrite it.
- Preserve legacy `studio` settings byte-for-byte at the data-structure level.
- Do not silently choose an engine or fallback. Engine selection remains a separate explicit review action.
- Do not create placeholder AssetRef entries for assets that do not exist.
- Keep UI and rendering imports out of the pure authoring module.
- Avoid network, subprocess, TTS, FFmpeg, and GPU calls in proposal generation.
- Keep all work sequential and deterministic.

## 7. Acceptance criteria

1. The same input and options produce equivalent ordered scene content and duration estimates (IDs are stable within a proposal, not necessarily across separate proposal builds).
2. Paragraph, explicit-marker, existing-scene, and manual split modes have documented edge-case behavior.
3. Empty input and empty segments are reported without creating invalid project scenes.
4. Duration estimates use a documented word-count formula, explicit WPM, and canonical tick conversion; rounding behavior is tested.
5. Every proposed ScenePlan key matches its Scene ID and begins in `proposed` state.
6. No engine is implicitly selected and no asset is fabricated.
7. Apply is all-or-nothing, preserves unrelated settings, and cannot overwrite a read-only Universal payload.
8. Reapplying the same proposal cannot duplicate scenes.
9. Existing legacy project fixtures and all current tests remain unchanged and pass.
10. The current desktop render path produces the same behavior for projects that do not use the new authoring workflow.

## 8. Implementation sequence

- **3.1a — Contract and pure proposal builder:** settle timing representation; implement deterministic splitting, estimates, proposal validation, and unit tests.
- **3.1b — Safe project apply/persistence:** implement atomic in-memory apply and UniversalState round-trip tests.
- **3.1c — Minimal authoring UI:** add a small review/apply surface only after the service contracts are stable; preserve existing UI patterns and keep work off the Tk main thread where appropriate.
- **3.1d — End-to-end characterization:** create a representative project, apply a proposal, save/reopen it, and verify scene order, plan metadata, and legacy rendering compatibility.

Each slice should be a focused PR with Windows and Ubuntu CI. Do not merge until the latest head SHA has green CI and the user explicitly approves.
