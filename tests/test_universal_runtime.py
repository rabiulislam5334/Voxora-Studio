from pathlib import Path

import pytest

from app.universal.engines import (
    EngineCapabilities,
    EngineDescriptor,
    EngineUnavailableError,
    UnknownEngineError,
)
from app.universal.models import AssetRef
from app.universal.normalizer import SegmentOutputSpec
from app.universal.requests import EngineRenderRequest, RawEngineOutput
from app.universal.runtime import (
    EngineBindingError,
    EngineInitializationError,
    EngineRenderError,
    EngineRuntimeRegistry,
)


def descriptor(engine_id="fake", **capability_overrides):
    caps = EngineCapabilities(
        scene_kinds=("documentary",),
        style_tags=("cinematic",),
        asset_kinds=("image",),
        output_formats=("webm",),
        supports_draft_render=True,
    )
    if capability_overrides:
        values = {
            "scene_kinds": caps.scene_kinds,
            "style_tags": caps.style_tags,
            "asset_kinds": caps.asset_kinds,
            "output_formats": caps.output_formats,
            "supports_draft_render": caps.supports_draft_render,
        }
        values.update(capability_overrides)
        caps = EngineCapabilities(**values)
    return EngineDescriptor(engine_id, engine_id.title(), "1.0", caps)


class FakeAdapter:
    def __init__(self, engine_descriptor, output):
        self.descriptor = engine_descriptor
        self.output = output
        self.calls = []

    def render(self, request, *, on_progress=None, cancel=None):
        self.calls.append((request, on_progress, cancel))
        return self.output


def request(tmp_path, **overrides):
    values = {
        "scene_id": "scene-1",
        "scene_kind": "documentary",
        "output_format": "webm",
        "output_spec": SegmentOutputSpec(2.0, 640, 360, 30),
        "destination": tmp_path / "normalized.mp4",
        "style_tags": ("cinematic",),
        "asset_refs": (AssetRef("asset-1", "image", path="scene.png"),),
        "engine_params": {"quality": "draft"},
    }
    values.update(overrides)
    return EngineRenderRequest(**values)


def test_request_validates_and_freezes_collections(tmp_path):
    item = request(tmp_path)
    assert item.destination == tmp_path / "normalized.mp4"
    assert item.style_tags == ("cinematic",)
    assert item.engine_params["quality"] == "draft"
    with pytest.raises(TypeError):
        item.engine_params["quality"] = "final"


@pytest.mark.parametrize("kwargs", [
    {"scene_id": ""},
    {"scene_kind": ""},
    {"output_format": ""},
    {"output_spec": None},
    {"destination": ""},
    {"style_tags": "cinematic"},
    {"asset_refs": ("not-an-asset",)},
])
def test_request_rejects_invalid_values(tmp_path, kwargs):
    values = {
        "scene_id": "scene-1",
        "scene_kind": "documentary",
        "output_format": "webm",
        "output_spec": SegmentOutputSpec(2.0, 640, 360, 30),
        "destination": tmp_path / "out.mp4",
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        EngineRenderRequest(**values)


def test_factory_is_lazy_and_render_forwards_progress_and_cancel(tmp_path):
    raw = tmp_path / "raw.webm"
    raw.write_bytes(b"raw-video")
    output = RawEngineOutput(raw, {"container": "webm"})
    adapter = FakeAdapter(descriptor(), output)
    created = []
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, lambda: (created.append(True), adapter)[1])
    assert created == []
    progress = lambda value: value
    cancel = object()
    result = registry.render("fake", request(tmp_path), on_progress=progress, cancel=cancel)
    assert result is output
    assert created == [True]
    assert adapter.calls[0][1] is progress
    assert adapter.calls[0][2] is cancel


def test_instance_binding_executes_exact_adapter(tmp_path):
    raw = tmp_path / "raw.webm"
    raw.write_bytes(b"raw")
    adapter = FakeAdapter(descriptor(), RawEngineOutput(raw))
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, adapter)
    assert registry.resolve("fake") is adapter


def test_duplicate_binding_requires_explicit_replacement(tmp_path):
    adapter = FakeAdapter(descriptor(), RawEngineOutput(tmp_path / "raw.webm"))
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, adapter)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(adapter.descriptor, adapter)


def test_descriptor_id_mismatch_is_rejected_for_instance_binding(tmp_path):
    adapter = FakeAdapter(descriptor("other"), RawEngineOutput(tmp_path / "raw.webm"))
    registry = EngineRuntimeRegistry()
    with pytest.raises(EngineBindingError, match="does not match"):
        registry.register(descriptor("expected"), adapter)


def test_lazy_factory_descriptor_mismatch_is_rejected_on_resolution():
    adapter = FakeAdapter(descriptor("other"), RawEngineOutput("unused.webm"))
    registry = EngineRuntimeRegistry()
    registry.register(descriptor("expected"), lambda: adapter)
    with pytest.raises(EngineBindingError, match="does not match"):
        registry.resolve("expected")


def test_factory_failure_has_engine_context():
    registry = EngineRuntimeRegistry()
    registry.register(descriptor(), lambda: (_ for _ in ()).throw(RuntimeError("missing runtime")))
    with pytest.raises(EngineInitializationError, match="missing runtime"):
        registry.resolve("fake")


def test_metadata_without_runtime_binding_is_explicit_error():
    from app.universal.engines import EngineRegistry
    registry = EngineRuntimeRegistry(EngineRegistry([descriptor()]))
    with pytest.raises(EngineBindingError, match="no runtime binding"):
        registry.resolve("fake")


def test_unknown_and_unavailable_engines_never_fallback():
    registry = EngineRuntimeRegistry()
    with pytest.raises(UnknownEngineError):
        registry.resolve("missing")
    unavailable = EngineDescriptor(
        "offline", "Offline", "1", EngineCapabilities(),
        available=False, unavailable_reason="runtime not installed",
    )
    registry.register(unavailable, lambda: None)
    with pytest.raises(EngineUnavailableError):
        registry.resolve("offline")


def test_incompatible_capabilities_are_rejected_before_adapter_creation():
    created = []
    adapter = FakeAdapter(descriptor(), RawEngineOutput("unused.webm"))
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, lambda: (created.append(True), adapter)[1])
    with pytest.raises(Exception) as error:
        registry.resolve("fake", scene_kind="scientific_3d")
    assert "capabilities" in str(error.value)
    assert created == []


def test_render_rejects_wrong_result_type_and_missing_output(tmp_path):
    class WrongAdapter(FakeAdapter):
        def render(self, request, *, on_progress=None, cancel=None):
            return tmp_path / "not-a-contract"

    registry = EngineRuntimeRegistry()
    wrong = WrongAdapter(descriptor(), None)
    registry.register(wrong.descriptor, wrong)
    with pytest.raises(EngineRenderError, match="RawEngineOutput"):
        registry.render("fake", request(tmp_path))

    missing = FakeAdapter(descriptor(), RawEngineOutput(tmp_path / "missing.webm"))
    registry = EngineRuntimeRegistry()
    registry.register(missing.descriptor, missing)
    with pytest.raises(EngineRenderError, match="missing or empty"):
        registry.render("fake", request(tmp_path))


def test_raw_output_cannot_overwrite_normalized_destination(tmp_path):
    target = tmp_path / "normalized.mp4"
    target.write_bytes(b"existing")
    adapter = FakeAdapter(descriptor(), RawEngineOutput(target))
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, adapter)
    with pytest.raises(EngineRenderError, match="different files"):
        registry.render("fake", request(tmp_path))
