# VXP-10.4 — Deterministic Production Director Core

## Purpose

Establish the first real decision-making layer between narration and the existing visual/render engines. The Director consumes the exact script segmentation and the selected channel profile, then proposes a structured scene/shot plan. It is intentionally local-first and dependency-free.

## Delivered in this slice

- app/universal/production_director.py adds a ProductionDirector service and version-1 serializable plan models.
- Each shot is linked to its exact source narration unit and carries the existing measured/estimated timing provenance.
- Transparent keyword/phrase heuristics classify narration into conservative visual intents: question reveal, map, diagram, evidence, timeline, character action, environment, or neutral illustration.
- Shot prompts combine the exact narration slice with the selected profile's style family, style tags and composition guidance.
- Adjacent shots are grouped into bounded scenes by narrative family, paragraph boundaries and configured shot limits.
- Recovered role rule is preserved: first scene is intro and last scene outro only when there are at least three scenes; otherwise all scenes are body.
- Rihvaya profile constraints are carried into visual prompts: no identifiable Prophet/Sahaba facial depiction and no invented religious dialogue/events.
- Stable plan IDs are derived from the source fingerprint, profile, configuration and serialized plan.
- Every plan remains marked requires_review; no proposal is silently approved.

## Explicit boundaries

This is a deterministic planning foundation, not yet a full semantic AI Director. It does not use an LLM, claim human-level understanding, infer facts absent from the script, generate or acquire assets, select a renderer, create animation, place sound/captions, or render an MP4. Keyword matches are transparent hints, not factual conclusions. Unmatched text receives a neutral illustrative intent and low confidence.

No paid API, cloud call, subscription, model download or new runtime dependency is introduced. Existing NarrationSource, StoryboardProposal timing, and ChannelProfile contracts are reused; no duplicate asset registry, profile registry, timeline or renderer is created.

## Tests and acceptance

tests/test_production_director.py covers stable output, profile style propagation, measured timing preservation, scene roles, bounded grouping, Rihvaya policy propagation and invalid input handling.

CI tests prove the pure planning contract only. They do not prove semantic quality, real visual asset selection, continuity across long videos, target-PC rendering or full Auto Produce.

## Next increments

1. Expand Script Intelligence into evidence-backed narrative beat and topic-transition analysis without rewriting source text.
2. Add a versioned external visual-direction package importer and validation path (VXP-10.2).
3. Add confidence/review diagnostics and stronger scene/shot purpose rules.
4. Connect approved shot intents to existing visual-generation, asset-library and composition capabilities only after capability/licence checks.
5. Keep a local model provider optional and separately benchmarked; do not make it a prerequisite for the user's 8 GB target PC.