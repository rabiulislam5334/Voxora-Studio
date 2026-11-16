# Voxora Studio — Subtitle System Stage 1

Status: implementation foundation; Stage 1 only
Target project schema: v3
Related decisions: project-level subtitle container; sentence-first generation; SRT + VTT initial export
Not included: caption timing, transcription, synchronization, editor UI, rendering, export generation

## 1. Scope

Stage 1 introduces a dedicated project-level `subtitles` namespace and a backwards-compatible schema migration. It does not implement subtitle generation or playback/rendering behavior.

The initial container is:

```json
{
  "subtitles": {
    "format_version": 1,
    "tracks": []
  }
}
```

The container is intentionally small. Track and caption field definitions are deferred until the project timebase and the owning subtitle stages define their contracts.

## 2. Why timing fields are deferred

Master Specification Rev 0.3 §9.5 leaves the authoritative project timebase open. TS-01 is the separately authorized technical spike for comparing floating-point seconds, integer frames, fixed fine-grained units, and rational values against exactness, drift, FFmpeg compatibility, compatibility with existing `duration_s` values, serialization simplicity, and migration cost.

No TS-01 result or authorization is assumed here. Therefore Stage 1 does not persist caption start/end values, frame positions, word timestamps, or any other timing representation. Sentence-level captions remain the approved initial generation granularity, but their stored timing contract must use the future authoritative timebase.

## 3. Storage placement

The namespace is project-level, alongside `settings`, `profile`, `assets`, and `director`. It is not nested in `settings.studio`.

This keeps subtitle data independent from current studio audio/video settings and avoids coupling the future subtitle engine to the existing scene-slot calculator.

## 4. Migration

### v1 → v2 → v3

1. Existing v1 migration remains unchanged: add the v2 `profile`, `assets`, and `director` object containers and preserve the existing migration marker.
2. The v2 → v3 migration adds `subtitles = {"format_version": 1, "tracks": []}` only when the key is absent.
3. Existing `settings` and `settings.studio` values are not moved, rewritten, or pruned.
4. Migration operates on a deep copy of parsed JSON. Loading does not rewrite the original file; the next normal save serializes the project as v3 through the existing repository save path.
5. Existing project-level unknown keys continue to round-trip through `extras`. Unknown keys inside the subtitle namespace are retained by the current opaque-container model.
6. A non-object subtitle namespace, non-positive/non-integer format version, unsupported newer subtitle format, or non-list tracks value fails loudly with `ProjectError`; it is not silently replaced.
7. The existing v1 backup-before-migration and normal rolling-backup behavior remain owned by `JsonProjectRepository`; this change does not alter that code.

### Compatibility guarantees

- v1 and v2 projects remain readable.
- Existing project settings and scene data remain unchanged by migration.
- A project with no subtitle data opens with an empty subtitle namespace.
- A v3 project with a newer subtitle format is rejected rather than downgraded.
- The project serializer writes schema version 3.
- The current subtitle namespace is data only; it does not execute code or invoke external services.

## 5. Tests added

- New projects serialize the v3 empty subtitle namespace.
- v1 and v2 projects migrate additively to v3 without mutating the source dictionary.
- Existing studio settings remain unchanged.
- Subtitle payloads round-trip, including unknown extension keys.
- Malformed or newer unsupported subtitle containers fail loudly.

## 6. Explicitly deferred

- TS-01 timebase technical spike and its authorization.
- Caption/track timing schema, sentence segmentation, word-level timestamps.
- Local transcription/alignment provider selection (UD-20).
- Subtitle generation and synchronization engines.
- Subtitle editor, typography, SRT/VTT writers, burned-in rendering, and UI integration.

No Stage 2 or later implementation is authorized by this document.
