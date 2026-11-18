from __future__ import annotations

import pytest

from app.universal.capability_resolution import (
    DiagnosticSeverity,
    EngineCapabilityResolver,
    EngineResourceContext,
)
from app.universal.engines import EngineCapabilities, EngineDescriptor, EngineRegistry


def descriptor(engine_id="ffmpeg", *, available=True, caps=None):
    return EngineDescriptor(
        engine_id=engine_id,
        display_name=engine_id,
        version="1",
        capabilities=caps or EngineCapabilities(
            scene_kinds=("image",),
            style_tags=("documentary",),
            asset_kinds=("image",),
            output_formats=("mp4",),
            estimated_memory_mb=1024,
            max_concurrent_jobs=1,
        ),
        available=available,
        unavailable_reason="dependency missing" if not available else "",
    )


def make_registry():
    return EngineRegistry([
        descriptor(),
        descriptor("alternate"),
        descriptor("offline", available=False),
        descriptor("gpu-only", caps=EngineCapabilities(
            scene_kinds=("image",),
            style_tags=("documentary",),
            asset_kinds=("image",),
            output_formats=("mp4",),
            requires_gpu=True,
            estimated_memory_mb=4096,
            max_concurrent_jobs=1,
        )),
    ])


def test_exact_engine_is_inspected_without_silent_substitution():
    resolver = EngineCapabilityResolver(make_registry())
    result = resolver.resolve("missing", scene_kind="image")

    assert result.status == "unknown_engine"
    assert result.selected_descriptor is None
    assert [item.engine_id for item in result.compatible_candidates] == [
        "alternate", "ffmpeg", "gpu-only"
    ]
    assert result.diagnostics[0].code == "engine.unknown"


def test_unavailable_engine_has_structured_diagnostic_and_keeps_alternatives():
    result = EngineCapabilityResolver(make_registry()).resolve(
        "offline", scene_kind="image"
    )

    assert result.status == "unavailable"
    assert result.selected_descriptor is None
    assert result.diagnostics[0].code == "engine.unavailable"
    assert "dependency missing" in result.diagnostics[0].message
    assert result.compatible_candidates


def test_incompatible_engine_reports_each_missing_requirement():
    result = EngineCapabilityResolver(make_registry()).resolve(
        "ffmpeg", scene_kind="scientific_3d", style_tags=("cinematic",)
    )

    assert result.status == "incompatible"
    assert result.selected_descriptor is None
    assert {item.requirement for item in result.diagnostics} == {
        "scene_kind", "style_tag"
    }
    assert all(item.severity is DiagnosticSeverity.ERROR for item in result.diagnostics)


def test_missing_selection_returns_candidates_but_does_not_choose():
    result = EngineCapabilityResolver(make_registry()).resolve(
        None, scene_kind="image"
    )

    assert result.status == "selection_required"
    assert result.selected_descriptor is None
    assert result.diagnostics[0].severity is DiagnosticSeverity.INFO
    assert result.compatible_candidates


def test_resource_estimates_are_advisory_and_do_not_change_compatibility():
    result = EngineCapabilityResolver(make_registry()).resolve(
        "gpu-only",
        scene_kind="image",
        resource_context=EngineResourceContext(
            available_memory_mb=1024,
            gpu_available=False,
            requested_concurrency=2,
        ),
    )

    assert result.status == "compatible"
    assert result.selected_descriptor.engine_id == "gpu-only"
    assert result.resource_assessment.status == "warning"
    codes = {item.code for item in result.resource_assessment.diagnostics}
    assert codes == {
        "resource.gpu_unavailable",
        "resource.memory_estimate_exceeds_available",
        "resource.concurrency_exceeds_declared_limit",
    }


def test_unknown_resource_context_is_reported_without_hardware_probing():
    result = EngineCapabilityResolver(make_registry()).resolve(
        "ffmpeg", scene_kind="image"
    )

    assert result.status == "compatible"
    assert result.resource_assessment.status == "unknown"
    assert "resource.memory_capacity_unknown" in {
        item.code for item in result.resource_assessment.diagnostics
    }


def test_resource_context_validation_is_strict():
    with pytest.raises(ValueError):
        EngineResourceContext(available_memory_mb=True)
    with pytest.raises(ValueError):
        EngineResourceContext(gpu_available="yes")
    with pytest.raises(ValueError):
        EngineResourceContext(requested_concurrency=0)


def test_resource_warning_never_mutates_registry_or_selects_alternative():
    registry = make_registry()
    before = registry.list_engines(include_unavailable=True)
    result = EngineCapabilityResolver(registry).resolve(
        "gpu-only",
        scene_kind="image",
        resource_context=EngineResourceContext(
            available_memory_mb=128, gpu_available=False
        ),
    )

    assert result.selected_descriptor.engine_id == "gpu-only"
    assert registry.list_engines(include_unavailable=True) == before
