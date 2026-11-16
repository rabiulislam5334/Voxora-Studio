from __future__ import annotations

import math

import pytest

from app.core.exceptions import GenerationCancelled
from app.universal.engines import EngineCapabilities, EngineDescriptor, EngineRegistry
from app.universal.execution import (
    SceneEngineExecutionError,
    SceneExecutionContext,
    SceneExecutionCoordinator,
    SceneExecutionValidationError,
    SceneNormalizationError,
    ScenePlanResolutionError,
)
from app.universal.models import AssetRef, EngineChoice, ScenePlan
from app.universal.normalizer import NormalizedSegment, SegmentOutputSpec
from app.universal.plan_resolver import EnginePlanResolver
from app.universal.requests import RawEngineOutput
from app.universal.runtime import EngineRuntimeRegistry
from pathlib import Path


def descriptor(engine_id="selected", *, available=True):
    return EngineDescriptor(
        engine_id,
        engine_id,
        "1",
        EngineCapabilities(
            scene_kinds=("documentary",),
            style_tags=("sketch",),
            asset_kinds=("image",),
            output_formats=("mp4",),
        ),
        available=available,
        unavailable_reason="not installed" if not available else "",
    )


def scene(**overrides):
    values = {
        "scene_id": "scene-42",
        "kind": "documentary",
        "style_tags": ["sketch"],
        "requirements": {"output_format": "mp4"},
        "engine_choice": EngineChoice("selected", fallback_chain=["alternative"]),
        "asset_refs": [AssetRef("asset-1", "image", path="source.png")],
    }
    values.update(overrides)
    return ScenePlan(**values)


class FakeAdapter:
    def __init__(self, engine_descriptor, output, events):
        self.descriptor = engine_descriptor
        self.output = output
        self.events = events
        self.request = None
        self.progress = None
        self.cancel = None

    def render(self, request, *, on_progress=None, cancel=None):
        self.events.append("render")
        self.request = request
        self.progress = on_progress
        self.cancel = cancel
        if on_progress:
            on_progress(0.5)
            on_progress(1.0)
        return self.output


class FakeNormalizer:
    def __init__(self, normalized, events):
        self.normalized = normalized
        self.events = events
        self.args = None
        self.progress = None
        self.cancel = None
        self.error = None

    def normalize(self, source, destination, spec, *, on_progress=None, cancel=None):
        self.events.append("normalize")
        self.args = (source, destination, spec)
        self.progress = on_progress
        self.cancel = cancel
        if on_progress:
            on_progress(0.0)
            on_progress(0.5)
            on_progress(1.0)
        if self.error:
            raise self.error
        return self.normalized


@pytest.fixture
def setup(tmp_path):
    events = []
    raw_path = tmp_path / "raw.webm"
    raw_path.write_bytes(b"fake raw bytes")
    raw = RawEngineOutput(raw_path, {"source": "fake"})
    destination = tmp_path / "normalized.mp4"
    spec = SegmentOutputSpec(4.0, 1280, 720, 30)
    normalized = NormalizedSegment(destination, 4.0, 1280, 720, 30)
    selected = descriptor()
    adapter = FakeAdapter(selected, raw, events)
    alternative = descriptor("alternative")
    created = []
    runtime = EngineRuntimeRegistry()
    runtime.register(selected, lambda: (created.append("selected"), adapter)[1])
    runtime.register(alternative, lambda: (created.append("alternative"), adapter)[1])
    resolver = EnginePlanResolver(runtime.metadata)
    normalizer = FakeNormalizer(normalized, events)
    coordinator = SceneExecutionCoordinator(resolver, runtime, normalizer)
    context = SceneExecutionContext(spec, destination, {"quality": "draft"})
    return coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created


def test_executes_exact_selected_engine_then_normalizes(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    progress = []
    cancel = object()

    result = coordinator.execute(scene(), context, on_progress=progress.append, cancel=cancel)

    assert events == ["render", "normalize"]
    assert created == ["selected"]
    assert result.scene_id == "scene-42"
    assert result.engine_id == "selected"
    assert result.raw_output is raw
    assert result.normalized is normalized
    assert adapter.request.scene_id == "scene-42"
    assert adapter.request.scene_kind == "documentary"
    assert adapter.request.style_tags == ("sketch",)
    assert adapter.request.asset_refs[0].asset_id == "asset-1"
    assert adapter.request.output_format == "mp4"
    assert adapter.request.output_spec == context.output_spec
    assert adapter.request.destination == context.destination
    assert adapter.request.engine_params["quality"] == "draft"
    assert adapter.cancel is cancel
    assert normalizer.args == (raw.path, context.destination, context.output_spec)
    assert normalizer.cancel is cancel
    assert progress[-1] == 1.0
    assert progress == sorted(progress)
    assert max(progress[:-1]) < 1.0


@pytest.mark.parametrize(
    "invalid_plan",
    [
        scene(engine_choice=EngineChoice()),
        scene(engine_choice=EngineChoice("missing")),
        scene(engine_choice=EngineChoice("offline")),
        scene(kind="scientific_3d"),
        scene(requirements={"output_format": "mp4", "unsupported": True}),
    ],
)
def test_resolution_failures_do_not_initialize_adapters(setup, invalid_plan):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    offline = descriptor("offline", available=False)
    runtime.metadata.register(offline)

    with pytest.raises(ScenePlanResolutionError) as error:
        coordinator.execute(invalid_plan, context)

    assert error.value.resolution.diagnostics
    assert created == []
    assert events == []


def test_missing_output_format_is_rejected_without_rendering(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    with pytest.raises(SceneExecutionValidationError, match="output_format"):
        coordinator.execute(scene(requirements={}), context)
    assert created == []
    assert events == []


def test_runtime_receives_progress_callback_and_same_cancel_token(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    cancel = object()
    coordinator.execute(scene(), context, on_progress=lambda value: None, cancel=cancel)
    assert callable(adapter.progress)
    assert adapter.cancel is cancel
    assert callable(normalizer.progress)
    assert normalizer.cancel is cancel


def test_progress_values_are_mapped_monotonically_and_observer_errors_are_ignored(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    seen = []

    def observer(value):
        seen.append(value)
        if value < 1.0:
            raise RuntimeError("UI disappeared")

    coordinator.execute(scene(), context, on_progress=observer)
    assert seen == sorted(seen)
    assert seen[-1] == 1.0
    assert max(seen[:-1]) < 1.0
    assert all(0.0 <= value <= 1.0 for value in seen)


def test_invalid_progress_values_are_ignored_and_never_break_execution(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    # Replace fake callbacks with deliberately malformed progress emissions.
    def malformed_render(request, *, on_progress=None, cancel=None):
        if on_progress:
            for value in (float("nan"), float("inf"), "bad", True, -10, 10):
                on_progress(value)
        return raw

    adapter = adapter
    adapter.render = malformed_render
    values = []
    coordinator.execute(scene(), context, on_progress=values.append)
    assert values == [0.0, 0.8, 0.8, 0.9, 0.999999, 1.0]


def test_adapter_error_is_wrapped_with_original_cause(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    cause = RuntimeError("adapter broke")

    def fail(*args, **kwargs):
        raise cause

    adapter.render = fail
    with pytest.raises(SceneEngineExecutionError) as error:
        coordinator.execute(scene(), context)
    assert error.value.__cause__ is cause
    assert events == []


def test_normalizer_error_is_wrapped_and_raw_output_is_preserved(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    cause = RuntimeError("normalization broke")
    normalizer.error = cause
    with pytest.raises(SceneNormalizationError) as error:
        coordinator.execute(scene(), context)
    assert error.value.__cause__ is cause
    assert raw.path.is_file()


@pytest.mark.parametrize("stage", ["render", "normalize"])
def test_cancellation_propagates_without_success_result(setup, stage):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    if stage == "render":
        adapter.render = lambda *args, **kwargs: (_ for _ in ()).throw(
            GenerationCancelled("cancelled during render")
        )
    else:
        normalizer.error = GenerationCancelled("cancelled during normalize")
    with pytest.raises(GenerationCancelled):
        coordinator.execute(scene(), context)
    assert raw.path.is_file()


def test_context_is_immutable_and_input_plan_is_not_mutated(setup):
    coordinator, runtime, adapter, normalizer, context, raw, normalized, events, created = setup
    plan = scene()
    before = plan.to_dict()
    coordinator.execute(plan, context)
    assert plan.to_dict() == before
    with pytest.raises(TypeError):
        context.engine_params["quality"] = "final"


def test_context_validates_inputs(tmp_path):
    with pytest.raises(TypeError):
        SceneExecutionContext(None, tmp_path / "out.mp4")
    with pytest.raises(ValueError):
        SceneExecutionContext(SegmentOutputSpec(1, 640, 360, 24), "")
    with pytest.raises(TypeError):
        SceneExecutionContext(SegmentOutputSpec(1, 640, 360, 24), tmp_path / "out.mp4", [])


def test_constructor_validates_dependencies():
    with pytest.raises(TypeError):
        SceneExecutionCoordinator(object(), object(), object())
