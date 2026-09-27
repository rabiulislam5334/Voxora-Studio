# Development Notes

## Architecture

See the Phase 0 design: layered architecture — UI (Tkinter/ttk) talks only
to manager/service classes (e.g. `TTSManager`, to be added in Phase 2),
never directly to providers, FFmpeg, or the filesystem for anything
provider-specific.

## Threading rule (enforced starting Phase 2+)

All network calls, TTS generation, and FFmpeg subprocess work must run off
the Tk main thread. Tk widgets are only touched from the main thread; worker
threads communicate back via a thread-safe queue polled with `root.after()`.

## Phase status

- [x] Phase 0 — Architecture & design
- [x] Phase 1 — Project setup + desktop shell
- [ ] Phase 2 — TTS provider abstraction + Edge TTS
- [ ] Phase 3 — Script editor + voice controls
- [ ] ... (see master project prompt for full phase list)

## Coding conventions

- `pathlib.Path` everywhere, never manual string path concatenation
- Type hints on public functions/methods
- No provider-specific code outside `app/tts/`
- No blocking I/O on the Tk main thread
