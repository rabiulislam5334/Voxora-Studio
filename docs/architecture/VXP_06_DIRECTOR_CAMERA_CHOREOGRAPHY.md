# VXP-06 — Director-driven cinematic camera presets (increment)

## Status
IN PROGRESS — implementation branch; CI and real-render acceptance pending.

## Scope
Connect the existing deterministic Production Director intent to the existing Cinematic Skill camera choreography. This is a narrow 2.5D camera-direction increment; it does not claim a general 2D/3D/4D motion engine.

## Implemented in this increment
- Add a finite, allowlisted camera-preset field to the existing `CinematicSkillShot` contract.
- Map the existing Director intents to conservative camera presets: reveal, map-wide, diagram-focus, evidence-detail, timeline-wide, action, environment-wide, and standard.
- Apply preset zoom, focus radius, and focus strength at the narration line's measured start time.
- Preserve the supplied narration timing, shot order, Director plan provenance, existing Film builder, and FFmpeg render/mux path.
- Reject unknown camera presets rather than accepting arbitrary renderer parameters.

## Deliberate boundaries
- No new renderer, dependency, model, provider, network call, or paid service.
- No changes to narration timestamps or audio.
- This is not yet 3D modeling, character animation, physics, 4D simulation, or Hybrid media production.
- Camera motion is evaluated by the existing Cinematic Skill camera spline between measured shot start keys; no target-PC performance or visual-quality claim is made.

## Validation
Focused tests cover intent-to-preset mapping, deterministic zoom/focus values, and rejection of unknown presets. Windows + Ubuntu CI remains the merge gate. A real Skia render and target-PC visual review remain separate acceptance gates.
