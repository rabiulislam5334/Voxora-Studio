# Phase 3.5.6.7 — Generated Image Raster Composition Support

## Goal

Allow verified generated-image assets to pass through the existing CPU raster
composition renderer and its explicit render-capability bridge.

## Delivered

- The raster composition adapter declares both `image` and
  `generated-image` asset kinds for PNG still-frame output.
- The bound-asset resolver accepts only matching scene-binding and catalog
  kinds: `image` or `generated-image`.
- A `generated-image` must retain a `generated:<provider>` provenance source.
  Missing or altered provenance blocks rendering.
- Existing content-addressed library path and SHA-256 verification remain
  mandatory before bound rendering.
- The composition bridge still requires a valid current preview and explicit
  user approval; it does not auto-render or auto-save.

## Scope boundaries

- Output is one transparent PNG still composition, not MP4/video.
- This does not add animation, timeline integration, AI generation, model
  downloads, GPU acceleration, or automatic asset binding.
- User-uploaded ordinary images continue through the existing `image` path.
- Existing project and `.voxora` schemas remain unchanged.

## Validation

Tests cover generated-image catalog/binding kind agreement, required provider
provenance, content identity resolution, actual PNG pixel output, and explicit
bridge rendering with the generated-image asset kind.
