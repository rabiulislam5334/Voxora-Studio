# Voxora Studio

A modular, provider-flexible desktop AI voice production studio for creating
Bengali and English YouTube narration/voiceovers.

## Current Phase

**Phase 1 — Project Setup + Desktop Shell**

## Requirements

- Windows 10
- Python 3.11+
- VS Code (recommended)

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

If PowerShell blocks activation with an execution-policy error, run this once
(user scope, no admin rights required):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Run

```powershell
python -m app.main
```

## Testing

```powershell
pytest
```

## Current Features

- Desktop shell: top bar, sidebar navigation, status bar
- Dark/light theme with runtime toggle
- Resizable window with sensible minimum size
- Config system with auto-created app directories (`projects/`, `output/`,
  `cache/`, `temp/`, `logs/`)
- Rotating file logging + console logging
- Application exception hierarchy
- Core data models: `Project`, `Scene`, `Voice`, `AudioInfo`
- `TTSProvider` abstract interface and `ProviderCapabilities` model
- pytest test suite for config, models, and capabilities

## Not Yet Implemented

- Edge TTS (or any) speech generation
- ElevenLabs / OpenAI / Azure / Piper providers
- Real script/scene editor
- Long-form chunking + generation queue
- Audio playback and processing
- Pronunciation and pause system
- SRT subtitle generation
- Background music / mixing
- Video voice-over / FFmpeg integration
- Project save/load/autosave
- Timeline
- Packaging (PyInstaller)

## Project Structure

## Current Features

- Everything from Phase 1 (shell, theming, navigation)
- Microsoft Edge TTS integration: dynamic voice discovery, Bengali/English/gender filtering
- Voice preview playback
- Text-to-speech generation to MP3, with speed control and a chosen output folder
- Background generation/voice-loading that never freezes the UI

## Not Yet Implemented

- ElevenLabs / OpenAI / Azure / Piper providers
- Pitch/volume/style controls in the UI (provider supports them; UI exposes them in a later phase)
- Scene-based script editor, long-form chunking, generation queue
- Pronunciation dictionary, pause system, SRT, background music, video, timeline
- Project save/load/autosave, packaging
