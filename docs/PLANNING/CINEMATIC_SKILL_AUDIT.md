# Cinematic Skill — Voxora Source Audit

> Audit status: PRELIMINARY SOURCE AUDIT COMPLETE; dependency/legal and target-PC acceptance remain OPEN.
> Audited upstream: [Moh4696/cinematic-skill](https://github.com/Moh4696/cinematic-skill)
> Audited ref: `main` at `bf435561c6203f90f971300efe952b68b5ec3417` (2026-11-20)
> Voxora planning branch: `docs/master-planning-source-of-truth`

## 1. Executive decision

**Recommendation: continue to a narrow, isolated Voxora adapter/prototype. Do not vendor or install the complete skill as-is, and do not call it production-integrated.**

The upstream is a real code-driven rendering toolkit wrapped as an agent skill. Its core is a Python/Skia scene engine that draws a designed 2D world (photos, clippings, documents, cards, maps, counters, stamps and routes) under one continuous animated camera, with spotlighting, film finish and word-cued visual events. It is especially relevant to Voxora's documentary, history, biography, investigation, invention and explainer styles.

It is **not** a general-purpose 2D cartoon/character animation system, a photorealistic video generator, or a drop-in replacement for Voxora's Universal Core / AI Production Director / Render Orchestrator. It must be treated as one specialized visual-production adapter.

## 2. Source and licence findings

- Upstream root contains `LICENSE`, `README.md`, `requirements.txt`, plugin manifests, installer, examples, tests, and `skills/cinematic-film/`.
- The checked-in `LICENSE` is the MIT License, copyright 2026 exploraX. It permits commercial use, modification and redistribution subject to retaining the copyright and permission notice. This is a positive repository-level finding, not clearance of every dependency or asset.
- The Python runtime requirements listed are `skia-python>=87.6`, `numpy>=1.24`, `pillow>=10`, and optional `scipy>=1.10`. FFmpeg/FFprobe with libx264, loudnorm and sidechaincompress are external runtime requirements.
- There is no pinned dependency lockfile in the inspected root listing. Exact resolved versions, transitive dependencies, binary wheel notices and each dependency's licence still require a separate audit before redistribution.
- `get_fonts.py` downloads Bebas Neue (SIL Open Font License 1.1) and Homemade Apple (Apache License 2.0) from Google Fonts and writes licence notes. Keep those notices if the fonts are used or redistributed; do not assume all system fonts are redistributable.
- The Wikimedia Commons fetcher records source/credit/licence and refuses files outside its accepted public-domain, CC0, CC BY and CC BY-SA patterns by default. Each acquired image's individual file page and licence must still be checked. Arbitrary URL imports rely on user-supplied rights metadata.
- The repository does not bundle an AI model or require a paid AI API for its core code-rendering path. AI stills and a music score are optional inputs. The README mentions a separate `motion-assets` skill for planning/pricing AI stills; that optional workflow is not approved as a Voxora dependency and must not be used if it introduces paid services.
- Scratch narration can use macOS `say`, Linux `espeak-ng`, or a supplied command-line TTS. Final narration may be recorded or produced by any TTS. Voxora should use the user's already-supplied narration and must not make a new TTS provider mandatory.
- The installer documents Node 22.20+ for the `npx skills` route; the shell installer needs Bash and Git. Neither installer is required for source reuse. The user's Node 22.17.0 is below that stated npx version, so do not make the npx installer the integration route.

**Licence gate:** repository MIT status is provisionally acceptable, but the candidate remains **NOT CLEARED FOR DISTRIBUTION** until direct/transitive dependency, Skia binary, FFmpeg build, fonts and any selected media/assets are audited for the exact versions and packaging model. No purchase or paid service is permitted.

## 3. Verified capabilities in source

| Capability | Source evidence | Voxora relevance |
|---|---|---|
| Skia CPU raster scene engine | `scripts/engine.py` | Reusable drawing and composition primitives |
| Continuous camera, monotone spline, zoom, rotation, drift and motion blur | `engine.py`, `references/film.md` | Cinematic movement across designed 2D scenes |
| Spotlight follows camera; per-item bounds/culling and cached vector art | `engine.py` | Visual focus and performance techniques |
| Seven visual looks: wall, slate, charcoal, paper, studio, blueprint, night | `engine.py` | Style starting points; not a substitute for Voxora channel profiles |
| Prints, document recreations, cards, counters, stamps, pen marks, strings, maps, routes, pins, dot fields | `engine.py`, `references/film.md` | Documentary, map, infographic and explainer scenes |
| Line/word cue API (`doc.L`, `doc.E`, `doc.W`) | `engine.py` | Narration-synchronised visual events |
| Beat-table generation and chronology lint | `scripts/make_beats.py` | Could inform a reviewable Director plan |
| Wikimedia Commons retrieval and credits | `scripts/fetch_commons.py` | Documentary media acquisition pattern |
| Procedural image grading and board textures | `scripts/prep_assets.py` | Consistent visual treatment |
| Procedural sound-effect synthesis | `scripts/build_sfx.py` | Optional non-sampled SFX generation |
| Voice/effects/music mix with sidechain ducking and loudness normalisation | `scripts/mix_soundtrack.py` | Sound-design reference; Voxora audio contracts remain authoritative |
| Four caption styles and SRT output | `scripts/captions.py`, `scripts/burn_captions.py` | Caption design reference; multilingual support needs testing |
| Still probes, contact strips, cue list and parallel MP4 render | `scripts/render.py` | Review/QC and render implementation reference |

## 4. Important mismatches and risks

### 4.1 Supplied narration audio contract

Upstream's normal path is not a single finished narration file. It expects:
1. `script.json` divided into takes and short lines.
2. A separate WAV recording for each take under `audio/takes/`.
3. `split_takes.py` to detect pauses and split each take into per-line clips.
4. `build_narration.py` to trim, tempo-fit (0.90–1.15x), concatenate and create its own narration track and `timing.json`.

Voxora already receives a complete narration audio file. The adapter must **import and preserve that file as the master**, derive or ingest word/line timestamps, and build the timing structure expected by the scene engine. Do not force the user to re-record line-by-line, and do not silently tempo-change or replace the supplied narration.

### 4.2 Word timing is approximate in the current engine

`Doc.W()` locates a word in the line's spoken text and estimates its time by the word's letter share across the line duration, plus a small offset. It is not true forced alignment or a measured word timestamp. The current implementation strips non-ASCII letters for its calculation. Bengali/Arabic/mixed-script timing therefore cannot be assumed correct.

For Voxora, provide an adapter that consumes actual word timestamps from Voxora's narration-analysis/alignment layer when available. Preserve a clearly marked approximate fallback only where exact alignment is unavailable. Bengali and Arabic need separate Unicode-aware timing and typography acceptance.

### 4.3 Creative scope

The core visual metaphor is a single designed board/world with a continuous camera. Its animation is primarily camera choreography, item entrances/exits, text, maps, marks and layered graphics over stills. It does not provide full character rigs, frame-by-frame cartoon acting, lip-sync, a general 2D animation timeline, or a 3D animation system. It can complement but cannot replace Voxora's Cartoon/Character and broader motion engines.

### 4.4 Hardware and rendering

Upstream's own performance guide reports approximate per-worker memory of 0.6 GB at 720p, 0.9 GB at 1080p, 1.3 GB at 1440p and 2 GB at 4K on its reference setup, and recommends memory-aware worker counts. Its 92-second 1080p example is reported at about six minutes on a 16 GB laptop. These are upstream-reported figures, not measurements on Voxora's Windows 10 / i5-8250U / 8 GB / NVIDIA 940MX machine. Initial integration should use one worker, 720p/1080p draft settings, strict memory limits and measured target-PC acceptance.

### 4.5 External services and assets

Core rendering can run without a paid AI endpoint. Do not adopt optional AI-image/music workflows that require payment, credits or a hosted subscription. Do not treat the sample project's rendered screenshots or external archive media as automatically cleared for redistribution. Maintain Voxora's asset provenance and per-file rights metadata.

## 5. Recommended Voxora integration boundary

**Reuse/adapt selectively; do not embed the agent workflow as the runtime.**

1. Keep Voxora Script Intelligence, channel profiles, ProjectSession, asset registry, narration audio, job system, Render Orchestrator, audio mixer and FFmpeg final assembly as the single source of truth.
2. Add a renderer adapter around the reusable Skia engine, with a Voxora-owned input contract: immutable scene/shot plan + narration timing + approved assets + channel style + output settings.
3. Map Voxora scene/shot events to upstream item primitives (cards, prints, labels, counters, maps, routes, highlights, camera keys and spotlight).
4. Replace the upstream per-take narration builder dependency with an adapter that reads Voxora's supplied audio and actual timing data. The renderer should emit silent video or a video stream that Voxora's existing FFmpeg pipeline muxes with the original narration and optional audio mix.
5. Port only required source modules and their MIT notice; keep upstream attribution and a third-party notices record. Avoid duplicating the upstream project folder structure, audio pipeline, asset registry or final mux.
6. Keep media acquisition provider-neutral. Wikimedia Commons is one optional source; all downloaded files must pass Voxora's own source, licence and provenance validation.
7. Expose this as one visual engine capability selected by the AI Production Director, not a separate editor or a mandatory workflow for every channel.

## 6. Prototype acceptance plan

The next implementation slice should be an isolated vertical prototype, not a broad engine rewrite:

- **Input:** one existing Voxora project, its matching script, its already-generated narration audio, one channel profile and a small approved asset set.
- **Scene:** a 20–30 second documentary/explainer sequence using at least a map or diagram, two visual cards/prints, one animated counter/marker, camera movement and a word-cued reveal.
- **Timing:** original narration remains byte-for-byte available as the mux source; visual cues use supplied/derived timestamps and report uncertainty.
- **Output:** a complete MP4 through Voxora's existing FFmpeg assembly path, with no manual scene-by-scene asset assignment.
- **Quality:** inspect opening/middle/ending frames and motion; verify audio sync, no black/missing frames, readable text, stable camera, provenance and repeatable render.
- **Resource gate:** target PC at 720p first, one worker, record peak RAM/VRAM, CPU, render time and failure behaviour. Do not start at 4K.
- **Licence gate:** resolve and record all direct/transitive dependency and binary licences before vendoring or distributing code.

**Do not mark the prototype accepted** until it renders and is reviewed on the target Windows PC. Do not claim that the upstream skill has been integrated merely because its source or documentation is present.

## 7. Upstream source references inspected

- `README.md`, `LICENSE`, `requirements.txt`, `PROMPT.md`, `install.sh`, `gemini-extension.json`.
- `skills/cinematic-film/SKILL.md`.
- `scripts/engine.py`, `render.py`, `make_beats.py`, `split_takes.py`, `build_narration.py`, `tts_say.py`, `fetch_commons.py`, `prep_assets.py`, `get_fonts.py`, `build_sfx.py`, `mix_soundtrack.py`, `captions.py`, `burn_captions.py`, `check_setup.py`.
- `references/story.md`, `voice.md`, `archive.md`, `film.md`, `sound.md`, `performance.md`.
- Starter template and Wright Flyer example metadata/scene files.

## 8. Remaining audit work

- Inspect all transitive dependency metadata and platform wheels, including Skia and FFmpeg packaging.
- Inspect the complete test suite and CI workflow; run upstream checks only in an isolated environment if needed.
- Verify every Wikimedia sample asset's current file-page rights and do not bundle unverified media.
- Validate font licences and attribution/notice retention in the intended desktop packaging.
- Prototype the Voxora timing adapter and target-PC render before making a final adoption decision.


## 9. Implemented Voxora adapter slice (PR branch)

The first source-reuse implementation is now present on the planning PR branch:

- `app/universal/cinematic_skill/engine.py`: upstream `scripts/engine.py` vendored from the recorded upstream revision without rewriting its drawing logic.
- `app/universal/cinematic_skill/prep_assets.py`: upstream procedural texture/asset preparation helper vendored so the Film's board looks can be generated locally rather than relying on missing downloaded textures.
- `app/universal/cinematic_skill/LICENSE`: upstream MIT notice retained.
- `app/universal/cinematic_skill_adapter.py`: Voxora-owned, single-worker frame adapter. It renders one Film frame at a time, stages numbered PNGs, delegates H.264 encoding and verification to Voxora's existing `FFmpegFrameSequenceEncoder`, atomically publishes a silent MP4, enforces a 1080p default ceiling, supports cancellation/progress, and cleans temporary files.
- `requirements-cinematic-skill.txt`: optional local runtime only; no paid endpoint, API key, account, credits or subscription. Pillow is already a core Voxora dependency.

The adapter intentionally accepts an already-constructed upstream `Film`. It does **not yet** turn a script into a Film, derive scene/shot layouts, map Voxora's measured word timestamps into the upstream `Doc` contract, or attach narration. It emits a silent MP4 so the existing Voxora narration/audio-mux workflow remains authoritative. This is a real renderer adapter slice, not end-to-end Auto Produce integration.

### Dependency/licence notes for the optional local runtime

- `skia-python`: upstream package metadata and its source repository identify BSD-3-Clause; it binds Google's Skia, which is BSD-3-Clause. Retain both notices for redistribution.
- `numpy`: project source licence is BSD-3-Clause. Some prebuilt wheels include additional bundled numerical/runtime components with their own notices (the NumPy project documents OpenBLAS and GCC runtime components for applicable wheels). The exact Windows wheel and bundled notices must be checked for the actual pinned release before packaging.
- `Pillow`: HPND licence; retain its licence notice if redistributed.
- `FFmpeg`: Voxora reuses the user's already-installed FFmpeg executable and does not bundle a new binary in this change. Any future packaged FFmpeg build needs a separate exact-build configuration/licence audit.
- No SciPy is required by this adapter; the upstream optional SciPy-only sound-effects path is not imported or adopted here.

The optional requirements are intentionally not added to core `requirements.txt` or `pyproject.toml`. They must not be installed automatically on machines that do not opt into the Cinematic Skill engine.

### Verification state

- Source files and adapter tests have been added to the PR branch.
- CI has not yet been confirmed for the latest PR head at the time this report was updated.
- No real Skia render, FFmpeg encode, Bengali typography check, memory benchmark or target-Windows-PC acceptance is claimed.
- The adapter is an initial integration boundary. The next implementation step is the narration timing bridge and a deterministic Film builder driven by Voxora's script/shot plan, followed by an actual 20–30 second render on the target machine.
