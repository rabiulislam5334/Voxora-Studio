# TS-02 — HyperFrames v0.9.46 embedded-font notice closure

> Status: **BLOCKED — exact source lock and package integrity pins are recovered; redistribution notice closure is not satisfied.**
> Audit date: 2026-11-27.
> Scope: the 18 Fontsource packages pinned by the immutable HyperFrames v0.9.46 source lock, and their embedding into the published `hyperframes@0.9.46` CLI archive.
> This is an engineering evidence record, not legal advice.

## 1. Decision

Do not clear HyperFrames for Voxora bundling or redistribution yet.

The user-supplied published CLI archive was independently matched to npm registry SHA-512/SHA-1 metadata and inspected as 774 regular files. That archive contains embedded font data for 18 Fontsource families but only **3 matching per-family OFL notices**. Therefore **15 of 18 required per-family notices are not present in the inspected archive**. The archive also has no package-root Apache-2.0 licence text. The prior archive inspection did not preserve the filenames/family mapping for the three notices, so this record deliberately does not guess which three are present.

The immutable upstream v0.9.46 `bun.lock` identifies all 18 exact package versions and SHA-512 package integrity values. The corresponding family/package licence classification is OFL-1.1 in the existing source audit. The source generator embeds WOFF2 bytes, while the reviewed CLI build-copy script and package allowlist do not copy the per-font notices.

This is a **redistribution packaging gap**, not a finding that OFL fonts cannot be embedded or commercially used. Do not silently treat the top-level Apache-2.0 declaration as a substitute for the font licences.

## 2. Exact upstream lock evidence

Source: [heygen-com/hyperframes v0.9.46 bun.lock](https://github.com/heygen-com/hyperframes/blob/v0.9.46/bun.lock), immutable source commit `43132411c86b23a55134afaf261d77f3785168cc`.

| Fontsource package | Exact version | SHA-512 from upstream lock |
|---|---:|---|
| `@fontsource/archivo-black` | 5.2.8 | `3zNj/o9LzWyDl/UEpY5IOHpAQyUtFr3hQaFS7NSKwCLLkXOfH/CMCt1L2b2Z+OF25OURtOYenCadgAebALz7/A==` |
| `@fontsource/eb-garamond` | 5.2.7 | `V42tTlHDbnDo0+lENnXKWMx63Llq6Gfl2l7ozkoeRQN60S0jm6hEgCLlOT/5YyKAN9QZ0e2ofpy0rGKlz9jBrw==` |
| `@fontsource/ibm-plex-mono` | 5.2.7 | `MKAb8qV+CaiMQn2B0dIi1OV3565NYzp3WN5b4oT6LTkk+F0jR6j0ZN+5BKJiIhffDC3rtBULsYZE65+0018z9w==` |
| `@fontsource/inter` | 5.2.8 | `P6r5WnJoKiNVV+zvW2xM13gNdFhAEpQ9dQJHt3naLvfg+LkF2ldgSLiF4T41lf1SQCM9QmkqPTn4TH568IRagg==` |
| `@fontsource/jetbrains-mono` | 5.2.8 | `6w8/SG4kqvIMu7xd7wt6x3idn1Qux3p9N62s6G3rfldOUYHpWcc2FKrqf+Vo44jRvqWj2oAtTHrZXEP23oSKwQ==` |
| `@fontsource/lato` | 5.2.7 | `k5mum1ADbDW5cTw1Ett1eQVWeoZ6gq0ct6SFBibEhB4LRxhniChJZTBgd6ph5yBxLkN1fcnsnmicBNA4S/3nbw==` |
| `@fontsource/league-gothic` | 5.2.8 | `xxu2kSPrZZZG2Gq+M75/4J5q0PWUshfgk4tH09mvMrmNzS6izlDRWVU4W+OFCf+3Hb22PswB4vJOr/PUUDpWCw==` |
| `@fontsource/montserrat` | 5.2.8 | `xTjLxSbSfCycDB0pwmNsfNvdfWPaDaRQ2LC6yt/ZI7SdvXG52zHnzNYC/09mzuAuWNJyShkteutfCoDgym56hQ==` |
| `@fontsource/noto-sans-jp` | 5.2.9 | `6yVGiofnrnbiJjU8ch4JGSs2HqyozxMvsVyVmFwOnDH3u//qQKLqmKM4n0lqN0637uaJNzUW9nIJqbbMgHVQzw==` |
| `@fontsource/nunito` | 5.2.7 | `pmtBq0H9ex9nk+RtJYEJOD9pag393iHETnl/PVKleF4i06cd0ttngK5ZCTgYb5eOqR3Xdlrjtev8m7bmgYprew==` |
| `@fontsource/open-sans` | 5.2.7 | `8yfgDYjE5O0vmTPdrcjV35y4yMnctsokmi9gN49Gcsr0sjzkMkR97AnKDe6OqZh2SFkYlR28fxOvi21bYEgMSw==` |
| `@fontsource/oswald` | 5.2.8 | `DFoPK1BqsFIQhVjs2xgO/oL9veF9oUJgFojEWIU+nazUrfqsBDtAMI4n9L9CZFX3kQNDLcCyzKx1xoEDvQT4WQ==` |
| `@fontsource/outfit` | 5.2.8 | `rXC6g0MqD7cOBjht0bMqc43qM6lRqDLML9KXsmg9uykz0wLQhy8Z/ajrMG6iyoT3NJR+MYgU+OEHp7uHoTb+Yw==` |
| `@fontsource/playfair-display` | 5.2.8 | `fUEhib70SszNhQVsGbUMSsWJhr7Je0rdeuZdtGpDNu0GKF1xJM8QhpI/y0pckU25GcChXm9TLOmeZupkvvZo2g==` |
| `@fontsource/poppins` | 5.2.7 | `6uQyPmseo4FgI97WIhA4yWRlNaoLk4vSDK/PyRwdqqZb5zAEuc+Kunt8JTMcsHYUEGYBtN15SNkMajMdqUSUmg==` |
| `@fontsource/roboto` | 5.2.10 | `8HlA5FtSfz//oFSr2eL7GFXAiE7eIkcGOtx7tjsLKq+as702x9+GU7K95iDeWFapHC4M2hv9RrpXKRTGGBI8Zg==` |
| `@fontsource/source-code-pro` | 5.2.7 | `7papq9TH94KT+S5VSY8cU7tFmwuGkIe3qxXRMscuAXH6AjMU+KJI75f28FzgBVDrlMfA0jjlTV4/x5+H5o/5EQ==` |
| `@fontsource/space-mono` | 5.2.9 | `b61faFOHEISQ/pD25G+cfGY9o/WW6lRv6hBQQfpWvEJ4y1V+S4gmth95EVyBE2VL3qDYHeVQ8nBzrplzdXTDDg==` |

These are SHA-512 package-integrity values from the immutable upstream Bun lock. They are not hashes of the HyperFrames CLI tarball and must not be conflated with its npm `dist.integrity`.

## 3. Evidence boundaries

| Item | Finding | Status |
|---|---|---|
| Exact 18 package names and versions | Present in v0.9.46 lock | SOURCE VERIFIED |
| Exact package SHA-512 integrity pins | Present in v0.9.46 lock | SOURCE VERIFIED |
| Font licence family classification | Existing audit classifies 18/18 as OFL-1.1 | SOURCE AUDIT VERIFIED |
| Embedded font data in published CLI archive | 18 families observed | ARCHIVE VERIFIED |
| Per-family notices in published CLI archive | 3 matching notices observed; exact family mapping not recorded | PARTIAL |
| Missing per-family notices | 15 of 18 not present in inspected archive | ARCHIVE GAP VERIFIED |
| Root Apache-2.0 licence text | Absent from inspected CLI archive | ARCHIVE GAP VERIFIED |
| Exact original npm font package archives re-extracted and independently hashed in this pass | Not performed | OPEN |
| Corrected HyperFrames build/archive with complete notices | Not available | NOT VERIFIED |

Do not invent the identity of the three notices found in the archive. Re-extract the user-supplied exact `hyperframes-0.9.46.tgz` and retain a machine-readable mapping before claiming any individual family is already covered.

## 4. Required remediation before redistribution

Preferred upstream/build remediation (not implemented or approved here):

1. In a clean, pinned build, obtain each exact package artifact listed in §2 and verify its SHA-512 against the lock value before reading any notice.
2. Extract the font's original copyright/author attribution and complete OFL-1.1 text from that exact package archive. Do not generate copyright lines from family names or copy a current-version notice.
3. Produce a deterministic third-party font notice directory in the CLI distribution containing one clearly identified notice per embedded family. Retain the exact upstream copyright text, OFL version and any Reserved Font Name clauses.
4. Include the package-root Apache-2.0 licence text separately; it does not replace the 18 font notices.
5. Add a build-time test that fails if any embedded font family lacks its corresponding notice, or if an untracked font is added to the generated font data.
6. Build a new versioned CLI archive. Inspect the final archive, enumerate all embedded font families and notices, and verify 18/18 coverage. Preserve its SHA-512, file list and build/source identity.
7. Review any font modification/subsetting/renaming against OFL-1.1 and Reserved Font Name conditions. Do not assume that copying notices alone resolves a modified-font issue.

If upstream will not provide a corrected archive, the alternative is to remove the embedded Fontsource font payload from the candidate build and use a separately reviewed font strategy. That alternative has not been tested and may change rendering/typography; it is not a drop-in assumption.

## 5. Reproducible acceptance checks

A future corrected candidate must pass all of these checks:

- [ ] Each of the 18 package tarballs matches the exact SHA-512 in §2.
- [ ] Each exact archive contains its own attributable copyright notice and complete OFL-1.1 text.
- [ ] A one-to-one mapping exists: embedded family → exact package/version → copyright notice → licence text.
- [ ] The final HyperFrames archive includes all 18 notices and the package-root Apache-2.0 text.
- [ ] The final archive contains no embedded font family without a matching notice.
- [ ] Any modified font preserves OFL conditions and Reserved Font Name restrictions.
- [ ] CI has a deterministic notice-coverage test.
- [ ] The final archive file list and SHA-512 are recorded in the audit.

Until then, the font redistribution gate remains **BLOCKED** and VXP-06.3 remains **BLOCKED**. This documentation-only increment does not select HyperFrames, add a dependency, change Voxora runtime code, or authorize bundling.

## 6. References

- [HyperFrames v0.9.46 immutable bun.lock](https://github.com/heygen-com/hyperframes/blob/v0.9.46/bun.lock)
- [HyperFrames v0.9.46 font generator](https://github.com/heygen-com/hyperframes/blob/v0.9.46/packages/core/scripts/generate-font-data.ts)
- [HyperFrames v0.9.46 CLI build-copy script](https://github.com/heygen-com/hyperframes/blob/v0.9.46/packages/cli/scripts/build-copy.mjs)
- [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/)
- [Fontsource licensing policy](https://github.com/fontsource/fontsource#licensing)
- [Existing Voxora archive/provenance audit](./TS-02_HYPERFRAMES_REGISTRY_ARCHIVE_AUDIT.md)
