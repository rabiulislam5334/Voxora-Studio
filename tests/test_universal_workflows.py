from dataclasses import replace

import pytest

from app.universal.engines import EngineCapabilities, EngineDescriptor, EngineRegistry
from app.universal.workflow import (
    BUILTIN_WORKFLOW_DESCRIPTORS,
    BUILTIN_WORKFLOW_REGISTRY,
    UnknownWorkflowError,
    WorkflowDescriptor,
    WorkflowFamily,
    WorkflowRegistry,
    WorkflowResolutionStatus,
    WorkflowResolver,
)


def _engine(engine_id="cartoon-engine", *, available=True, families=("2d",)):
    return EngineDescriptor(
        engine_id=engine_id,
        display_name=engine_id,
        version="1.0",
        available=available,
        unavailable_reason="" if available else "optional renderer is not installed",
        capabilities=EngineCapabilities(
            scene_kinds=("cartoon", "illustration"),
            style_tags=("flat_vector", "hand_drawn"),
            workflow_families=families,
            asset_kinds=("image", "character"),
            output_formats=("mp4",),
        ),
    )


def test_builtin_workflow_catalog_is_stable_and_channel_agnostic():
    ids = [item.workflow_id for item in BUILTIN_WORKFLOW_REGISTRY.list_workflows()]
    assert ids == sorted(ids)
    assert {
        "2d_storytelling",
        "2_5d_motion",
        "3d_4d_visualization",
        "real_map",
        "documentary",
        "character_performance",
        "sketch_illustration",
        "stickman",
    }.issubset(ids)
    assert len(BUILTIN_WORKFLOW_DESCRIPTORS) == len(ids)


def test_workflow_registry_rejects_duplicate_ids_and_returns_sorted_items():
    registry = WorkflowRegistry(BUILTIN_WORKFLOW_DESCRIPTORS[:2])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(BUILTIN_WORKFLOW_DESCRIPTORS[0])
    assert [item.workflow_id for item in registry.list_workflows()] == sorted(
        item.workflow_id for item in BUILTIN_WORKFLOW_DESCRIPTORS[:2]
    )
    with pytest.raises(UnknownWorkflowError):
        registry.get("missing")


def test_workflow_descriptor_validates_family_and_scene_kinds():
    with pytest.raises(TypeError, match="WorkflowFamily"):
        WorkflowDescriptor("custom", "Custom", "Description", "2d")
    with pytest.raises(ValueError, match="non-empty strings"):
        WorkflowDescriptor("custom", "Custom", "Description", WorkflowFamily.TWO_D, ("",))


def test_resolver_returns_candidates_but_never_selects_an_engine():
    engines = EngineRegistry((_engine(), _engine("map-engine", families=("real_map",))))
    resolver = WorkflowResolver(BUILTIN_WORKFLOW_REGISTRY, engines)

    result = resolver.resolve(
        "2d_storytelling",
        scene_kind="cartoon",
        style_tags=("flat_vector",),
        asset_kinds=("character",),
        output_format="mp4",
    )

    assert result.status is WorkflowResolutionStatus.SELECTION_REQUIRED
    assert result.selected_engine_id is None
    assert [item.engine_id for item in result.compatible_candidates] == ["cartoon-engine"]


def test_resolver_accepts_only_exact_selected_engine_with_declared_family():
    engines = EngineRegistry((_engine(), _engine("other", families=("documentary",))))
    resolver = WorkflowResolver(BUILTIN_WORKFLOW_REGISTRY, engines)

    result = resolver.resolve("2d_storytelling", selected_engine_id="cartoon-engine")
    assert result.status is WorkflowResolutionStatus.COMPATIBLE
    assert result.selected_descriptor.engine_id == "cartoon-engine"

    incompatible = resolver.resolve("2d_storytelling", selected_engine_id="other")
    assert incompatible.status is WorkflowResolutionStatus.ENGINE_INCOMPATIBLE
    assert incompatible.selected_descriptor is None


def test_resolver_reports_unknown_and_unavailable_engine_without_fallback():
    engines = EngineRegistry((
        _engine(),
        _engine("offline-engine", available=False),
    ))
    resolver = WorkflowResolver(BUILTIN_WORKFLOW_REGISTRY, engines)

    unknown = resolver.resolve("2d_storytelling", selected_engine_id="missing")
    assert unknown.status is WorkflowResolutionStatus.UNKNOWN_ENGINE
    assert unknown.selected_descriptor is None

    unavailable = resolver.resolve("2d_storytelling", selected_engine_id="offline-engine")
    assert unavailable.status is WorkflowResolutionStatus.ENGINE_UNAVAILABLE
    assert unavailable.selected_descriptor is None


def test_resolver_reports_unknown_workflow_and_invalid_requirements():
    resolver = WorkflowResolver(BUILTIN_WORKFLOW_REGISTRY, EngineRegistry((_engine(),)))
    unknown = resolver.resolve("not-a-workflow")
    assert unknown.status is WorkflowResolutionStatus.UNKNOWN_WORKFLOW

    invalid = resolver.resolve("2d_storytelling", style_tags="flat_vector")
    assert invalid.status is WorkflowResolutionStatus.ENGINE_INCOMPATIBLE
    assert "Invalid workflow requirements" in invalid.diagnostics[0]


def test_engine_workflow_families_are_validated_and_default_empty():
    assert EngineCapabilities().workflow_families == ()
    with pytest.raises(ValueError, match="workflow_families"):
        EngineCapabilities(workflow_families=("2d", "2d"))
    with pytest.raises(ValueError, match="workflow_families"):
        EngineCapabilities(workflow_families=(" ",))
