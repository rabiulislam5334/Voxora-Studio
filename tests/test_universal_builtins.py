from types import SimpleNamespace

import pytest

from app.universal.builtins import BUILTIN_ENGINE_IDS, build_builtin_engine_runtime_registry
from app.universal.engines import EngineUnavailableError


class FakeFFmpeg:
    def __init__(self, available=True, message="FFmpeg ready"):
        self.available = available
        self.message = message
        self.detect_calls = 0
        self.status = None

    def detect(self):
        self.detect_calls += 1
        self.status = SimpleNamespace(available=self.available, message=self.message)
        return self.status


def test_builtin_registry_registers_ffmpeg_and_keeps_adapter_lazy():
    ffmpeg = FakeFFmpeg()
    registry = build_builtin_engine_runtime_registry(ffmpeg, probe_availability=True)

    assert ffmpeg.detect_calls == 1
    assert tuple(item.engine_id for item in registry.list_engines()) == BUILTIN_ENGINE_IDS
    assert registry.list_engines()[0].available is True
    assert registry.resolve("ffmpeg").descriptor.engine_id == "ffmpeg"


def test_unavailable_ffmpeg_remains_visible_with_reason_and_never_binds():
    ffmpeg = FakeFFmpeg(available=False, message="FFmpeg executable not found")
    registry = build_builtin_engine_runtime_registry(ffmpeg, probe_availability=True)

    descriptor = registry.list_engines(include_unavailable=True)[0]
    assert descriptor.engine_id == "ffmpeg"
    assert descriptor.available is False
    assert descriptor.unavailable_reason == "FFmpeg executable not found"
    assert registry.list_engines() == ()

    with pytest.raises(EngineUnavailableError, match="FFmpeg executable not found"):
        registry.resolve("ffmpeg")


def test_availability_probe_failure_becomes_explicit_unavailable_reason():
    class BrokenFFmpeg:
        status = None

        def detect(self):
            raise RuntimeError("verification process failed")

    registry = build_builtin_engine_runtime_registry(BrokenFFmpeg())
    descriptor = registry.list_engines(include_unavailable=True)[0]

    assert descriptor.available is False
    assert "verification process failed" in descriptor.unavailable_reason


def test_repeated_initialization_is_deterministic_and_has_no_duplicate_ids():
    first = build_builtin_engine_runtime_registry(FakeFFmpeg(), probe_availability=True)
    second = build_builtin_engine_runtime_registry(FakeFFmpeg(), probe_availability=True)

    first_ids = tuple(item.engine_id for item in first.list_engines(include_unavailable=True))
    second_ids = tuple(item.engine_id for item in second.list_engines(include_unavailable=True))

    assert first_ids == second_ids == BUILTIN_ENGINE_IDS
    assert len(first_ids) == len(set(first_ids)) == 1


def test_unverified_dependency_is_unavailable_without_starting_probe():
    ffmpeg = FakeFFmpeg()
    registry = build_builtin_engine_runtime_registry(ffmpeg)
    descriptor = registry.list_engines(include_unavailable=True)[0]

    assert ffmpeg.detect_calls == 0
    assert descriptor.available is False
    assert "not been verified" in descriptor.unavailable_reason
