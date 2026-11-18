# Phase 3.4i.2–3.4i.4 — Composition Binding, Preview, and Persistence

## Scope

This increment combines three implementation stages in one reviewable change:

- **3.4i.2 — Scene Composition Binding & Validation:** every composition element must reference an asset already present in the target scene's Universal `ScenePlan.asset_refs`. No implicit catalog import or automatic binding is performed.
- **3.4i.3 — Composition Preview & Layout Diagnostics:** normalized geometry is projected onto the declared pixel canvas; elements are sorted by layer order and stable element ID. Diagnostics identify missing scene assets, empty compositions, hidden/transparent elements, overlaps, and overlapping elements with equal layer order.
- **3.4i.4 — Explicit Apply & Persistence:** a reviewed composition can be persisted only with `approved=True`. It is stored additively in `Project.settings["universal"]["scene_compositions"]`, through `UniversalState.extra`.

## Safety and compatibility

- Preview and validation are deterministic and read-only.
- Pixel geometry is calculated from normalized coordinates; no image bytes are opened and no renderer is invoked.
- Overlap checks use unrotated axis-aligned rectangles. They are advisory because overlap may be intentional.
- Persistence re-computes the preview and checks both composition and target fingerprints to reject stale reviews.
- Existing per-scene asset references, ScenePlans, Project scenes, and legacy project schema are not rewritten.
- Universal future-version/read-only state and malformed stored composition entries block persistence.
- Unknown Universal settings remain preserved through the existing forward-compatible `UniversalState.extra` mechanism.
- No FFmpeg, TTS, cache, timeline, asset generation, AI provider, or renderer behavior is changed.

## Public API

- `preview_scene_composition(project, composition)`
- `apply_scene_composition(project, composition, preview, approved=False)`

The preview returns canvas dimensions, stable layer-sorted pixel geometry, binding validation diagnostics, and layout diagnostics. The apply operation updates only the additive Universal settings payload and calls `project.touch()` after the new settings object is ready.

## Deliberate limitations

This stage does not decode or display raster previews, render layers, evaluate rotated overlap bounds, animate elements, or alter actual video output. Those require later editor and render-capability work and must be verified against a real renderer before being advertised as supported.
