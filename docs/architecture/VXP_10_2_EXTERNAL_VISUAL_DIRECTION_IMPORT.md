# VXP-10.2 — External Visual-Direction Package Import

## Initial interchange contract

The first supported package is UTF-8 JSON using schema version 1 and the
existing `DirectorPlan.to_dict()` shape. This keeps the interchange contract
aligned with Voxora's existing scene/shot, narration-unit, timing, intent and
profile data instead of introducing a parallel planning model.

## Validation and safety

- Bind the package to the exact active script SHA-256, narration source ID and
  active channel profile ID/style family.
- Reject unknown schema versions, duplicate JSON keys, non-finite numbers,
  oversized packages, invalid enums, duplicate IDs and incomplete/reordered
  narration or scene/shot coverage.
- Preserve the imported prompts, shot cues and timing provenance. Package
  timestamps remain planning data; measured supplied-audio alignment remains
  the timing authority at Auto Produce handoff.
- Imported plans always require explicit review and approval. Importing never
  acquires assets, calls a provider, renders media or silently replaces the
  internal Director plan.

## Scope

This is the local JSON interchange/validation foundation. A Claude-specific
prompt/export workflow, UI file picker, external provider integration and
additional interchange schemas remain future work. No network access, paid
API, cloud upload or new dependency is introduced.
