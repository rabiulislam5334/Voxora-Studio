# Voxora Studio

A local-first desktop studio for producing Bengali and English narration and video content.

## Current Phase

**Phase 2 — Production reliability and visual-production foundation (in progress).**

See [Phase 2 status](docs/architecture/PHASE_2_STATUS.md) for completed milestones, remaining hardening work, and exit criteria.

## Requirements

- Windows 10 or later
- Python 3.11+
- FFmpeg and FFprobe available on `PATH`
- VS Code (recommended)

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation with an execution-policy error, run this once (user scope; no admin rights required):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Run

```powershell
python -m app.main
```

## Testing

```powershell
python -m pytest -q tests
```

## Current capabilities

- Desktop application shell with navigation, status display, and light/dark themes.
- Edge TTS integration with voice discovery, language/gender filtering, voice preview, and MP3 generation.
- Scene-oriented narration and video-production workflow using the existing FFmpeg renderer.
- Sequential multi-scene execution with progress reporting and cancellation.
- Audio/video assembly and final-output inspection, including stream, duration, frame-count, timestamp, and synchronization checks.
- Video segment caching with validation before cached segments are reused.
- Universal Core scene-plan, engine-resolution, runtime-adapter, and production-bridge contracts, while retaining compatibility with legacy projects.

## Not yet in scope

- Additional cloud or local TTS provider integrations.
- A complete visual scene-authoring experience and automatic creation of Universal scene plans.
- Parallel rendering, a render scheduler, automatic engine fallback, and distributed rendering.
- Commercial packaging and installer workflows.

## Development

- Keep rendering and network work off the Tk main thread.
- Preserve sequential, deterministic production unless a separately reviewed design changes that constraint.
- Do not change cache identity, project schema, or timeline behavior without focused compatibility tests.
- Treat cancellation, temporary-file ownership, and final-output validation as production-safety requirements.
