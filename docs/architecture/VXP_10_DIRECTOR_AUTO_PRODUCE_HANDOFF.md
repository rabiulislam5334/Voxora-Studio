# Director Plan → Auto Produce Planning Handoff

**Status: IMPLEMENTED — CI NOT YET VERIFIED**

This supporting integration connects the merged deterministic Production Director plan to the existing supplied-script + supplied-narration Auto Produce service. It does not introduce a new VXP subphase ID.

## Scope

- Require an explicit approval flag before a DirectorPlan can enter Auto Produce.
- Verify the exact script SHA-256 fingerprint and active channel-profile ID.
- Verify ordered narration-unit coverage: every source unit appears exactly once across Director shots.
- Verify Director scenes reference every shot exactly once and in order.
- Require one measured aligned narration line per source unit. A count mismatch fails closed; the adapter does not infer a mapping.
- Map current Director intents to the existing Cinematic Skill card or title shot contract.
- Keep the original narration alignment and supplied audio as the timing/voice authority.
- Preserve the existing timed-card path when no DirectorPlan is supplied.

## Explicit limitations

- The current Cinematic Skill builder supports cards, titles and counters; this handoff only uses cards and titles.
- A map, diagram, evidence, timeline, character action or environment intent is not thereby a real specialized renderer. These intents currently receive a conservative card representation until capability-specific visual adapters are integrated.
- The Director visual prompt is not yet used to acquire or generate an asset.
- The caller must pass the exact NarrationSource used to create the DirectorPlan. The adapter checks its script fingerprint, ordered unit IDs, aligned line count and exact spoken text for each unit.
- Stable-ts/Skia real inference, Bengali timing quality, target-PC performance and final visual quality are not validated by unit tests.
- This does not implement VXP-10.5, which remains automatic visual selection/acquisition/generation per shot. It also does not implement VXP-10.2 external visual-direction package ingestion or Produce UI wiring.

## Acceptance boundary

The handoff is a deterministic, fail-closed planning bridge. It is not full Auto Produce acceptance and must not be reported as a finished Director-to-MP4 production system.