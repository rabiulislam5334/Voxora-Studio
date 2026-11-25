# VXP-06.2 — Motion Candidate Licence & Local-Use Audit

> Status: IN PROGRESS — original workspace recovered; Motion Canvas and Remotion lockfiles inventoried; HyperFrames CLI command is pinned but its downloaded package/dependency closure is not preserved.
> Audit date: 2026-11-25.
> Scope: Motion Canvas, HyperFrames CLI 0.9.46 and Remotion 4.0.543 from the recovered TS-02 workspace. This is an engineering evidence record, not legal advice.

## 1. Decision boundary

This audit separates individual local video creation, Voxora bundling/redistribution, and the licence closure of every dependency/runtime asset. A permissive top-level repository licence does not answer all three questions. No candidate is approved for bundling or selected as the primary adapter.

## 2. Recovered benchmark evidence

The user supplied `D:\Voxora-TS02-Benchmark.zip`. The archive contains the three isolated projects, source files, installed package trees for Motion Canvas and Remotion, project metadata and render artifacts. It was inspected without rerunning any benchmark. The 199 MB archive and its `node_modules`/renders are audit evidence only and must not be committed into Voxora.

### 2.1 Motion Canvas

- Project manifest declares `@motion-canvas/core`, `@motion-canvas/2d`, `@motion-canvas/ui` and `@motion-canvas/vite-plugin` at `^3.17.2`; `@motion-canvas/ffmpeg` at `^1.1.0`.
- The v3 lockfile has **112 package entries** (including optional platform packages). It resolves core, 2d, ui and vite-plugin to **3.17.2**, and the FFmpeg exporter to **1.1.1**.
- Lockfile licence metadata counts: 80 MIT, 7 GPL-3.0, 6 GPLv3, 5 ISC, 5 Apache-2.0, 4 LGPL-2.1, 2 BSD-3-Clause, one BSD-3-Clause/Apache-2.0 expression, one FFmpeg licence URL and one package with no declared licence (`async@0.2.10`). Counts include optional platform-specific packages and are an inventory signal, not a legal conclusion.
- The Windows x64 installed tree contains `@ffmpeg-installer/win32-x64@4.1.0` with a 64,458,752-byte `ffmpeg.exe`, package metadata declaring **GPLv3**, and FFmpeg build identifier `20181217-f22fcd4`. It also contains `@ffprobe-installer/win32-x64@5.1.0` with an 80,995,328-byte `ffprobe.exe`, metadata declaring **GPL-3.0**, and build identifier `20230213-2296078`.
- The parent installer packages declare LGPL-2.1, but that does not replace the separate licence declarations for the platform-specific executable packages. The exporter depends on these installers. Motion Canvas' top-level MIT licence therefore does **not** clear the benchmark's Windows FFmpeg/FFprobe runtime for redistribution.
- Exact lockfile and installed package tree are recovered, but full binary build configuration, notices/source correspondence and redistribution obligations still need review. A possible alternative is to evaluate Motion Canvas without its bundled FFmpeg exporter and hand frames to Voxora's existing FFmpeg pipeline; proposal only, not approved or tested.

Upstream references: [Motion Canvas](https://github.com/motion-canvas/motion-canvas), [Video exporter documentation](https://motion-canvas.io/docs/rendering/video/), [Windows FFmpeg package metadata](https://github.com/kribblo/node-ffmpeg-installer/blob/master/platforms/win32-x64/package.json).

### 2.2 HyperFrames CLI 0.9.46

- Project scripts explicitly invoke `npx --yes hyperframes@0.9.46` for preview, check and render. This recovers the requested CLI version from the benchmark workspace.
- Its `package-lock.json` is only **147 bytes** and contains the project root entry only; it has no resolved dependency entries, tarball URL, integrity hash or dependency tree.
- No HyperFrames `node_modules` tree or npm npx cache is present in the archive. Project configuration and `.hyperframes` check/render artifacts are present, but do not identify exact downloaded package contents.
- The current official project is [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes), whose repository identifies Apache-2.0. This establishes the current upstream project's top-level licence, not the provenance or transitive/runtime closure of the exact CLI tarball used by this benchmark.
- The command pin is recovered, but exact 0.9.46 tarball integrity, immutable source commit, dependency graph, Puppeteer/browser payload, FFmpeg expectations, font and binary notices remain **unverified**. Do not substitute current npm versions for the benchmark's 0.9.46 package.

### 2.3 Remotion 4.0.543

- Project manifest pins `remotion`, `@remotion/cli`, `@remotion/three` and `@remotion/eslint-config-flat` to **4.0.543**; it also records `@react-three/fiber@9.8.2`, `three@0.182.0`, React/React DOM 19.3.1 and TypeScript 5.9.3.
- The v3 lockfile has **407 package entries**, including exact registry tarball URLs and integrity hashes. The benchmark's local Git repository records commit `36374240cba1902e8dfc2624c1b7fe85cf96b892`; it has no tags. The upstream Remotion release page identifies tag `v4.0.543` at upstream commit `4190c2a`.
- Eight lockfile entries have no declared licence metadata: seven platform compositor packages and `@remotion/media`. The installed Windows x64 compositor package contains `remotion.exe`, `ffmpeg.exe`, FFmpeg DLLs and supporting runtime DLLs, but its package metadata has no licence field and the package tree contains no licence file. The separate `@remotion/media@4.0.543` package also has no declared licence; it depends on `mediabunny@1.64.0` (MPL-2.0).
- Six Remotion packages use `SEE LICENSE IN LICENSE.md`; the installed `remotion@4.0.543` package includes the custom Free/Company License and a third-party notices file. The Free License permits eligible individuals to create commercial videos, but prohibits copying or modifying Remotion code to sell, rent, license, relicense or sublicense a Remotion derivative. Individual video-creation permission does not clear embedding or redistributing the runtime inside Voxora.
- No Chrome Headless Shell binary is present in the archive. Remotion's browser documentation says the default browser is downloaded separately; exact downloaded browser build, binary notices and redistribution terms are not established by this workspace.
- The Remotion package lock is available, but native compositor, media package and browser/runtime licensing and the product-distribution boundary remain open.

Upstream references: [Remotion v4.0.543 release](https://github.com/remotion-dev/remotion/releases/tag/v4.0.543), [Remotion licence](https://github.com/remotion-dev/remotion/blob/v4.0.543/LICENSE.md), [Chrome Headless Shell documentation](https://www.remotion.dev/docs/miscellaneous/chrome-headless-shell).

## 3. Local-first and paid-service boundary

- HyperFrames' benchmark project invokes a local CLI, and its official project documents local CLI operation with Node.js and FFmpeg alongside optional hosted workflows. The archive does not prove that exact CLI 0.9.46 performs no network calls or media uploads. Verify the pinned build with network monitoring/disabled access before adoption.
- Motion Canvas' recovered Windows exporter installation includes bundled FFmpeg and FFprobe executables. Their GPL declarations must be reviewed against Voxora's distribution model; the existing Voxora FFmpeg pipeline may offer a way to avoid bundling those binaries, but this has not been tested.
- Remotion's benchmark rendered locally using software rendering, but the default Chrome Headless Shell is a separately downloaded runtime. Local rendering does not waive licence eligibility or binary redistribution obligations.
- No candidate may introduce a mandatory subscription, paid API, hosted renderer or hidden upload into Voxora's core workflow.

## 4. Evidence status and remaining adoption gates

| Evidence | Motion Canvas | HyperFrames 0.9.46 | Remotion 4.0.543 |
|---|---|---|---|
| Project manifest / requested version | Recovered; manifest ranges plus exact lockfile versions | Recovered; CLI explicitly pinned in scripts | Recovered; exact manifest pins |
| Dependency lockfile / integrity | Recovered; 112 package entries | **Incomplete**; root-only lockfile, no package integrity/tree | Recovered; 407 package entries |
| Direct/transitive licence inventory | Lock metadata inventoried; one missing declaration; full notices/binaries still open | **Not available** without exact CLI tarball/lockfile | Lock metadata inventoried; 8 missing declarations and custom licence packages |
| Windows native binaries | FFmpeg + FFprobe present; GPLv3/GPL-3.0 metadata | Not preserved | Remotion compositor + FFmpeg/DLLs present; no package licence metadata |
| Browser/headless runtime | Not applicable to this benchmark path | Puppeteer/browser payload not preserved | Chrome Headless Shell not in archive; downloaded runtime terms/build open |
| Fonts / codecs / media assets | Font and binary provenance not fully closed | Font and runtime provenance not closed | Font, codec and browser binary provenance not closed |
| Local-only / no hidden upload | Not verified | Not verified for exact 0.9.46 | Local software render observed; separate browser download and network behavior open |
| Individual commercial video creation | Top-level MIT permits, subject to dependency terms | Apache-2.0 upstream reference; exact CLI package provenance open | Free License permits eligible individuals to create commercial videos |
| Bundling/redistribution inside Voxora | Not cleared; Windows exporter brings GPL binaries | Not cleared; exact package/runtime closure absent | Not cleared; custom licence and native/browser binaries need review |

## 5. Required next steps (no benchmark rerun)

1. Preserve the recovered manifests and lockfiles as audit evidence; do not commit the benchmark ZIP, `node_modules`, render files or user project assets into Voxora.
2. Recover exact HyperFrames 0.9.46 npm tarball metadata/integrity and immutable source revision, or record that this evidence cannot be recovered.
3. Inspect actual Motion Canvas FFmpeg/FFprobe binaries and Remotion compositor/browser binaries against upstream build configurations, source versions and licence notices.
4. Decide whether candidate adapters can emit frames/video into Voxora's existing FFmpeg pipeline without bundling candidate-specific FFmpeg binaries.
5. Verify local-only operation with network access disabled or monitored; no media upload is allowed without explicit user consent.
6. Review Remotion's Free/Company eligibility and derivative/redistribution boundary for the actual intended Voxora distribution model.
7. Keep renderer-neutral motion contracts and the existing FFmpeg pipeline available while the audit is open.

## 6. Decision

**No candidate is approved for bundling or selected as the primary framework.** The recovered workspace closes the earlier Motion Canvas and Remotion lockfile gaps, but exposes material Windows binary licensing questions: Motion Canvas' exporter installed GPLv3/GPL-3.0 FFmpeg/FFprobe binaries, while Remotion's Windows compositor package includes FFmpeg binaries without a declared package licence. HyperFrames is pinned in the benchmark command to 0.9.46, but its downloaded tarball and dependency closure were not preserved.

VXP-06.3 remains **BLOCKED** until HyperFrames package/runtime provenance, native/browser binary and font notices, local-only behavior and Remotion product-distribution eligibility (if still considered) are resolved. This audit does not reduce the permanent 2D, 2.5D, 3D, 4D/time-based 3D or Hybrid product capabilities.


## 7. HyperFrames 0.9.46 immutable upstream-source inspection (2026-11-25)

The exact upstream Git tag is now recoverable: `v0.9.46` resolves to commit `43132411c86b23a55134afaf261d77f3785168cc` in `heygen-com/hyperframes`. This is stronger source provenance than the previous unpinned current-main reference, but it does **not** prove that the npm tarball used by the benchmark was byte-for-byte built from this commit.

The tag's `packages/cli/package.json` identifies `@hyperframes/cli@0.9.46`, declares Apache-2.0, and requires Node.js >=22. Its direct runtime dependencies include `@hono/node-server`, `@puppeteer/browsers`, `puppeteer-core`, `fontkit`, `sharp` (optional), and other packages. The CLI manifest also declares internal workspace packages including core, engine, producer, parsers, lint and studio-server as development/build dependencies. The tagged producer/engine manifests additionally declare Puppeteer and Puppeteer Core dependencies. These manifests provide an auditable dependency map to investigate; they are not a resolved npm lockfile and cannot establish exact transitive versions or integrity hashes.

The official rendering guide documents local mode using Puppeteer/Chromium and the system FFmpeg, while Docker mode supplies a pinned Chrome/font environment. Therefore local operation is a supported path, but the exact 0.9.46 browser payload, FFmpeg binary expectations, font sources and network behavior still require verification. Do not assume the Docker route is suitable for the target PC or mandatory-free merely because local mode exists.

**Newly established:** immutable upstream tag/commit, exact CLI package name/version, top-level Apache-2.0 declaration, Node >=22 engine floor, and declared direct dependency families.

**Still open:** npm tarball dist.integrity and provenance attestation; exact installed package contents matching the tag; resolved transitive graph and per-package licences; bundled/downloaded Chromium and font notices; FFmpeg build/licence and whether Voxora can delegate encoding to its existing FFmpeg pipeline; network-disabled behavior; actual 8GB Windows target-PC performance.

Sources inspected: upstream tag ref and files at `v0.9.46` (commit above), `packages/cli/package.json`, `packages/producer/package.json`, `packages/engine/package.json`, and official local/Docker rendering documentation. This remains an engineering audit, not legal advice.


## 8. HyperFrames 0.9.46 runtime, privacy and font follow-up (2026-11-25)

This pass inspected additional files at immutable upstream tag v0.9.46 / commit 43132411c86b23a55134afaf261d77f3785168cc. This is source inspection only; no package was installed and no network-isolation or target-PC test was run.

### Published package and integrity boundary

- The npm package is published as unscoped hyperframes, while the source workspace manifest names @hyperframes/cli; the upstream publish workflow rewrites the package name before npm publish.
- The release workflow checks out an immutable release commit, builds the workspace, and publishes the CLI package to npm. This is useful release-process evidence, but it is not an npm provenance attestation and does not reveal the published tarball's dist.integrity.
- Public npm version history confirms hyperframes@0.9.46 was published, but the registry's version metadata/tarball integrity could not be retrieved in this inspection. The benchmark's installed tarball therefore cannot yet be cryptographically matched to the source tag.
- Source manifests identify direct dependencies, but the workspace uses internal workspace packages and caret ranges for many external dependencies. Without exact published package metadata and resolved lock data, a complete transitive licence inventory remains unavailable.

### Build-time assets and font coverage

- The CLI build runs build:fonts, build:runtime and build:copy. The copy stage includes generated runtime, Studio assets, templates, skills, player bundles, inspector runtime and GSAP vendor files. This is a wider distribution surface than the CLI manifest alone.
- The font generator embeds WOFF2 data as base64 data URIs in a generated TypeScript module. It reads selected weights from canonical @fontsource packages and explicitly selects files containing the -latin- subset.
- The inspected canonical family list includes Inter, Montserrat, Outfit, Nunito, Oswald, League Gothic, Archivo Black, Space Mono, IBM Plex Mono, JetBrains Mono, EB Garamond, Playfair Display, Source Code Pro, Noto Sans JP, Roboto, Open Sans, Lato and Poppins. It does not include a Bengali-specific family or Bengali subset in this generator.
- This does not prove Bengali rendering is impossible: user-supplied/system fonts or browser fallback may work. It means deterministic Bengali glyph coverage, shaping and font redistribution cannot be claimed from the bundled canonical font set. Bengali যুক্তাক্ষর/কারচিহ্ন must be tested with an explicit font path and its licence/notice.
- Exact generated font files and applicable per-font licence/notice texts were not available in the recovered benchmark archive. Do not assume every embedded font has the same licence merely because the CLI declares Apache-2.0.

### Network and privacy behavior observed in source

- Production defaults set telemetryEnabled=true. Normal CLI startup shows a first-run telemetry disclosure, tracks command/system metadata, and queues events to PostHog at https://us.i.posthog.com/batch/. Payload properties include CLI version, OS/architecture, Node version, CPU count/model, total memory, CI/WSL/agent runtime metadata and command/render event properties. The source sets $ip=null in the event payload.
- The first-run disclosure says usage data is collected; source comments/docs state paths and composition content are not collected. After HeyGen sign-in, events can be linked to the HeyGen username/account; the first-run notice warns that account email and username are linked.
- Telemetry opt-outs exist through HYPERFRAMES_NO_TELEMETRY=1, DO_NOT_TRACK=1, or the hyperframes telemetry disable preference. These controls disable telemetry specifically; they are not equivalent to a network-disabled build.
- The normal CLI path also checks the npm registry for updates (two-hour cache in this tag's source). HYPERFRAMES_NO_UPDATE_CHECK=1 is an opt-out. Background auto-install has additional guards and is skipped for unattended/CI runs, but the update-check path itself is a separate outbound request.
- The browser manager can download a managed Chrome Headless Shell when no suitable cached/system browser is available. This is an explicit external runtime download path; it must be provisioned and pinned or disabled/redirected for a strict offline installation.
- The inspected engine network policy blocks selected private/local address ranges for certain fetch/capture paths. That is not a global egress-deny policy and does not establish offline operation.

Adoption implication: unmodified production CLI behavior is not a no-network default. A Voxora adapter would need explicit opt-outs plus a verified runtime/browser provisioning strategy, or a narrowly scoped integration that excludes telemetry/update/publish/cloud features. No hidden upload can be permitted in Voxora's core workflow.

### Updated evidence status

| Gate | New evidence | Status |
|---|---|---|
| Immutable source | Tag resolves to exact source commit | Established |
| npm package identity | Publish workflow rewrites source package name to hyperframes; version is listed publicly | Partial |
| npm tarball integrity/provenance | Registry metadata and tarball integrity unavailable in this pass | Open |
| Direct/transitive dependency closure | Source manifests identify direct families; no exact resolved published graph | Open |
| Bundled font assets | Generator embeds selected Latin WOFF2 subsets from Fontsource packages | Partial |
| Font licence notices | Exact generated files and notices not preserved | Open |
| Bengali typography | No Bengali family/subset in canonical embedded list; fallback behavior untested | Open |
| Telemetry/privacy | Production default enabled; explicit opt-outs; signed-in identity linkage documented | Established from source |
| Update network calls | npm registry background check present; opt-out exists | Established from source |
| Browser provisioning | Managed Chrome download path present | Established from source |
| Strict offline operation | No global egress-deny evidence or isolated run | Open |
| Target PC performance | Not tested on 8GB Windows target | Open |

Source files inspected at the immutable tag include packages/cli/package.json, packages/cli/scripts/build-fonts.mjs, packages/cli/scripts/build-runtime.ts, packages/cli/scripts/build-copy.mjs, packages/core/scripts/generate-font-data.ts, packages/core/package.json, packages/cli/src/telemetry/client.ts, packages/cli/src/telemetry/config.ts, packages/cli/src/telemetry/policy.ts, packages/cli/src/telemetry/transport.ts, packages/cli/src/utils/updateCheck.ts, packages/cli/src/utils/autoUpdate.ts, packages/cli/src/browser/manager.ts, and packages/engine/src/utils/networkPolicy.ts. Public npm version history and official CLI documentation were also checked. This remains an engineering audit, not legal advice.
