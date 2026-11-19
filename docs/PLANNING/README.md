# Voxora Studio — Master Product Plan & Delivery Registry

> Status: Active planning baseline (PR #113)
> Canonical location: docs/PLANNING/README.md
> Last reconciled: 2026-11-20

## 0. Non-negotiable product outcome

Voxora is a **Script-to-Finished-Video Production Studio**. Its defining workflow is not merely image generation or a manual editing timeline. A user supplies a script and selects a channel profile, then invokes **Auto Produce**. Voxora automatically creates narration and turns the script into a complete, synchronized video.

### Target automatic workflow

    Script + Channel Profile + Output Preferences
                       |
                       v
              Script Understanding
          structure / story beats / claims
                       |
                       v
                 Narration Engine
          voice / pronunciation / pauses / TTS
                       |
                       v
          Actual Narration Timing Analysis
       audio duration / word timestamps / sentence
                  and scene boundaries
                       |
                       v
              Scene & Shot Breakdown
        visual intent / duration / continuity
                       |
                       v
              AI Production Director
       chooses suitable production engine per shot
              /            |             \
             v             v              v
         Footage /     Motion &         Audio /
          Images       Animation       Sound Design
              \            |             /
                       v
             Automatic Draft Timeline
       narration + visuals + transitions + captions
              + SFX + ambience + background music
                       |
                       v
                Render Orchestrator
       dependencies / cache / progress / cancellation
                       |
                       v
          FFmpeg Final Assembly, Mix and Mux
                       |
                       v
             Automated Quality Validation
       duration / sync / frames / audio / missing media
                       |
                       v
                 Finished Video

**The script and the generated narration are the source of truth for the edit.** Scene and shot boundaries, visual changes, motion, captions and sound cues must align with what is actually spoken—not only rough word-count estimates. Use word timestamps when a provider supplies them. Otherwise use measured audio duration plus deterministic sentence/segment timing, and label estimated timing honestly.

### Automation requirements

- Auto Produce must create a complete first draft without requiring the user to manually attach every image, clip, animation, transition or sound cue.
- The Director may use user assets, managed libraries, deterministic templates, procedural graphics and configured generation providers.
- If a suitable visual cannot be found or generated, use a deliberate profile-compatible fallback (map, diagram, typography, sketch, neutral illustration or clearly marked placeholder), never a silent missing-media gap.
- Factual visuals retain source/provenance and license notes. AI reconstructions must never be represented as genuine archival footage.
- Optional AI providers are adapters. No mandatory paid API, cloud account, subscription or hidden upload. Remote calls require explicit setup/consent and cost/network disclosure.
- Review checkpoints remain available, but review must not force the user to hand-build every scene.
- Manual production remains first-class. Automation must not overwrite explicit manual edits without a reviewable proposal.
- “Fully automatic” means end-to-end orchestration and assembly. It does not promise photorealistic generative video for every shot on the baseline PC.

## 1. Architecture and engineering principles

One local-first desktop application; one Universal Core; specialized production engines; capability-declared providers; one Render Orchestrator.

- **Universal Core:** project/session, scenes/shots, assets, profiles, timeline/timebase, audio contracts, cache, jobs, persistence, diagnostics and export.
- **AI Production Director:** interprets script/profile, creates a reviewable plan, routes shots to engines, coordinates asset/sound choices and collects results.
- **Specialized engines:** narration, planning, motion graphics, documentary, cartoon/character, hybrid media, sound design, colorization, etc.
- **Provider registries:** TTS/voice, visual generation, media acquisition and optional AI. Capabilities must be declared; unsupported controls must not be displayed as functional.
- **Motion adapters:** framework integrations; distinct from scene-segment engines and still composition renderers.
- **Render Orchestrator:** dependency graph, resource-aware scheduling, cache, cancellation, progress, temporary-file ownership, retries and validation.
- **FFmpeg:** remains the final encoding, audio mix/mux and media assembly backbone unless a separately approved decision changes it.

Principles: no duplicated shared infrastructure; deterministic and reproducible core behavior; local-first and low-memory operation; provider capability checks; backward-compatible .voxora files; preview/final-render parity; truthful completion reporting; every implementation phase maps to this plan and the Master Specification.

## 2. Master Specification structure — inventory distinction

The recovered Rev 0.4 Master Specification defines:
- **19 Universal Core responsibilities**.
- **12 Specialized Engines**: Script Intelligence, Narration, Scene Planning, Director, Universal Motion Graphics, Audio/Sound Design, Cartoon/Character, Documentary Production, Colorization/Artwork, Hybrid Media, Import/Export, Optional AI Integration.
- **R-1 through R-11**, with **R-12 Basic Motion Graphics** and **R-13 Advanced Motion Graphics** added in Rev 0.3.
- Shared contracts SC-01 through SC-10 and technical spikes TS-01 through TS-11.

**Important discrepancy:** previous planning notes also refer to “29 Modular Systems”. Rev 0.4 explicitly says the 12-engine catalogue and the broader modular-system inventory are different decomposition levels. The exact original 29 names/definitions are not reproduced in the recovered Rev 0.4 text. Therefore:
- Do not call 19 + 12 = 29 (it is 31 entries across two categories).
- Do not rename the 12 engines as the 29 systems.
- Keep MS-01…MS-29 as **source transcription pending** until the exact original list is located.
- The VXP phases below organize recovered requirements; they do not invent canonical MS IDs.

### Master roadmap stage mapping (original R IDs preserved)

| Master stage | Original scope | Main VXP mapping |
|---|---|---|
| R-1 | Existing verified foundations / first usable video | VXP-01, VXP-02, VXP-09 baseline |
| R-2 | Core reliability and data integrity | VXP-01 |
| R-3 | Profiles, assets and Script Intelligence | VXP-02, VXP-03, VXP-04 |
| R-4 | Scene Planning and Director | VXP-05 |
| R-5 | Timeline and manual editing foundations | VXP-12 |
| R-6 | Audio and Sound Design Studio | VXP-07 |
| R-7 | Script-to-video and audio-to-video | VXP-09, VXP-10 |
| R-8 | Hybrid media and colorization | VXP-08, VXP-11 |
| R-9 | Cartoon, story and short-film engines | VXP-11 |
| R-10 | Documentary and prompt/code production engines | VXP-08, VXP-11 |
| R-11 | Advanced optional AI integrations and higher-end features | VXP-08.8, VXP-11.8, future provider work |
| R-12 | Basic Motion Graphics foundation | VXP-06, VXP-08 |
| R-13 | Advanced Motion Graphics | VXP-06, VXP-08, VXP-11 |

R-stage numbers are Master Specification IDs, not an instruction that every later stage must wait for every earlier stage. Follow the dependency column and the original Rev 0.4 workstream rules. The automatic first-video path must not wait for a complete manual NLE or advanced 3D.

## 3. Status vocabulary and delivery rules

| Status | Meaning |
|---|---|
| NOT STARTED | No implementation started |
| PLANNED | Scope and dependencies defined |
| IN PROGRESS | Active on a named branch/PR |
| IMPLEMENTED | Code exists; acceptance incomplete |
| CI VERIFIED | Exact latest PR head passed required CI |
| PC VERIFIED | Target Windows PC acceptance reported |
| DONE | Phase acceptance and evidence recorded |
| BLOCKED | Named decision/authorization/dependency prevents work |
| DEFERRED | Intentionally postponed with reason |

A merged PR does not mean the whole product capability is complete. Synthetic fixtures do not prove real model inference. A renderer benchmark does not equal renderer integration.

## 4. Small-phase roadmap — dependency-aware sequence

R-stage IDs remain those of the Master Specification. **VXP IDs** are proposed small implementation phases. They do not replace R-n or GitHub PR numbers.

### VXP-00 — Planning governance and source recovery

| Subphase | Deliverable | Current status |
|---|---|---|
| 00.1 | Recover Rev 0.3/0.4, R-1…R-13, SC/TS decisions | PARTIAL — Rev 0.4 recovered |
| 00.2 | Transcribe exact 29 Modular Systems | BLOCKED — exact source list not yet recovered |
| 00.3 | Establish phase/PR/completion registry | IN PROGRESS — this document |
| 00.4 | Map merged PRs to requirements, tests and remaining gaps | PARTIAL — PR #80–112 feature-group mapping |
| 00.5 | Freeze duplicate-work/change-control rules | PLANNED |

Exit: original requirements are traceable; no phase starts from an isolated chat idea.

### VXP-01 — Universal Core and project integrity (R-2a; SC-01/02/05/06/10)

01.1 Shared project/session ownership across workspaces.  
01.2 Canonical project/scene/shot/asset/character contracts and stable IDs.  
01.3 Schema migration, unknown-field preservation and backward compatibility.  
01.4 Asset references, path resolution, relinking and provenance.  
01.5 Job contract: progress, cancellation, retry and temporary-file cleanup.  
01.6 Cache identity and selective invalidation.  
01.7 Persistence/recovery audit and Windows-specific authorization gate.

**Already delivered in part:** project save/load, atomic writes, backups, conflict detection, revision/dirty tracking, cross-process save serialization, shared ProjectSession, schema and snapshot work on merged branches. Reuse these. Do not rebuild them.

**Blocked boundary:** Windows Lock Spike, Fix-A, autosave/session recovery remain separately gated where required by R10. Do not make blocked Windows-only work a dependency for unrelated engines.

### VXP-02 — Script Intelligence and narration foundation (R-3; Engines 1 & 2)

02.1 Script parser/markup contract.  
02.2 Deterministic Script Intelligence issue model and diagnostics.  
02.3 Mixed-language and pronunciation analysis for Bengali/English.  
02.4 Narration jobs: chunking, retry, cache, cancellation and per-scene audio.  
02.5 Actual narration timing extraction (audio duration and provider word timestamps).  
02.6 Subtitle/caption generation (SRT/VTT, punctuation and timing validation).

**Existing foundation:** Edge TTS provider, voice discovery/preview, narration parsing, pause handling, chunking, narration generation and audio assembly. Do not rewrite these. First inventory exact gaps and preserve tested behavior.

### VXP-03 — Channel profiles and creative rules (R-3; SC-08)

03.1 Versioned profile registry.  
03.2 Profile precedence: built-in → user → project override.  
03.3 Capability preferences and fallback policy.  
03.4 Per-profile narration, visual, motion, audio and export defaults.  
03.5 Profile editor, validation, import/export and compatibility tests.

Profiles are data, not hard-coded branches in the Universal Core. A profile cannot require a paid provider.

### VXP-04 — Asset library and provenance (R-3; SC-02)

04.1 Unified media asset registry and capability metadata.  
04.2 Import, probe, validation, hashing and duplicate detection.  
04.3 Missing-media detection and safe relinking.  
04.4 License/source/provenance metadata and attribution.  
04.5 Search, tags, favorites, preview and reusable collections.  
04.6 Scene/shot asset binding and continuity diagnostics.

**Already delivered in part:** Visual Asset/Character library, scene asset preview/binding, managed import, generated-image provenance checks and explicit binding/apply workflows. Extend these; do not create a second asset registry.

### VXP-05 — Scene planning, shot planning and deterministic Director (R-4; Engines 3 & 4)

05.1 Script-to-scene segmentation and intro/body/outro roles.  
05.2 Scene purpose, narrative beat and duration proposal.  
05.3 Scene-to-shot breakdown (wide/medium/detail/diagram/map/etc.).  
05.4 Narration-aware timing using actual audio boundaries.  
05.5 Deterministic profile-based Director defaults.  
05.6 Continuity rules for characters, locations, visual motifs and repeated facts.  
05.7 Proposal review, accept/reject/edit and selective regeneration.

Preserve recovered rules: first scene role is intro; last scene is outro only with at least 3 scenes; otherwise all roles are body; known narration duration overrides estimates; Director fills only unset fields; user values are preserved. Unrecovered formulas stay unresolved—not invented.

### VXP-06 — Motion framework decision and animation adapter (R-12; TS-02)

| Subphase | Deliverable | Status |
|---|---|---|
| 06.1 | Motion Canvas / HyperFrames / Remotion comparative benchmark | DONE — user evaluation, 14–15 Nov 2026 |
| 06.2 | Formal matrix: quality, speed, memory, Bengali typography, portability, license, determinism | PLANNED |
| 06.3 | Select primary adapter and document limitations | BLOCKED — final decision not recorded |
| 06.4 | Renderer-neutral motion scene/animation contract | PLANNED |
| 06.5 | Implement selected adapter in isolation | BLOCKED by 06.3 |
| 06.6 | Preview/render parity and deterministic tests | BLOCKED by 06.5 |
| 06.7 | FFmpeg handoff, cache, cancellation and resource limits | BLOCKED by 06.5 |

**TS-02 completed evidence (user workload, not universal benchmark):**
- Motion Canvas: 29-second animation rendered in 39 seconds; visual quality judged weak.
- HyperFrames CLI 0.9.46: 93 seconds; visual result judged good; 3D elements added successfully.
- Remotion 4.0.543: 1920×1080, 30 FPS, 870 frames; 175,486 ms frame capture, 708 ms stitching; 7.2 MB H.264 MP4 without audio; software rendering; initial Chrome Headless Shell timeout, retry succeeded.
- Hardware: Windows, i5-8250U, 8 GB RAM, NVIDIA 940MX 4 GB; memory pressure is material.
- Isolated workspace: D:\Voxora-TS02-Benchmark. Voxora source/dependencies were not changed.
- **No winner declared.** Do not rerun the same benchmark. Fill only missing decision-matrix evidence. FFmpeg remains final encoding/mux.

### VXP-07 — ElevenLabs-inspired Sound & Voice System (R-6; Engine 6)

This is a major product pillar, not a cosmetic audio panel.

07.1 Provider capability model and searchable voice catalog.  
07.2 Voice preview, favorites and reusable voice profiles.  
07.3 Expressive controls (emotion/style/intensity/stability/pace/emphasis) only where genuinely supported.  
07.4 Pronunciation dictionary and per-project/profile overrides.  
07.5 Character voice assignment and multi-voice narration.  
07.6 SFX/BGM/ambience/non-verbal vocal library with tags, audition and licensing.  
07.7 Multitrack audio model and mixer; narration, dialogue/vocals, SFX, BGM and ambience remain separate.  
07.8 Smart Audio Director for scene/action cue proposals.  
07.9 Ducking, fades, gain/pan and automation; ducking opt-in.  
07.10 Loudness, clipping, silence and synchronization QC.  
07.11 Mixdown/mastering presets and final mux.  
07.12 Offline/local voice and non-verbal vocal feasibility benchmark.

Edge TTS does not currently provide expressive style/emotion controls through the existing adapter. Never fake unsupported ElevenLabs-like controls. Evaluate free/local and optional remote providers as separate adapters with cost/privacy disclosure.

### VXP-08 — Visual production and composition (R-8/R-12; Engines 5, 9, 10)

08.1 Unified shot visual brief and engine capability matching.  
08.2 Still/layer composition contract and persistence.  
08.3 Raster still renderer (PNG) and preview validation.  
08.4 Motion composition and animation through the selected adapter.  
08.5 Maps, charts, timelines, diagrams and data-driven graphics.  
08.6 Sketch/whiteboard/2D/2.5D parallax styles.  
08.7 Character/stickman/pose/expression animation tiers.  
08.8 Optional local image/video generation providers.  
08.9 Visual continuity, provenance, licensing and factual/illustrative labels.

**Already delivered in part:** composition domain/editor, CPU raster PNG renderer, motion/camera contracts and frame rendering, motion-to-MP4 bridge, transitions, generated-image provider and binding. PNG still composition is not animated video; motion-framework selection remains separate.

### VXP-09 — Render Orchestrator and production graph (R-1/R-5/R-7)

09.1 Canonical render graph for narration, visuals, motion, sound and captions.  
09.2 Resource-aware sequential scheduler with bounded memory/concurrency.  
09.3 Per-stage progress, cancellation and safe temporary-file ownership.  
09.4 Dependency-aware cache and selective invalidation.  
09.5 Frame/video adapters and FFmpeg encoding/mux.  
09.6 Resume/retry policy for failed jobs.  
09.7 Automated output validation and actionable diagnostics.  
09.8 Export profiles and reproducibility manifest.

Do not introduce parallel rendering or silent engine fallback without a separate measured design. Extend the existing sequential Universal Produce pipeline.

### VXP-10 — AI Production Director and Auto Produce (R-7; orchestration layer)

This is the main automation milestone. It integrates existing engines; it must not duplicate them.

10.1 Production-plan schema: scenes, shots, narration ranges, visual intent, audio cues and engine choice.  
10.2 Script understanding and creative treatment from profile.  
10.3 Automatic scene/shot plan generation.  
10.4 Automatic narration generation and actual timing alignment.  
10.5 Automatic visual selection/acquisition/generation per shot.  
10.6 Automatic motion/animation/graphics direction per shot.  
10.7 Automatic SFX/BGM/ambience cue placement and mix intent.  
10.8 Build a complete draft timeline without manual per-shot placement.  
10.9 One-click Auto Produce: plan → assets → narration → motion → sound → render → QC.  
10.10 Review checkpoints and selective regeneration of one scene/shot/track.  
10.11 Failure recovery and deterministic rerun from cached successful stages.

**Auto Produce acceptance:** with a valid script, profile and configured available providers/libraries, one user action produces a playable final MP4 with narration, automatically assigned visuals, motion/transitions, sound mix and passing media validation. The user must not manually attach media to every scene. Missing providers/assets yield explicit fallback or actionable errors, never fake success.

### VXP-11 — Hybrid media, documentary, cartoon and specialized workflows (R-8/R-9/R-10)

11.1 Hybrid stills, clips, graphics, overlays and optional 2.5D.  
11.2 Documentary research/source tracking and factual review.  
11.3 Maps, archival material, timelines and reconstruction labels.  
11.4 Cartoon/character library, reusable poses, props and locations.  
11.5 Dialogue-free-but-not-silent comedy with non-verbal vocals.  
11.6 Story/short-film continuity and beat timing.  
11.7 Colorization/artwork tools and non-destructive layers.  
11.8 Optional advanced 3D/AI integrations (future research).

All these workflows reuse the same Core and render/audio systems; they are not separate applications.

### VXP-12 — Timeline, editor UX and production review (R-5)

12.1 Timeline data model using canonical project timebase.  
12.2 Video/image/graphics/audio/caption tracks.  
12.3 Clip trim/split/move, markers, mute/solo/lock.  
12.4 Undo/redo and non-destructive editing.  
12.5 Synchronized storyboard/shot-list and timeline views.  
12.6 Low-resolution proxy preview and memory-aware playback.  
12.7 UI toolkit prototype/decision if Tkinter becomes a bottleneck.

The full manual timeline is not a prerequisite for the first automatic video. The Director can create a draft timeline model and render it through the existing pipeline first.

### VXP-13 — Reliability, performance, security and distribution

13.1 Target-Windows-PC acceptance for full Auto Produce.  
13.2 Memory/performance budgets and graceful degradation.  
13.3 Project recovery, render-job recovery and crash-safe cleanup.  
13.4 Security review: paths, subprocesses, imported projects and secrets.  
13.5 Licensing/redistribution audit for FFmpeg, fonts, media and engines.  
13.6 Installer, first-run setup, logs, diagnostics and updates.  
13.7 Release regression matrix and reproducible build.

Target hardware: Windows 10, Intel i5-8250U, 8 GB RAM, NVIDIA 940MX 4 GB + Intel UHD 620, 1 TB HDD. Prefer sequential jobs, low-resolution previews, lazy loading, bounded caches and CPU fallback. Do not promise high-end 3D or local video diffusion on this machine.

## 5. Completed-work registry — do not rebuild

This registry records delivered PR scope, not completion of the entire associated product system.

### 5.1 Merged PR implementation groups

| PR | Delivered scope | Mapping | Boundary |
|---:|---|---|---|
| #80 | CPU raster composition renderer adapter registration | VXP-08.3 | Registration only |
| #81 | Frame sequence and FFmpeg encoding bridge | VXP-09.5 | Merged |
| #82 | Scene timeline/audio integration plan | VXP-00 | Documentation |
| #83 | Audit existing timeline/audio production contracts | VXP-00/09 | Audit |
| #84 | Immutable composition scene render timelines | VXP-08/09 | Merged |
| #85 | Reuse Studio audio mixer for composition MP4 mux | VXP-07/09 | Not a full multitrack sound studio |
| #86 | Composition render coordinator | VXP-09 | Merged |
| #87 | Motion and camera domain contracts | VXP-06/08 | Contracts; not framework selection |
| #88 | Motion-aware raster frame rendering | VXP-08 | Merged |
| #89 | Motion-to-MP4 rendering pipeline | VXP-08/09 | Not final framework selection |
| #90 | Timeline-aware multi-scene motion rendering | VXP-08/09 | Merged |
| #91 | Scene transitions and crossfade rendering | VXP-08/09 | Merged |
| #92 | Advanced transitions and camera integration | VXP-08 | Merged |
| #93 | Transition editor UI and scene-level configuration | VXP-08/12 | Merged |
| #94 | Persisted transition settings in motion rendering | VXP-08 | Merged |
| #95 | Automatic project motion and narration alignment | VXP-05/08 | Scoped alignment, not full AI Director |
| #96 | Universal Produce readiness preflight | VXP-09 | Merged |
| #97 | Universal Produce real rendering and safe publication validation | VXP-09 | Integration tests; not universal real-content proof |
| #98 | Multi-scene Universal Produce rendering validation | VXP-09 | Merged |
| #99 | Provider-neutral visual generation contracts | VXP-04/08 | Merged |
| #100 | Master gap audit and roadmap | VXP-00 | Documentation |
| #101–102 | Safe visual-generation provider runtime | VXP-08.8 | Merged |
| #103 | Local stable-diffusion.cpp image provider | VXP-08.8 | Real inference still needs PC acceptance |
| #104 | Local image-generation desktop workflow | VXP-08.8 | Merged |
| #105 | Generated-image-to-scene binding workflow | VXP-04.6/08.9 | Explicit approval |
| #106 | Integrate bound generated images into scene composition | VXP-08 | Proposal/apply/save workflow |
| #107 | Generated-image raster composition support | VXP-08.3 | Still PNG only |
| #108 | Generated-image Universal Produce end-to-end fixture | VXP-09 | Synthetic fixture, not real model inference |
| #109 | Phase 3.5.6.9 integration gap audit | VXP-00 | Documentation/audit |
| #111 | Shared application-owned ProjectSession across workspaces | VXP-01.1 | Merged; no schema migration |
| #112 | Composition editor PNG render, capability catalog, navigation/docs integration | VXP-08.3/00 | PNG still, not animated MP4 |

**PR #110:** an earlier shared-project-session implementation remains open in the latest issue listing, while PR #111 is the merged canonical delivery. Treat #110 as superseded/duplicate pending explicit repository cleanup; do not implement or merge a second copy.

### 5.2 Earlier foundations already present

Extend rather than rebuild:
- Desktop shell and Script/Voice/Audio/Timeline/Video/Produce workspaces.
- Edge TTS provider abstraction, voice discovery/preview and narration generation.
- Narration markup parser, pause tags, chunker and duration/word-count estimation.
- Audio assembly/mixer and user-supplied BGM controls.
- Sequential multi-scene production coordinator and cancellation.
- FFmpeg scene video rendering, still-image motion, transitions and audio mux.
- Video cache, readiness preflight, FFprobe stream/duration/frame/timestamp/synchronization validation.
- Project persistence, atomic save, rolling backups, disk-stamp conflict detection, dirty-state/revision handling.
- Channel profiles, universal scene plan and explicit proposal/apply flow.
- Visual asset/character library, asset binding, composition editor and raster PNG renderer.
- Optional local Stable Diffusion.cpp provider, generated-image provenance and explicit binding.
- Shared project session across desktop workspaces.

Exact PR mapping for some older foundations still needs Git-history reconciliation. Do not rebuild them merely because their original PR number is not listed here.

### 5.3 Explicitly not complete

- AI Production Director and fully automatic script-to-finished-video workflow.
- Production-quality automatic semantic scene/shot breakdown.
- Automatic visual selection/acquisition/generation for every shot.
- Final Motion Canvas/HyperFrames/Remotion selection and production adapter integration.
- Full ElevenLabs-inspired expressive voice and sound design studio.
- Full multitrack audio timeline, SFX/ambience/character vocals, smart cue placement, ducking and mastering.
- Full editable multitrack timeline.
- Automated captions/subtitle workflow.
- Documentary source workflow, map/data graphics, cartoon/character animation tiers and colorization.
- Real Stable Diffusion inference and sustained target-PC performance acceptance.
- Installer/packaging/release hardening.

## 6. Open decision and technical-spike register

| ID | Question | Status | Rule |
|---|---|---|---|
| TS-01 | Canonical timebase | DONE in Rev 0.4: 141,120,000 ticks/sec | Do not rerun absent regression/new requirement |
| TS-02 | Motion framework comparison | User benchmark done; formal decision pending | Do not repeat benchmark; fill missing matrix evidence |
| TS-03 | Composition serialization/storage | OPEN | Decide before persistent animated composition schema |
| TS-04 | Prompt-based graphics coverage | OPEN | Template/rule-first; measure editable drafts |
| TS-05 | Preview/memory/Tkinter adequacy | OPEN | Prototype and measure on target PC |
| TS-06 | Actual WPM by voice/language | OPEN | Measure; do not silently change TTS speed |
| TS-07 | Map data sources/licenses | OPEN | Verify data and redistribution license |
| TS-08 | Render reproducibility | OPEN | Record tool versions and repeat output |
| TS-09 | Non-verbal vocal feasibility | OPEN | Compare recorded/procedural/local approaches |
| TS-10 | Undo/redo mechanism | OPEN | Prototype representative edit sequences |
| TS-11 | GPU acceleration on baseline hardware | OPEN | Benchmark before relying on it |

Other open decisions: profile field schemas, script issue severity/thresholds, scene-duration formulas, hold_s versus duration_s, media/codec support, audio buses, sound preset format, asset-license metadata, UI toolkit adequacy, packaging and installer licensing.

## 7. Duplicate-work prevention and change control

Before proposing or starting any task:

1. Search this plan for the capability and its VXP/R/TS IDs.
2. Search the completed-work registry and GitHub PR/commit history.
3. Inspect current main and relevant tests; never rely on old branch state or stale Master Spec baselines.
4. Classify the task: **already done**, **partial gap**, **bug**, **new requirement**, or **blocked decision**.
5. If already done: do not implement again; add only missing evidence/documentation.
6. If partial: name the exact missing behavior and add tests only for that gap.
7. If bug: reproduce it and link the regression test to the original phase.
8. If new: add it to this plan, define dependencies and obtain approval before implementation.
9. Every PR must include VXP phase, Master R-stage/engine/contract, prior PRs reused, scope/non-goals, tests, acceptance evidence and this document's status update.
10. Update this registry in the same PR that completes work. Never mark a feature done from a PR title alone.
11. Never merge a PR without the user's explicit approval.
12. Do not rerun completed benchmarks/tests unless a changed path, regression, missing criterion or new requirement justifies it; record why.

### Required PR template

    ## Plan mapping
    - VXP phase:
    - Master R-stage / engine / contract:
    - Related completed PRs reused:

    ## Gap being solved
    - Current verified behavior:
    - Exact missing behavior:
    - Why existing implementation is insufficient:

    ## Scope / non-goals
    ## Dependencies / decisions
    ## Tests and acceptance evidence
    ## Registry updates
    - Completed work:
    - Remaining gaps:
    - Duplicate-work check:

## 8. Definition of Done for each small phase

A phase is DONE only when:
- User-visible behavior matches acceptance criteria.
- Existing .voxora projects and prior workflows remain compatible.
- Unit/integration tests cover success, failure, cancellation and relevant edge cases.
- Required Windows and Ubuntu CI pass on the exact latest PR head, where configured.
- Target-PC acceptance is separated and reported honestly.
- No duplicate registry/contract/provider/renderer was introduced.
- Documentation, registry and dependency decisions are updated.
- User approval is obtained before merge.

## 9. Current next sequence

1. Finalize this plan and reconcile its PR registry against repository history.
2. Close the VXP-00 source-recovery gap: exact 29 Modular Systems and precise R-stage definitions from their original source.
3. Complete the requirement-to-implementation traceability matrix against merged PRs and current Core code.
4. Finish the TS-02 formal decision matrix using the already completed Motion Canvas / HyperFrames / Remotion results. Do not repeat the same experiment.
5. Design Sound & Voice System contracts and the smallest testable vertical slices.
6. Define the Auto Produce production-plan schema and end-to-end acceptance fixture.
7. Implement only the next approved small phase.

Do not start an unrelated feature phase while VXP-00 traceability and the next dependency decision are unresolved.

## 10. Source documents and provenance

- VOXORA_MASTER_SPECIFICATION_REV_0.3.md — original consolidated architecture and roadmap.
- VOXORA_MASTER_SPECIFICATION_REV_0.4.md — current-state overlay; includes TS-01 completion, AI Production Director direction and TS-02 candidate research.
- VOXORA_MASTER_SPECIFICATION_PROMPT.docx — original product requirements.
- GitHub PRs #80–#112 — implementation and documentation evidence in Section 5.
- TS-02 benchmark workspace: D:\Voxora-TS02-Benchmark — isolated user-run framework evaluation.

**Authority rule:** this file organizes delivery; the recovered Master Specification remains the source for original requirements. If a conflict is found, record it and resolve it with the user rather than silently changing either source.
