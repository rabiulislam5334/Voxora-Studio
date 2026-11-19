# Phase 3.5.6.5 — Generated Image to Scene Binding

Generated images are imported into the Visual Asset Library first. This phase adds a
small domain workflow for selecting generated-image assets, previewing their binding
to a specific Project scene, and applying the binding only after explicit approval.

## Safety and compatibility
- Preview is read-only and uses the existing scene-binding fingerprint/staleness checks.
- Only assets marked as `generated-image` with `generated:<provider>` provenance qualify.
- User uploads and arbitrary library assets are not accepted by this generated-image handoff.
- Applying is explicit; no automatic scene mutation occurs after image generation.
- Existing `.voxora` scene plans and additive UniversalState persistence are reused.

## Scope
This phase does not create image-to-video motion, scene composition, or automatic
layout. After applying, the existing Scene Assets & Continuity workspace can inspect
the scene binding and the existing Composition Editor can use the bound asset.
