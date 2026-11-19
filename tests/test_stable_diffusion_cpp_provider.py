import subprocess
import threading
from pathlib import Path

import pytest

from app.universal.asset_library import VisualAssetLibrary
from app.universal.visual_generation import VisualGenerationRequest
from app.universal.visual_generation_runtime import (
    VisualGenerationCancelled,
    VisualGenerationRuntime,
    VisualGenerationRuntimeError,
)
from app.universal.providers.stable_diffusion_cpp import StableDiffusionCppProvider


def make_request(**overrides):
    values = {
        "request_id": "sdcpp-01",
        "scene_id": "scene-01",
        "prompt": "A quiet observatory beneath the stars",
        "negative_prompt": "blurry, low quality",
        "width": 512,
        "height": 512,
        "output_format": "png",
        "image_count": 1,
        "seed": 42,
    }
    values.update(overrides)
    return VisualGenerationRequest(**values)


def png_bytes():
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def configured_provider(tmp_path, **kwargs):
    executable = tmp_path / "sd-cli.exe"
    model = tmp_path / "sd15.safetensors"
    executable.write_bytes(b"test executable placeholder")
    model.write_bytes(b"test model placeholder")
    return StableDiffusionCppProvider(executable, model, **kwargs)


class CompletedProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.returncode = 0
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(png_bytes())

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def test_provider_runs_local_cli_and_imports_generated_asset(tmp_path, monkeypatch):
    provider = configured_provider(tmp_path)
    commands = []

    def fake_popen(command, **kwargs):
        commands.append(command)
        return CompletedProcess(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    library = VisualAssetLibrary(tmp_path / "library")
    runtime = VisualGenerationRuntime(library, [provider])
    events = []
    result = runtime.generate(make_request(), provider.PROVIDER_ID, progress=events.append)

    assert len(result.assets) == 1
    assert result.assets[0].provenance.source == f"generated:{provider.PROVIDER_ID}"
    assert "--backend" in commands[0]
    assert commands[0][commands[0].index("--backend") + 1] == "cpu"
    assert commands[0][commands[0].index("--seed") + 1] == "42"
    assert any(event.stage == "completed" for event in events)
    assert library.verify_asset(result.assets[0])


def test_provider_is_unavailable_when_executable_or_model_is_missing(tmp_path):
    provider = StableDiffusionCppProvider(tmp_path / "missing.exe", tmp_path / "missing.safetensors")
    assert provider.descriptor.available is False
    assert "executable not found" in provider.descriptor.unavailable_reason
    assert "model file not found" in provider.descriptor.unavailable_reason


def test_provider_rejects_resolution_above_low_memory_profile(tmp_path):
    provider = configured_provider(tmp_path)
    with pytest.raises(VisualGenerationRuntimeError, match="512x512"):
        provider.generate(
            make_request(width=768, height=512), tmp_path, threading.Event(), lambda *_: None
        )


def test_provider_terminates_process_when_cancelled(tmp_path, monkeypatch):
    provider = configured_provider(tmp_path)
    cancel = threading.Event()

    class RunningProcess:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

    process = RunningProcess()

    def fake_popen(*args, **kwargs):
        cancel.set()
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with pytest.raises(VisualGenerationCancelled):
        provider.generate(make_request(), tmp_path, cancel, lambda *_: None)
    assert process.returncode == -15


def test_provider_reports_nonzero_cli_exit(tmp_path, monkeypatch):
    provider = configured_provider(tmp_path)

    class FailedProcess:
        returncode = 2

        def poll(self):
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FailedProcess())
    with pytest.raises(VisualGenerationRuntimeError) as error:
        provider.generate(make_request(), tmp_path, threading.Event(), lambda *_: None)
    assert error.value.code == "provider_process_failed"


def test_provider_validates_configuration(tmp_path):
    executable = tmp_path / "sd-cli"
    model = tmp_path / "model.safetensors"
    executable.touch()
    model.touch()
    with pytest.raises(ValueError):
        StableDiffusionCppProvider(executable, model, threads=0)
    with pytest.raises(ValueError):
        StableDiffusionCppProvider(executable, model, steps=0)
