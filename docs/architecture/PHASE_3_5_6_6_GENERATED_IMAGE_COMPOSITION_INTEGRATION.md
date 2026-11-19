# Phase 3.5.6.6 — Generated Image Composition Integration

## Goal

Provide a deliberate handoff from generated images already bound to a scene into
the existing Scene Composition Editor. This phase does not generate, bind, render,
or persist anything automatically.

## Workflow

1. Generate an image through the local Visual Generation workflow.
2. Import it into the Visual Asset Library.
3. Review and bind it to a Project scene through Scene Assets & Continuity.
4. Open that scene in Scene Composition Editor.
5. Use **Add Bound Generated Images** to add verified generated assets not already
   present in the composition.
6. Review the auto-grid, make manual layout changes, run Preview & Validate, then
   explicitly apply and save the project.

## Domain safeguards

- Only scene-bound `generated-image` references are considered.
- The matching library asset must still be `generated-image` and have
  `generated:<provider>` provenance.
- Missing or changed provenance is a blocking error; arbitrary uploads are not
  silently included.
- Existing composition elements and their transforms/layers are preserved.
- Already-present asset IDs are skipped to prevent duplicates.
- The default auto-grid is capped at 12 new assets per action to keep the layout
  reviewable; larger sets require multiple deliberate additions/layout decisions.
- The helper returns a new composition proposal only. Project state is not mutated.
- Existing preview validation, explicit apply confirmation, and project save remain
  the only persistence path.

## Scope boundary

This does not enable layered composition rendering/export. The existing renderer
capability check remains authoritative and must not silently flatten or discard
layers/transforms. Real inference, UI responsiveness, and rendering performance
still require the planned end-of-Phase-3 test on the target Windows PC.
