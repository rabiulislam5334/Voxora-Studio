from __future__ import annotations

import copy

import pytest

from app.universal.engines import EngineCapabilities, EngineDescriptor, EngineRegistry
from app.universal.models import AssetRef, EngineChoice, ScenePlan
from app.universal.plan_resolver import EnginePlanResolver, EnginePlanStatus


def engine(engine_id, *, available=True, caps=None):
    return EngineDescriptor(
        engine_id=engine_id,
        display_name=engine_id,
        version="1",
        capabilities=caps or EngineCapabilities(
            scene_kinds=("image", "footage"),
            style_tags=("documentary", "parallax"),
            asset_kinds=("image", "video"),
            output_formats=("mp4",),
        ),
        available=available,
        unavailable_reason="not installed" if not available else "",
    )


def plan(**kwargs):
    values = {
        "scene_id": "scene-1",
        "kind": "image",
        "style_tags": ["documentary"],
        "asset_refs": [AssetRef("asset-1", "image")],
        "requirements": {"output_format": "mp4"},
        "engine_choice": EngineChoice("ffmpeg"),
        "plan_status": "draft",
    }
    values.update(kwargs)
    return ScenePlan(**values)


@pytest.fixture
def registry():
    return EngineRegistry([engine("ffmpeg"), engine("remotion")])


def test_exact_requested_engine_is_returned_without_auto_switch(registry):
    result = EnginePlanResolver(registry).resolve(plan())
    assert result.status is EnginePlanStatus.COMPATIBLE
    assert result.selected_descriptor.engine_id == "ffmpeg"
    assert result.plan_status == "draft"


def test_missing_selection_returns_candidates_but_selects_nothing(registry):
    result = EnginePlanResolver(registry).resolve(
        plan(engine_choice=EngineChoice())
    )
    assert result.status is EnginePlanStatus.SELECTION_REQUIRED
    assert result.selected_descriptor is None
    assert [item.engine_id for item in result.compatible_candidates] == ["ffmpeg", "remotion"]


def test_unknown_primary_engine_is_reported_without_implicit_fallback(registry):
    result = EnginePlanResolver(registry).resolve(plan(
        engine_choice=EngineChoice("missing")
    ))
    assert result.status is EnginePlanStatus.UNKNOWN_ENGINE
    assert result.selected_descriptor is None


def test_unavailable_primary_engine_is_reported():
    registry = EngineRegistry([engine("ffmpeg", available=False)])
    result = EnginePlanResolver(registry).resolve(plan())
    assert result.status is EnginePlanStatus.ENGINE_UNAVAILABLE
    assert result.selected_descriptor is None


def test_incompatible_primary_engine_is_reported(registry):
    result = EnginePlanResolver(registry).resolve(plan(kind="scientific_3d"))
    assert result.status is EnginePlanStatus.ENGINE_INCOMPATIBLE


def test_explicit_compatible_fallback_requires_review(registry):
    result = EnginePlanResolver(registry).resolve(plan(
        engine_choice=EngineChoice("missing", fallback_chain=["remotion"])
    ))
    assert result.status is EnginePlanStatus.FALLBACK_REVIEW_REQUIRED
    assert result.requested_engine_id == "missing"
    assert result.selected_descriptor is None
    assert [item.engine_id for item in result.fallback_candidates] == ["remotion"]


def test_fallback_chain_is_inspected_in_declared_order_and_diagnosed():
    registry = EngineRegistry([
        engine("good"),
        engine("offline", available=False),
    ])
    result = EnginePlanResolver(registry).resolve(plan(
        engine_choice=EngineChoice(
            "missing", fallback_chain=["unknown", "offline", "good"]
        )
    ))
    assert [item.engine_id for item in result.fallback_candidates] == ["good"]
    assert any("unknown" in item for item in result.diagnostics)
    assert any("unavailable" in item for item in result.diagnostics)


def test_fallback_suggestions_do_not_change_plan_or_engine_choice(registry):
    scene = plan(engine_choice=EngineChoice("missing", fallback_chain=["remotion"]))
    before = copy.deepcopy(scene.to_dict())
    EnginePlanResolver(registry).resolve(scene)
    assert scene.to_dict() == before
    assert scene.engine_choice.engine_id == "missing"


def test_asset_kinds_are_derived_from_asset_refs(registry):
    result = EnginePlanResolver(registry).resolve(plan(
        asset_refs=[AssetRef("asset-1", "audio")]
    ))
    assert result.status is EnginePlanStatus.ENGINE_INCOMPATIBLE


def test_contradictory_asset_kinds_are_rejected(registry):
    result = EnginePlanResolver(registry).resolve(plan(
        requirements={"output_format": "mp4", "asset_kinds": ["video"]}
    ))
    assert result.status is EnginePlanStatus.INVALID_PLAN
    assert any("contradict" in item for item in result.diagnostics)


def test_matching_asset_kinds_declaration_is_accepted(registry):
    result = EnginePlanResolver(registry).resolve(plan(
        requirements={"output_format": "mp4", "asset_kinds": ["image"]}
    ))
    assert result.status is EnginePlanStatus.COMPATIBLE


def test_unknown_requirement_keys_are_not_ignored(registry):
    result = EnginePlanResolver(registry).resolve(plan(
        requirements={"output_format": "mp4", "needs_raytracing": True}
    ))
    assert result.status is EnginePlanStatus.UNSUPPORTED_REQUIREMENTS
    assert any("needs_raytracing" in item for item in result.diagnostics)


@pytest.mark.parametrize("requirements", [
    {"output_format": ""},
    {"output_format": 123},
    {"asset_kinds": "image"},
])
def test_malformed_known_requirements_are_invalid(registry, requirements):
    result = EnginePlanResolver(registry).resolve(plan(requirements=requirements))
    assert result.status is EnginePlanStatus.INVALID_PLAN


def test_malformed_scene_plan_is_invalid(registry):
    result = EnginePlanResolver(registry).resolve(plan(style_tags=[""]))
    assert result.status is EnginePlanStatus.INVALID_PLAN


def test_registry_and_plan_are_not_mutated(registry):
    scene = plan()
    before_plan = copy.deepcopy(scene.to_dict())
    before_engines = registry.list_engines(include_unavailable=True)
    EnginePlanResolver(registry).resolve(scene)
    assert scene.to_dict() == before_plan
    assert registry.list_engines(include_unavailable=True) == before_engines


def test_resolver_requires_engine_registry():
    with pytest.raises(TypeError):
        EnginePlanResolver(object())


def test_resolver_requires_scene_plan(registry):
    with pytest.raises(TypeError):
        EnginePlanResolver(registry).resolve({})
