# TS-02 — HyperFrames v0.9.46 npm Registry & Published-Archive Verification

> Audit date: 2026-11-25  
> Source ref: `heygen-com/hyperframes@v0.9.46`  
> Registry package: `hyperframes@0.9.46` (the monorepo CLI is renamed before publish)  
> Result: **REGISTRY METADATA AND EXACT PUBLISHED TARBALL SHA-512 VERIFIED; SIGNATURE/RAW ATTESTATION AND REDISTRIBUTION CLOSURE STILL OPEN.**  
> This is an evidence record, not a framework selection or legal opinion.

## 1. Source-level facts verified against the immutable upstream tag

The following files were inspected directly at the `v0.9.46` tag:

- [CLI package manifest](https://github.com/heygen-com/hyperframes/blob/v0.9.46/packages/cli/package.json)
- [Publish workflow](https://github.com/heygen-com/hyperframes/blob/v0.9.46/.github/workflows/publish.yml)
- [Font data generator](https://github.com/heygen-com/hyperframes/blob/v0.9.46/packages/core/scripts/generate-font-data.ts)
- [CLI build-copy script](https://github.com/heygen-com/hyperframes/blob/v0.9.46/packages/cli/scripts/build-copy.mjs)

Findings:

1. The source manifest is named `@hyperframes/cli`, version `0.9.46`, Apache-2.0, Node `>=22`, with package files allowlisted as `bin` and `dist`.
2. Immediately before publication, the workflow rewrites the manifest name to the unscoped `hyperframes` and runs `npm publish --access public --tag "$DIST_TAG"`.
3. The publish job declares `id-token: write`, but the visible publish command does not pass `--provenance`.
4. npm trusted publishing can generate provenance automatically without the flag when trusted publishing is configured. The source workflow alone does not establish whether the npm package's trusted-publisher configuration was enabled for this exact version.
5. The font generator embeds selected WOFF2 files as base64 data URIs. The generated file records keys and font data, not per-font copyright/licence notices.
6. The inspected CLI build-copy script copies selected runtime assets, docs, templates, skills and other files. It has no explicit step copying the 18 Fontsource packages' OFL notice files into the CLI distribution.
7. These are source-build findings only. They do not establish the exact contents of the published npm tarball.

## 2. Registry metadata retrieval result

The exact public registry version endpoint is:

`https://registry.npmjs.org/hyperframes/0.9.46`

The endpoint could not be retrieved by the available audit access path during this review. Consequently, no authoritative version-specific registry JSON was captured.

| Required evidence | Result |
|---|---|
| `dist.tarball` URL | **NOT CAPTURED** |
| `dist.integrity` SHA-512 | **NOT CAPTURED** |
| `dist.signatures` ECDSA signature and key ID | **NOT CAPTURED** |
| npm publish attestation | **NOT CAPTURED** |
| Sigstore/SLSA provenance subject digest and workflow identity | **NOT CAPTURED** |
| Published tarball SHA-512 independently recomputed | **NOT PERFORMED** |

Do not infer that signatures or provenance are absent. A workflow with `id-token: write` and no explicit `--provenance` is compatible with trusted publishing, but it is not proof that the package was configured for it.

npm documents that registry signatures cover the package name, version and tarball integrity, while provenance provides build/source identity evidence. These are distinct checks; neither proves that package code is safe.

References:
- [npm registry metadata format](https://github.com/npm/registry/blob/main/docs/responses/package-metadata.md)
- [npm registry signatures](https://docs.npmjs.com/about-registry-signatures/)
- [Verifying registry signatures](https://docs.npmjs.com/verifying-registry-signatures/)
- [Viewing package provenance](https://docs.npmjs.com/viewing-package-provenance/)
- [Generating provenance statements and trusted publishing](https://docs.npmjs.com/generating-provenance-statements/)

## 3. Published tarball and font-notice verification

The prior source audit classified all 18 locked Fontsource families as OFL-1.1 and identified a source-level notice-closure gap. The exact published CLI archive has still not been downloaded or inspected.

Therefore:

- **SOURCE-LEVEL GAP:** confirmed — the reviewed build-copy path has no explicit per-font notice-copy step.
- **PUBLISHED-ARCHIVE GAP:** unverified — the exact npm tarball has not been inspected, so no claim is made about its actual file list.
- **Font package notices:** exact 18 npm package archives have not been downloaded and checked for notice files.
- **Redistribution clearance:** remains blocked until actual archive contents and required notices are verified and corrected/cleared.

The 18 locked package/version pairs are recorded in [CINEMATIC_SKILL_AUDIT.md](./CINEMATIC_SKILL_AUDIT.md). They must be checked at those exact versions, not against current Fontsource releases.

## 4. Reproducible verification commands for a network-enabled audit workstation

Run these commands in a clean temporary PowerShell directory with Node/npm installed. They do not change Voxora source files.

```powershell
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force .\hyperframes-0.9.46-audit | Out-Null
Set-Location .\hyperframes-0.9.46-audit

# Capture exact registry metadata, including dist.integrity and signatures.
npm view hyperframes@0.9.46 --json |
  Set-Content -Encoding utf8 .\hyperframes-0.9.46.registry.json

npm view hyperframes@0.9.46 dist --json |
  Set-Content -Encoding utf8 .\hyperframes-0.9.46.dist.json

# Download the exact published archive without running package scripts.
npm pack hyperframes@0.9.46 --ignore-scripts

# List and extract the archive for notice inspection.
tar -tf .\hyperframes-0.9.46.tgz |
  Set-Content -Encoding utf8 .\hyperframes-0.9.46.files.txt

New-Item -ItemType Directory -Force .\unpacked | Out-Null
tar -xzf .\hyperframes-0.9.46.tgz -C .\unpacked

# Inspect package metadata and all bundled licence/notice files.
Get-Content .\unpacked\package\package.json
Get-ChildItem .\unpacked\package -Recurse -File |
  Where-Object { $_.Name -match '^(LICENSE|LICENCE|NOTICE|COPYING)(\.|$)' } |
  Select-Object -ExpandProperty FullName
```

Then, in a separate clean npm project, install the exact version and verify npm's registry signatures/provenance with a modern npm CLI (npm 9.5.0 or later):

```powershell
New-Item -ItemType Directory -Force .\signature-check | Out-Null
Push-Location .\signature-check
npm init -y
npm install --ignore-scripts --save-exact hyperframes@0.9.46
npm audit signatures
Pop-Location
```

A successful signature audit must be preserved with its npm version, command output and timestamp. If npm reports a missing attestation, record that exact result; do not infer it from the source workflow. Separately compare the tarball's computed SHA-512 with the registry `dist.integrity` value.

For each of the 18 Fontsource packages listed in the master audit, retrieve the exact locked package version and inspect its archive for the font copyright notice and OFL text. Record the archive SHA-512 and the notice paths. Do not mark the font redistribution gate cleared based only on the package manifest's `license` field.

## 5. Gate status and decision

| Gate | Status |
|---|---|
| Immutable v0.9.46 source publish workflow | **SOURCE VERIFIED** |
| Exact registry tarball URL/integrity | **NOT VERIFIED** |
| npm ECDSA registry signature | **NOT VERIFIED** |
| npm provenance attestation | **NOT VERIFIED** |
| Exact published CLI tarball contents | **NOT VERIFIED** |
| Exact 18 Fontsource package notice files | **NOT VERIFIED** |
| Source-level font notice-copy gap | **CONFIRMED** |
| HyperFrames redistribution clearance | **BLOCKED** |
| TS-02 primary framework selection | **NOT SELECTED** |

No framework has been selected. No HyperFrames package was installed, no npm tarball was downloaded, and no Voxora runtime/source code was changed in this audit. The next evidence step is to run the reproducible commands from a network-enabled workstation and attach the raw outputs/archive hashes to the decision record.


## 6. User-supplied registry and published-archive evidence — 2026-11-27

The user supplied `HyperFrames-Audit.zip`, containing the exact `hyperframes-0.9.46.tgz`, version-specific `registry.json`, an npm lockfile and the installed Windows `node_modules` tree. The archive was inspected without installing or executing HyperFrames and without rerunning the TS-02 benchmark.

### 6.1 Registry identity and integrity — VERIFIED

Captured from the supplied version-specific registry metadata:

- Package/version: `hyperframes@0.9.46`.
- Registry tarball URL: `https://registry.npmjs.org/hyperframes/-/hyperframes-0.9.46.tgz`.
- Registry `dist.integrity`: `sha512-Izx/LaXc2dxpKQli0AzWkAGKJ8tp2RI3gMcuWnYYDPhXSaMnA98TsgTMQqRIzexyPABvwnl5BJ05f+zlOnUHKQ==`.
- Independently computed SHA-512 of the supplied 8,233,504-byte tarball: **exact match**.
- Registry SHA-1: `d18f36f71a662c6b8b343d4791d7b8525b7ce93a`; independently computed SHA-1: **exact match**.
- Registry file count: 774; inspected tar archive regular-file count: **774**.
- Registry `gitHead`: `43132411c86b23a55134afaf261d77f3785168cc`, matching the immutable upstream v0.9.46 source commit already audited.
- Registry metadata identifies the publisher as `GitHub Actions <npm-oidc-no-reply@github.com>`, npm `11.19.1`, Node `24.22.2`.

This establishes that the supplied tarball bytes match the version-specific registry integrity metadata and that the registry source commit matches the audited upstream tag.

### 6.2 Registry signatures and provenance — METADATA PRESENT; CRYPTOGRAPHIC VERIFICATION OPEN

- `dist.signatures` contains **two signature records**, both carrying key ID `SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U`.
- `dist.attestations` contains the version-specific npm attestations endpoint and declares predicate type `https://slsa.dev/provenance/v1`.
- The ZIP does not contain the output of `npm audit signatures` or the raw attestation response. Therefore the signature records are captured from registry metadata, but their cryptographic verification and the SLSA provenance statement's subject/workflow identity are **NOT YET VERIFIED**.
- Do not describe signatures or provenance as absent.

### 6.3 Published archive and font notices — ARCHIVE GAP CONFIRMED

The exact published tarball contains 774 files and was inspected directly:

- The bundled generated font-data chunk contains embedded data entries for all **18** locked Fontsource families: Archivo Black, EB Garamond, IBM Plex Mono, Inter, JetBrains Mono, Lato, League Gothic, Montserrat, Noto Sans JP, Nunito, Open Sans, Oswald, Outfit, Playfair Display, Poppins, Roboto, Source Code Pro and Space Mono.
- The archive contains only **three** matching per-family OFL notice files: EB Garamond, Inter and JetBrains Mono. It also contains six standalone WOFF2 files for those same three families.
- The other **15 embedded Fontsource families have no corresponding per-family OFL notice file** in the published archive.
- No package-root `LICENSE`, `LICENCE`, `NOTICE` or `COPYING` file is present, although the package manifest declares Apache-2.0. The archive does contain a separate Unicode contract licence file; that does not replace the package's Apache licence text or the missing font notices.

This upgrades the earlier source-level finding: the per-font notice gap is now confirmed in the **published npm archive itself**, not merely inferred from the build-copy source.

### 6.4 npm dependency lock and Windows native payload — INVENTORIED; REDISTRIBUTION REVIEW OPEN

- The supplied npm lockfile uses lockfile version 3 and contains 127 package records including the root package (126 dependency records).
- All 126 dependency records have a declared licence field in the lock metadata. The inventory includes MIT, Apache-2.0, ISC, BSD-3-Clause, CC0-1.0, 0BSD, LGPL-3.0-or-later and combined licence expressions.
- The installed Windows x64 tree includes optional `sharp@0.35.5` and `@img/sharp-win32-x64@0.35.5`, including native `.node` and libvips DLL files. Its package metadata declares `Apache-2.0 AND LGPL-3.0-or-later`; its included `LICENSE` file is Apache-2.0 text. The LGPL component and the precise optional-runtime distribution boundary still need review before bundling.
- The CLI package manifest declares Node.js `>=22` and external FFmpeg as a requirement in its README. No FFmpeg binary was found in the npm tarball file list.

The lockfile inventory is not a complete legal clearance of every dependency or native binary.

### 6.5 Updated gate status

| Gate | Updated result |
|---|---|
| Exact registry package/version and tarball URL | **VERIFIED** |
| Registry SHA-512 vs supplied tarball | **VERIFIED — exact match** |
| Registry SHA-1 vs supplied tarball | **VERIFIED — exact match** |
| Immutable source commit identity | **VERIFIED — gitHead matches v0.9.46 source commit** |
| Registry signature records | **PRESENT IN METADATA; npm cryptographic audit output not supplied** |
| SLSA provenance | **ATTESTATION ENDPOINT/PREDICATE PRESENT; raw statement not verified** |
| Exact published tarball contents | **VERIFIED — 774 files inspected** |
| Embedded 18-family font set | **VERIFIED IN ARCHIVE** |
| Per-font OFL notices | **BLOCKED — only 3 of 18 corresponding notices present** |
| Package Apache-2.0 licence text | **BLOCKED — no package-root licence/notice file in archive** |
| npm dependency lock | **INVENTORIED — 126 dependency records** |
| Windows sharp/libvips native dependency | **PRESENT; LGPL component review open** |
| Telemetry/update opt-out, pre-provisioned browser, offline render | **NOT VERIFIED** |
| Target-PC resource/performance/cancellation | **NOT VERIFIED** |
| HyperFrames redistribution clearance / VXP-06.3 | **BLOCKED — do not bundle or integrate yet** |

### 6.6 Evidence boundary

No HyperFrames command was executed from the supplied installation. No network-isolated render, target-PC performance test, browser acquisition test or cancellation test was performed. The archive inspection does not clear the font, Apache package licence, LGPL/native dependency, browser or FFmpeg redistribution obligations. HyperFrames remains the preferred lead for gated evaluation only; no framework winner is selected.
