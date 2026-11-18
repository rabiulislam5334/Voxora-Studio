# Phase 3.4i.5–3.4i.6 — Desktop Composition Editor & Render Capability Bridge

## 3.4i.5 Desktop Composition Editor

Adds a dedicated **Composition** workspace to the desktop application:

- Open and save an existing `.voxora` project, with an unsaved-change confirmation before switching projects.
- Select a project scene and inspect its existing bound visual assets.
- Add only assets already present in that scene's Universal ScenePlan bindings.
- Render a local editor canvas from the stored normalized composition geometry.
- Drag elements to move them, drag the lower-right handle to resize, use the mouse wheel to scale, double-click to reset, and use layer controls to reorder or remove elements.
- Inspect the selected element's geometry, rotation, opacity, fit mode, and layer order.
- Run the deterministic validation preview and explicitly apply a reviewed composition through the Phase 3.4i.4 API.
- Save the resulting project using the existing ProjectManager save path.

The editor works with composition metadata and local asset previews. It does not create art, animate elements, or render a final video. Pillow is used when available for raster previews; unavailable/unsupported previews fall back to a labeled canvas placeholder.

## 3.4i.6 Render Capability Bridge

Adds a strict adapter contract for future composition-capable renderers:

- `CompositionRenderCapabilities` explicitly declares output formats, asset kinds, layer, transform, opacity, and rotation support.
- `CompositionRenderBridge.inspect(engine_id)` reports capability for the exact registered engine.
- `render(..., approved=True)` requires explicit approval, a current valid composition preview, exact local asset references, and a declared output format.
- The bridge verifies that the adapter writes a non-empty output to the exact requested destination.
- No automatic engine fallback, implicit flattening, or silent dropping of unsupported layers is permitted.

### Current renderer status

The existing `FFmpegSegmentAdapter` declares single-source scene rendering (blank/image/video) and implements `render()`; it does **not** implement layered `render_composition()` and does not declare layer/transform composition capabilities. It is therefore correctly reported as unsupported by this bridge. No claim of final composition video rendering is made in this phase. A future FFmpeg composition adapter or another renderer must implement and pass real integration tests before Voxora enables composition export.

## Compatibility and safety

- No Project, Scene, or legacy `.voxora` schema migration.
- Composition persistence remains additive under Universal settings.
- Existing scene asset bindings and ScenePlans are not rewritten.
- Applying a composition marks the project dirty; saving remains an explicit ProjectManager operation.
- Rendering is blocked unless a capable adapter is explicitly registered and the user approves the operation.
- No AI/model downloads, network asset retrieval, hidden engine selection, or changes to existing audio/TTS/timeline/render paths.
