# Phase 3.4i — Scene Visual Composition & Asset Placement

## Status
Architecture and implementation-boundary proposal. This increment defines the composition model and staged delivery plan; it does not claim that assets can already be interactively positioned or that the renderer consumes composition transforms.

## Goal
Define a channel-independent, reviewable way to describe how already-imported and explicitly scene-bound visual assets are arranged inside a scene frame. The same composition vocabulary should support documentary stills, 2D storytelling, stickman/flat-vector scenes, sketch/illustration, and later 2.5D/3D workflows without embedding channel-specific behavior in Universal Core.

## User-facing outcome
A creator should eventually be able to choose assets already in the scene bindings; place each item on a scene canvas; set size, position, rotation, opacity, layer order, and image fitting; preview the complete composition before applying it; and save an explicitly approved composition without changing narration, scene identity, or unrelated project data.

## Composition contract
The initial 2D composition vocabulary should be declarative and renderer-independent:
- stable composition and element IDs;
- scene ID and explicit canvas width/height;
- element references to existing scene asset bindings (no implicit library lookup);
- normalized frame coordinates with a documented origin and axis direction;
- position, size, anchor, rotation, opacity, visibility, and integer layer order;
- image fitting mode (contain, cover, or stretch) with deterministic crop/overflow semantics;
- optional human-authored label/role metadata.

Coordinates use a single documented convention: top-left origin, x increasing right, y increasing down; normalized values in the 0..1 frame range. Size must be positive; opacity must be in 0..1; rotation must be finite and bounded/canonicalized; layer order must be an integer. Validation must reject NaN/infinity, invalid dimensions, duplicate IDs, unknown asset references, and out-of-frame values unless an explicit clipping/overflow policy is part of the contract.

## Existing boundaries to preserve
- SceneAssetBinding remains the source of truth for which assets are allowed in a scene.
- VisualAssetCatalog remains the source of asset identity and provenance.
- ScenePlan remains the existing visual-intent contract; composition is a separate declarative layer and must not silently rewrite narration or visual prompts.
- Project/Scene/.voxora schema versions must not be bumped in the first composition-contract increment.
- Existing render clock, audio timing, cache keys, FFmpeg behavior, TTS, and legacy project loading/saving remain unchanged.
- No automatic asset selection, generated art, remote AI calls, model downloads, arbitrary code execution, or automatic renderer fallback.
- A composition preview is not proof that the current FFmpeg adapter can render every transform. Renderer capability must be explicit and separately verified.

## Proposed staged implementation
1. **3.4i.1 — Composition domain contracts:** immutable canvas, transform, element, and composition records; strict validation; deterministic serialization/fingerprints; unit tests independent of UI and rendering.
2. **3.4i.2 — Scene composition binding & validation:** resolve element references only against the target scene's existing asset bindings; report missing, duplicate, stale, or unsupported references; no mutation.
3. **3.4i.3 — Composition preview & layout diagnostics:** deterministic normalized-to-pixel geometry, overlap/out-of-frame diagnostics, layer-order preview data, and read-only scene preview. No image decoding or renderer calls in the pure core.
4. **3.4i.4 — Explicit apply & persistence:** preview/diff, target fingerprint checks, explicit approval, atomic additive persistence in the existing Universal settings envelope only if compatibility is proven; preserve unknown settings and legacy .voxora files. If a safe additive location cannot be established, stop and revise the design rather than changing the project schema.
5. **3.4i.5 — Desktop composition editor:** canvas preview, select/move/resize/rotate controls, layer list, property editor, undo-safe interaction, explicit apply and explicit project save. UI must not silently persist changes.
6. **3.4i.6 — Render capability bridge:** only after a real adapter declares and tests the required transform/fitting/layer capabilities. Unsupported operations must produce actionable diagnostics; no claim of visual fidelity without render tests.

## Non-goals for this phase
- Keyframe animation, motion paths, nested groups, masks, blend modes, particle effects, camera rigs, 3D transforms, generated backgrounds, and AI image generation.
- Full Photoshop/After Effects-style editing.
- Treating a static composition preview as a rendered video.
- Changing the existing production renderer or default export path.

## Acceptance criteria
- Identical input contracts serialize and fingerprint deterministically.
- Every element references an asset already bound to the same scene.
- Coordinate, dimension, rotation, opacity, layer, and fit-mode validation is strict and documented.
- Preview and diagnostics are read-only and do not mutate project/catalog/scene data.
- Apply, when implemented, requires explicit approval and rejects stale previews.
- Existing scene assets, characters, narration, prompts, project schema, and legacy .voxora fixtures remain intact.
- Pure tests run without FFmpeg, TTS, Pillow, network access, or external AI services.
- Renderer support is claimed only for capabilities covered by adapter declarations and integration tests.

## First increment scope
This PR is architecture documentation only. It intentionally creates no runtime models, UI, persistence, renderer integration, or project schema changes. The next implementation PR should be limited to 3.4i.1 domain contracts and their tests.