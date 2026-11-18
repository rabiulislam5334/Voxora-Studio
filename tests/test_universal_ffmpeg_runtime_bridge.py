from pathlib import Path

import pytest

from app.universal.adapters.ffmpeg import FFmpegSegmentAdapter
from app.universal.engines import (
    EngineCompatibilityError,
    EngineRuntimeError,
)
from app.universal.normalizer import SegmentOutputSpec
from app.universal.requests import EngineRenderRequest, RawEngineOutput
from app.universal.runtime import EngineRenderError, EngineRuntimeRegistry


class WritingFFmpeg:
    def __init__(self, *, write_output=True, error=None):
        self.write_output = write_output
        self.error = error
        self.calls = []

    def require(self):
        return Path("ffmpeg.exe")

    def run_with_progress(self, args, total_s, on_progress=None, cancel=None):
        self.calls.append((args, total_s, on_progress, cancel))
        if self.write_output:
            Path(args[-1]).write_bytes(b"ffmpeg-rendered-mp4")
        if self.error:
            raise self.error


def make_request(destination, **overrides):
    values = {
        "scene_id": "scene-runtime-1",
        "scene_kind": "blank",
        "output_format": "mp4",
        "output_spec": SegmentOutputSpec(2.0, 640, 360, 30),
        "destination": destination,
    }
    values.update(overrides)
    return EngineRenderRequest(**values)


def test_ffmpeg_adapter_implements_runtime_contract_and_uses_isolated_raw_path(tmp_path):
    final_path = tmp_path / "normalized.mp4"
    final_path.write_bytes(b"existing-final-output")
    ffmpeg = WritingFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)
    request = make_request(final_path)

    result = adapter.render(request)

    assert isinstance(result, RawEngineOutput)
    assert result.path.is_file()
    assert result.path.read_bytes() == b"ffmpeg-rendered-mp4"
    assert result.path != final_path
    assert result.path.parent.resolve() == final_path.parent.resolve()
    assert result.path.suffix == ".mp4"
    assert final_path.read_bytes() == b"existing-final-output"
    assert result.metadata["engine_id"] == "ffmpeg"
    assert result.metadata["engine_version"] == adapter.descriptor.version
    assert result.metadata["container"] == "mp4"
    assert result.metadata["normalization_required"] is True


def test_runtime_registry_executes_ffmpeg_bridge_and_validates_raw_output(tmp_path):
    ffmpeg = WritingFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, adapter)

    result = registry.render("ffmpeg", make_request(tmp_path / "normalized.mp4"))

    assert isinstance(result, RawEngineOutput)
    assert result.path.is_file()
    assert result.path != tmp_path / "normalized.mp4"


def test_runtime_bridge_forwards_progress_and_cancellation_unchanged(tmp_path):
    ffmpeg = WritingFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)
    progress = lambda value: value
    cancel = object()

    adapter.render(
        make_request(tmp_path / "normalized.mp4"),
        on_progress=progress,
        cancel=cancel,
    )

    assert ffmpeg.calls[0][2] is progress
    assert ffmpeg.calls[0][3] is cancel


def test_invalid_ffmpeg_request_is_rejected_before_process_execution(tmp_path):
    ffmpeg = WritingFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)
    request = make_request(
        tmp_path / "normalized.mp4",
        engine_params={"unreviewed_parameter": True},
    )

    with pytest.raises(ValueError, match="unsupported FFmpeg request parameters"):
        adapter.render(request)

    assert ffmpeg.calls == []


def test_runtime_rejects_missing_ffmpeg_raw_output(tmp_path):
    ffmpeg = WritingFFmpeg(write_output=False)
    adapter = FFmpegSegmentAdapter(ffmpeg)
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, adapter)

    with pytest.raises(EngineRenderError, match="missing or empty"):
        registry.render("ffmpeg", make_request(tmp_path / "normalized.mp4"))


def test_failed_ffmpeg_render_removes_partial_raw_artifact(tmp_path):
    ffmpeg = WritingFFmpeg(error=RuntimeError("ffmpeg failed"))
    adapter = FFmpegSegmentAdapter(ffmpeg)

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        adapter.render(make_request(tmp_path / "normalized.mp4"))

    assert list(tmp_path.glob("*.engine-raw.mp4")) == []


def test_runtime_bridge_does_not_overwrite_the_requested_destination(tmp_path):
    final_path = tmp_path / "normalized.mp4"
    final_path.write_bytes(b"keep-me")
    adapter = FFmpegSegmentAdapter(WritingFFmpeg())
    registry = EngineRuntimeRegistry()
    registry.register(adapter.descriptor, adapter)

    raw = registry.render("ffmpeg", make_request(final_path))

    assert final_path.read_bytes() == b"keep-me"
    assert raw.path.resolve() != final_path.resolve()
