# VXP-10.5 — Per-shot Visual Selection, Acquisition and Generation

**Status:** IMPLEMENTED (bounded coordinator); CI verification pending; PC verification NOT STARTED.

## Purpose

Resolve each approved Production Director shot to a suitable visual without requiring manual per-shot asset assignment. Reuse the existing Visual Asset Library and Visual Generation Runtime. This is a VXP-10.5 implementation slice, not a new roadmap phase or a new asset/provider system.

## Current flow

1. Validate the DirectorPlan, exact script SHA-256 fingerprint, the exact NarrationSource and ordered narration-unit coverage, active profile ID/style family, explicit approval, and one-to-one scene/shot references.
2. Load the existing local VisualAssetCatalog.
3. Rank assets deterministically using exact keyword/tag overlap and intent tags. An asset is eligible only when its content hash verifies, its path resolves safely inside the library, its optional profile restriction allows the active profile, and provenance indicates a user import, generated asset, or a declared public-domain/CC0/CC BY/CC BY-SA licence family (non-commercial and no-derivatives variants are excluded).
4. Select the highest-scoring asset, with asset ID as a deterministic tie-breaker.
5. If no suitable local asset exists, generation is attempted only when the host injects a VisualGenerationRuntime and names one exact provider ID. The same VisualAssetLibrary must be used by both.
6. Forward network and API-key consent explicitly; both default to false. The existing runtime stages, validates and imports provider output.
7. Return one typed result per shot: selected, generated, or unresolved, with asset ID/path, provenance/provider and diagnostics.

## Safety and product boundaries

- Director prompts must be explicitly approved before resolution.
- The supplied script, Director timing and narration are not rewritten.
- Local asset matching is deterministic and content-based; it is not embedding search or factual verification.
- A matching tag does not prove that an image depicts the factual subject accurately. Documentary/evidence assets still require source and claim review.
- User-upload provenance is accepted as owner-supplied. Other imported sources are eligible only with a declared public-domain/CC0/CC BY/CC BY-SA licence family; non-commercial and no-derivatives variants are excluded. This declaration is not independently verified legal clearance. Missing/unsafe/hash-mismatched assets are skipped.
- Generated images are recorded as generated assets. Model and output rights still require review; generation is not a licence clearance.
- No stock-media website, remote search, hidden upload, cloud provider discovery or paid API is contacted.
- No project scene binding is applied here. The existing preview/apply binding workflow remains the explicit persistence boundary.
- If no eligible asset/provider is available, the shot is returned as unresolved with an actionable diagnostic. Downstream production must use a profile-compatible procedural fallback or report the gap; it must not claim that a visual exists.
- This slice resolves still images only. It does not claim video-footage acquisition, map/chart rendering, 2D character animation, 2.5D, 3D, 4D/time-based 3D, or Hybrid production is complete. Those remain permanent first-class product capabilities and require their respective adapters.

## Reused systems

- `app/universal/production_director.py`
- `app/universal/asset_library.py` and `visual_assets.py`
- `app/universal/visual_generation.py` and `visual_generation_runtime.py`
- Existing generated-image provenance and content-addressed import

No duplicate registry, downloader, generation runtime or renderer is introduced.

## Acceptance in this slice

- Reject stale script/profile and unapproved plans.
- Reject incomplete/duplicate scene-to-shot mappings.
- Prefer a verified local asset over invoking a generator.
- Skip assets without acceptable provenance, profile compatibility or verified bytes.
- Generate one still per unmatched shot only through the explicitly selected injected provider.
- Preserve explicit network/API-key consent and report generation failures as unresolved.
- Keep every result associated with its exact Director shot and scene.

## Remaining work

This does not complete all of VXP-10.5 or VXP-10. The coordinator is not yet wired into the one-action Auto Produce/Render Orchestrator path, does not automatically persist reviewed scene bindings, and has no semantic image ranking, documentary source research, stock-media acquisition, cache/retry orchestration, per-shot regeneration UI or visual-quality QC. Real local Stable Diffusion.cpp inference, model licensing, resource use and quality on the target Windows PC remain unverified. No CI or PC verification is claimed until the corresponding evidence exists.
