from pathlib import Path

import pytest

from app.universal.models import AssetRef, EngineChoice, ScenePlan
from app.universal.production_bridge import (
    ProductionPlanError,
    build_production_render_request,
)
from app.video.render import SegmentSpec


def image_spec(path):
    return SegmentSpec("image", str(path), 2.5, 640, 360, 24, "zoom_in", "fit", 352800000, 60)


def test_legacy_scene_builds_ephemeral_ffmpeg_plan_and_immutable_request(tmp_path):
    source = tmp_path / "still.png"
    destination = tmp_path / "scene.part"
    spec = image_spec(source)

    plan, request = build_production_render_request("scene-1", spec, destination)

    assert plan.scene_id == "scene-1"
    assert plan.kind == "image"
    assert plan.engine_choice.engine_id == "ffmpeg"
    assert plan.engine_choice.chosen_by == "legacy-production"
    assert plan.asset_refs == [
        AssetRef("scene-1:primary-visual", "image", path=str(source))
    ]
    assert request.scene_id == "scene-1"
    assert request.scene_kind == "image"
    assert request.output_format == "mp4"
    assert request.output_spec.duration_s == 2.5
    assert request.output_spec.width == 640
    assert request.output_spec.height == 360
    assert request.output_spec.fps == 24
    assert request.destination == destination
    assert request.engine_params["motion"] == "zoom_in"
    assert request.engine_params["fit"] == "fit"
    assert request.engine_params["length_ticks"] == 352800000
    assert request.engine_params["frame_count"] == 60
    with pytest.raises(TypeError):
        request.engine_params["motion"] = "none"


def test_existing_plan_is_preserved_and_forwarded_without_mutation(tmp_path):
    source = tmp_path / "still.png"
    plan = ScenePlan(
        scene_id="scene-1",
        kind="image",
        requirements={"output_format": "mp4", "asset_kinds": ["image"]},
        engine_choice=EngineChoice("ffmpeg"),
        asset_refs=[AssetRef("asset-main", "image", path=str(source), license="user-owned")],
        notes="approved visual selection",
    )
    before = plan.to_dict()

    returned_plan, request = build_production_render_request(
        "scene-1", image_spec(source), tmp_path / "scene.part", plan
    )

    assert returned_plan is plan
    assert plan.to_dict() == before
    assert request.asset_refs[0].asset_id == "asset-main"
    assert request.asset_refs[0].license == "user-owned"


def test_blank_scene_builds_request_without_asset_refs(tmp_path):
    spec = SegmentSpec("blank", None, 1.0, 640, 360, 24)

    plan, request = build_production_render_request(
        "scene-blank", spec, tmp_path / "blank.part"
    )

    assert plan.kind == "blank"
    assert plan.asset_refs == []
    assert request.asset_refs == ()


@pytest.mark.parametrize(
    "plan, message",
    [
        (
            ScenePlan("other-scene", kind="image", requirements={"output_format": "mp4"},
                      engine_choice=EngineChoice("ffmpeg"),
                      asset_refs=[AssetRef("asset", "image", path="still.png")]),
            "does not match scene",
        ),
        (
            ScenePlan("scene-1", kind="video", requirements={"output_format": "mp4"},
                      engine_choice=EngineChoice("ffmpeg"),
                      asset_refs=[AssetRef("asset", "video", path="still.png")]),
            "does not match configured media kind",
        ),
        (
            ScenePlan("scene-1", kind="image", requirements={"output_format": "mp4"},
                      engine_choice=EngineChoice("ffmpeg"),
                      asset_refs=[AssetRef("asset", "image", path="different.png")]),
            "path does not match",
        ),
        (
            ScenePlan("scene-1", kind="image", requirements={"output_format": "webm"},
                      engine_choice=EngineChoice("ffmpeg"),
                      asset_refs=[AssetRef("asset", "image", path="still.png")]),
            "must explicitly request",
        ),
    ],
)
def test_existing_plan_must_match_current_scene_configuration(tmp_path, plan, message):
    source = tmp_path / "still.png"
    if plan.asset_refs and plan.asset_refs[0].path == "still.png":
        plan.asset_refs[0].path = str(source)

    with pytest.raises(ProductionPlanError, match=message):
        build_production_render_request("scene-1", image_spec(source), tmp_path / "scene.part", plan)


def test_non_asset_entries_are_rejected(tmp_path):
    plan = ScenePlan(
        scene_id="scene-1",
        kind="image",
        requirements={"output_format": "mp4"},
        engine_choice=EngineChoice("ffmpeg"),
        asset_refs=[{"asset_id": "bad", "kind": "image", "path": "still.png"}],
    )
    with pytest.raises(ProductionPlanError, match="AssetRef"):
        build_production_render_request(
            "scene-1", image_spec(tmp_path / "still.png"), tmp_path / "scene.part", plan
        )
