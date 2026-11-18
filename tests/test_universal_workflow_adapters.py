import pytest

from app.universal.adapters.workflows import (
    DocumentaryWorkflowAdapter,
    TwoDStorytellingAdapter,
    WorkflowAdapterCompatibilityError,
)
from app.universal.engines import EngineCapabilities, EngineDescriptor
from app.universal.normalizer import SegmentOutputSpec
from app.universal.requests import EngineRenderRequest, RawEngineOutput
from app.universal.runtime import EngineRuntimeRegistry


class FakeEngine:
    def __init__(self, descriptor, output):
        self.descriptor = descriptor
        self.output = output
        self.calls = []

    def render(self, request, *, on_progress=None, cancel=None):
        self.calls.append((request, on_progress, cancel))
        return self.output


def make_descriptor(engine_id, family):
    return EngineDescriptor(
        engine_id=engine_id,
        display_name=engine_id,
        version="test",
        capabilities=EngineCapabilities(
            scene_kinds=("image",),
            style_tags=("cinematic",),
            asset_kinds=("image",),
            output_formats=("mp4",),
            workflow_families=(family,),
        ),
    )


def make_request(tmp_path):
    return EngineRenderRequest(
        scene_id="scene-1",
        scene_kind="image",
        output_format="mp4",
        output_spec=SegmentOutputSpec(2.0, 640, 360, 30),
        destination=tmp_path / "normalized.mp4",
        style_tags=("cinematic",),
    )


@pytest.mark.parametrize(
    ("adapter_type", "engine_id", "family"),
    [
        (TwoDStorytellingAdapter, "two-d-engine", "2d"),
        (DocumentaryWorkflowAdapter, "doc-engine", "documentary"),
    ],
)
def test_workflow_adapter_delegates_exact_request_and_tags_output(
    tmp_path, adapter_type, engine_id, family
):
    descriptor = make_descriptor(engine_id, family)
    raw_path = tmp_path / f"{engine_id}.raw.mp4"
    raw_path.write_bytes(b"video")
    engine = FakeEngine(descriptor, RawEngineOutput(raw_path, {"codec": "h264"}))
    runtime = EngineRuntimeRegistry()
    runtime.register(descriptor, engine)
    adapter = adapter_type(runtime, engine_id)
    request = make_request(tmp_path)
    progress = lambda value: value
    cancel = object()

    output = adapter.render(request, on_progress=progress, cancel=cancel)

    assert engine.calls == [(request, progress, cancel)]
    assert output.path == raw_path
    assert output.metadata["codec"] == "h264"
    assert output.metadata["workflow_id"] == adapter.workflow_id
    assert output.metadata["workflow_engine_id"] == engine_id


def test_workflow_adapter_rejects_engine_without_declared_family():
    runtime = EngineRuntimeRegistry()
    descriptor = make_descriptor("wrong-family", "documentary")
    runtime.metadata.register(descriptor)

    with pytest.raises(WorkflowAdapterCompatibilityError, match="does not declare"):
        TwoDStorytellingAdapter(runtime, "wrong-family")


def test_workflow_adapter_does_not_fallback_to_another_engine(tmp_path):
    runtime = EngineRuntimeRegistry()
    doc_descriptor = make_descriptor("doc-only", "documentary")
    doc_path = tmp_path / "doc.raw.mp4"
    doc_path.write_bytes(b"doc")
    runtime.register(doc_descriptor, FakeEngine(doc_descriptor, RawEngineOutput(doc_path)))

    with pytest.raises(WorkflowAdapterCompatibilityError):
        TwoDStorytellingAdapter(runtime, "doc-only")


def test_workflow_adapter_rejects_invalid_request(tmp_path):
    descriptor = make_descriptor("two-d-engine", "2d")
    raw_path = tmp_path / "raw.mp4"
    raw_path.write_bytes(b"video")
    runtime = EngineRuntimeRegistry()
    runtime.register(descriptor, FakeEngine(descriptor, RawEngineOutput(raw_path)))
    adapter = TwoDStorytellingAdapter(runtime, "two-d-engine")

    with pytest.raises(TypeError, match="EngineRenderRequest"):
        adapter.render(object())
