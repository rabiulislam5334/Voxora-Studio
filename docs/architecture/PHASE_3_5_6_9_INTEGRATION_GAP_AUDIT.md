# Phase 3.5.6.9 — Integration Gap Audit

**Audit baseline:** `main` at `8a4835595a914b4f687810bdc6fdb066fe2b3698` (PR #108 merge commit).  
**Scope:** Read-only inspection of the current repository tree, desktop navigation, project ownership, Universal Core composition/render registries, visual-generation workflow, production workflow, architecture documentation, and related tests.  
**No source code or project files were changed during this audit.**

## Executive summary

The generated-image domain pipeline is now covered by a real FFmpeg-backed Universal Produce end-to-end test. However, the desktop application still has integration gaps between its separate project workspaces and the composition renderer capabilities.

The most important next implementation should be a **shared project session** across Script/Studio, Scene Assets, and Composition. The next should connect the existing CPU raster composition renderer to the composition editor UI without implying that a still PNG renderer is an animated video engine.

## Findings

### P1 — Project state is not shared across the visual-production workspaces

**Evidence**

- `ScriptPanel` owns its own `ProjectManager` (`app/ui/script_panel.py`).
- `StudioContext.project()` reads the project from the Script page (`app/ui/studio_context.py`).
- `SceneAssetBindingTab` constructs a separate `ProjectManager` (`app/ui/scene_asset_binding_tab.py`).
- `CompositionEditorTab` constructs another separate `ProjectManager` (`app/ui/composition_editor_tab.py`).
- Scene Assets and Composition each expose their own Open Project / Save Project controls. Universal Produce uses the Script/Studio project instance.

**Impact**

The user cannot treat image generation → scene binding → composition → Universal Produce as one continuous in-memory project session. The same `.voxora` file may need to be opened and saved independently in multiple pages. Project repository file-stamp checks help reject stale writes, but they do not provide shared live state or remove the repeated manual hand-off.

**Recommendation**

Introduce one application-owned project session/repository context and inject it into Script, Studio, Scene Assets, and Composition. Keep existing dirty-state prompts, revision/stamp conflict protection, and legacy `.voxora` compatibility. Do not introduce a schema migration for this work.

**Acceptance**

- Opening a project once makes the same project ID and in-memory project visible to all workspaces.
- Binding or composition changes are visible to Studio/Universal Produce without reopening the file.
- Dirty state and save prompts are coordinated once.
- A stale external file modification still produces a safe conflict rather than silently overwriting newer data.
- Add UI-level tests for the complete generated-image hand-off.

### P1 — The raster composition renderer is not connected to the Composition Editor's capability check

**Evidence**

- `app/universal/composition_builtins.py` explicitly builds a `RasterCompositionAdapter` registry with ID `raster`.
- `app/universal/adapters/raster.py` declares layered PNG composition support for ordinary and generated images.
- `CompositionEditorTab._check_render_support()` instead constructs an empty `CompositionRenderBridge()` and inspects `ffmpeg`.
- The editor consequently reports that a renderer with `render_composition()` is required, without consulting the existing raster composition built-in.
- The motion/Universal Produce path separately uses the CPU raster renderer for animated frame production; this does not mean the editor's still-composition renderer UI is wired.

**Impact**

The renderer capability shown by the desktop editor does not reflect the available raster adapter. Users cannot discover or invoke the existing still-PNG composition capability through the editor's render-support action. This is an integration gap, not evidence that layered MP4 rendering is already supported by the raster adapter.

**Recommendation**

Wire the editor's still-composition preview/render capability to `build_builtin_composition_render_bridge()` and the explicit `raster` adapter. Clearly label the output as a still PNG. Keep animated MP4 generation in the separate motion/Universal Produce pipeline, with its own explicit validation and approval.

**Acceptance**

- The editor discovers the registered raster adapter and reports PNG support accurately.
- A valid approved composition can render a still PNG through the adapter.
- Unsupported video formats remain rejected; no implicit FFmpeg fallback or flattening.
- Tests cover capability discovery, explicit approval, generated-image provenance, cancellation, and output validation.

### P2 — Engine Catalog currently describes only the scene-segment engine registry

**Evidence**

- `BUILTIN_ENGINE_IDS` in `app/universal/builtins.py` contains only `ffmpeg`.
- `EngineCatalogTab` displays descriptors from that registry.
- The raster composition adapter is registered through a separate composition-renderer registry, while Stable Diffusion.cpp is a visual-generation provider rather than a scene-segment engine.

**Impact**

The Engine Catalog currently shows only FFmpeg. That is consistent with the current scene-segment registry, but the UI does not make the separation between segment engines, composition renderers, and visual-generation providers obvious.

**Recommendation**

Keep the registries separate where their contracts differ, but make the catalog terminology and navigation explicit. Either add read-only sections for composition renderers and visual-generation providers, or rename the existing page to “Scene Segment Engines” and provide separate capability summaries.

**Acceptance**

- The UI never implies that a still PNG renderer is an MP4 scene engine.
- Users can inspect FFmpeg, raster composition, and Stable Diffusion.cpp in the correct capability category.
- No engine/provider is selected or silently substituted by a catalog refresh.

### P2 — Top-level navigation and README contain stale or placeholder actions

**Evidence**

- `README.md` still identifies Phase 2 as the current in-progress phase and does not describe the Phase 3.5.6.8 generated-image Universal Produce coverage.
- `MainWindow._on_new_project()`, `_on_open_project()`, and `_on_export()` only set “implemented later” status text.
- Dashboard New Project / Open Project and the top-bar Export button use those placeholder callbacks.
- The actual project creation/open/save workflow lives on the Script page.
- The sidebar's Projects, Subtitles, and Settings entries still route to placeholder pages.

**Impact**

The app presents duplicate project/export actions that do not perform the workflow available elsewhere. The README and navigation understate current capabilities and make it difficult to understand which workspace is authoritative.

**Recommendation**

Route Dashboard New/Open actions to the Script workspace's real project actions or remove the duplicate placeholders. Connect the top-bar Export action to the real Produce workflow, or remove/disable it until a clear export contract exists. Update README and phase-status documentation to match the current main branch and clearly distinguish implemented, partial, and deferred capabilities.

**Acceptance**

- No visible primary action claims to create/open/export when it only updates the status bar.
- Project actions route to one authoritative project session.
- README current phase and capability list match the code on main.
- Placeholder Subtitles/Settings/Projects pages are clearly labelled as planned, or replaced only when their actual workflows are implemented.

### P2 — UI-level generated-image workflow coverage is much thinner than service-level coverage

**Evidence**

- `tests/test_universal_produce_e2e.py` exercises the service-level Universal Produce path with synthetic generated-image assets and a test narration job.
- `tests/test_visual_generation_ui_registration.py` verifies only that Image Generation is registered in navigation.
- `tests/test_scene_asset_binding_ui.py` tests preview/report formatting helpers, not the full Tk project-binding interaction.
- The current UI tests do not demonstrate one shared project being opened, generated images bound, composed, and produced through the actual desktop pages.

**Impact**

The service contracts have meaningful regression coverage, but the end-user integration between independent Tk pages remains unverified. CI passing therefore does not establish that a user can complete the whole workflow without manual project hand-offs.

**Recommendation**

After the shared project-session work, add a focused Tk integration test that drives the desktop workflow with a fake local image provider and synthetic media. Keep the real Stable Diffusion inference and hardware performance test as a separate manual PC acceptance step.

**Acceptance**

- Automated UI test covers Image Generation → Visual Assets → Scene Assets → Composition → Universal Produce using one project session.
- Test verifies project dirty/save state and generated-image provenance throughout.
- Real local inference remains explicitly excluded from CI and is verified on the target PC.

## Explicitly deferred — real local inference and hardware acceptance

The current Stable Diffusion.cpp provider is a local CPU subprocess adapter. The automated generated-image E2E test creates synthetic image assets; it does not invoke the real model or validate the user's machine performance.

Keep the planned PC acceptance test at the end of Phase 3:

- Verify the selected `sd-cli.exe` and model actually run on Windows.
- Record inference time, peak RAM, CPU usage, output validity, and cancellation behavior.
- Verify the generated image appears in the asset library and can pass through binding, composition, and Universal Produce.
- Test a representative final MP4 and A/V synchronization.
- Do not assume the NVIDIA 940MX is being used; the current provider explicitly selects the CPU backend.

## Recommended implementation order

1. **Phase 3.5.6.10 — Shared Project Session:** solve the P1 project-state fragmentation first.
2. **Phase 3.5.6.11 — Raster Composition UI Integration:** connect the existing PNG renderer to the editor without conflating it with MP4 rendering.
3. **Phase 3.5.6.12 — Navigation, Catalog, and Documentation Alignment:** remove misleading placeholders and expose renderer/provider categories accurately.
4. **Phase 3 UI Integration Test:** exercise the complete desktop path after the shared session exists.
5. **Phase 3 PC Acceptance:** real inference, memory/performance, and final export verification.

## Verification boundary

This audit is based on source and test inspection at the stated main SHA. It is not a manual desktop run and does not claim real Stable Diffusion inference or long-duration hardware performance has been tested. PR #108's Windows and Ubuntu pull-request checks passed for its exact head SHA. The post-merge `main` push workflow was still running when this audit was recorded; its final result must be checked separately.
