# VXP-06.2 — Preliminary Motion Candidate Licence & Local-Use Audit

> Status: IN PROGRESS — upstream top-level terms inspected; exact benchmark package provenance and transitive/runtime closure remain unverified.
> Audit date: 2026-11-25.
> Scope: Motion Canvas, HyperFrames CLI 0.9.46 and Remotion 4.0.543 from the recorded TS-02 evaluation. This is an engineering evidence record, not legal advice.

## 1. Decision boundary

This audit separates three questions that must not be conflated:

1. May an individual use the candidate locally to create and monetize videos?
2. May Voxora depend on, bundle, redistribute or commercially ship the candidate/runtime?
3. Are every exact direct/transitive package, browser/runtime binary, codec, font and asset cleared?

A permissive top-level repository licence does not answer questions 2–3 by itself. No candidate is approved for bundling or selected as the primary adapter by this preliminary audit.

## 2. Upstream evidence inspected

| Candidate / benchmark version | Upstream source inspected | Top-level evidence | Preliminary result |
|---|---|---|---|
| Motion Canvas (benchmark exact version not recorded in the current summary) | https://github.com/motion-canvas/motion-canvas, root `LICENSE`; historical tag `v3.17.2` also inspected | MIT text grants use, modification, distribution and sale subject to retaining copyright/permission notice | **Top-level permissive**. Exact benchmark version, package set and transitive notices still need pinning/audit. |
| HyperFrames CLI 0.9.46 | Correct upstream identified by the current official README as https://github.com/heygen-com/hyperframes; root `LICENSE` | Apache License 2.0, including copyright and patent grants and redistribution conditions | **Top-level permissive**. Exact 0.9.46 tag/package provenance and its bundled/runtime dependency closure are not yet tied to the original benchmark artifact. |
| Remotion 4.0.543 | https://github.com/remotion-dev/remotion, tag `v4.0.543`, root `LICENSE.md` | Custom two-tier Remotion Free/Company License, not MIT/Apache. Free tier explicitly includes individuals and allows commercial video creation; Company License is required outside eligible categories. Free tier prohibits copying/modifying Remotion code to sell, rent, license, relicense or sublicense a Remotion derivative. | **Conditional for individual video creation; not cleared for Voxora redistribution/product packaging.** Company-size eligibility and derivative/redistribution boundary require explicit review. |

### HyperFrames identity correction

The current `hyperframes/hyperframes` GitHub repository is a different repository that points readers to `heygen-com/hyperframes`. The TS-02 record says “HyperFrames CLI 0.9.46” but does not preserve its package tarball, lockfile, commit or executable provenance. The source identity above is therefore the current official project reference, **not yet proof** that the benchmark executable was built from that exact repository/release. Recover the original workspace metadata before attributing the benchmark binary's licence conclusively.

## 3. Local-first and paid-service boundary

- HyperFrames upstream describes local CLI operation requiring Node.js and FFmpeg, while also promoting optional cloud rendering. A local-only path appears to exist; Voxora must not call cloud services or upload user media implicitly. Verify the exact 0.9.46 CLI behavior and network activity before adoption.
- Motion Canvas is an open-source code-driven animation tool; this audit did not verify the complete runtime or any optional paid service because the benchmark version/lockfile is absent.
- Remotion's licence eligibility is distinct from whether the benchmark used a local software-rendering path. Local rendering does not waive licence eligibility or packaging obligations.
- No candidate may introduce a mandatory subscription, paid API, hosted renderer or hidden upload into Voxora's core workflow.

## 4. Outstanding evidence — exact blockers

| Evidence | Motion Canvas | HyperFrames 0.9.46 | Remotion 4.0.543 |
|---|---|---|---|
| Exact benchmark tag, package manifest and lockfile | Missing | Missing | Version recorded; original lockfile missing |
| Direct + transitive dependency licence inventory | Missing | Missing | Missing |
| Browser/headless runtime and binary redistribution terms | Not established | Not established | Chromium/Chrome Headless Shell exact build and redistribution terms not established |
| Fonts, codecs and optional plugin terms | Missing | Missing | Missing |
| Target-PC install and offline/local-only behavior | Not verified | Not verified for exact benchmark build | Partial benchmark observation only; clean install not verified |
| Commercial video creation by this individual | Top-level MIT permits it, subject to dependency terms | Apache 2.0 top-level permits it, subject to dependency terms | Free tier expressly permits eligible individuals to create commercial videos |
| Bundling/redistributing inside Voxora | Not cleared until dependency closure | Not cleared until dependency closure | Not cleared; custom licence boundary must be reviewed |

## 5. Required next steps (no benchmark rerun)

1. Recover `D:\Voxora-TS02-Benchmark` manifests, lockfiles, package metadata, CLI version output, scripts and logs. Do not repeat the render benchmark just to recreate missing metadata.
2. Match each executable to an immutable release/tag/commit and exact package versions.
3. Generate a direct/transitive licence inventory from those exact lockfiles; separately inspect browser, native binaries, codecs, fonts and optional plugins.
4. Verify local-only operation with network access disabled or monitored; no media upload is allowed without explicit user consent.
5. Review Remotion's Free/Company eligibility for the actual intended Voxora distribution model before considering it as a bundled dependency.
6. Keep the current renderer-neutral Voxora motion contracts and FFmpeg pipeline available while the audit is open.

## 6. Decision

**No candidate is approved for bundling or selected as the primary framework.** Motion Canvas and HyperFrames have permissive top-level licence evidence, but their exact benchmark dependency closures are not audited. Remotion permits eligible individuals to create commercial videos under its Free License, but its custom terms do not establish that embedding/redistributing it inside a commercial Voxora product is free or permitted in every intended distribution scenario.

VXP-06.3 remains **BLOCKED** until exact benchmark provenance, dependency/runtime notices, target-PC local operation and Remotion distribution eligibility (if still considered) are resolved. This audit does not reduce the permanent 2D, 2.5D, 3D, 4D/time-based 3D or Hybrid product capabilities.
