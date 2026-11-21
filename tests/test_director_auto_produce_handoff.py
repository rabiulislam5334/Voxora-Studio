from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.universal.director_auto_produce_handoff import (
    DirectorHandoffError,
    build_cinematic_skill_handoff,
)
from app.universal.narration_segmentation import segment_narration
from app.universal.production_director import ProductionDirector
from app.universal.profiles.models import ChannelProfile
from app.universal.storyboard import NarrationSource, NarrationTextUnit


def _profile():
    return ChannelProfile.from_dict({
        "schema_version": 1,
        "profile_id": "quasivanta",
        "display_name": "Quasivanta",
        "visual_defaults": {
            "style_family": "cinematic_scientific_visualization",
            "style_tags": ["infographics"],
            "mood": ["curious"],
            "composition_guidance": ["Keep claims proportional to narration."],
        },
    })


def _fixture():
    script = "Why does the planet move? Its orbit follows gravity."
    source = segment_narration(script, source_id="handoff-test", total_duration_ms=8000)
    plan = ProductionDirector().create_plan(source, _profile())
    lines = {
        index: SimpleNamespace(line_id=index, caption=text, spoken_text=text)
        for index, text in enumerate(
            ("Why does the planet move?", "Its orbit follows gravity."), start=1
        )
    }
    return script, source, plan, SimpleNamespace(lines=lines)


def _args(script, source, doc):
    return {
        "script": script,
        "profile_id": "quasivanta",
        "narration_doc": doc,
        "narration_source": source,
        "approved": True,
    }


def test_handoff_maps_approved_current_plan_to_existing_shot_contract():
    script, source, plan, doc = _fixture()
    shots = build_cinematic_skill_handoff(
        plan, **_args(script, source, doc)
    )
    assert [shot.line_id for shot in shots] == [1, 2]
    assert all(shot.kind in {"card", "title"} for shot in shots)
    assert shots[0].body == ("Why does the planet move?",)


def test_handoff_requires_explicit_approval():
    script, source, plan, doc = _fixture()
    args = _args(script, source, doc)
    args["approved"] = False
    with pytest.raises(DirectorHandoffError, match="explicit user approval"):
        build_cinematic_skill_handoff(plan, **args)


def test_handoff_rejects_stale_script_and_wrong_profile():
    script, source, plan, doc = _fixture()
    args = _args(script, source, doc)
    with pytest.raises(DirectorHandoffError, match="fingerprint"):
        build_cinematic_skill_handoff(plan, **{**args, "script": script + " Changed"})
    with pytest.raises(DirectorHandoffError, match="profile"):
        build_cinematic_skill_handoff(plan, **{**args, "profile_id": "veltracis"})


def test_handoff_rejects_incomplete_or_wrong_narration_coverage():
    script, source, plan, doc = _fixture()
    args = _args(script, source, doc)
    incomplete = NarrationSource(
        source_id=source.source_id, text=source.text,
        units=source.units[:-1], total_duration_ms=source.total_duration_ms,
    )
    renamed_units = tuple(
        NarrationTextUnit(
            unit_id=f"other-{index}",
            start_offset=unit.start_offset,
            end_offset=unit.end_offset,
            timing=unit.timing,
            metadata=unit.metadata,
        )
        for index, unit in enumerate(source.units, start=1)
    )
    wrong_ids = NarrationSource(
        source_id=source.source_id, text=source.text,
        units=renamed_units, total_duration_ms=source.total_duration_ms,
    )
    with pytest.raises(DirectorHandoffError, match="coverage"):
        build_cinematic_skill_handoff(plan, **{**args, "narration_source": incomplete})
    with pytest.raises(DirectorHandoffError, match="coverage"):
        build_cinematic_skill_handoff(plan, **{**args, "narration_source": wrong_ids})


def test_handoff_rejects_line_count_mismatch_instead_of_guessing():
    script, source, plan, doc = _fixture()
    doc.lines.pop(2)
    with pytest.raises(DirectorHandoffError, match="line count"):
        build_cinematic_skill_handoff(plan, **_args(script, source, doc))


def test_handoff_rejects_line_text_that_does_not_match_source_unit():
    script, source, plan, doc = _fixture()
    doc.lines[1].spoken_text = "A different sentence."
    with pytest.raises(DirectorHandoffError, match="does not exactly match"):
        build_cinematic_skill_handoff(plan, **_args(script, source, doc))



def test_handoff_expands_one_director_shot_over_its_multiple_narration_units():
    script, source, plan, doc = _fixture()
    merged = replace(
        plan.shots[0],
        narration_unit_ids=tuple(unit.unit_id for unit in source.units),
    )
    grouped_plan = replace(
        plan,
        scenes=(replace(plan.scenes[0], shot_ids=(merged.shot_id,)),),
        shots=(merged,),
    )

    shots = build_cinematic_skill_handoff(
        grouped_plan, **_args(script, source, doc)
    )

    assert [item.line_id for item in shots] == [1, 2]
    assert [item.director_shot_id for item in shots] == [merged.shot_id, merged.shot_id]
