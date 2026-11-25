# TS-02 — HyperFrames v0.9.46 npm Registry & Published-Archive Verification

> Audit date: 2026-11-25  
> Source ref: `heygen-com/hyperframes@v0.9.46`  
> Registry package: `hyperframes@0.9.46` (the monorepo CLI is renamed before publish)  
> Result: **SOURCE WORKFLOW VERIFIED; REGISTRY METADATA AND PUBLISHED TARBALL NOT VERIFIED.**  
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
