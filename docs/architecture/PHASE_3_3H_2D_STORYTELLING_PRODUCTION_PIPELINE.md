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

## Phase 3.3h.4 — Continuity and timing diagnostics

The diagnostics layer is read-only and deterministic. It reports stable codes for timeline gaps and overlaps, narration units that are unmapped or reused across beats, source identity mismatches, beats extending beyond a declared narration duration, unused continuity declarations, and estimated beat timing that needs review. Structural violations already rejected by the immutable domain contracts remain construction-time validation errors. Diagnostics never repair or reorder beats, invent missing character/location/prop references, change review status, or mutate a proposal.

## Phase 3.3h.5 — Preview and explicit apply

The preview/apply adapter converts a reviewed storyboard proposal into additive
Project Scene and Universal ScenePlan records. Preview is deterministic and
read-only. Each proposed scene shows its stable derived ID, exact narration
slice, visual description, action/continuity notes, integer-millisecond timing,
and measured/estimated timing provenance.

Applying requires a separate explicit approval argument and a previously
reviewed preview. Immediately before mutation, the adapter revalidates the
proposal against the supplied narration source and recomputes both source and
target fingerprints. Any source mismatch, target Project edit, malformed or
future read-only Universal payload, duplicate proposal application, or scene
ID collision blocks the operation. The operation builds detached scene,
settings, and UniversalState copies, then commits them together only after all
validation succeeds.

Existing Project scenes and unrelated Universal settings are preserved.
Storyboard-derived ScenePlans record beat identity, narration-unit IDs,
continuity references, and timing provenance. The timing values are planning
metadata only; they do not change the project's render clock or audio timeline.
No proposal is silently approved, no engine is selected, and no image,
character, animation, or other visual asset is generated.

## Phase 3.3h.6 — Opt-in workflow execution integration

The execution coordinator accepts only a storyboard proposal that has already
been applied to the target Project, its original source, and the reviewed
preview. A separate `approved=True` argument is required to start execution.
Before invoking any adapter it verifies the applied-proposal marker, preview
identity and scene content, each persisted Scene and ScenePlan, and the
selected workflow/engine compatibility.

The caller explicitly supplies the workflow ID, engine ID, matching engine
descriptor, already-bound workflow adapter, scene kind, style tags, output
format, output directory, dimensions, and frame rate. The selected engine must
be the exact engine bound to the adapter and must declare the requested
workflow family and render capabilities. No automatic selection, fallback,
or adapter initialization is performed by this coordinator.

Runtime-only ScenePlan copies receive the explicit engine choice and render
requirements; persisted Project ScenePlans are not modified. Scenes execute
sequentially through the existing SceneExecutionCoordinator,
MultiSceneExecutionCoordinator, EngineRuntimeRegistry, and SegmentNormalizer.
Progress and cancellation are forwarded. Existing normalized output files are
not overwritten.

This is an execution integration boundary, not a claim that current built-in
engines generate 2D artwork or animation. The existing FFmpeg adapter does not
declare a 2D/documentary workflow family and remains limited to its declared
blank/image/video segment capabilities. A compatible visual engine and
workflow adapter must be installed and explicitly selected before those
workflows can run. No UI wiring, default renderer replacement, AI service,
asset generation, project schema change, or legacy .voxora change is included.

# Phase 3.4a — Visual Asset & Character Domain Contracts

## Goal
Introduce reusable, renderer-independent records for visual assets and recurring
characters. These contracts are channel-agnostic and can be referenced by later
2D, 2.5D, documentary, sketch, and other production engines.

## Included contracts
- `VisualAsset`: stable asset ID, open-ended kind, file/URI location, optional
  SHA-256 content identity, media type, dimensions, tags, metadata, and provenance.
- `AssetProvenance`: caller-supplied source, license, attribution, source URI,
  and structured metadata. A license label is recorded as data, not interpreted
  as legal clearance.
- `CharacterAppearance`: stable appearance revision ID, canonical visual
  description, reference asset IDs, style tags, and structured attributes.
  Its deterministic SHA-256 fingerprint makes appearance changes detectable.
- `CharacterDefinition`: stable character ID and reusable identity metadata.
- `VisualAssetCatalog`: deterministic versioned collection with unique IDs
  and validated character-to-asset references.

## Safety and compatibility boundaries
- Pure local data contracts; no file reads, image decoding, network calls,
  model/provider access, artwork generation, or renderer integration.
- Locations are stored as caller-provided strings; existence and content hashes
  are not asserted unless verified by a later importer.
- License/provenance fields are declarations only and do not imply permission
  to use an asset.
- Unknown metadata fields are preserved for forward compatibility.
- No changes to Project, Scene, ScenePlan, .voxora serialization, project schema,
  render cache, FFmpeg, TTS, or existing production workflow.
- Future catalog versions are rejected by this writer rather than rewritten.

## Acceptance criteria
- Stable round-trip serialization for assets, provenance, characters, and catalog.
- Duplicate asset/character IDs and unresolved character asset references fail.
- Invalid hashes, dimensions, identifiers, and non-JSON metadata fail.
- Appearance fingerprints are deterministic and change when canonical appearance
  content changes.
- Unit tests run without FFmpeg, TTS, network access, or external AI services.


# Phase 3.4b — Visual Asset Storage & Import Pipeline

## Goal
Add a local-only asset library that imports supported raster images into a
managed, content-addressed directory and records verified identity and basic
image metadata in a persistent catalog.

## Included behavior
- VisualAssetLibrary owns a caller-selected local library root and a
  versioned VisualAssetCatalog JSON manifest.
- Imports PNG, JPEG, GIF, and BMP files from local regular files only.
  Extension and detected file signature must agree; dimensions are read from
  bounded image headers without requiring Pillow or another runtime dependency.
- Copies are streamed through a temporary staging file while calculating
  SHA-256 and enforcing configurable file-size and pixel-count limits.
- Stored image paths are content-addressed under assets/<hash-prefix>/.
  Re-importing identical bytes is idempotent; conflicting IDs or corrupted
  content-addressed destinations are rejected.
- Catalog writes use a temporary file and atomic replacement. Asset locations
  are relative to the library root; verification rejects traversal and
  symbolic-link paths.
- Import returns a VisualAsset containing verified SHA-256, detected media
  type, dimensions, size metadata, and caller-supplied provenance/tags.

## Safety and compatibility boundaries
- No network URLs, remote providers, AI generation, image editing, or rendering.
- The importer inspects image signatures and dimension headers; it does not
  fully decode or sanitize image pixels. Downstream renderers must treat
  imported files as untrusted input and decode them with their own safeguards.
- SVG and other active/document formats are intentionally not accepted.
- The library is opt-in and independent of Project, Scene, ScenePlan, and
  legacy .voxora serialization. No existing renderer or cache behavior changes.
- The content-addressed store is local application data; provenance/license
  values remain declarations and are not legal clearance.

## Acceptance criteria
- Supported formats import with stable content hashes and dimensions.
- Unsupported, mismatched, oversized, malformed-header, and empty files fail
  without catalog mutation.
- Duplicate imports do not create duplicate catalog entries.
- Catalog survives reload and rejects invalid/future catalog data through the
  existing domain contracts.
- Hash verification detects missing or modified files; unsafe relative paths
  and symlink traversal are rejected.
- Tests run without Pillow, FFmpeg, TTS, network access, or external AI services.


# Phase 3.4c–3.4e — Visual Asset & Character Library Workspace

## Goal
Expose the local VisualAssetCatalog through a desktop workspace for asset
management, image inspection, and reusable character appearance management.
The workspace remains independent of project serialization and rendering.

## Visual asset library UI (3.4c)
- Add a dedicated Visual Assets navigation page with Assets and Characters
  sections.
- Browse, search, filter, import, refresh, edit catalog metadata, and remove
  catalog entries.
- Import remains local-only and uses the Phase 3.4b signature, size, pixel,
  content-hash, and path checks.
- Removing an asset removes its catalog entry only. The content-addressed
  file is retained on disk; no destructive file deletion or garbage collection
  is performed in this increment.
- Assets referenced by a character cannot be removed until the reference is
  changed or the character is removed.

## Image preview and inspection (3.4d)
- Show a bounded preview when the local platform image decoder supports the
  file; Pillow is optional and is not added as a dependency.
- Display detected media type, dimensions, file size, SHA-256, tags, and
  provenance. Provide an explicit integrity verification action.
- Preview path resolution rejects traversal and symlink paths. The importer
  validates bounded headers and dimensions, but does not fully decode or
  sanitize pixels; preview decoder failures are shown as diagnostics.
- The interface never claims that a provenance/license declaration is legal
  clearance.

## Character library (3.4e)
- Create, edit, inspect, and remove reusable CharacterDefinition records.
- Manage stable character IDs, appearance IDs, visual descriptions, style
  tags, structured JSON attributes, and reference asset IDs.
- The catalog validates reference IDs and refuses to remove an asset while a
  character still references it. Appearance fingerprints remain generated by
  the existing domain contract.
- Character edits are catalog-local; no existing project scenes or .voxora
  files are rewritten.

## Compatibility and safety
- The library is stored under the configured local assets directory and is
  opt-in; no external services, AI generation, or network access are used.
- Existing project schema, Scene, ScenePlan, storyboard execution, FFmpeg,
  TTS, and legacy render paths remain unchanged.
- UI metadata edits use the existing versioned catalog and atomic catalog
  writer. Unknown catalog metadata remains preserved.
- Tests cover catalog mutations, reference integrity, and inspection helpers
  without requiring a display server, Pillow, FFmpeg, or TTS.

- Preview decoding is capped at 16 megapixels to avoid unexpectedly large
  temporary image allocations on low-memory machines; unsupported or larger
  files remain available for metadata inspection and integrity verification.


# Phase 3.4f–3.4g — Scene Asset Binding & Cross-Scene Continuity

## Phase 3.4f — Scene-to-asset and character binding
- Bind selected library assets and reusable character identities to an existing
  Project Scene through an immutable preview and a separate explicit approval.
- Store visual assets in the existing Universal ScenePlan.asset_refs contract,
  including stable asset ID, relative library path, content hash, and declared
  role metadata. Store character ID, appearance revision, fingerprint,
  reference assets, and style tags in the ScenePlan requirements extension.
- Preserve existing ScenePlan notes, style tags, engine choice, requirements,
  asset references, project settings, and all other scenes.
- Refuse unknown catalog IDs, duplicate bindings, malformed/future Universal
  payloads, stale previews, and missing target scenes.
- No Project/Scene/.voxora schema migration; binding writes remain inside the
  existing Universal settings envelope. Applying is explicit and atomic.

## Phase 3.4g — Asset continuity and reuse analysis
- Provide a deterministic, read-only analyzer across all project ScenePlans.
- Detect missing bound assets/characters, changed asset content identity,
  changed character appearance since binding, inconsistent appearance
  fingerprints for the same character across scenes, malformed bindings,
  orphaned ScenePlans, and missing character reference assets.
- Report asset reuse groups when the same asset ID is used in multiple scenes
  and when distinct catalog IDs share the same verified content hash.
- Report character usage groups and appearance fingerprints to support
  continuity review. Suggestions are informational; no automatic replacement,
  rebinding, catalog mutation, file deletion, or project repair occurs.
- Tests cover explicit approval, stale-preview rejection, additive ScenePlan
  mutation, catalog reference validation, cross-scene reuse, character
  appearance drift, missing references, and read-only future-version behavior.
