from __future__ import annotations

import json

import pytest

from app.universal.auto_produce_plan import create_auto_produce_plan
from app.universal.external_visual_direction import VisualDirectionImportError
from app.universal.narration_segmentation import segment_narration
from app.universal.production_director import ProductionDirector
from app.universal.profiles.models import ChannelProfile


def _inputs():
    source = segment_narration(
        "Why does the planet move? Its orbit follows gravity.",
        source_id="auto-produce-source",
        language="en",
    )
    profile = ChannelProfile.from_dict({
        "schema_version": 1,
        "profile_id": "quasivanta",
        "display_name": "Quasivanta",
        "visual_defaults": {
            "style_family": "cinematic_scientific_visualization",
            "style_tags": ["infographics"],
            "mood": ["curious"],
            "composition_guidance": [],
        },
    })
    return source, profile


def test_uses_internal_director_when_no_external_package_is_selected():
    source, profile = _inputs()
    plan = create_auto_produce_plan(source, profile)
    assert plan.to_dict() == ProductionDirector().create_plan(source, profile).to_dict()


def test_loads_external_package_against_active_normalized_script_and_profile(tmp_path):
    source, profile = _inputs()
    package = ProductionDirector().create_plan(source, profile).to_dict()
    path = tmp_path / "visual-direction.json"
    path.write_text(json.dumps(package), encoding="utf-8")

    imported = create_auto_produce_plan(source, profile, visual_direction_path=path)

    assert imported.to_dict() == package
    assert imported.requires_review is True


def test_invalid_external_package_fails_closed_without_internal_fallback(tmp_path):
    source, profile = _inputs()
    package = ProductionDirector().create_plan(source, profile).to_dict()
    package["source_fingerprint"] = "0" * 64
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(VisualDirectionImportError, match="fingerprint"):
        create_auto_produce_plan(source, profile, visual_direction_path=path)


def test_external_package_style_must_match_active_profile(tmp_path):
    source, profile = _inputs()
    package = ProductionDirector().create_plan(source, profile).to_dict()
    package["profile_style_family"] = "unrelated-style"
    for shot in package["shots"]:
        shot["style_family"] = "unrelated-style"
    path = tmp_path / "wrong-style.json"
    path.write_text(json.dumps(package), encoding="utf-8")

    with pytest.raises(VisualDirectionImportError, match="profile_style_family"):
        create_auto_produce_plan(source, profile, visual_direction_path=path)
