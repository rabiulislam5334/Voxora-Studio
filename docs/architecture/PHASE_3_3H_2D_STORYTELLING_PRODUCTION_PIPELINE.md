# Phase 3.3h — 2D Storytelling Production Pipeline

## Status
Architecture and contract-planning increment. This document defines the first safe implementation boundary; it does not claim that Voxora can yet generate complete 2D animation or artwork from narration.

## Goal
Create a reusable, channel-independent planning pipeline that transforms approved narration/script material into a deterministic, reviewable storyboard proposal. The proposal will later feed the existing Universal scene and render contracts.

Initial consumers include Rihvaya's 2D cartoon storytelling preset and MindNiq's educational explainers. The core must not contain channel-specific rules or visual assumptions.

## Existing boundaries to preserve
- ScenePlan remains the existing per-scene Universal visual-intent contract.
- EngineRenderRequest remains the immutable single-scene render input.
- WorkflowAdapter delegates to one explicitly selected compatible engine.
- SceneExecutionCoordinator remains opt-in and does not replace the legacy production renderer.
- Existing .voxora serialization, project schema versions, scene IDs, narration text, audio timing, cache keys, and legacy render behavior must not change in this increment.
- No automatic engine selection, fallback, external AI calls, model downloads, arbitrary code execution, or hidden asset generation.

## Proposed pipeline
1. Narration input — accept caller-provided text and optional externally measured narration duration/word timing. Do not synthesize or rewrite narration.
2. Segmentation proposal — split text into ordered narration units using deterministic, configurable rules. Preserve exact source text and stable source offsets.
3. Storyboard proposal — map narration units to proposed visual beats. Each beat carries an explicit timing basis, visual intent, action cues, and optional asset/character references.
4. Continuity validation — report missing or inconsistent character, location, prop, and visual references. Diagnostics only; never silently invent assets or rewrite the proposal.
5. Human review — expose proposal/diff and require explicit approval before applying it to a project.
6. Scene-plan conversion — convert approved beats to existing ScenePlan values while preserving stable scene IDs and unrelated project data.
7. Execution — use the existing workflow adapter, engine resolver, runtime, and normalizer boundaries. Rendering remains opt-in.

## First implementation increment: planning contracts
The first code increment should add pure, renderer-independent data contracts for narration sources and text units with validated offsets; timing information that distinguishes measured timings from estimates; storyboard beats with stable IDs, narration-unit references, visual descriptions, action cues, and optional continuity references; a versioned proposal envelope with deterministic ordering and explicit review status; and structured diagnostics for invalid references, timing gaps/overlaps, duplicate IDs, and unresolved continuity references.

Contracts should be immutable where practical, validate inputs strictly, preserve unknown metadata for forward compatibility where appropriate, and avoid dependencies on UI, FFmpeg, TTS providers, image generators, or channel profiles.

## Timing rules
- Never assume one universal words-per-minute value as factual narration timing.
- If only total narration duration is supplied, per-beat timing is explicitly marked estimated and derived deterministically from a documented weighting strategy.
- If measured word/phrase timings are supplied, preserve them and validate monotonicity and source offsets.
- Represent intervals as integer milliseconds or another canonical integer timebase; avoid cumulative floating-point drift.
- Detect gaps/overlaps rather than silently adjusting user-supplied measured timings.
- Keep visual beat duration separate from audio/narration duration; a visual may span multiple narration units.

## Character and visual continuity
- Character, location, and prop references are IDs plus descriptive metadata, not generated assets.
- An unresolved continuity reference produces a diagnostic instead of an invented match.
- Character appearance descriptions must remain stable across beats sharing the same character ID.
- Camera and action cues are declarative planning data, not proof that an engine supports the requested movement.
- Channel profile presets may provide defaults later, but the universal proposal remains portable across channels.

## Approval and application safety
- Proposal generation is pure and deterministic for identical inputs and configuration.
- Preview must not mutate project scenes, narration, profile snapshots, assets, or render settings.
- Applying a proposal requires explicit approval and a stale-input/fingerprint check.
- Reapplying the same approved proposal must not duplicate scenes.
- Existing scene IDs and user-authored content must be preserved unless the user explicitly chooses a reviewed replacement.
- Missing required assets or unsupported engine capabilities block execution with actionable diagnostics, not fallback.

## Planned staged work
- 3.3h.1 — Narration and storyboard domain contracts: immutable models, validation, stable IDs, canonical timing, serialization round-trip tests.
- 3.3h.2 — Deterministic narration segmentation: sentence/paragraph segmentation, source offsets, configurable rules, no text rewriting.
- 3.3h.3 — Storyboard proposal builder: map narration units to visual beats, deterministic duration estimates, action/visual intent fields.
- 3.3h.4 — Continuity and timing diagnostics: character/location/prop references, gaps/overlaps, unresolved references, stable diagnostic codes.
- 3.3h.5 — Preview and explicit apply: proposal diff, stale-input protection, stable scene identity, idempotent apply.
- 3.3h.6 — Workflow execution integration: opt-in conversion to existing ScenePlan and WorkflowAdapter boundaries, with end-to-end tests and no default renderer replacement.

## Acceptance criteria
- Pure domain tests run without FFmpeg, TTS, network access, or external AI services.
- Identical inputs produce identical proposal content and ordering.
- Source narration is preserved exactly at the text-unit level.
- Timing provenance is explicit; estimates are never presented as measured values.
- Invalid timing, offsets, duplicate IDs, and unresolved references produce deterministic diagnostics.
- Preview is side-effect free; apply is explicit, stale-safe, and idempotent.
- Existing .voxora fixtures and legacy rendering tests remain unchanged and pass.
- No claim of full cartoon generation until a real visual asset/animation engine is implemented and verified.