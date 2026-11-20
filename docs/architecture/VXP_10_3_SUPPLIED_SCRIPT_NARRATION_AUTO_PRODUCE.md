# VXP-10.3 — Supplied Script + Narration Auto Produce Vertical Slice

## Delivered in this change

- A single orchestration service accepts a complete script, an already-generated narration audio file, language, project workspace and MP4 destination.
- FFmpeg probes the supplied file and the workflow refuses inputs without a readable audio stream and finite duration.
- The optional local Stable-ts adapter aligns the exact supplied script to the audio. Existing strict line/word validation remains in force; uncertain or mismatched alignment fails instead of inventing timestamps.
- The existing Cinematic Skill Film builder turns measured narration lines into a timed Film.
- The existing single-worker Cinematic Skill renderer renders frames and encodes H.264.
- A dedicated FFmpeg mux adapter adds the supplied narration as AAC, preserves its spoken samples, and pads only the final frame-quantization tail when needed.
- Temporary alignment and mux artifacts are cleaned up. Output is not overwritten. Cancellation and progress are propagated.

## Deliberate scope limits

- This is the first executable voice-led vertical slice, not the finished AI Production Director.
- The current Film builder uses deterministic explainer cards; it does not yet perform semantic shot planning, image acquisition/generation, maps, Stickman/character animation, or per-shot adapter selection.
- This slice does not add BGM/SFX mixing, captions, UI controls, or automatic project-scene persistence.
- Stable-ts, Skia and NumPy remain optional. No paid API, account, subscription or mandatory cloud upload is introduced.
- FFmpeg muxing currently attaches the supplied narration only. Existing multitrack sound-design work remains a separate integration step.

## Acceptance and validation

- Unit tests cover orchestration handoff, audio-stream rejection, exact input preservation, FFmpeg mux arguments, final stream checks and temporary-file cleanup.
- These tests use injected fake alignment/rendering components. They do not prove actual Stable-ts accuracy, real Skia rendering, Windows performance, or English/Bengali model quality.
- Required next gates: Windows + Ubuntu CI for this PR; then a real 30–60 second English audio render on the user's Windows PC. Bengali alignment must be benchmarked separately before claiming support quality.
- The first target-PC acceptance must confirm final MP4 has H.264 video + AAC narration, correct duration, no silent/missing voice, and no manually assigned scene assets.
