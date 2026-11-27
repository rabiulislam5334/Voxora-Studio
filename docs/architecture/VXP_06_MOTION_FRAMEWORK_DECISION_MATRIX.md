# VXP-06.2 — Motion Framework Decision Matrix

> Status: IN PROGRESS — exact HyperFrames 0.9.46 tarball identity/integrity and raw npm/SLSA attestation subject/source identity are matched; published font/package notices and runtime redistribution gates remain open.
> Baseline: `main` at `19c7b4383f5a1b547970ca47bf77927715e47c83` (2026-11-25).
> Parent: [Master Product Plan](../PLANNING/README.md), VXP-06 / TS-02.

## 1. Decision scope

Compare Motion Canvas, HyperFrames and Remotion as candidate adapters for Voxora's motion-production needs. This is a decision about an adapter, not a replacement for the Universal Core, Production Director, composition contracts, Render Orchestrator or FFmpeg final assembly.

The selected approach must preserve the product requirements:
- Local-first and $0-cost-first; no mandatory hosted service, paid API, subscription or hidden upload.
- Supplied narration remains the timing and audio master.
- Deterministic, reproducible rendering with cancellation and bounded resource use.
- Windows 10 compatibility on the documented i5-8250U / 8 GB RAM / NVIDIA 940MX target, with CPU fallback.
- Bengali/Unicode typography and mixed-language captions must be validated, not assumed.
- 2D, 2.5D, 3D, 4D/time-based 3D and Hybrid remain first-class product capabilities. A single adapter need not implement every capability; the architecture must support capability-declared adapters.
- FFmpeg remains the final encoding/mux backbone.

## 2. Existing benchmark evidence (user-run, 14–15 Nov 2026)

These are the recorded results from the isolated `D:\\Voxora-TS02-Benchmark` workspace. They are workload-specific observations, not a controlled head-to-head benchmark.

| Candidate | Recorded workload/result | Visual assessment | Evidence limits |
|---|---|---|---|
| Motion Canvas | 29-second animation rendered in 39 seconds | User judged visual quality weak | Exact scene parity, resolution/FPS, memory, typography and repeatability metrics are not recorded in this summary |
| HyperFrames CLI 0.9.46 | 93-second workload; 3D elements added successfully | User judged visual result good | Exact scene parity, output settings, memory, typography and repeatability metrics are not recorded in this summary |
| Remotion 4.0.543 | 1920×1080, 30 FPS, 870 frames; 175,486 ms frame capture + 708 ms stitching; 7.2 MB silent H.264 MP4; software rendering | User confirmed 3D elements were added in the broader benchmark evaluation | Chrome Headless Shell initially timed out; retry succeeded. Peak RAM, Bengali typography and repeatability metrics are not recorded here |

**Interpretation:** do not rank raw render times across these rows. The recorded durations and workloads differ, so they do not establish relative throughput. The HyperFrames visual assessment is positive but is not by itself a portability, licensing or production-readiness decision. Remotion has the most explicit output configuration recorded, but its browser-based software-render path and initial timeout need resource/reliability consideration on the target PC. Motion Canvas has a faster recorded run but weak user-assessed visual quality for that sample.

No candidate is selected by this evidence alone.

## 3. Formal decision matrix

Legend: **Observed** = directly recorded above; **Partial** = some evidence exists but is insufficient; **Unknown** = not verified in the available benchmark record; **Gate** = must pass before adoption.

| Criterion | Motion Canvas | HyperFrames | Remotion | Adoption gate |
|---|---|---|---|---|
| Visual quality on evaluated sample | Observed: weak | Observed: good | Partial: 3D elements demonstrated; comparative quality not scored | Representative profile scenes reviewed side by side |
| Render speed | Partial: 39 s / 29 s sample | Partial: 93 s sample | Partial: 175.486 s capture + 0.708 s stitch | Same scene, duration, resolution, FPS and machine |
| Peak RAM / VRAM | Unknown | Unknown | Unknown | Measure peak process and system memory on target PC |
| CPU/GPU behavior | Unknown | Partial: Remotion software rendering recorded | Observed: software rendering | Record CPU/GPU path and graceful CPU fallback |
| Bengali Unicode typography | Unknown | Unknown | Unknown | Bengali যুক্তাক্ষর, vowel marks, shaping, fallback fonts and mixed English test |
| 2D / 2.5D | Unknown in comparable sample | Partial: visual composition demonstrated | Partial: composition/render demonstrated | Test layered motion, easing, masks and camera choreography |
| 3D capability | Unknown in comparable sample | Observed: 3D elements added | Partial: 3D elements added in broader evaluation | Verify actual scene implementation, not a static 3D-looking render |
| 4D/time-evolving 3D | Unknown | Unknown | Unknown | Adapter capability test or explicit delegation to another engine |
| Hybrid footage + graphics | Unknown | Unknown | Unknown | Mix real footage/stills with animated overlays and provenance |
| Windows 10 portability | Partial: user benchmark environment was Windows | Partial: user benchmark environment was Windows | Partial: user benchmark environment was Windows | Clean install/run on target PC with pinned dependencies |
| Headless/automation suitability | Unknown | Partial: CLI version used | Partial: CLI/browser render used | Repeatable unattended invocation, structured progress and errors |
| Determinism / reproducibility | Unknown | Unknown | Unknown | Same inputs/settings produce stable frame sequence or documented variance |
| Cancellation / recovery | Unknown | Unknown | Unknown | Cancel mid-render, cleanup, retry and no partial final publication |
| Licence / redistribution | Lockfile: 112 entries; Windows exporter installs GPLv3 FFmpeg + GPL-3.0 FFprobe binaries; one dependency has no licence metadata | CLI command pins 0.9.46, but root-only lockfile has no tarball integrity/dependency graph; Apache-2.0 upstream reference only | Lockfile: 407 entries; 8 packages lack licence metadata; Windows compositor includes FFmpeg binaries; custom Remotion licence applies | Close exact binary/runtime notices and product redistribution terms before adoption |
| $0 local-first operation | Unknown for complete dependency/runtime path | Partial: CLI benchmark was local | Partial: software-render benchmark was local | No mandatory paid account, hosted service or hidden upload |
| FFmpeg handoff | Not yet proven in this comparison | Not yet proven in this comparison | Observed silent H.264 output for sample | Feed validated frames/video to existing FFmpeg pipeline without duplicate mux ownership |

## 4. Existing Voxora foundations to reuse

Voxora already has renderer-independent integer-frame motion contracts, a CPU raster frame renderer, sequential PNG sequence rendering, and a silent MP4 coordinator that reuses the validated FFmpeg frame-sequence encoder. These are merged foundations (PRs #87–#89 and subsequent motion/timeline work); they do not constitute selection of Motion Canvas, HyperFrames or Remotion.

The Cinematic Skill adapter is a separate specialized Skia-based visual adapter. It must not be treated as proof that one of the three TS-02 candidates has been selected. PR #129 adds Director-driven camera presets to that existing adapter; it does not close VXP-06.2 or 06.3.

## 5. Decision method and next evidence

Do not rerun the previous benchmark wholesale. First recover the original benchmark scripts, exact scene inputs, settings and logs from the isolated workspace if still available. Fill only missing fields where source evidence or existing artifacts can establish them.

If a final comparison is still needed, run one controlled, minimal scene on the same Windows target PC:
1. One 20–30 second narration-led explainer scene with identical visual content and motion intent.
2. Same output resolution/FPS, asset set, font files, frame count and quality target.
3. Record wall time, peak RAM, peak VRAM, CPU/GPU utilization, disk footprint, cold/warm run, and whether a retry was required.
4. Include Bengali text with যুক্তাক্ষর/কারচিহ্ন and mixed Bengali-English labels.
5. Inspect 2D, layered 2.5D camera movement, one actual 3D element, and a hybrid footage/graphics composite. Do not claim 4D capability from a camera zoom or simple animation.
6. Verify deterministic output, cancellation cleanup, unattended invocation, Windows packaging and FFmpeg handoff.
7. Audit exact direct/transitive dependency, browser/runtime, binary and font licences before adopting or redistributing.

A controlled run is justified only if the original artifacts cannot fill the decision-critical gaps. Do not repeat completed work merely to produce a new benchmark.

## 6. Current recommendation

**No primary framework selected.** Keep the existing Voxora motion contracts and renderer adapters independent. Continue using the already integrated Cinematic Skill adapter only for its documented documentary/evidence-board strengths, subject to its separate licence and target-PC gates. Do not make Motion Canvas, HyperFrames or Remotion a mandatory dependency yet.

The recovered package and licence evidence is recorded in [VXP_06_MOTION_CANDIDATE_LICENSE_AUDIT.md](./VXP_06_MOTION_CANDIDATE_LICENSE_AUDIT.md). Motion Canvas has an exact 112-entry lockfile, but its installed Windows FFmpeg/FFprobe binaries declare GPLv3/GPL-3.0. HyperFrames' project scripts pin CLI 0.9.46, but its root-only lockfile preserves no tarball integrity or dependency graph. Remotion 4.0.543 has an exact 407-entry lockfile, while eight package entries lack licence metadata and its Windows compositor includes FFmpeg binaries. No candidate is approved for bundling or selected.

The final selection (VXP-06.3) remains BLOCKED until HyperFrames package provenance, candidate binary/browser/font notices, local-only behavior and Remotion's product-distribution boundary are resolved. A capability-based multi-adapter architecture remains valid; the product's permanent 2D/2.5D/3D/4D/Hybrid scope must not be reduced to whichever candidate wins this comparison.


### HyperFrames 0.9.46 source provenance follow-up

The official upstream tag `v0.9.46` resolves to immutable commit `43132411c86b23a55134afaf261d77f3785168cc`. Its CLI package manifest is `@hyperframes/cli@0.9.46`, Apache-2.0, Node >=22, with declared Puppeteer/browser, fontkit and related runtime dependencies; producer/engine manifests also declare Puppeteer dependencies. The official guide documents local Puppeteer/Chromium + system FFmpeg mode and a separate Docker mode. This improves source provenance and establishes the dependency families, but does not prove npm tarball identity, resolved transitive closure, browser/font/FFmpeg redistribution terms, or no-network behavior. HyperFrames remains a lead candidate for further audit only—not selected or cleared for bundling.


### HyperFrames 0.9.46 runtime/privacy/font follow-up

Source inspection at upstream tag v0.9.46 (commit 43132411c86b23a55134afaf261d77f3785168cc) adds decision-critical findings:

- The source CLI manifest is published under the unscoped npm name hyperframes by a release workflow that rewrites the package name before npm publish. The workflow pins its source checkout to an immutable release commit, but npm tarball dist.integrity and provenance metadata were not retrievable here. Exact source-to-tarball identity remains unverified.
- The CLI build embeds generated WOFF2 font data and copies several runtime surfaces into its published dist. The font generator selects Latin subsets from its canonical font list; that list has no Bengali-specific family/subset. Bengali shaping and fallback must be validated separately, and exact embedded font notices remain open.
- Production telemetry defaults to enabled and sends command/system/render event metadata to PostHog. The source provides HYPERFRAMES_NO_TELEMETRY=1, DO_NOT_TRACK=1 and a persistent disable command. A separate npm update check runs in the normal CLI path, with HYPERFRAMES_NO_UPDATE_CHECK=1 as an opt-out.
- The browser manager can download a managed Chrome Headless Shell. The engine's private-address filtering is not a global network-deny policy. Therefore the unmodified CLI is not proven to operate offline; strict local-first use requires explicit telemetry/update opt-outs and a pinned, pre-provisioned browser or a verified offline integration path.
- The npm version history confirms hyperframes@0.9.46 was published, but not its tarball integrity. No package install, network-isolated execution or target-PC benchmark was performed.

The lead-candidate assessment is now more qualified: HyperFrames remains the most promising candidate from the user's visual benchmark, but default telemetry/update behavior, managed-browser downloads, missing Bengali font coverage and unclosed npm/runtime licence evidence prevent adoption approval. Do not bundle or integrate it until the remaining gates are resolved. VXP-06.3 remains BLOCKED; no framework is selected.


### HyperFrames 0.9.46 npm/font lock follow-up

The immutable upstream publish workflow runs on GitHub-hosted Ubuntu with `id-token: write` and publishes the CLI using `npm publish` without an explicit `--provenance` flag. npm trusted publishing can generate provenance automatically, so this is OIDC-compatible evidence—not proof that trusted publishing was configured for this version. The exact npm `dist.integrity`, registry signature and build attestation could not be retrieved; provenance is **unverified**, not confirmed absent.

The same upstream tag's `bun.lock` pins all 18 Fontsource build packages to exact versions with SHA-512 integrity values. The core font generator embeds selected WOFF2 subsets into generated source. This closes the source-build dependency-version question for those fonts, but not the exact licence/notice question: Fontsource requires per-family licence review and the collection includes OFL-1.1, Apache-2.0 and Ubuntu Font License families. The exact licence files for these 18 locked artifacts remain open. The canonical generator still selects Latin subsets only; Bengali shaping remains unverified.

See [the detailed candidate licence audit](./VXP_06_MOTION_CANDIDATE_LICENSE_AUDIT.md), section “HyperFrames 0.9.46 publish-workflow and embedded-font lock follow-up”. No framework is selected; VXP-06.3 remains BLOCKED.


## 7. Reconciled decision update — 2026-11-27

This section reconciles the benchmark record above with the subsequent version-pinned audits in:

- [Remotion v4.0.543 licence eligibility audit](../PLANNING/TS-02_REMOTION_LICENSE_AUDIT.md) (PR #138; Windows and Ubuntu CI passed; PR remains unmerged at the time of this update).
- [HyperFrames v0.9.46 registry/archive audit](../PLANNING/TS-02_HYPERFRAMES_REGISTRY_ARCHIVE_AUDIT.md) (PR #139; Windows and Ubuntu CI passed; PR remains unmerged at the time of this update).

### 7.1 Updated candidate assessment

| Candidate | Positive evidence | Decision-critical unresolved risks | Current role |
|---|---|---|---|
| HyperFrames 0.9.46 | Best user-assessed visual result in the recorded workload; 3D elements were added; local CLI workflow was exercised; immutable upstream source tag and Apache-2.0 source manifest were inspected | Published npm tarball identity/integrity/signature/provenance not captured; actual archive and exact font notices not inspected; source build has no explicit per-font notice-copy step; default telemetry and update checks require opt-out; managed browser may download; Bengali font/shaping coverage is not established; offline/local-only behavior and target-PC resource use remain unverified | **PREFERRED LEAD FOR THE NEXT GATED EVALUATION — NOT SELECTED OR CLEARED FOR INTEGRATION** |
| Remotion 4.0.543 | User benchmark produced a 1080p/30 FPS H.264 output; individual free-use category permits eligible individuals to create commercial or non-commercial videos/images and modify for their own custom use | Pinned licence does not expressly establish third-party Windows desktop-app redistribution; written vendor clarification is needed; 407-entry dependency/browser/binary notice closure and target-PC reliability remain open; software rendering and an initial Chrome Headless Shell timeout were recorded | **SECONDARY CANDIDATE — PERSONAL EVALUATION ELIGIBLE, PRODUCT REDISTRIBUTION NOT CLEARED** |
| Motion Canvas | Existing 29-second sample completed in 39 seconds | User judged visual quality weak; Windows exporter installs GPLv3 FFmpeg and GPL-3.0 FFprobe binaries; dependency/licence closure and capability evidence remain incomplete | **DEPRIORITIZED; DO NOT REPEAT THE SAME BENCHMARK** |

The recorded wall times are not comparable because the workloads and output settings were not controlled. The lead-candidate preference is based on the user's visual assessment and demonstrated local CLI/3D workflow, not a claim that HyperFrames is faster than Remotion or proven to use less memory.

### 7.2 Decision

**Do not declare a production framework winner yet.** For the next focused evaluation, prioritize HyperFrames as the lead candidate and keep Remotion as the fallback candidate. This narrows the work without weakening the product's local-first, $0-cost, licensing, privacy or target-PC requirements.

HyperFrames may not be added as a mandatory dependency, bundled into the desktop installer, or invoked in Auto Produce until all of the following are evidenced:

1. Exact npm registry metadata, tarball SHA-512/integrity, signature and provenance status are captured; absence must be recorded only if the registry/tool explicitly reports absence.
2. The exact published archive and all 18 pinned Fontsource package archives are inspected; required notices are retained or the font packaging path is corrected.
3. Telemetry and update checks are disabled by default in the Voxora invocation, and the browser is pre-provisioned/pinned without a hidden download or network requirement.
4. The exact runtime/dependency/browser/FFmpeg redistribution obligations are closed for the intended Voxora distribution model.
5. A narrow, isolated local-only invocation succeeds on the documented Windows target PC with measured RAM/VRAM, CPU, disk and render time, including a cancellation/cleanup check.

If HyperFrames fails a mandatory gate, stop and reassess Remotion's exact desktop distribution route; do not silently relax the gate or switch to an unreviewed framework.

### 7.3 Work that can proceed without framework selection

The existing `app/universal/motion.py`, `motion_raster_renderer.py`, `motion_video.py` and `motion_timeline.py` foundations already provide renderer-independent scalar keyframes, camera transforms, deterministic frame evaluation, PNG frame rendering, sequential silent MP4 encoding and timeline/audio handoff.

Do not duplicate or replace these modules. Continue renderer-neutral contracts and tests only where a concrete missing requirement is identified. Framework-specific adapter implementation remains gated by VXP-06.3. The permanent 2D, 2.5D, 3D, 4D/time-based 3D and Hybrid capabilities remain architecture requirements; none is removed or made dependent on one framework.


## 9. HyperFrames registry, archive and provenance reconciliation — 2026-11-27

This section supersedes the earlier provisional evidence statements in §§7–8 where they say that the exact npm tarball, raw attestation or provenance subject could not be verified. The detailed evidence record is [TS-02_HYPERFRAMES_REGISTRY_ARCHIVE_AUDIT.md](../PLANNING/TS-02_HYPERFRAMES_REGISTRY_ARCHIVE_AUDIT.md), §§6–7.

- The supplied `hyperframes@0.9.46` tarball SHA-512 and SHA-1 exactly match version-specific npm registry metadata; all 774 regular archive files were inspected.
- The raw npm publish and SLSA v1 attestation statements both identify `pkg:npm/hyperframes@0.9.46` and the exact archive SHA-512. The SLSA statement identifies `heygen-com/hyperframes`, `.github/workflows/publish.yml`, `refs/heads/main`, source commit `43132411c86b23a55134afaf261d77f3785168cc`, and Actions run `43602505718`.
- The user's npm audit output reports 74 verified registry signatures and 24 verified attestations across the audited package set. Per-package JSON output was not supplied, and this review did not independently re-run Sigstore cryptographic verification. Record these boundaries; do not overstate them.
- The published archive contains embedded font data for 18 Fontsource families but only three matching per-family OFL notices. Fifteen corresponding notices are missing; the package-root Apache-2.0 licence text is also absent.
- The installed Windows dependency tree includes native sharp/libvips payload with an LGPL-3.0-or-later component; its redistribution boundary remains open. Browser pre-provisioning, FFmpeg/runtime obligations, telemetry/update opt-out, offline/local-only operation and target-PC performance/cancellation are not verified.

**Updated decision:** HyperFrames remains the preferred lead for the next gated evaluation, not a selected or cleared production framework. VXP-06.2 remains IN PROGRESS; VXP-06.3 remains BLOCKED. Do not bundle or invoke HyperFrames in Auto Produce until all licence, runtime, privacy, offline and target-PC gates close. No benchmark was rerun and no Voxora runtime code was changed.
