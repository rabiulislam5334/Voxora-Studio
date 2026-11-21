from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.universal.director_auto_produce_handoff import (
    DirectorHandoffError,
    build_cinematic_skill_handoff,
)
from app.universal.narration_segmentation import segment_narration
from app.universal.production_director import ProductionDirector
from app.universal.profiles.models import ChannelProfile


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
        index: SimpleNamespace(
            line_id=index,
            caption=text,
            spoken_text=text,
        )
        for index, text in enumerate(
            ("Why does the planet move?", "Its orbit follows gravity."), start=1
        )
    }
    doc = SimpleNamespace(lines=lines)
    return script, source, plan, doc


def test_handoff_maps_approved_current_plan_to_existing_shot_contract():
    script, source, plan, doc = _fixture()

    shots = build_cinematic_skill_handoff(
        plan,
        script=script,
        profile_id="quasivanta",
        narration_doc=doc,
        source_unit_ids=tuple(unit.unit_id for unit in source.units),
        approved=True,
    )

    assert [shot.line_id for shot in shots] == [1, 2]
    assert all(shot.kind in {"card", "title"} for shot in shots)
    assert shots[0].body == ("Why does the planet move?",)


def test_handoff_requires_explicit_approval():
    script, source, plan, doc = _fixture()
    with pytest.raises(DirectorHandoffError, match="explicit user approval"):
        build_cinematic_skill_handoff(
            plan, script=script, profile_id="quasivanta",
            narration_doc=doc,
            source_unit_ids=tuple(unit.unit_id for unit in source.units),
            approved=False,
        )


def test_handoff_rejects_stale_script_and_wrong_profile():
    script, source, plan, doc = _fixture()
    args = {
        "profile_id": "quasivanta",
        "narration_doc": doc,
        "source_unit_ids": tuple(unit.unit_id for unit in source.units),
        "approved": True,
    }
    with pytest.raises(DirectorHandoffError, match="fingerprint"):
        build_cinematic_skill_handoff(plan, script=script + " Changed", **args)
    with pytest.raises(DirectorHandoffError, match="profile"):
        build_cinematic_skill_handoff(
            plan, script=script, **{**args, "profile_id": "veltracis"}
        )


def test_handoff_rejects_incomplete_or_reordered_narration_coverage():
    script, source, plan, doc = _fixture()
    ids = tuple(unit.unit_id for unit in source.units)
    args = {
        "script": script,
        "profile_id": "quasivanta",
        "narration_doc": doc,
        "approved": True,
    }
    with pytest.raises(DirectorHandoffError, match="coverage"):
        build_cinematic_skill_handoff(plan, source_unit_ids=ids[:-1], **args)
    with pytest.raises(DirectorHandoffError, match="coverage"):
        build_cinematic_skill_handoff(plan, source_unit_ids=tuple(reversed(ids)), **args)


def test_handoff_rejects_line_count_mismatch_instead_of_guessing():
    script, source, plan, doc = _fixture()
    doc.lines.pop(2)
    with pytest.raises(DirectorHandoffError, match="line count"):
        build_cinematic_skill_handoff(
            plan, script=script, profile_id="quasivanta",
            narration_doc=doc,
            source_unit_ids=tuple(unit.unit_id for unit in source.units),
            approved=True,
        )
