# VXP-06.2 — Motion Framework Decision Matrix

> Status: IN PROGRESS — original workspace recovered; Motion Canvas and Remotion lockfiles inventoried; HyperFrames package closure and binary/runtime licensing remain open.
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
