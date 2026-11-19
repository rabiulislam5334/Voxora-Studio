# Voxora Studio — Master Gap Audit

**Audit date:** 2026-11-19  
**Audited base:** `main` at `a6a820afab3569f1962942ebf1516cc5b8dc79c2`  
**Scope:** Repository structure, selected implementation modules, architecture documents, tests inventory, open pull requests, and CI checks.  
**Purpose:** Establish a practical implementation roadmap; this is a source-level audit, not a complete manual runtime or performance certification.

## Executive summary

Voxora has a substantial foundation for a local-first creative production desktop application: project and scene workflows, channel profiles, storyboard proposals, visual asset/character data, composition editing, CPU raster rendering, FFmpeg frame encoding, motion, transitions, audio mixing, and an opt-in Universal Produce path.

It is **not yet a complete prompt-to-video AI production studio**. The most significant gaps are executable visual generation, AI-directed scene authoring, richer editing, additional visual engines, subtitles, character animation/lip sync, documentary research provenance, and release hardening.

The audit must distinguish implemented runtime behavior from data contracts and architecture plans. A contract, registry descriptor, or project data namespace does not imply an executable feature.

## Status definitions

- **Implemented:** Concrete code and UI/runtime path exist for the described bounded capability. This does not imply every advanced use case is complete.
- **Partially implemented:** A useful subset exists, but important user-facing or end-to-end behavior remains.
- **Contract only:** Data/API contracts or schemas exist; the executable feature is not present.
- **Missing:** No meaningful implementation was identified in the inspected current-main paths.
- **Needs runtime verification:** Source inspection alone cannot establish performance, usability, or production reliability.

## Current capability inventory

| Area | Status | Evidence / boundary |
|---|---|---|
| Project and scene management | Implemented | Existing project model, persistence, scene workflow and legacy compatibility paths. |
| Channel Profile System | Implemented | Profile contracts, built-in profiles, snapshots, evaluators, diagnostics and UI are present. |
| Engine Registry | Partially implemented | Registry/capability/resource resolution and catalog UI exist; the inspected built-in runtime registration currently includes FFmpeg, not a complete set of visual engines. |
| Narration segmentation | Implemented | Deterministic narration segmentation and storyboard proposal workflow exist. |
| AI script understanding / AI Director | Missing / partially implemented foundation | Storyboard proposal is deterministic; no complete AI director that interprets scripts, directs shots and generates visual plans was identified. |
| Visual Asset Library | Implemented | Asset import/storage, metadata/preview and catalog/character definitions exist. |
| Character continuity | Partially implemented | Reusable character definitions and scene references exist; visual identity enforcement across generated imagery and animation is not complete. |
| Composition Editor | Implemented | Composition domain/workflow and desktop editor are present. |
| CPU raster composition renderer | Implemented, bounded | Raster frame rendering exists; it is not a general-purpose 2D/3D animation engine. |
| FFmpeg frame sequence encoding | Implemented | Numbered frame sequence can be encoded to silent MP4; audio integration exists in later pipeline stages. |
| Motion and camera | Implemented, bounded | Motion-aware raster frames and camera behavior exist; this is not arbitrary 3D camera/scene rendering. |
| Scene transitions | Implemented, bounded | Cuts, crossfade, directional wipes, dip-to-color and easing are supported by the current transition path. |
| Audio mix / mux | Implemented, bounded | Audio mixing and MP4 mux integration exist; advanced per-scene SFX authoring and a professional multitrack audio editor remain gaps. |
| Universal Produce | Implemented, opt-in | Readiness/preflight, timeline/narration alignment, render coordination and E2E validation exist. The workflow still requires saved compositions and supported local raster assets. |
| Visual generation | Contract only | Provider-neutral request, capability, descriptor and registry contracts exist. No default executable provider or end-user image-generation workflow is registered by this phase. |
| Subtitle system | Contract/data foundation only | Project-level subtitle namespace/migration exists. Caption timing, generation, SRT/VTT export, editor, synchronization and burn-in rendering are explicitly outside the inspected Stage 1 scope. |
| Professional multitrack timeline | Partially implemented | Scene timing and transition editing exist; drag/drop multi-track editing, keyframes, playback preview and full undo/redo timeline workflow were not identified. |
| Additional visual engines | Missing / incomplete | Dedicated Sketch, Stickman, 2D Cartoon, 2.5D, documentary, real-map and general 3D/4D production engines are not complete end-to-end engines in the inspected runtime. |
| Character animation / lip sync | Missing | Character metadata is not equivalent to rigging, acting, phoneme timing or lip synchronization. |
| Documentary research and provenance | Missing | Research collection, source verification, citation tracking and claim-to-source provenance workflow remain to be built. |
| Commercial packaging | Needs implementation / verification | Installer, release pipeline, crash recovery, diagnostics, backup/restore and release acceptance need a dedicated pass. |

## Important architectural distinctions

1. **Engine registry versus engine implementation:** Registration and capability metadata do not create a renderer. The current built-in registration path inspected for this audit exposes FFmpeg; raster rendering exists as a separate implementation/adapter and needs a deliberate end-to-end integration review.
2. **Storyboard versus AI Director:** Existing deterministic segmentation/proposals provide a foundation, not autonomous script comprehension or AI shot direction.
3. **Asset Library versus image generation:** The library imports and manages local assets. The Visual Generation Contracts PR defines provider-neutral request/descriptor contracts only; it does not generate images.
4. **Character definitions versus animation:** Character appearance and references support continuity metadata, not animated performance or lip sync.
5. **Scene timeline versus professional editor:** Scene timing and transitions are present; a full multitrack editing experience is not.
6. **Produce E2E versus universal input generation:** Produce can render supported compositions/assets, but it does not itself create the images or compositions required by every script.

## Reliability and test observations

- The audited `main` commit had successful GitHub Actions checks for both `pytest (Ubuntu)` and `pytest (Windows)`.
- The repository contains a substantial test suite; the tree inventory showed 98 test files at the time of audit. This count is a file inventory, not a test-case count.
- Historical Phase 2.0 reliability work includes fixes for cancellation during final inspection, corrupt cache validation, safe cache cleanup, timestamp continuity and stream-origin alignment. These fixes are present in the current history/source lineage, but each should be tied to current acceptance tests before closing the older reliability audit.
- Source-media cache identity currently uses file path, size and modification time in the inspected implementation. This is a practical cache key, not a guarantee of full content identity; document this trade-off and test stale-cache scenarios.
- CI passing is not a substitute for real long-duration render tests, memory profiling, audio/video sync measurements, or manual desktop UI verification.

## Documentation debt

- The README and some older development/architecture documents still describe earlier phases as current. Update status references to match the merged Phase 3 work.
- Keep architecture plans clearly labelled as plans, and link them to the implementation PRs that completed or superseded them.
- Maintain one canonical roadmap and record each phase's actual acceptance criteria, supported limitations and verification evidence.
- Review stale/open historical PRs and audit reports against current `main` before treating them as active blockers.

## Recommended implementation roadmap

### A. Documentation and reliability closure
1. Update README and development status to reflect current `main`.
2. Reconcile the historical Phase 2.0 reliability audit (including PR #28) against current code and tests; close only after evidence-based review.
3. Add measurable acceptance checks for render duration, A/V synchronization, cancellation latency, cache correctness, memory use and failure cleanup.
4. Keep a traceable matrix linking each capability to implementation files, tests and CI evidence.

### B. Executable visual generation runtime
1. Define a provider execution protocol: capability negotiation, progress events, cancellation, structured errors and deterministic request correlation.
2. Implement output staging and verification (file type, dimensions, size limits, decode validation, safe filenames and cleanup).
3. Import verified images into the existing content-addressed Asset Library and return stable asset IDs.
4. Add provider availability diagnostics and explicit user consent for network/API-key use.
5. Keep providers optional; do not require a discrete GPU or paid API key. Benchmark CPU-compatible options against the supported Windows hardware before selecting defaults.
6. Add integration tests using deterministic fake providers; keep real model downloads and heavyweight inference out of ordinary CI.

### C. AI scene authoring and director
1. Convert scripts into editable scene/shot proposals with traceable source text.
2. Generate scene-specific visual prompts and shot suggestions.
3. Bind approved generated/imported assets to scenes and preserve character continuity references.
4. Require user review before applying destructive or expensive operations.
5. Distinguish generated assets from suggestions/placeholders in UI and project data.

### D. Editing and visual engines
1. Improve timeline editing incrementally: tracks, snapping, keyframes, preview, undo/redo and audio/SFX lanes.
2. Integrate the raster adapter cleanly into the engine registry and end-to-end workflow.
3. Deliver engines as separate, testable capabilities: motion graphics, sketch/whiteboard, stickman, 2D cartoon, 2.5D parallax, real maps and documentary compositions.
4. Treat general 3D/4D as a separate high-cost capability; do not promise support until a real renderer and hardware profile are validated.

### E. Audio, subtitles and character performance
1. Add scene-based SFX and BGM automation/ducking.
2. Define subtitle timing against the authoritative project timebase; implement SRT/VTT import/export, editor, synchronization and burn-in.
3. Add character performance only after stable character assets and voice/phoneme timing contracts exist.
4. Implement lip sync as a distinct capability with language/voice limitations documented.

### F. Documentary intelligence
1. Add research source capture and provenance.
2. Link factual claims to sources and expose uncertainty/conflicts.
3. Add reusable timelines, map/data visualizations and evidence review.
4. Do not present generated research as verified fact without source checks.

### G. Release readiness
1. Add crash recovery, autosave/backup restore and actionable diagnostics.
2. Profile memory and render performance on low-resource Windows hardware.
3. Add packaging, installer, versioning, signing strategy and release CI.
4. Run long-form export, cancellation, disk-full, corrupt-input and interrupted-process acceptance tests.

## Immediate next phase

**Phase 3.5.6.2 — Local Provider Runtime & Safe Artifact Import**

This should be the next implementation phase because it converts the current visual-generation contracts into a real but bounded capability. Scope should remain narrow: provider protocol, cancellation/progress, output validation and Asset Library import. Do not bundle AI Director, a new visual engine or a full timeline editor into this phase.

## Audit limitations

This report is a source-level gap audit based on the current `main` tree, selected high-impact modules and architecture documents, test inventory and CI status. It does not claim exhaustive review of every source line, manual testing of every desktop screen, benchmarking on the user's machine, or certification of all render edge cases. Status labels should be refined as each module receives a focused implementation and runtime audit.
