# Voxora Studio — Master Product Plan & Delivery Registry

> Status: Active planning baseline (PR #113)
> Canonical location: docs/PLANNING/README.md
> Last reconciled: 2026-11-20

## 0. Non-negotiable product identity and outcome

Voxora is an **AI Video Generator / automated video production application — NOT a video editing application or NLE**. Its primary job is to transform a supplied narration voice track and its matching script into a complete, professional-standard video. The user should not have to manually edit a timeline, attach media scene by scene, or assemble transitions.

### Primary user inputs

1. **Script:** the complete text spoken in the video.
2. **Narration audio:** the user's already-generated voice track. This is the primary timing and synchronization source.
3. **Optional visual-direction package:** scene breakdowns, visual prompts, image/video prompts, camera/motion directions, visual references and style guidance. This may be authored by Claude or another assistant and supplied alongside the script/audio.
4. **Channel profile and output preferences:** visual language, aspect ratio, resolution, frame rate and other production defaults.

Voxora must also support a fallback path when the optional visual-direction package is absent: its own Script Intelligence and AI Production Director derive a scene/shot plan and visual prompts from the script and narration. Claude is a supported upstream planning assistant/workflow, not a mandatory runtime dependency.

The defining action is **Generate Video / Auto Produce**. The output is a complete synchronized video, not an editable project that expects the user to finish editing. Internal timelines, tracks and composition data are implementation details used by the generator and may support optional review/corrections, but they do not redefine Voxora as an editor.

### Target user workflow: supplied voice + script → finished video

    User supplies:
    Script + Narration Audio
    + optional Claude visual-direction package
    + Channel Profile / Output Preferences
                       |
                       v
          Input Validation & Script/Audio Match
      language / duration / text-audio consistency
                       |
                       v
            Narration Audio Analysis
       waveform / silence / sentence boundaries /
       word timestamps when available / pacing
                       |
                       v
         Visual-Direction Package Ingestion
       scene prompts / shot prompts / references /
          camera movement / style / constraints
                       |
              (if not supplied)
                       |
                       v
          Script Intelligence + AI Director
       derive scenes, shots and visual prompts
                       |
                       v
            Voice-led Scene & Shot Timing
       map every scene/shot to narration intervals
                       |
                       v
            Automatic Visual Production
       select / generate / compose images, clips,
           diagrams, maps and motion graphics
                       |
                       v
              Motion & Sound Direction
       camera motion / animation / transitions /
          optional SFX, ambience and BGM
                       |
                       v
            Automatic Video Composition
       narration-led visuals + captions + sound
                       |
                       v
                Render Orchestrator
       dependencies / cache / progress / cancel
                       |
                       v
          FFmpeg Final Assembly, Mix and Mux
                       |
                       v
             Automated Quality Validation
       voice sync / duration / visual coverage /
         missing media / black frames / audio
                       |
                       v
                 Finished Video.mp4

**The supplied narration audio is the timing master; the script is the semantic master.** Voxora does not need to generate a replacement voice when the user has supplied narration. It analyses the audio, aligns it with the script, detects pauses and sentence/phrase boundaries, and maps scenes/shots to the real spoken intervals. Use word timestamps when available; otherwise combine audio analysis, forced alignment where practical, and measured segment boundaries. Clearly label uncertain timing. If script and audio materially disagree, report the mismatch and ask for correction or offer a reviewable alignment proposal rather than silently producing an unrelated video.

### Automation requirements

- The primary path starts from user-supplied narration audio + matching script; TTS generation is optional, not a required first step.
- Auto Produce creates the complete video without requiring manual timeline editing or scene-by-scene media attachment.
- Accept an optional structured visual-direction package from Claude/another assistant (scene and shot breakdown, per-shot visual prompts, image/video prompts, camera/motion directions, style references and constraints). Validate and map it to the script/audio rather than blindly trusting it.
- When that package is absent, the internal Director generates equivalent scene/shot directions and prompts.
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
02.6 Script-assisted caption pipeline: supplied script is the text source; supplied narration is the timing master. Use forced alignment/word timestamps, sentence-aware segmentation, ASR discrepancy verification and uncertainty flags; export SRT/VTT and burned-in captions.
02.7 Multilingual caption correctness: Bengali Unicode/যুক্তাক্ষর, English and mixed-language text; Arabic/English parallel tracks where a profile requires them.
02.8 Caption layout/readability: profile-aware typography, line length, reading speed, safe margins, speaker labels/highlight modes and configurable caption-off export.
02.9 Caption QC: missing/duplicated words, overlap, timing drift, punctuation, clipping and font fallback.

**Existing foundation:** Edge TTS provider, voice discovery/preview, narration parsing, pause handling, chunking, narration generation and audio assembly. Do not rewrite these. First inventory exact gaps and preserve tested behavior. **Scheduling boundary:** keep the current Edge TTS implementation available, but defer advanced Bengali TTS quality work (Bangladesh-accented male voice tuning, Bengali text normalization, pronunciation dictionary, narration presets, long-form voice quality controls and dedicated Bengali audio QC) to the final VXP-14 stage. Do not pull this work forward into VXP-02 or make it a dependency of automatic video generation.

### VXP-03 — Channel profiles and creative rules (R-3; SC-08)

03.1 Versioned profile registry.  
03.2 Profile precedence: built-in → user → project override.  
03.3 Capability preferences and fallback policy.  
03.4 Per-profile narration, visual, motion, audio and export defaults.  
03.5 Profile editor, validation, import/export and compatibility tests.  
03.6 Profile catalogue and creative rules for all 14 planned channels (CP-01–CP-14); detailed definitions live in [Channel & Visual Production Profiles](./CHANNEL_VISUAL_PRODUCTION_PROFILES.md).

Profiles are data, not hard-coded branches in the Universal Core. A profile cannot require a paid provider. The 14 profiles cover Quasivanta, Veltracis, Sizzjin, Drowsehaven, Rihvaya, Niq Exposed, Deep Ocean Creatures, Crime Documentary, Educational Explainer, Inventions & Discoveries, Cartoon & Animated Stories, Biography & Famous Personalities, Animals & Wildlife, and Science & Discovery. Current and future channels share the same Universal Core and production engines.

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
| 06.8 | Audit and adapt the MIT-licensed [Cinematic Skill](https://github.com/Moh4696/cinematic-skill): beat tables, word-synchronised visual cues, camera choreography, Skia drawing, maps/cards/archive layouts, sound cue lists, caption finishing and render review | PLANNED |
| 06.9 | Advanced animation grammar: keyframes, easing, camera rigs, parallax/depth layers, masks, particles, shape/text animation, 2D character/Stickman rigs, transitions and reusable motion presets | PLANNED |
| 06.10 | Render-quality tiers and benchmark: draft/proxy/final, resolution/FPS, anti-aliasing, typography, frame pacing, memory ceiling, deterministic output and preview/final parity | PLANNED |
| 06.11 | Cinematic Skill adapter/prototype using Voxora's existing project, script and supplied-audio contracts; no duplicate project, audio or render pipeline | PLANNED |

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
08.6 Sketch/whiteboard/hand-drawn illustration, 2D cartoon, 2.5D parallax and layered camera movement.  
08.7 First-class character and Stickman animation: reusable character identity, rigs/poses/expressions/actions, multi-character interaction, continuity and narration/dialogue synchronization.  
08.8 Optional local image/video generation providers.  
08.9 Visual continuity, provenance, licensing, source attribution and factual/illustrative/reconstruction labels.  
08.10 Profile-aware style selection across documentary photography, animation, maps, sketch, infographic, scientific/3D visualization and procedural graphics.
08.11 Advanced 2D animation: keyframed transforms, easing curves, camera choreography, layered parallax, depth staging, masks, shape morphs, kinetic typography, animated maps, diagrams, particles and compositing.
08.12 Character animation: reusable 2D rigs, pose libraries, expression/action systems, multi-character blocking, lip-sync where supported and narration-beat synchronization.
08.13 Cinematic code-rendering toolkit: evaluate/adapt Skia-based drawing, designed-world/evidence-board layouts, continuous camera journeys, word-timed highlights, stamps, routes, counters and spotlight cues from Cinematic Skill.
08.14 Render finishing: anti-aliasing, motion blur where affordable, colour/look pipeline, typography/font fallback, frame pacing, caption-safe composition, sound cue alignment and final-frame validation.
08.15 Animation/render quality tiers: low-memory preview, draft and final profiles with deterministic settings and capability-aware graceful degradation.

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
09.9 Render quality controls: output resolution, FPS, codec/bitrate, pixel format, scaling/anti-aliasing, audio loudness and caption burn-in; expose only validated capabilities.
09.10 Frame-level QC and visual review artifacts: contact sheets/keyframes, blank/black/frozen-frame checks, dropped/duplicate frames, text clipping, caption safe area and scene transition integrity.
09.11 Memory-aware render scheduling: bounded concurrency, sequential fallback on the target PC, per-stage resource estimates, resumable frame batches and safe cleanup; parallel render only when measured headroom allows.

Do not introduce parallel rendering or silent engine fallback without a separate measured design. Extend the existing sequential Universal Produce pipeline.

### VXP-10 — AI Production Director and Auto Produce (R-7; orchestration layer)

This is the main automation milestone. It integrates existing engines; it must not duplicate them.

10.1 Production-plan schema: scenes, shots, narration audio ranges, visual prompts, motion directions, audio cues and engine choice.  
10.2 Import and validate external visual-direction packages (Claude-generated or compatible structured input).  
10.3 Script/audio alignment and narration-led scene/shot timing.  
10.4 Internal Script Intelligence fallback: derive scene/shot plan and prompts when no external package is supplied.  
10.5 Automatic visual selection/acquisition/generation per shot from approved prompts.  
10.6 Automatic motion/animation/graphics direction per shot.  
10.7 Automatic SFX/BGM/ambience cue placement and mix intent, respecting the supplied narration track.  
10.8 Build the internal composition/timeline automatically; no manual per-shot assembly required.  
10.9 One-action Generate Video: validate inputs → align voice/script → plan → visuals → motion → sound → render → QC.  
10.10 Optional review and selective regeneration of a scene/shot; never make editing a prerequisite.  
10.11 Failure recovery and deterministic rerun from cached successful stages.
10.12 Automatic cinematic direction: convert narration beats into camera paths, visual focal points, timed highlights, map/document/card reveals, kinetic typography and sound/caption cues.
10.13 Select the best compatible animation/render adapter per shot (2D, Stickman, map, infographic, 2.5D, code-drawn cinematic scene or optional 3D); keep one unified production graph.
10.14 Auto-select render quality tier from output request and measured hardware budget; render proxy for review if useful, then final MP4 without user timeline assembly.
10.15 Integrate caption alignment, caption styling, SRT/VTT sidecars and burned-in caption QC into the same Auto Produce job.

**Generate Video acceptance:** with a matching script + supplied narration audio + profile, and optionally a Claude visual-direction package, one user action produces a playable final MP4. The narration track is preserved as the primary voice track; visuals, scene changes, motion, captions and optional sound design align to its actual timing. Without an external prompt package, Voxora creates the scene/shot prompts itself. No manual timeline editing or per-scene asset attachment is required. Missing providers/assets yield explicit profile-compatible fallback or actionable errors, never fake success.

### VXP-11 — Hybrid media, documentary, cartoon and specialized workflows (R-8/R-9/R-10)

11.1 Hybrid stills, clips, graphics, overlays and optional 2.5D.  
11.2 Documentary research, real-photo/footage acquisition, source/license/provenance tracking and factual review.  
11.3 Maps, archival material, timelines, evidence/document graphics and clearly labelled reconstructions.  
11.4 Cartoon/character library, reusable poses, props, locations, character identity and continuity.  
11.5 First-class Stickman animation and reusable pose/action/expression systems.  
11.6 Dialogue-free-but-not-silent comedy with non-verbal vocals.  
11.7 Story/short-film continuity, multi-character interaction, lip-sync where supported and narration-synchronized beat timing.  
11.8 Biography production: verified real-person portraits/archives, chronological life timelines, achievements/legacy graphics and labelled illustrative reconstruction.  
11.9 Animal/wildlife production: species-accurate illustration, anatomy/behavior visualization, habitats and documentary footage.  
11.10 Scientific visualization: 2D/3D concepts, diagrams, simulations, units/data and evidence-vs-hypothesis labelling.  
11.11 Colorization/artwork tools and non-destructive layers.  
11.12 Optional advanced 3D/AI integrations (future research).

All these workflows reuse the same Core and render/audio systems; they are not separate applications.

### VXP-12 — Internal timeline/composition model and optional production review (R-5)

12.1 Internal timeline/timebase model using canonical project timebase.  
12.2 Internal video/image/graphics/audio/caption tracks for synchronization and rendering.  
12.3 Optional shot-list/storyboard review and limited corrections where useful.  
12.4 Selective regeneration, accept/reject and non-destructive production proposals.  
12.5 Low-resolution proxy preview and memory-aware playback.  
12.6 UI toolkit prototype/decision if Tkinter becomes a bottleneck.

**Explicit product boundary:** Voxora is an automated video generator, not a user-facing NLE. Internal tracks and composition data are implementation details. A full manual multitrack timeline editor, clip trim/split/move workflow, and manual assembly are not planned acceptance requirements. Auto Produce must create a finished MP4 without the user opening or editing a timeline. Optional review/corrections must never become a prerequisite.

### VXP-13 — Reliability, performance, security and distribution

13.1 Target-Windows-PC acceptance for full Auto Produce.  
13.2 Memory/performance budgets and graceful degradation.  
13.3 Project recovery, render-job recovery and crash-safe cleanup.  
13.4 Security review: paths, subprocesses, imported projects and secrets.  
13.5 Licensing/redistribution audit for FFmpeg, fonts, media and engines.  
13.6 Installer, first-run setup, logs, diagnostics and updates.  
13.7 Release regression matrix and reproducible build.

Target hardware: Windows 10, Intel i5-8250U, 8 GB RAM, NVIDIA 940MX 4 GB + Intel UHD 620, 1 TB HDD. Prefer sequential jobs, low-resolution previews, lazy loading, bounded caches and CPU fallback. Do not promise high-end 3D or local video diffusion on this machine.

### VXP-14 — Advanced Bengali TTS and natural male narration (FINAL DEFERRED WORKSTREAM)

**Priority rule: this is the final planned enhancement workstream, not a prerequisite for the core video generator.** Do not begin VXP-14 until the end-to-end Auto Produce path, AI Production Director, required visual production/animation adapters, final rendering and their target-PC acceptance priorities have been addressed. This workstream must not delay or block the script + supplied narration audio → finished video outcome.

14.1 Preserve and reuse the existing Edge TTS provider, voice discovery/preview, narration parser, pause handling, chunking and audio assembly; no duplicate narration engine.  
14.2 Evaluate the free bn-BD-PradeepNeural Bangladesh-accented male voice as the primary candidate, subject to availability and listening-based quality acceptance.  
14.3 Bengali script normalization for numbers, dates, abbreviations, punctuation, sentence boundaries and mixed Bengali/English terms.  
14.4 User-editable Bengali pronunciation dictionary for names, places, scientific terms and Islamic/Arabic vocabulary.  
14.5 Narration presets for documentary, storytelling, educational and respectful Islamic narration; expose only controls supported by the provider.  
14.6 Long-form narration reliability: sentence-aware chunking, stable joins, natural pauses, selective retry, cache and export validation.  
14.7 Bengali speech quality checks and a repeatable listening benchmark for pronunciation, prosody, pacing, clipping, omissions and long-form consistency.  
14.8 Keep the solution free-first and API-key-free where practical; disclose online-service dependence, access limits and policy changes. Do not assume Edge TTS is a guaranteed unlimited or permanent public API.  
14.9 Treat offline/local Bengali models as optional future research only after license, commercial-use rights, memory use and target-PC performance are verified.

**Acceptance boundary:** existing Edge TTS workflows remain functional throughout the project. VXP-14 is complete only when the enhanced Bengali male narration is measurably better on a representative listening set, long-form generation is reliable, and no paid API is required for the accepted free-first path.

## 4A. Candidate open-source integrations — audit before adoption

This is a **candidate registry**, not an implementation commitment. These projects must not be installed wholesale or treated as production-ready Voxora dependencies merely because they are open source. The goal is to extract reusable capabilities through narrow adapters while preserving Voxora's supplied-script + supplied-narration → finished-MP4 product workflow and its existing project/audio/render contracts.

### Candidate catalogue

| Candidate | Potential Voxora capability | Proposed treatment | Status / constraints |
|---|---|---|---|
| [Cinematic Skill](https://github.com/Moh4696/cinematic-skill) | Code-driven cinematic scenes, beat/word-aware visual direction, camera choreography and visual finishing (verify actual repository capabilities) | Highest-priority source audit; reuse compatible code or build a thin adapter; compare output against Voxora's existing FFmpeg pipeline | AUDIT FIRST; MIT licence reported by project, verify exact files/dependencies and current licence before reuse |
| [OpenMontage](https://github.com/OpenMontageInc/OpenMontage) | Agentic production workflow, pipeline manifests, tool/skill orchestration, documentary footage acquisition and quality gates | Study architecture and reusable workflow patterns; do not replace Voxora's Core, project model or user-supplied narration flow | AUDIT FIRST; official repository currently identifies AGPL-3.0. No code copying/linking/distribution decision until licence and dependency review |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | Node-based image/video generation workflows and model/provider orchestration | Optional external visual-generation adapter; keep model execution optional and resource-aware | RESEARCH; repository is GPL-3.0; review redistribution/integration implications and each model/weight licence separately |
| [Synfig Studio](https://github.com/synfig/synfig) | 2D vector animation, interpolation and reusable character motion | Evaluate whether its rendering/animation capabilities can be driven headlessly or via a narrow interchange adapter | CANDIDATE; inspect current licence, automation surface, export and Windows resource use |
| [Animate / StykAnimate](https://github.com/abubakrabdulahadov/Animate) | Stick-figure posing, keyframes, motion paths, camera movement and frame/video export | Evaluate as a specialized Stickman asset/animation workflow; verify project format and headless automation before integration | CANDIDATE; confirm upstream identity, licence, project-format stability and export automation |
| [OpenToonz](https://github.com/opentoonz/opentoonz) | Traditional 2D/cartoon production and frame-based animation | Research reusable pipeline/export concepts for the Cartoon & Animated Stories profile | CANDIDATE; likely better as optional external tool than a bundled runtime until automation and licence are reviewed |
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | Documentary maps, routes, borders, locations, terrain and geographic motion | Build a map-scene adapter with deterministic camera/time controls; audit tile/data source licences separately | CANDIDATE; validate offline rendering, screenshot/video capture and data attribution |
| [Manim Community](https://github.com/ManimCommunity/manim) | Mathematical, scientific and explanatory animations | Specialized scene renderer for Science & Discovery / Educational Explainer shots | CANDIDATE; measure render speed, typography, memory and deterministic export on target PC |
| [WhisperX](https://github.com/m-bain/whisperX) | Speech transcription, word timestamps and forced alignment | Optional narration-analysis/caption adapter; script remains semantic source and supplied audio remains timing master | CANDIDATE; benchmark Bengali alignment specifically; do not assume English alignment quality transfers to Bengali |
| [Audio Separator](https://github.com/nomadkaraoke/python-audio-separator) | Voice/music/stem separation for audio cleanup and sound-design workflows | Optional audio utility behind capability detection; never alter the supplied narration without explicit policy | CANDIDATE; verify model licences, disk/GPU/RAM requirements and audio-quality impact |
| [Motion Canvas](https://github.com/motion-canvas/motion-canvas), [HyperFrames](https://github.com/HyperFrames](https://github.com/HyperFrames), [Remotion](https://github.com/remotion-dev/remotion) | Code-driven motion graphics and composition | Reuse the completed TS-02 benchmark evidence; do not repeat the same benchmark. Decide adapter only after the formal matrix | BENCHMARK PARTIAL; primary framework decision remains open |

### Integration rules and acceptance gates

1. **Source and licence audit:** record canonical upstream URL, exact commit/tag, licence file, transitive dependencies, model/weight/data licences, attribution duties and redistribution obligations. A repository licence does not automatically license its models, datasets, fonts, footage or generated assets.
2. **Capability audit:** identify the exact reusable modules, public APIs/CLI, automation/headless support, input/output formats, platform support and maintenance status. Verify claims against source code rather than repository marketing copy.
3. **Architecture fit:** use adapters or isolated subprocesses where appropriate. Do not duplicate Voxora's ProjectSession, asset registry, narration pipeline, composition contracts, Render Orchestrator or FFmpeg final assembly.
4. **Hardware gate:** measure peak RAM/VRAM, CPU use, disk footprint, render time and graceful CPU fallback on the documented Windows 10 / i5-8250U / 8 GB RAM / NVIDIA 940MX target PC. Heavy generation may remain an optional remote or higher-end-machine provider.
5. **Visual-quality gate:** render representative Stickman, 2D cartoon, map, scientific explainer and documentary scenes; assess motion smoothness, character continuity, Bengali typography, camera control and narration synchronization.
6. **End-to-end gate:** one supplied script + matching narration audio + channel profile must produce a complete playable MP4 without manual per-scene asset assignment or timeline editing. Validate audio preservation, duration, captions where enabled, visual coverage, black frames and provenance.
7. **Adoption decision:** classify each project as REUSE CODE, ADAPTER, EXTERNAL OPTIONAL TOOL, NATIVE IMPLEMENTATION, REFERENCE ONLY or REJECT. No dependency is added until its specific acceptance and licence gates pass.

### Audit sequence

1. Cinematic Skill — exact source/architecture/licence audit and a small Voxora-compatible prototype.
2. OpenMontage — workflow/tool/quality-gate architecture audit, with AGPL boundary explicitly reviewed.
3. ComfyUI — optional provider/workflow adapter and model-licence audit.
4. Stickman and 2D animation candidates — Animate/StykAnimate, Synfig and OpenToonz capability/export comparison.
5. MapLibre and Manim — documentary/science specialized visual adapters.
6. WhisperX and Audio Separator — narration alignment and optional audio processing.
7. Reconcile all findings with the existing TS-02 Motion Canvas / HyperFrames / Remotion benchmark; do not rerun completed tests without a changed requirement.

**Current status:** all entries above are candidates or audit targets only. None is represented as integrated, installed, tested or accepted in Voxora by this planning entry. This registry does not change the core Auto Produce priority or advance the deferred VXP-14 Bengali TTS workstream.
 
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
- Full user-facing NLE/manual multitrack editor (explicitly not a product goal); only optional production review/correction UX is in scope.
- Automated captions/subtitle workflow (script-first forced alignment, multilingual typography, SRT/VTT, burned-in rendering and QC).
- Production-grade advanced animation grammar, reusable character rigs and full cinematic camera/motion direction.
- Cinematic Skill audit/adaptation and its Skia-based rendering techniques integrated with Voxora's existing audio, project, motion and FFmpeg contracts.
- Final render-quality tiers, memory-aware scheduling and target-PC visual-quality acceptance.
- Documentary source workflow, map/data graphics, cartoon/character animation tiers and colorization.
- Real Stable Diffusion inference and sustained target-PC performance acceptance.
- Installer/packaging/release hardening.
- Advanced natural Bengali male TTS enhancement beyond the existing Edge TTS foundation; intentionally deferred to final VXP-14.

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
5. Audit Cinematic Skill source, MIT licence, dependencies and workflow; prototype its highest-value code-rendering, camera and beat-sync techniques against Voxora's supplied narration and existing FFmpeg pipeline.
6. Design the script-first Auto Caption pipeline and multilingual caption acceptance matrix.
7. Define advanced animation/render quality acceptance criteria and integrate them into the Auto Produce production graph.
8. Design Sound & Voice System contracts and the smallest testable vertical slices.
9. Define the Auto Produce production-plan schema and end-to-end acceptance fixture.
10. Implement only the next approved small phase.
11. After the core automatic video-generation workflow and its visual/animation/rendering acceptance priorities, schedule VXP-14 as the final deferred workstream; do not advance Bengali TTS ahead of those priorities.

Do not start an unrelated feature phase while VXP-00 traceability and the next dependency decision are unresolved.

## 10. Channel and visual production profile catalogue

The 14 planned channel profiles and their creative rules, preferred visual treatments, factual safeguards, and acceptance mapping are maintained in [CHANNEL_VISUAL_PRODUCTION_PROFILES.md](./CHANNEL_VISUAL_PRODUCTION_PROFILES.md). This catalogue is part of the planning baseline; it does not claim that all listed engines are implemented. One Universal Visual Production Engine and shared specialized engines serve all profiles.

**Profile coverage:** Quasivanta; Veltracis; Sizzjin; Drowsehaven; Rihvaya; Niq Exposed; Deep Ocean Creatures; Crime Documentary; Educational Explainer; Inventions & Discoveries; Cartoon & Animated Stories; Biography & Famous Personalities; Animals & Wildlife; Science & Discovery.

## 11. Source documents and provenance

- VOXORA_MASTER_SPECIFICATION_REV_0.3.md — original consolidated architecture and roadmap.
- VOXORA_MASTER_SPECIFICATION_REV_0.4.md — current-state overlay; includes TS-01 completion, AI Production Director direction and TS-02 candidate research.
- VOXORA_MASTER_SPECIFICATION_PROMPT.docx — original product requirements.
- GitHub PRs #80–#112 — implementation and documentation evidence in Section 5.
- TS-02 benchmark workspace: D:\Voxora-TS02-Benchmark — isolated user-run framework evaluation.

**Authority rule:** this file organizes delivery; the recovered Master Specification remains the source for original requirements. If a conflict is found, record it and resolve it with the user rather than silently changing either source.
