# Phase 3.5.6.1 — Visual Generation Domain Contracts

## Goal

Establish a provider-neutral, testable boundary for generating still-image visual assets for individual scenes. This is the first implementation slice of the Visual Asset Generation & Scene Authoring phase.

## Implemented

- Immutable `VisualGenerationRequest` with scene/request identity, prompt and negative prompt, optional exact model ID, dimensions, output format, image count, seed, style tags, reference asset IDs, and JSON metadata.
- Canonical serialization and SHA-256 request fingerprinting. Any generation-relevant input change produces a different fingerprint.
- Strict validation for identifiers, prompt size, dimensions, pixel budget, output format, image count, seed range, duplicate references, and JSON-safe metadata.
- Provider capability declarations for formats, resolution, batch size, reference-image support, deterministic seeds, network/API-key requirements, and estimated memory.
- Explicit provider registry with deterministic discovery, compatibility diagnostics, exact provider resolution, and no silent fallback.
- Public exports from `app.universal`.

## Important boundary

This slice does **not** generate images and does not call cloud APIs or load local models. No provider is registered by default. A provider descriptor marked unavailable remains visible only when callers request unavailable entries. This prevents the UI or planner from implying that an uninstalled model/provider can produce an image.

The contracts describe scene-specific generation intent but do not yet write to the Asset Library, mutate scene bindings, or alter project files.

## Hardware and privacy constraints

- Provider metadata explicitly declares whether network access and an API key are required.
- A local provider can declare `requires_network=False` and `requires_api_key=False`.
- Resource estimates are descriptive; actual admission control and memory probing belong to a later provider-runtime stage.
- Credentials must never be stored in request metadata, project files, or provider descriptors.

## Tests

`tests/test_visual_generation_contracts.py` covers request round trips and fingerprints, invalid inputs, capability validation, compatibility diagnostics, exact provider selection, unavailable providers, and duplicate registration.

## Next sub-phase

**3.5.6.2 — Local Provider Runtime & Safe Artifact Import:** define the executable provider protocol, cancellation/progress behavior, output verification, and safe handoff into the existing content-addressed Visual Asset Library. The first concrete backend should be optional and CPU/offline-aware; it must not make a GPU or paid API mandatory.
