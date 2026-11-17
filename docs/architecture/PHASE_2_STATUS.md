# Phase 2 — Status, Scope, and Exit Criteria

**Status:** In progress  
**Baseline:** `main` after PR #34, commit `e2bd3144a6905e01a52c673a6d5756063c99d082`  
**Guiding constraints:** local-first, hardware-aware, sequential, deterministic, and backward-compatible.

## Goal

Deliver a dependable local production path for narration and scene-based video rendering. Phase 2 focuses on production correctness and reliability, not on adding a large collection of visual effects or renderer providers.

The existing FFmpeg renderer remains the production baseline. Universal Core contracts are connected through an explicit bridge; unsupported engine choices or visual requirements must fail clearly rather than silently switching engines.

## Completed milestones

The following capabilities are present on `main`:

- Final-output stream and duration validation (PR #21).
- Structured FFprobe inspection foundation (PR #23).
- Decoded video-frame count validation (PR #24).
- Per-stream audio/video duration validation (PR #25).
- Audio/video stream-start alignment validation (PR #26).
- Decoded-frame timestamp continuity and CFR validation (PR #27).
- Cancellable final media inspection and cancellation-safe publication (PR #29).
- Validation and rejection of corrupt cached video segments (PR #30).
- Removal of unsafe directory-wide temporary-segment cleanup (PR #31).
- Zero-based audio/video stream-origin validation (PR #32).
- Universal ScenePlan/AssetRef-to-production bridge while preserving the legacy rendering path (PR #34).

PR #22 was a documentation audit of synchronization properties. PR #28 and PR #33 were audit proposals; they are not counted as merged runtime milestones.

## Explicitly deferred to Phase 3

**P2-01 — A first-class scene-plan authoring/production-plan builder is deferred to Phase 3.**

Phase 2 can consume an explicit supported Universal scene plan and can create an ephemeral compatibility plan for legacy projects. It does not need to introduce a new authoring UI or persist generated plans into the project schema to meet its reliability goal.

This deferral avoids mixing production hardening with a broader authoring and schema initiative.

## Remaining Phase 2 work

The remaining work is a reliability checklist, not a promise that every item is a currently reproducible user-facing defect. Each implementation should be a small, separately tested change.

1. **Windows CI:** run the complete test suite on Windows in addition to Ubuntu. The Windows job must install and verify both FFmpeg and FFprobe.
2. **Preflight validation:** validate all scene/plan inputs before starting expensive TTS, audio-mix, or render work where practical.
3. **Filesystem error boundaries:** convert expected filesystem failures around temporary output, replacement, and cleanup into actionable production errors while preserving the original cause.
4. **FFmpeg command-length guard:** detect Windows command-line length risk for large join/crossfade commands and fail early with a clear error rather than launching an impossible command.
5. **Temporary artifact hygiene:** design conservative cleanup for abandoned temporary artifacts. Never delete another active render's files; ownership must be established before cleanup.
6. **Cache output contract tests:** strengthen tests for the exact stream/codec/pixel-format/FPS properties the cache relies on. Do not change cache identity or format without a separate compatibility review.
7. **Decoded audio placement tests:** verify rendered audio placement/onsets from decoded output, not only generated filter arguments and container duration.
8. **Cache eviction review:** assess hit recency, image-cache coverage, and cleanup timing; keep eviction changes separate from render correctness fixes.

## Exit criteria

Phase 2 is complete only when:

- Ubuntu and Windows CI both run the full test suite successfully; the Windows job verifies FFmpeg and FFprobe before testing.
- The full Windows test run has no unexpected skips or failures. Platform-specific skips must be explained.
- Preflight validation, filesystem error handling, and Windows command-length protection have focused regression tests.
- Temporary-file cleanup is ownership-safe and cannot sweep another active render's artifacts.
- Cache validation has tests for the output properties required by the current renderer and cache contract.
- Decoded audio placement has deterministic tests against generated media.
- A real local production render is completed and its output passes the existing final MP4 validation path.
- Legacy projects without an explicit Universal scene plan continue to render through the compatibility path.
- Existing cache keys, project schema, timeline/sample/frame calculations, and final-output validation remain backward-compatible unless a separately reviewed change explicitly authorizes otherwise.
- Parallel rendering, scheduling, automatic engine fallback, and distributed execution remain out of scope.

## Implementation order

1. Land and verify Windows CI.
2. Add preflight validation and filesystem/command-length hardening in separate PRs.
3. Strengthen cache contract tests and decoded-audio placement tests.
4. Review conservative temporary-artifact and cache-eviction policies.
5. Run the complete Windows suite and a real local render before declaring Phase 2 complete.

## Validation record

The user-reported Windows baseline after PR #34 was **624 passed in 90.45s** on the feature branch. A fresh test run on the merged `main` commit is still required; this document does not claim that a post-merge run has occurred.
