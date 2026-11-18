# Phase 3.5.4.4 — Composition Render Coordinator

## Purpose

Provide the first opt-in end-to-end runtime path from persisted scene compositions to a final MP4. The coordinator composes one still PNG per scene, encodes those stills over the immutable frame timeline, then reuses the existing Studio audio mixer and composition MP4 muxer.

## Execution contract

The caller must obtain explicit render approval and pass:
- the current project and immutable `CompositionTimelinePlan`;
- the exact narration-duration and pause tick maps used to build that plan;
- one already-assembled, timeline-aligned narration WAV;
- a local `VisualAssetLibrary`, configured `FFmpegTool`, and a new MP4 destination.

The coordinator revalidates the plan before visual rendering, before encoding, and immediately before audio mux. It resolves every visible image through the local catalog and scene bindings, verifies asset identity, renders each scene once with the CPU raster renderer, and writes a compact FFmpeg concat manifest. It does not create one PNG per output frame, avoiding frame-count-proportional temporary disk usage.

The silent H.264 output is CFR and constrained to the plan's exact frame count. The existing composition audio muxer then validates the silent input, reuses Studio audio settings/mixer, muxes AAC, validates the final MP4, and publishes without overwriting an existing destination.

## Explicit current limitations

- Only cut transitions are supported. Crossfade plans are rejected rather than silently rendered incorrectly.
- Each scene is a still composition held for its timeline frame interval. No camera motion, animation, procedural drawing, or AI generation is added.
- Narration WAV assembly and TTS generation are not performed here. The caller must supply one aligned WAV; existing Studio narration production remains unchanged.
- No UI wiring, schema migration, automatic engine fallback, or legacy ProductionJob changes.
- Dedicated SFX tracks are not introduced; only existing Studio AudioSettings are used.

## Safety

- Rejects stale plans, missing/invalid compositions, invalid bindings, non-contiguous frame intervals, unsupported transitions, malformed Studio settings, missing narration, and pre-existing/symlink destinations.
- Uses a temporary work directory beside the destination; failed or cancelled renders clean up temporary artifacts.
- Does not mutate project, scene, composition, or settings data.
