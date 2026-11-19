# Voxora Studio

A local-first desktop studio for producing Bengali and English narration and video content.

## Current Phase

**Phase 3 — Universal visual-production integration (final integration phases in progress).**

The current work consolidates the shared project session, local visual-generation workflow, still-image composition, production catalog, and desktop navigation. The final PC acceptance test remains separate from automated CI.

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
- Universal Core scene plans, shared project session, and backward-compatible `.voxora` project persistence.
- Local Stable Diffusion.cpp image generation with explicit executable/model setup and validated asset-library import.
- Generated-image scene binding and composition workflows with provenance checks and explicit approval.
- CPU raster composition rendering for transparent still PNG output; animated MP4 production remains in the separate Produce pipeline.
- Read-only catalog entries for scene-segment engines, composition renderers, and visual-generation providers.

## Not yet in scope

- Additional cloud or local TTS provider integrations.
- A full project-browser page, centralized application settings page, and subtitle editing workflow.
- Automatic AI scene planning, multi-provider/cloud visual generation, and automatic scene mutation.
- Parallel rendering, a render scheduler, automatic engine fallback, and distributed rendering.
- Commercial packaging and installer workflows.

## Development

- Keep rendering and network work off the Tk main thread.
- Keep scene-segment engines, composition renderers, and visual-generation providers as distinct capability contracts.
- Preserve sequential, deterministic production unless a separately reviewed design changes that constraint.
- Do not change cache identity, project schema, or timeline behavior without focused compatibility tests.
- Treat cancellation, temporary-file ownership, and final-output validation as production-safety requirements.
