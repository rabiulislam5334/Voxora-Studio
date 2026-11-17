# Development Notes

## Architecture

The application uses a layered architecture: UI (Tkinter/ttk) communicates with manager/service classes and does not directly own provider-specific, FFmpeg, or filesystem workflows.

## Threading rule

All network calls, TTS generation, and FFmpeg subprocess work must run off the Tk main thread. Tk widgets are only touched from the main thread; worker threads communicate back through a thread-safe queue polled with `root.after()`.

## Phase status

- [x] Phase 0 — Architecture and design
- [x] Phase 1 — Project setup and desktop shell
- [ ] Phase 2 — Production reliability and visual-production foundation (in progress)
- [ ] Phase 3 — Expanded authoring workflows and higher-level production features

Phase 2 scope, completed milestones, deferred work, and exit criteria are maintained in [PHASE_2_STATUS.md](architecture/PHASE_2_STATUS.md).

## Coding conventions

- Use `pathlib.Path`; avoid manual path-string concatenation.
- Add type hints to public functions and methods.
- Keep provider-specific code inside the TTS/provider boundary.
- Do not perform blocking I/O on the Tk main thread.
- Preserve existing behavior unless a focused change and regression tests explicitly authorize it.
