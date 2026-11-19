# Phase 3.5.6.11–3.5.6.12 — Combined Integration Delivery

**Baseline:** main at `1f09a24e55f74d68e27eb2176686d07e85885f8a` (Phase 3.5.6.10 merge).

## Phase 3.5.6.11 — Raster Composition Editor Integration

- Connect the Composition Editor to the built-in raster composition bridge.
- Add an explicit Render Still PNG action after a valid, reviewed composition preview.
- Resolve assets through the managed Visual Asset Library and verify scene binding, asset kind, generated-image provenance, and content hash before rendering.
- Run raster rendering on the shared background worker; expose progress and cooperative cancellation.
- Require explicit user approval and a new `.png` destination. Existing files are not overwritten.
- Keep output transparent PNG only. The raster renderer does not create MP4 or animated video.

## Phase 3.5.6.12 — Catalog, Navigation, and Documentation Alignment

- Present scene-segment engines, composition renderers, and visual-generation providers as three distinct catalog categories.
- Show the built-in raster renderer as still-PNG only, and Stable Diffusion.cpp as an explicitly configured local CPU provider.
- Keep catalog refresh read-only: no automatic provider selection, model download, generation, or network fallback.
- Route Dashboard New/Open actions to the real Script workspace actions.
- Change the top-bar Export shortcut into navigation to Produce; production still requires the user to review and start the job.
- Update project name display and mark remaining Projects/Subtitles/Settings pages as planned.
- Update README capabilities and phase status.

## Verification boundaries

- Unit and UI integration tests cover catalog capability formatting, project navigation, and the composition render worker.
- Existing raster adapter tests cover explicit approval, asset validation, output validation, cancellation, and rejection of MP4.
- Windows and Ubuntu CI must pass for the exact final PR head.
- Real local Stable Diffusion inference, memory/performance, and final long-form A/V acceptance remain manual Windows PC checks; they are not claimed by this PR.

No project schema migration, automatic model downloads, cloud provider, engine auto-selection, or automatic composition application. Animated video remains the responsibility of the separate Universal Produce pipeline.
