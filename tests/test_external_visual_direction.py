from __future__ import annotations

import hashlib
import json

import pytest

from app.universal.external_visual_direction import (
    VisualDirectionImportError,
    import_visual_direction_package,
)
from app.universal.narration_segmentation import segment_narration
from app.universal.production_director import ProductionDirector
from app.universal.profiles.models import ChannelProfile


def _fixture():
    script = "Why does the planet move? Its orbit follows gravity."
    source = segment_narration(script, source_id="external-test", total_duration_ms=8000)
    profile = ChannelProfile.from_dict({
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
    package = ProductionDirector().create_plan(source, profile).to_dict()
    return script, source, package


def test_imports_valid_external_director_json_and_preserves_plan():
    script, source, package = _fixture()
    imported = import_visual_direction_package(
        json.dumps(package), script=script, profile_id="quasivanta", narration_source=source
    )
    assert imported.to_dict() == package
    assert imported.requires_review is True


def test_import_accepts_mapping_and_rejects_stale_script_or_profile():
    script, source, package = _fixture()
    assert import_visual_direction_package(
        package, script=script, profile_id="quasivanta", narration_source=source
    ).profile_id == "quasivanta"
    with pytest.raises(VisualDirectionImportError, match="fingerprint"):
        import_visual_direction_package(
            package, script=script + " Changed", profile_id="quasivanta", narration_source=source
        )
    with pytest.raises(VisualDirectionImportError, match="profile_id"):
        import_visual_direction_package(
            package, script=script, profile_id="veltracis", narration_source=source
        )


def test_import_rejects_wrong_source_and_unapproved_package():
    script, source, package = _fixture()
    package["source_id"] = "other-project"
    with pytest.raises(VisualDirectionImportError, match="source_id"):
        import_visual_direction_package(
            package, script=script, profile_id="quasivanta", narration_source=source
        )
    package["source_id"] = source.source_id
    package["requires_review"] = False
    with pytest.raises(VisualDirectionImportError, match="explicit review"):
        import_visual_direction_package(
            package, script=script, profile_id="quasivanta", narration_source=source
        )


def test_import_rejects_duplicate_json_keys_and_oversized_payload():
    script, source, package = _fixture()
    duplicate = '{"schema_version":1,"schema_version":1}'
    with pytest.raises(VisualDirectionImportError, match="duplicate JSON key"):
        import_visual_direction_package(
            duplicate, script=script, profile_id="quasivanta", narration_source=source
        )
    with pytest.raises(VisualDirectionImportError, match="10 MiB"):
        import_visual_direction_package(
            " " * (10 * 1024 * 1024 + 1), script=script,
            profile_id="quasivanta", narration_source=source
        )


def test_import_rejects_missing_duplicate_or_reordered_narration_coverage():
    script, source, package = _fixture()
    package["shots"][0]["narration_unit_ids"] = [source.units[1].unit_id]
    with pytest.raises(VisualDirectionImportError, match="exactly once"):
        import_visual_direction_package(
            package, script=script, profile_id="quasivanta", narration_source=source
        )


def test_import_rejects_unknown_intents_bad_confidence_and_scene_coverage():
    script, source, package = _fixture()
    package["shots"][0]["intent"] = "invented_renderer"
    with pytest.raises(VisualDirectionImportError, match="intent"):
        import_visual_direction_package(
            package, script=script, profile_id="quasivanta", narration_source=source
        )
    package = _fixture()[2]
    package["shots"][0]["confidence"] = float("nan")
    with pytest.raises(VisualDirectionImportError, match="confidence"):
        import_visual_direction_package(
            package, script=script, profile_id="quasivanta", narration_source=source
        )
    package = _fixture()[2]
    package["scenes"][0]["shot_ids"] = []
    with pytest.raises(VisualDirectionImportError, match="shot_ids"):
        import_visual_direction_package(
            package, script=script, profile_id="quasivanta", narration_source=source
        )
