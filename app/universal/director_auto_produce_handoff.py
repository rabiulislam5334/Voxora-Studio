"""Validated handoff from an approved DirectorPlan to the existing Film builder.

This adapter deliberately reuses the current Cinematic Skill renderer. It does
not acquire assets, call providers, or claim that a card is a semantic renderer
for every Director intent. Narration alignment remains the timing authority.
"""
from __future__ import annotations

import hashlib

from app.universal.cinematic_skill_builder import CinematicSkillShot
from app.universal.production_director import DirectorIntent, DirectorPlan
from app.universal.storyboard import NarrationSource


class DirectorHandoffError(ValueError):
    """Raised when a Director plan cannot safely enter Auto Produce."""


# The current Film builder supports cards, titles and counters only. Keep the
# mapping explicit; unsupported/complex intents fall back to a labelled card.
_INTENT_KIND = {
    DirectorIntent.QUESTION_REVEAL: "title",
    DirectorIntent.MAP: "card",
    DirectorIntent.DIAGRAM: "card",
    DirectorIntent.EVIDENCE: "card",
    DirectorIntent.TIMELINE: "card",
    DirectorIntent.CHARACTER_ACTION: "card",
    DirectorIntent.ENVIRONMENT: "card",
    DirectorIntent.ILLUSTRATIVE: "card",
}


def build_cinematic_skill_handoff(
    plan: DirectorPlan,
    *,
    script: str,
    profile_id: str,
    narration_doc,
    narration_source: NarrationSource,
    approved: bool,
) -> tuple[CinematicSkillShot, ...]:
    """Validate plan provenance/coverage and map its ordered shots to aligned lines.

    `source_unit_ids` must be the exact ordered IDs from the NarrationSource
    used to create the DirectorPlan. The current aligner emits one line for
    each non-empty script line; therefore a count/coverage mismatch fails
    closed instead of guessing how multiple source units map to a line.
    """
    if not isinstance(plan, DirectorPlan):
        raise DirectorHandoffError("director_plan must be a DirectorPlan")
    if approved is not True:
        raise DirectorHandoffError("Director plan requires explicit user approval")
    if not isinstance(script, str) or not script.strip():
        raise DirectorHandoffError("script must be non-empty")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise DirectorHandoffError("profile_id is required")
    fingerprint = hashlib.sha256(script.encode("utf-8")).hexdigest()
    if plan.source_fingerprint != fingerprint:
        raise DirectorHandoffError("Director plan is stale: script fingerprint does not match")
    if plan.profile_id != profile_id:
        raise DirectorHandoffError("Director plan profile does not match the active channel profile")
    if not hasattr(narration_doc, "lines"):
        raise DirectorHandoffError("narration_doc must expose measured aligned lines")

    if not isinstance(narration_source, NarrationSource):
        raise DirectorHandoffError("narration_source must be the exact NarrationSource used by the Director")
    if narration_source.text != script or narration_source.source_fingerprint != fingerprint:
        raise DirectorHandoffError("NarrationSource text does not match the supplied script")
    unit_ids = tuple(unit.unit_id for unit in narration_source.units)
    if not unit_ids or len(set(unit_ids)) != len(unit_ids):
        raise DirectorHandoffError("NarrationSource must contain unique narration units")

    shots = tuple(plan.shots)
    if not shots:
        raise DirectorHandoffError("Director plan contains no shots")
    flattened = tuple(unit_id for shot in shots for unit_id in shot.narration_unit_ids)
    if flattened != unit_ids:
        raise DirectorHandoffError(
            "Director shot coverage must match every narration unit exactly once and in order"
        )
    scene_shot_ids = tuple(shot_id for scene in plan.scenes for shot_id in scene.shot_ids)
    shot_ids = tuple(shot.shot_id for shot in shots)
    if scene_shot_ids != shot_ids or len(set(shot_ids)) != len(shot_ids):
        raise DirectorHandoffError("Director scenes must reference every shot exactly once and in order")

    lines = tuple(narration_doc.lines.values())
    if len(lines) != len(unit_ids):
        raise DirectorHandoffError(
            "aligned narration line count does not match Director narration-unit count; "
            "no timing or scene mapping was guessed"
        )

    shot_by_unit = {
        unit_id: shot
        for shot in shots
        for unit_id in shot.narration_unit_ids
    }
    result = []
    for line, unit in zip(lines, narration_source.units):
        shot = shot_by_unit[unit.unit_id]
        exact_unit_text = narration_source.text_for_unit(unit).strip()
        if line.spoken_text != exact_unit_text:
            raise DirectorHandoffError(
                f"aligned narration line {line.line_id} does not exactly match source unit {unit.unit_id}"
            )
        try:
            kind = _INTENT_KIND[shot.intent]
        except (KeyError, TypeError):
            raise DirectorHandoffError(f"unsupported Director intent: {shot.intent!r}") from None
        # Preserve the exact spoken script in the visual card. The Director
        # prompt remains available in plan metadata for a future richer adapter.
        result.append(CinematicSkillShot(
            line_id=line.line_id,
            kind=kind,
            title=shot.shot_type.replace("_", " ").title(),
            body=(line.caption or line.spoken_text,),
            director_shot_id=shot.shot_id,
            camera_preset=_INTENT_CAMERA_PRESET[shot.intent],
        ))
    return tuple(result)
