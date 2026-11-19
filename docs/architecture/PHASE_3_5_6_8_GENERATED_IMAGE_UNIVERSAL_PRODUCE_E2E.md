# Phase 3.5.6.8 — Generated Image Universal Produce End-to-End

## Goal

Prove that generated-image assets already imported into the managed Visual
Asset Library can travel through the same reviewed Universal Produce pipeline
as ordinary images, without bypassing provenance, binding, or content checks.

## Delivered

- Extend the Universal Produce end-to-end fixture to create generated-image
  assets with explicit `generated:<provider>` provenance.
- Exercise a complete two-scene production run using generated images:
  scene binding, saved composition preview/apply, deterministic camera motion,
  crossfade composition, frame-sequence encoding, and narration audio mux.
- Verify the resulting MP4 stream metadata, frame count, frame rate, dimensions,
  audio codec, and duration.
- Add a generated-image Universal Produce readiness test and confirm the
  read-only preflight does not mutate project settings.

## Safety and compatibility

- Generated assets still enter through the existing managed local asset library.
- The existing scene-binding kind, provenance, path, and SHA-256 checks remain
  authoritative; this phase adds no bypass or alternate resolver.
- No provider invocation, model download, network access, GPU use, or automatic
  scene mutation is introduced.
- Existing user-uploaded image flow and legacy project serialization remain
  unchanged.

## Scope boundaries

This phase validates the current still-image-to-motion video workflow. It does
not add AI Director planning, generated video, new animation engines, character
lip sync, or guarantee real-time performance on low-memory hardware.

## Validation

The acceptance gate is the repository's Windows and Ubuntu CI, including the
real FFmpeg integration test. Manual inference and long-duration performance
checks remain deferred to the planned Phase 3 PC test.
