# Phase 3.2 — Channel Profile System & Production Rules

**Status:** Design proposal  
**Parent architecture:** Universal Creative Production Architecture  
**Depends on:** Phase 3.1a Scene Plan Proposal Builder and Phase 3.1b Safe Project Apply & Persistence (merged in PR #45)

## 1. Objective

Introduce reusable, versioned Channel Profiles that describe a channel's creative identity and production defaults without coupling the Universal Core, scene model, renderer, or engine registry to any one YouTube niche.

A new channel must be addable by registering a profile and its production rules. It must not require changes to the Universal Project/Scene contract or the shared FFmpeg production pipeline.

This phase starts with a data/domain foundation. UI, automatic asset generation, model integrations, and engine implementations are separate later slices.

## 2. Architectural boundaries

### Channel Profile layer

Owns:
- Stable profile identity and display metadata.
- Channel purpose, audience, language defaults, and content categories.
- Default visual direction and reusable style tags.
- Production rules and review requirements.
- Preferred engine IDs as preferences only (never silently force or invent an engine).
- Profile-level defaults for aspect ratio, target frame rate, resolution, and audio policy where explicitly configured.

### Universal Core

Remains authoritative for:
- Project, Scene, Asset, Character, Timeline, Audio, and scene-level visual intent.
- Stable scene IDs, project persistence, and canonical timing.
- Approved scene plans and explicit user decisions.

### Engine Registry and shared production pipeline

Remain independent of channel identity. A profile may express engine preferences and requirements, but engine availability/capability is resolved by the existing registry and resolver. Rendering, FFmpeg, synchronization, caching, validation, and cancellation behavior are not changed by this phase.

## 3. Profile contract (proposed)

A profile is immutable registry data at runtime and serializable configuration when attached to a project.

Conceptual fields:

- `profile_id`: stable lowercase identifier, e.g. `quasivanta`.
- `schema_version`: profile document version, independent of Project.schema_version and Universal format version.
- `display_name`, `description`.
- `content_domains`: open list of subject domains.
- `audience`: language/region intent; descriptive metadata, not demographic inference.
- `narration_defaults`: optional language, tone, pacing, and voice preference hints.
- `visual_defaults`: style family, style tags, palette/mood descriptors, composition guidance.
- `production_defaults`: optional aspect ratio, resolution, frame rate, audio mix hints.
- `preferred_engines`: ordered engine IDs, advisory only.
- `rules`: declarative requirements and warnings.
- `metadata`: forward-compatible extension object.

No profile may contain executable Python, arbitrary callbacks, shell commands, or untrusted templates.

### Production rule shape

Rules are declarative and deterministic. Initial rule categories:
- `required`: a field or review step must be satisfied before the relevant approval action.
- `recommended`: a quality recommendation that produces a warning, not a hard failure.
- `prohibited`: a disallowed production choice that must be surfaced as a blocking diagnostic.
- `review`: a human review checkpoint (e.g. source verification or visual sensitivity review).

Each rule has a stable `rule_id`, `severity`, `scope`, and a typed condition/target. Unknown rule types or future schema versions must be preserved safely and treated as unsupported—not executed.

Rules must not mutate a project, scene, or proposal. Evaluation returns diagnostics only. Applying a profile or accepting a proposal remains an explicit user action.

## 4. Initial built-in profiles

These are initial product presets, not hard-coded branches in the renderer.

| Profile ID | Channel | Domain | Visual direction |
|---|---|---|---|
| `quasivanta` | Quasivanta | Space and science | Scientific visualization, cinematic 3D/4D concepts, planetary motion, diagrams and infographics |
| `veltracis` | Veltracis | History and mystery | Documentary collage, sketch, maps, artifacts, timelines, 2.5D |
| `sizzjin` | Sizzjin | Horror and suspense | Atmospheric 2.5D, silhouette, paper-cutout, cinematic illustration |
| `drowsehaven` | Drowsehaven | Sleep stories | Watercolor/cinematic illustration, calm environments, slow visual pacing |
| `rihvaya` | Rihvaya | Islamic stories, history and education | Respectful documentary, historical maps/manuscripts, illustration and 2D storytelling |
| `mindniq` | MindNiq | Educational explainers | Stickman, flat vector, whiteboard and motion graphics |
| `inventions-discoveries` | Inventions & Discoveries | Inventions, engineering and technology | Technical diagrams, 3D/4D visualization, animated explainers |

Profiles must remain extensible. Future examples include biography, deep ocean, crime documentary, nature/wildlife, geography/exploration, and animation channels.

## 5. Rihvaya production presets

Rihvaya demonstrates why a channel profile must support multiple production presets.

- `islamic_documentary`: evidence-led narration, source verification checkpoints, historical context, maps/manuscripts/diagrams, respectful visual constraints.
- `islamic_2d_cartoon_storytelling`: scene-based 2D cartoon storytelling, recurring character continuity, narration-aligned actions/reactions, backgrounds/props/camera direction, and review checkpoints for sensitive depictions.

These are production presets selectable under the Rihvaya profile, not separate Universal Core types. Rules should support profile-level defaults plus explicitly selected preset overrides. Sensitive historical/religious visual constraints must be expressed as reviewable rules; the system must not generate unsupported dialogue or claim source authenticity automatically.

## 6. Project persistence and compatibility

- Do not bump Project.schema_version for this foundation.
- Do not change the existing `Project.profile` or `Project.settings["universal"]` meaning without a focused migration proposal.
- Store the selected profile reference and a versioned, self-contained snapshot additively. The snapshot allows a project to remain understandable if a built-in profile is later updated or removed.
- Keep the canonical profile ID separate from display name.
- Preserve unknown fields during load/save.
- Unknown future profile schema versions must enter a safe read-only/unsupported state; never overwrite their raw payload.
- Legacy projects without a profile continue to load and behave exactly as before.
- Changing a project's profile must not silently rewrite existing scenes, visual prompts, voice settings, engine choices, or assets.

The exact storage location and snapshot envelope will be finalized in the implementation design after inspecting current project serialization and profile usage. Avoid introducing a second competing source of truth.

## 7. Profile application semantics

Applying a profile to a project is an explicit operation:
1. Resolve the profile ID from the registry.
2. Validate the profile and selected production preset.
3. Produce a preview/diff of defaults and rule changes.
4. Require explicit confirmation.
5. Persist the profile reference/snapshot without rewriting existing scene content.
6. Mark the project dirty through the owning project manager/UI layer.

A separate explicit action may apply selected defaults to newly created scenes. Existing scenes are not retroactively rewritten unless the user chooses a future bulk-apply operation.

## 8. Rule evaluation semantics

- Pure function: no I/O, UI, network, subprocess, model, or renderer calls.
- Deterministic output for the same profile, preset, project and scene inputs.
- Diagnostics have stable codes, severity, message, and optional scene/rule identifiers.
- Missing optional metadata produces no failure.
- Required missing data produces an error; recommended omissions produce warnings.
- Unsupported rule types produce a non-executable warning/error according to compatibility policy.
- Rule evaluation never auto-corrects content or marks a plan approved.
- Human approval remains separate from rule evaluation.

## 9. Proposed implementation slices

1. **3.2a — Profile Domain Contracts:** immutable profile/rule/preset models, validation, serialization, forward-compatible parsing.
2. **3.2b — Built-in Profile Registry:** register the seven initial profiles and Rihvaya presets; deterministic lookup/listing; no UI.
3. **3.2c — Project Profile Snapshot:** safe additive persistence, legacy compatibility, unknown-version preservation, explicit apply/clear operations.
4. **3.2d — Production Rule Evaluator:** pure diagnostics for project/scene/scene-plan inputs, with focused tests.
5. **3.2e — Authoring Integration:** use selected profile defaults during proposal creation only when explicitly supplied; no silent behavior changes.
6. **3.2f — UI:** profile selection, preset selection, preview/diff, rule diagnostics, and explicit apply confirmation.

Each slice should be a small PR with focused tests. Do not combine UI, model integration, renderer changes, or arbitrary code execution with the domain foundation.

## 10. Acceptance criteria

- A new profile can be registered without editing Universal Core models or renderer code.
- Built-in profiles are data-driven and use stable IDs.
- Rihvaya supports both documentary and 2D cartoon storytelling presets.
- Profile/rule validation is deterministic and rejects malformed data.
- Rule evaluation is pure and returns diagnostics without mutation.
- Unknown fields round-trip; unsupported future versions are not destructively rewritten.
- Legacy projects with no profile remain loadable and unchanged.
- Applying a profile is explicit and does not silently rewrite scenes or assets.
- Existing test suite and Windows CI remain green.
- No changes to FFmpeg, TTS, render scheduling, cache identity, timeline timebase, or engine execution in this phase.

## 11. Out of scope

- Automatic script research or fact verification.
- Image/video generation and external AI APIs.
- Character generation or character animation.
- Prompt-to-Video / AI Director implementation (kept in the broader Phase 3 architecture).
- UI implementation in the domain-contract PR.
- Commercial packaging, publishing, or platform upload automation.

## 12. Immediate next step

Implement **3.2a — Profile Domain Contracts** as a standalone, test-first change after this design is reviewed. Before deciding the persistence envelope, inspect all current reads/writes of `Project.profile` and `settings["universal"]` to avoid a competing source of truth.
