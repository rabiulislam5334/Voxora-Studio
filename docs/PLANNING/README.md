# Voxora Studio — Master Product Plan

> **Status:** Planning baseline / recovery draft  
> **Document role:** Single Source of Truth for product direction, architecture boundaries, roadmap, and implementation decisions.  
> **Rule:** No new feature phase starts unless it maps to this plan and updates its status here.

Last reconciled: 2026-11-20

---

## 1. Product vision

Voxora Studio is a **local-first, modular AI-powered creative production desktop studio**. It is intended to help one creator or a small team produce different kinds of narrated and non-narrated video content through reusable production systems—not merely generate images or run an FFmpeg export.

The product must support multiple creative formats through pluggable engines while keeping one coherent project, timeline, asset, audio, and rendering foundation.

### Product principles

1. **Plan-first, integrated development:** every implementation belongs to a named system and roadmap item.
2. **Local-first and cost-conscious:** core workflows must remain usable without paid APIs or mandatory cloud services. Optional providers require explicit user configuration and consent.
3. **One project, one source of truth:** all workspaces operate on the same application-owned project session.
4. **Engine independence:** creative engines, motion frameworks, composition renderers, audio providers, and visual-generation providers are separate capability contracts.
5. **Human approval:** AI proposes; the user reviews and approves consequential project changes, provider calls, and final production.
6. **Backward compatibility:** preserve existing `.voxora` projects unless a separately planned migration is approved.
7. **Hardware-aware:** default workflows must be conservative on the target Windows machine (Core i5-8250U, 8 GB RAM, NVIDIA 940MX 4 GB). Heavy inference/rendering must be optional and measurable.
8. **No false completion:** CI, synthetic tests, and real-device acceptance are reported separately.

## 2. Scope: what Voxora is—and is not

### In scope

- Script, narration, scene, shot, asset, character, timeline, and project management.
- AI Production Director and structured scene/shot planning.
- Multiple motion/animation/visual production engines.
- Advanced voice, sound-effects, music, and audio-post-production systems.
- Unified render orchestration and final audio/video assembly.
- Channel profiles that configure style, workflow defaults, and suitable engines.
- Optional local/remote AI providers behind explicit adapters.
- Reusable asset and provenance management.

### Not the product's central purpose

- Image generation by itself.
- A single renderer or framework.
- A collection of disconnected demo pages.
- Mandatory cloud APIs, paid API keys, or automatic network fallback.
- Automatically mutating a user's project without review.

Image generation is an **optional visual-asset capability** within the larger production pipeline. It must not displace sound, motion, directing, or renderer integration in roadmap priority.

## 3. Canonical architecture

```text
User Brief / Channel Profile
          |
          v
   AI Production Director
          |
          +--> Script & Narration Plan
          +--> Story / Structure / Research Plan
          +--> Scene & Shot Planner
          +--> Visual / Motion / Audio Direction
          |
          v
    Reviewable Production Plan
          |
          v
       Universal Core
  Project / Scene / Shot / Asset
  Character / Timeline / Track
  Audio / Metadata / Provenance
          |
          +-----------------------------+
          |             |               |
          v             v               v
   Motion/Visual     Sound & Voice    Other Media
      Engines          Engines        Providers
          |             |               |
          +-------------+---------------+
                        |
                        v
              Render Orchestrator
                        |
             +----------+-----------+
             |          |           |
             v          v           v
          Frame/     Audio Mix    Validation
          Video      & Mux        & QC
          Renderer
             |
             v
        Final Export
```

### Architectural boundaries

- **Universal Core:** canonical project data and domain contracts; no framework-specific UI state.
- **AI Production Director:** turns a brief into a reviewable plan; it does not directly bypass project approval.
- **Engine Registry:** scene/shot production engines; each declares capabilities and requirements.
- **Motion Framework Adapters:** integrations for evaluated motion technologies; not conflated with the scene-segment engine registry.
- **Composition Renderer Registry:** still-image/layer composition capabilities, separate from animated video engines.
- **Sound/Voice Provider Registry:** TTS, voice conversion/design (if later approved), SFX, music, and audio processing capabilities.
- **Visual Generation Provider Registry:** optional image/video asset generation providers.
- **Render Orchestrator:** schedules and connects approved outputs, handles cancellation/progress/temp files, and validates final media.
- **Project Session:** one application-owned live project session shared across all relevant workspaces.

## 4. Master system inventory — 29 modular systems

The original planning conversations refer to **29 Modular Systems**. The complete original 29-item names and definitions have not yet been recovered in the material currently verified. To avoid silently inventing or renumbering the original specification, this section is a controlled recovery register.

| ID | System | Recovery status | Notes |
|---|---|---|---|
| MS-01–MS-29 | Original 29-system inventory | **SOURCE RECOVERY REQUIRED** | Restore exact names, boundaries, dependencies, and acceptance criteria from Master Specification Rev 0.3 / original planning notes. Do not substitute guessed names. |

**Hard rule:** the table above is not permission to treat the 29 systems as absent. It means their canonical inventory must be transcribed from the original source before system IDs are assigned. Until then, use the workstreams in Section 7 as planning categories only—not as replacement MS-01…MS-29 identifiers.

## 5. Master Specification stages

The prior planning record identifies **Master Specification Rev 0.3** and stages **R-1 through R-11**. These identifiers are distinct from GitHub implementation phase numbers (for example, Phase 1.8, 1.9, 2.0, or 3.5.6.x).

The exact original R-1…R-11 titles and acceptance criteria still require source recovery. Do not infer their names from implementation history.

| Master stage | Status in this recovery draft |
|---|---|
| R-1 … R-11 | Original stage definitions and order: **SOURCE RECOVERY REQUIRED** |
| Phase 1.8 | Previously recorded as Multi-Scene Coordinator |
| Phase 1.9 | Previously recorded as Cross-Process Save Lock |
| Phase 2.0 | Previously planned as Reliability work; exact original scope must be recovered |

Keep Master Specification stage IDs and GitHub PR/phase IDs in separate columns in all future tracking.

## 6. Core product systems and required capabilities

These are product-level capability groups used to organize the roadmap while the exact 29-system source inventory is being recovered.

### 6.1 Universal Core & Project System

- One canonical project/session shared across Script, Assets, Composition, Timeline, and Produce.
- Project, scene, shot, asset, character, timeline, track, audio, and metadata contracts.
- Backward-compatible `.voxora` serialization, revisioning, backups, conflict detection, and recovery.
- Explicit dirty-state management and safe project replacement.
- Stable IDs, deterministic operations, provenance, and schema-version discipline.

### 6.2 AI Production Director

- Brief/prompt intake with channel-profile context.
- Content format selection and creative treatment proposal.
- Script and narration planning; duration and pacing estimates.
- Scene breakdown, shot list, camera/motion direction, visual continuity, and asset requirements.
- Audio direction: voice, delivery, ambience, SFX, music, transitions, and mix intent.
- Engine/provider capability matching based on declared support—not hard-coded assumptions.
- Reviewable plan, revision history, explicit approval, and regeneration of selected sections.
- No automatic scene mutation or provider execution without the relevant user approval.

### 6.3 Motion & Animation System

- A unified motion/animation scene description that can be translated by multiple adapters.
- 2D motion graphics, typography, infographic, charts, maps, diagrams, sketch/whiteboard, 2.5D parallax, character/stickman animation, and 3D/4D-capable integrations as future capability tiers.
- Timeline-aware keyframes, transforms, camera moves, easing, layers, masks, transitions, and reusable templates.
- Deterministic preview/render settings and explicit engine capability declarations.
- Keep motion-framework experiments and evaluation evidence in a dedicated decision record.
- **HyperFrames, Remotion, Motion Canvas, and the other framework(s) evaluated by the user must be recorded with actual test results before selecting or implementing an adapter.** The full tested-framework list and comparative results remain to be recovered; no winner is assumed here.

### 6.4 Sound & Voice System — high-priority product pillar

The target is a professional, ElevenLabs-inspired **sound production experience**, not simply a TTS button. This is a product direction, not a claim that every feature is already implemented.

Required capability areas to design and phase:

- Voice catalog, provider capability discovery, voice preview, language/accent/gender/style metadata where supported.
- Script-to-speech generation with chunking, pronunciation controls, pauses, and consistent voice selection.
- Expressive delivery controls where provider/model supports them: emotion, intensity, pace, stability/variation, emphasis, and delivery style. Never expose unsupported controls as if they work.
- Voice profiles and reusable per-channel/per-character voice assignments.
- Multiple narration tracks and scene-level voice assignment.
- SFX library, search/tagging, cue placement, fades, gain, and synchronization to scene/shot events.
- Background music library, track placement, ducking under narration, fades, looping, and per-scene ambience.
- Audio timeline/mixer: track gain, pan where supported, fades, clip trim, offsets, automation, and mute/solo.
- Loudness/peak/clipping checks, silence detection, normalization/limiting where appropriate, and final audio QC.
- Audio cache, provenance/licensing metadata, provider errors, cancellation, and retry behavior.
- Offline/local options where feasible; optional remote providers only with explicit user consent and clear cost/network disclosure.

Current baseline known from repository: Edge TTS integration, narration generation, audio/video assembly and validation exist. This does **not** mean the full advanced sound system above is implemented.

### 6.5 Visual Asset System

- Asset library, metadata, provenance, content hashes, validation, and reuse.
- Support user-provided images, generated images, video clips, audio, fonts, and other media types as appropriate.
- Optional local image generation is one provider capability, not the central workflow.
- Generated assets must be reviewed and deliberately bound to scenes.
- Provider registration, model management, and inference must remain explicit and local-first where possible.

### 6.6 Renderer & Production System

- Separate scene/shot engines from composition renderers and motion-framework adapters.
- Render orchestration, dependency checks, capability negotiation, progress, cancellation, temp-file ownership, cache, and retries.
- Frame sequence, video encoding, audio mix/mux, transitions, and final media validation.
- Output profiles for aspect ratio, resolution, frame rate, codecs, and quality.
- Deterministic export and reproducibility metadata.
- Do not describe still PNG composition support as animated MP4 rendering.
- Do not select, substitute, or fall back to a renderer silently.

### 6.7 Channel Profile System

Profiles configure creative defaults and allowed/preferred capabilities, not separate application architectures.

Known channel profiles:
- Quasivanta — space/science; cinematic 3D-style visuals, data visualization, and infographics.
- Veltracis — history/mystery/documentary; maps, archival collage, sketch, and 2.5D.
- Sizzjin — horror/suspense; silhouette, paper-cutout, atmosphere, and controlled motion.
- Drowsehaven — sleep stories; calm illustrated/watercolor visuals and restrained movement.
- Rihvaya — Islamic education/history; respectful evidence-led documentary visuals and religious-content safeguards.
- MindNiq — educational explainers; stickman, flat vector, diagrams, and whiteboard.
- Inventions & Discoveries — separate planned channel/profile; discovery storytelling, diagrams, timelines, and explanatory motion.

Profiles must be editable, versioned, and mapped to capabilities. A profile must never require a paid provider.

## 7. Roadmap workstreams and dependency order

This roadmap is an integration order, not a replacement for the original R-1…R-11 stage names or the 29-system inventory.

| Order | Workstream | Main outcome | Dependency / gate |
|---|---|---|---|
| W0 | Planning & source recovery | Restore Rev 0.3, exact 29 systems, R-1…R-11, framework test notes | Must precede new feature phases |
| W1 | Architecture & Universal Core | One canonical domain model, project session, contracts, compatibility | Foundation for all workstreams |
| W2 | AI Production Director | Brief → reviewable production plan → scene/shot/audio/motion plan | W1 contracts |
| W3 | Motion framework decision & adapters | Evidence-based framework selection and reusable motion engine integration | Recover user test results; define adapter contract |
| W4 | Sound & Voice System | Advanced voice controls, audio assets, SFX/BGM, mixer, audio QC | W1 timeline/audio contracts |
| W5 | Renderer orchestration | Unified render graph across motion, visual, and audio outputs | W1 + W3 + W4 |
| W6 | Channel profile integration | Profile-driven director, engine, and audio defaults | W2–W5 capability contracts |
| W7 | Visual asset providers | Optional image/video generation and asset ingestion | W1 asset contracts; must not block W3/W4 |
| W8 | End-to-end production UX | One project from brief to approved final export | W2–W7 |
| W9 | Reliability, performance & packaging | Recovery, performance budgets, hardware acceptance, distribution readiness | End-to-end workflows stable |

### Priority correction

The recent Phase 3.5.6.x work delivered meaningful visual-generation and composition integration. It is one subsystem. It must not automatically dictate the next phase.

**Next planning priority:** recover the original specification and framework evaluation evidence, then perform a gap map against current main. After that, prioritize the architecture and sound/motion pillars based on the recovered plan—not on whichever feature is easiest to implement next.

## 8. Current implementation baseline (verified from current repository/docs)

This section records known repository capabilities, not the full product completion percentage.

| Area | Current known state | Important boundary |
|---|---|---|
| Desktop shell / navigation | Implemented | Some secondary areas may remain planned |
| Edge TTS / narration | Implemented baseline | Not equivalent to full expressive voice platform |
| Project / scene / asset core | Implemented baseline; shared project session delivered | Continue validating end-to-end UX |
| `.voxora` persistence | Existing backward-compatible project format | Avoid unplanned schema migration |
| FFmpeg production | Existing sequential render and A/V assembly pipeline | Not a complete multi-engine motion platform |
| Audio/video validation | Existing stream, duration, frame-count, timestamp, sync checks | Advanced sound design/mixer still needs planning |
| Local Stable Diffusion.cpp | Implemented optional CPU provider and desktop workflow | Real model inference and hardware performance require manual PC acceptance |
| Generated-image binding | Implemented with provenance checks and approval | Not a general AI Director |
| Raster composition | Still PNG composition integration implemented | Not an animated motion renderer |
| Universal Produce | Existing end-to-end pipeline with synthetic generated-image fixture | Synthetic tests do not prove real local inference or long-form device performance |
| Motion frameworks | Evaluation was discussed/performed by user | Exact test matrix/results must be recovered before integration decision |
| ElevenLabs-like sound system | Product requirement captured here | Full feature implementation is not yet verified |

Repository baseline at plan creation: main includes the merged Phase 3.5.6.11–3.5.6.12 work (PR #112). Do not infer that the full Master Specification is complete from that phase history.

## 9. Acceptance and completion rules

A roadmap item may be marked **Done** only when all applicable conditions are met:

1. Its scope maps to one or more named systems in the recovered master inventory.
2. Architecture and dependency decisions are documented.
3. Implementation and focused automated tests are complete.
4. Regression tests protect existing project formats and workflows.
5. CI result is checked against the exact latest PR head SHA.
6. UI behavior is tested where the change affects the desktop workflow.
7. Real-device checks are explicitly separated from CI and completed when required.
8. User-facing limitations, provider requirements, and performance costs are documented.
9. This plan and the relevant decision/acceptance records are updated in the same PR.

Use these statuses only:
- **PLANNED** — approved by the master plan, not started.
- **IN PROGRESS** — implementation underway.
- **IMPLEMENTED / NOT INTEGRATED** — code exists but end-to-end workflow is incomplete.
- **AUTOMATED VERIFIED** — exact-head CI and relevant automated tests pass.
- **DEVICE VERIFIED** — target-PC/manual acceptance completed and recorded.
- **BLOCKED** — dependency or decision prevents progress.
- **DEFERRED** — intentionally postponed with a reason.

Never use “complete” without naming which verification level was achieved.

## 10. Change-control rules

- Read this file before proposing or starting any implementation.
- Every PR must reference its Master Plan section, system ID(s), dependencies, and acceptance criteria.
- Every new technology evaluation gets a decision record: test setup, machine, version, workload, measurements, pros/cons, limitations, and decision.
- Do not add a framework/provider just because it is popular or easy to wire in.
- Do not create parallel implementations of the same capability without an architecture decision.
- No hidden cloud fallback, automatic download, API-key requirement, or paid dependency.
- No unrelated scope bundled into a phase.
- Update the roadmap status in the same PR as implementation.
- Never merge a PR without the user's explicit approval.

## 11. Open source-recovery tasks

These are mandatory before declaring this a faithful transcription of the original plan:

- [ ] Retrieve and transcribe **Master Specification Rev 0.3**.
- [ ] Restore exact titles, descriptions, and dependencies for all **29 Modular Systems**.
- [ ] Restore the exact **R-1…R-11** stage names, order, and acceptance criteria.
- [ ] Recover the two-day motion-framework evaluation notes, including all four tested frameworks, versions, test cases, results, and selected direction.
- [ ] Recover the detailed ElevenLabs-like sound-system requirements from prior planning/Claude notes.
- [ ] Map every existing GitHub phase/PR to the recovered master system IDs.
- [ ] Reconcile this draft with the recovered source and mark any conflicts explicitly.

Until these checkboxes are completed, this document is the current planning control point but remains a **recovery draft**, not a claim that every original planning detail has been recovered.

---

## 12. Immediate next step

**Do not start another feature implementation yet.** First complete W0 source recovery and produce a traceability matrix:

`Original requirement → Master System ID → R-stage → Existing PR/commit → Current status → Remaining gap → Acceptance test`

Only after that matrix is reviewed should the next implementation phase be proposed.
