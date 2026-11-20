# Voxora Studio — Implementation Traceability Audit

**Audit baseline:** `main` at `68129e8575ac0cec506b0c3324fd89d349bb3c22` (2026-11-20).  
**Purpose:** Reconcile the current repository against the recovered Rev 0.4 Master Specification and recent merged delivery history.  
**Audit type:** Source/document/test inventory. This is not a target-PC runtime, performance, visual-quality, or licensing certification.

## 1. Source-of-truth and inventory findings

- The recovered `VOXORA_MASTER_SPECIFICATION_REV_0.4.md` is available in the user's ChatGPT Library, but is **not committed in the current repository tree**. It is a draft status rebaseline dated 2026-11-14 and must not be copied into the repository as though it were current without a reviewed update.
- Rev 0.4 defines **19 Universal Core responsibilities** and **12 Specialized Engines**. These are two distinct catalogues (31 entries across both categories), not a 29-item list.
- The exact separate inventory previously referred to as **“29 Modular Systems”** is not present in Rev 0.4's text under that name, and no exact MS-01…MS-29 catalogue was found in the current repository tree or default-branch code search. Its source remains **UNRECOVERED**. Do not invent or derive 29 names by combining the 19 + 12 catalogues.
- Rev 0.4's T-01…T-73 matrix is a historical baseline from 2026-11-14. Its implementation statuses are stale for recent work and must be re-evaluated against current source and merged PRs.

## 2. Current implementation traceability

Status meanings:
- **IMPLEMENTED (bounded):** executable code and tests exist for the stated limited behavior.
- **PARTIAL:** a useful slice exists, but the product workflow or acceptance scope is incomplete.
- **CONTRACT / PLAN:** data structures or documentation exist without the full runtime behavior.
- **NOT VERIFIED:** source/tests do not establish real hardware, visual, model-quality, or end-to-end user acceptance.

| Capability / Rev 0.4 area | Current evidence on main | Delivery evidence | Current status and boundary |
|---|---|---|---|
| Project persistence, save integrity, backups, revisions (Universal Core; T-23…T-30) | `app/persistence/*`, `app/projects/manager.py`; persistence and characterization tests | Earlier Step 2 / R10 implementation history; see merged history | **IMPLEMENTED (bounded).** Windows lock spike, Fix-A, autosave/crash recovery gates remain separately unresolved; do not claim zero-loss recovery. |
| Shared project session (Universal Core; SC-01/SC-02) | `app/ui/studio_context.py` and shared session integration; inspect session-specific tests | PR #111 | **IMPLEMENTED (bounded).** Shared in-memory project ownership is present; broader UI/runtime acceptance remains distinct. |
| Channel profiles (Engine/profile policy; T-11) | `app/universal/profiles/*`, profile UI and profile tests | Phase 3.2 delivery history | **IMPLEMENTED (bounded).** Profile registry/rules exist. The catalogue contains 14 planned channel profiles, including current channels and future channel concepts; profile availability is not equivalent to complete specialized production engines. |
| Script segmentation / storyboard proposals (Script Intelligence; R-3/R-4) | `app/universal/storyboard.py`, `storyboard_builder.py`, `storyboard_diagnostics.py`, `storyboard_apply.py`; corresponding tests | Phase 3.3h delivery history | **IMPLEMENTED (bounded).** Deterministic narration segmentation/proposals exist; this is not semantic AI understanding. |
| Production Director (Scene Planning / Director; R-4; T-13) | `app/universal/production_director.py`; `tests/test_production_director.py` | PR #115 | **IMPLEMENTED (bounded).** Deterministic keyword/phrase heuristics produce review-required scene/shot plans. No LLM, factual inference, asset selection, animation or render routing. |
| Visual Asset Library and provenance (T-12/T-64/T-65) | `app/universal/asset_library.py`, `visual_assets.py`; asset library tests | Phase 3.4 delivery history | **IMPLEMENTED (bounded).** Local raster import/catalog/provenance; not automatic stock/media discovery or documentary source verification. |
| Generated-image provider contracts | `app/universal/visual_generation.py`; `tests/test_visual_generation_contracts.py` | PR #99 | **IMPLEMENTED (contracts).** Contracts alone do not generate media. |
| Visual-generation runtime | `app/universal/visual_generation_runtime.py`; `tests/test_visual_generation_runtime.py` | PR #102 | **IMPLEMENTED (bounded).** Explicitly injected provider, staging/validation and asset import; no implicit cloud or provider discovery. |
| Local Stable Diffusion.cpp provider | `app/universal/providers/stable_diffusion_cpp.py`; `tests/test_stable_diffusion_cpp_provider.py` | PR #103 | **IMPLEMENTED (adapter), NOT VERIFIED (real inference).** Requires user-supplied executable/model; CPU profile caps output at 512×512. No target-PC speed/RAM or image-quality acceptance recorded here. |
| Generated image desktop workflow and scene binding | `app/ui/visual_generation_tab.py`, `app/universal/generated_image_scene_workflow.py`; related UI/workflow tests | PRs #104–105 | **IMPLEMENTED (bounded).** User-triggered generation and explicit preview/apply binding; not automatic per-shot generation from a Director plan. |
| Generated image → composition → raster rendering | `app/universal/generated_image_composition.py`, `app/universal/adapters/raster.py`, composition tests | PRs #106–107, #112 | **IMPLEMENTED (bounded).** Supported still-image composition/rendering; not a general-purpose 2D animation engine. |
| Generated-image Universal Produce validation | `tests/test_universal_produce_e2e.py` and readiness tests | PR #108 | **TESTED (fixture-backed).** Test coverage does not prove arbitrary scripts can autonomously produce suitable visuals. |
| Motion, transitions and FFmpeg render pipeline | `app/universal/*motion*`, composition adapters/coordinators, transition modules and render tests | PRs #80–98 (feature groups) | **IMPLEMENTED (bounded).** Scene/frame motion, transitions and MP4 encoding exist; advanced character rigs, expressive 2D animation and universal visual coverage remain incomplete. |
| Cinematic Skill renderer adapter and Film builder | `app/universal/cinematic_skill/*`, `cinematic_skill_adapter.py`, `cinematic_skill_builder.py`, timing/alignment adapters | PR #113 | **IMPLEMENTED (adapter/prototype).** Real Skia render, optional alignment accuracy, full dependency/binary clearance and target-PC performance remain unverified. |
| Supplied script + narration Auto Produce orchestration | `app/universal/cinematic_skill_auto_produce.py`; `tests/test_cinematic_skill_auto_produce.py` | PR #114 | **IMPLEMENTED (vertical slice).** Validates/probes supplied audio, aligns script, builds a timed Film, renders and muxes original narration. Current builder is timed explainer cards; no full semantic shot plan, automatic asset routing, captions, BGM/SFX or UI wiring. |
| Subtitle/caption production (T-45 and related caption requirements) | Project data foundations may exist; no complete script-first alignment/export/burn-in pipeline identified in this audit | Earlier subtitle-stage foundation | **PARTIAL / NOT COMPLETE.** No end-to-end SRT/VTT, multilingual layout, burn-in and QC workflow established. |
| Documentary research provenance (T-38/T-61) | No complete claim-to-source research workflow identified in inspected current paths | No delivery identified | **NOT IMPLEMENTED as a workflow.** Asset provenance is not equivalent to verified factual claims and source citations. |
| Stickman / 2D cartoon character performance (T-47…T-49; CE tiers) | Character metadata and visual assets exist; no complete rig/pose/action performance runtime identified | No complete engine delivery identified | **NOT IMPLEMENTED end-to-end.** Character records do not imply animation, continuity enforcement or lip sync. |
| Sound design / multitrack automation (T-17/T-18/T-42…T-46/T-62) | Existing mixer and supplied narration mux; inspect `app/audio/*` | PR #85 and #114 boundaries | **PARTIAL.** Basic mix/mux exists; dedicated SFX/ambience/character-vocal tracks, smart cue placement, ducking and mastering workflow remain open. |
| Commercial packaging / release hardening | No complete installer/release acceptance evidenced in this audit | No delivery identified | **NOT VERIFIED / INCOMPLETE.** Requires packaging, binary notices, crash recovery and target-machine acceptance. |

## 2A. Permanent visual capability traceability

The product scope requires five permanent first-class visual production dimensions: **2D, 2.5D, 3D, 4D (time-evolving 3D), and Hybrid**. The capability itself is not optional even when a particular renderer, model, provider or adapter is optional. This section records the bounded evidence found in the audited main-branch source; it does not upgrade planned capabilities to implemented status.

| Permanent capability | Main-branch evidence inspected | Evidence-based status | Exact boundary / remaining acceptance |
|---|---|---|---|
| **2D** | `app/universal/composition.py`; `app/universal/raster_renderer.py`; `app/universal/adapters/raster.py`; `tests/test_raster_renderer.py`; `app/universal/motion.py`; `tests/test_motion.py` | **PARTIAL — implemented still-composition and motion foundations** | Layered raster PNG composition, transforms, opacity/rotation and deterministic frame-based element/camera motion contracts exist. The raster adapter declares PNG output only. This does not establish a complete 2D animation, cartoon-character rig, Stickman performance, lip-sync or end-to-end animated-scene system. |
| **2.5D** | `app/universal/composition.py`; `app/universal/motion.py`; `tests/test_motion.py`; existing motion/FFmpeg delivery group PRs #87–#95 | **PARTIAL — foundations only** | Layering plus camera pan/zoom/rotation tracks provide reusable ingredients. The inspected evidence does not establish a depth-aware scene graph, parallax renderer, multi-plane camera choreography or preview/final-render parity for a complete 2.5D workflow. |
| **3D** | Planning references to scientific/advanced 3D; no 3D scene/model/lighting/animation runtime identified in the inspected implementation paths | **PLANNED / NOT IMPLEMENTED in audited runtime** | No verified 3D modeling, environment, character, lighting, camera, animation, physics or particle production pipeline is evidenced here. Must remain a permanent capability requirement; do not mark it optional because no adapter is currently accepted. |
| **4D / time-evolving 3D** | No time-evolving 3D scene runtime, temporal 3D simulation contract or corresponding tests identified in the inspected implementation paths | **NOT IMPLEMENTED; planning traceability gap** | 4D here means 3D production evolving over time, not a fourth spatial dimension. Add explicit architecture contracts, adapter capability declarations and acceptance coverage in the appropriate approved planning work; do not infer support from ordinary 2D frame animation. |
| **Hybrid** | `app/universal/adapters/ffmpeg.py` (image/video scene segments); `app/universal/composition.py`; `app/universal/adapters/raster.py`; `app/universal/visual_generation_runtime.py`; `app/universal/generated_image_composition.py` | **PARTIAL — separate media/composition foundations** | Existing paths support image/video scene segments, layered raster image composition and generated-image staging/binding. The audited evidence does not establish one automatic hybrid scene pipeline that combines footage, photography, 2D/2.5D/3D/4D scenes, graphics, provenance and synchronized composition under the Director. |

**Planning alignment gap:** the current planning catalogue describes several 2D/2.5D/3D and hybrid workflows, but does not yet state all five dimensions together as permanent first-class architecture requirements; 4D is not explicitly traced in the inspected roadmap/profile text. VXP-00 must reconcile this wording in the authoritative Planning Documents without changing the five capabilities into optional features. This audit records the requirement and current evidence; it does not claim implementation.

**Interpretation rule:** contracts, frame evaluators, PNG still renderers, video-segment adapters, provider interfaces and test fixtures are evidence only for their exact bounded behavior. They are not proof of full 2D animation, 2.5D parallax, 3D, 4D or end-to-end Hybrid production.

## 3. Recent merged PR history checked

The GitHub closed-PR collection was inspected for PRs #80–#115. The following relevant merged delivery groups were confirmed:

- #80–98: composition/raster, motion, transitions, render orchestration, Universal Produce readiness and E2E validation.
- #99: provider-neutral visual-generation contracts.
- #100: historical master gap audit.
- #102: safe visual-generation provider runtime.
- #103: local Stable Diffusion.cpp provider adapter.
- #104–108: local generation UI, generated-image binding/composition/raster and Universal Produce fixture validation.
- #109: historical Phase 3.5.6.9 integration audit (its own document explicitly labels its baseline historical).
- #111–112: shared project session and composition/catalog/navigation integration.
- #113: Cinematic Skill renderer adapter and Film builder.
- #114: supplied script + narration Auto Produce vertical slice.
- #115: deterministic Production Director core.

PR #101 was closed without merging to `main` (its base was the temporary audit branch); PR #102 is the merged runtime delivery. PRs #82/#83 are closed without a main-branch merge and should be treated as historical planning/audit artifacts, not implementation evidence. PR #110 remains superseded by #111 per the planning registry.

## 4. Confirmed gaps and dependency order

1. **VXP-00 source recovery:** exact “29 Modular Systems” source/catalogue remains unlocated. Rev 0.4 does not contain that named catalogue.
2. **VXP-00 traceability:** this matrix is a first current-main reconciliation of major capability groups, now including the five permanent visual dimensions. Fine-grained T-01…T-73 row-by-row status and exact file/test/merged-PR evidence still need review before VXP-00 can be called DONE. Unmerged or closed-without-merge PRs must never be counted as implementation evidence.
3. **VXP-10.2 package ingestion:** versioned external Visual Direction Package schema/import/validation is not evidenced as implemented.
4. **VXP-10.5+ Director-to-production integration:** the current Director plan is not consumed by Auto Produce. The Auto Produce Film builder still creates deterministic timed cards. A safe, reviewable mapping from approved shot plan → existing provider/asset/composition/render capabilities is a real next integration gap.
5. **Visual-provider acceptance:** local Stable Diffusion.cpp real inference, model licence, executable provenance, memory/time and quality on the documented Windows PC remain unverified. Keep it optional; never make it a mandatory dependency.
6. **Animation engines:** sketch/whiteboard, Stickman, 2D cartoon, 2.5D parallax, map and documentary visual engines require distinct capability audits and staged acceptance; do not call the existing raster renderer a full animation engine.
7. **Captions and sound design:** script-first caption alignment/export/QC and multi-track SFX/BGM/ambience remain separate workstreams.
8. **Target-PC acceptance:** no source/CI result in this audit substitutes for a real 30–60 second English render and measured resource/quality review on the target Windows PC.

## 5. Recommended next implementation slice

After this audit is reviewed and VXP-00 traceability is closed, the highest-value next bounded implementation is **VXP-10.5 — Director Plan → Auto Produce Planning Handoff (no new renderer)**:

- Consume an approved `DirectorPlan` in the existing supplied-script/narration Auto Produce orchestration.
- Validate source fingerprint, profile identity, narration-unit coverage, timing basis, scene/shot ordering and review approval.
- Preserve exact narration text and measured audio timing; reject stale or partial plans instead of silently guessing.
- Map supported shot intents to existing, capability-declared visual paths only; unsupported intents receive explicit review/fallback diagnostics, not fabricated assets.
- Keep generated image calls opt-in and user-approved; do not automatically download models or contact a network provider.
- Keep the existing timed-card path as a deterministic fallback.
- Add tests for plan mismatch, missing/duplicate narration units, measured-vs-estimated timing, cancellation, unsupported capabilities and backward compatibility.

This is a proposal for the next small slice, not authorization to implement it. No new dependency, paid API, cloud service, or renderer is required for the contract/handoff layer.

## 6. Audit limitations

This audit used current-main source files, the recursive repository tree, selected tests/architecture documents and GitHub PR metadata. The visual-capability matrix is a bounded source-path review, not an exhaustive engine audit. It does not claim every module or all 73 Rev 0.4 traceability rows were exhaustively reviewed. The exact original “29 Modular Systems” catalogue was not recovered from the Rev 0.4 specification or current repository; its absence from those two inspected sources is not proof that it never existed elsewhere. Real model inference, target-PC performance, long-form sync, visual quality, packaging, and license clearance remain separate acceptance gates.
