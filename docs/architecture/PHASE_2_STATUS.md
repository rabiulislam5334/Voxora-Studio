# Phase 2 — Status, Scope, and Exit Criteria

**Status:** Production-hardening implementation is complete; final acceptance is pending a Windows locked-output integration test in CI and one real local production render.  
**Baseline:** `main` at `58764dae4135156de0e93b693bba0daae80822b9` (PR #40 merged).  
**Guiding constraints:** local-first, hardware-aware, sequential, deterministic, and backward-compatible.

## Goal

Deliver a dependable local production path for narration and scene-based video rendering. Phase 2 focuses on production correctness and reliability, not on adding a large collection of visual effects or renderer providers.

The existing FFmpeg renderer remains the production baseline. Universal Core contracts are connected through an explicit bridge; unsupported engine choices or visual requirements must fail clearly rather than silently switching engines.

## Completed implementation

The following Phase 2 hardening work is present on `main`:

- Final MP4 stream, duration, decoded-frame, timestamp-continuity, CFR, stream-start, and zero-origin validation (PRs #21, #23–#27, #29, #32).
- Cancellable final FFprobe inspection and cancellation-safe publication (PR #29).
- Corrupt cached-segment rejection and cache output-contract checks (PRs #30, #39).
- Ownership-safe temporary-file handling; no directory-wide sweep of potentially active segment `.part` files (PRs #31, #39).
- Universal ScenePlan/AssetRef-to-production bridge while preserving the legacy rendering path (PR #34).
- Preflight validation before TTS, production filesystem error boundaries, and decoded-audio placement tests (PR #37).
- Windows FFmpeg command-line length guard (PR #38).
- Cache LRU/image-budget eviction improvements (PR #40).
- Windows CI configured to install and verify FFmpeg and FFprobe (PR #36).

## Explicitly deferred to Phase 3

**P2-01 — A first-class scene-plan authoring/production-plan builder is deferred to Phase 3.**

Phase 2 consumes an explicit supported Universal scene plan and can create an ephemeral compatibility plan for legacy projects. It does not introduce a new authoring UI or persist generated plans into the project schema. This avoids mixing production hardening with a broader authoring and schema initiative.

## Remaining Phase 2 acceptance checks

Implementation checklist items P2-02 through P2-09 have corresponding code and regression coverage. The remaining acceptance checks are:

1. **Real Windows locked-output integration test:** hold an existing destination MP4 open with a native Windows file handle that omits `FILE_SHARE_DELETE`; verify final publication fails safely, the previous output bytes remain unchanged, and the job-owned `.part` file is removed. This test is Windows-only because POSIX rename semantics differ. Added in the current PR and awaiting CI.
2. **Real local production render:** complete a representative render from the desktop application on the user's machine and confirm the output passes the existing final MP4 validation path. Automated synthetic-media tests do not replace this acceptance check.
3. **Final documentation/CI review:** keep this status aligned with the latest green Ubuntu and Windows run; explain platform-specific skips rather than treating them as failures or silently ignoring them.

## Latest CI evidence

PR #41's diagnostic-only waveform test change passed GitHub Actions run #173:

- Windows: **635 passed, 1 skipped**.
- Ubuntu: **624 passed, 12 skipped**.

The same waveform UI test passed 10 consecutive times locally on Windows, and the user's full local Windows suite reported **636 passed**. Run #173 is evidence that the previous Windows failure did not reproduce on that run; it does not prove the intermittent failure is permanently fixed. PR #41 is diagnostic-only and remains separate from production behavior.

The Ubuntu runner is headless; Tk UI tests that require a display are platform-skipped there. Windows CI exercises the Windows UI path. Review skip reasons whenever the workflow or test environment changes.

## Compatibility and accepted trade-offs

- Legacy projects without an explicit Universal scene plan continue through the compatibility path.
- Existing segment cache keys, project schema, timeline/sample/frame calculations, and final-output validation are not intentionally changed by the Phase 2 hardening work.
- Source-media cache identity remains based on path, size, and modification timestamp. A content change that preserves all three can evade invalidation; this is a documented trade-off, not a content-hash guarantee.
- Parallel rendering, scheduling, automatic engine fallback, and distributed execution remain out of scope.

## Closure rule

Do not declare Phase 2 fully closed until the Windows locked-output integration test passes in CI and a real local production render is confirmed to pass final MP4 validation. After those checks, record the exact commit, CI run, local test result, and render verification here.
