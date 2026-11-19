import threading
from pathlib import Path

import pytest

from app.universal.asset_library import VisualAssetLibrary
from app.universal.visual_generation import (
    VisualGenerationProviderCapabilities,
    VisualGenerationProviderDescriptor,
    VisualGenerationRequest,
)
from app.universal.visual_generation_runtime import (
    VisualGenerationCancelled,
    VisualGenerationProgress,
    VisualGenerationRuntime,
    VisualGenerationRuntimeError,
)


def request(**overrides):
    values = {
        "request_id": "runtime-01",
        "scene_id": "scene-01",
        "prompt": "A quiet observatory beneath the stars",
        "width": 256,
        "height": 256,
        "image_count": 1,
        "output_format": "png",
    }
    values.update(overrides)
    return VisualGenerationRequest(**values)


def descriptor(**overrides):
    values = {
        "provider_id": "fake-local",
        "display_name": "Fake Local Provider",
        "version": "1",
        "capabilities": VisualGenerationProviderCapabilities(
            output_formats=("png",), max_width=512, max_height=512,
            max_images_per_request=2, requires_network=False, requires_api_key=False,
        ),
        "available": True,
        "unavailable_reason": "",
    }
    values.update(overrides)
    return VisualGenerationProviderDescriptor(**values)


def png_bytes(width=2, height=2):
    import struct
    import zlib
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00\x00\x00")) + chunk(b"IEND", b"")


class FakeProvider:
    def __init__(self, *, output_count=1, outside=False, cancel=False):
        self.descriptor = descriptor()
        self.output_count = output_count
        self.outside = outside
        self.cancel = cancel

    def generate(self, request, output_dir, cancel_event, progress):
        if self.cancel:
            cancel_event.set()
        paths = []
        for index in range(self.output_count):
            path = (output_dir.parent / "escape.png") if self.outside else (output_dir / f"image-{index}.png")
            path.write_bytes(png_bytes())
            paths.append(path)
        progress(len(paths), request.image_count, "fake complete")
        return paths


def test_runtime_generates_and_imports_content_addressed_asset(tmp_path):
    library = VisualAssetLibrary(tmp_path / "library")
    events = []
    runtime = VisualGenerationRuntime(library, [FakeProvider()], max_output_bytes=1024)
    result = runtime.generate(request(), "fake-local", progress=events.append)

    assert len(result.assets) == 1
    asset = result.assets[0]
    assert asset.kind == "generated-image"
    assert asset.provenance.source == "generated:fake-local"
    assert library.verify_asset(asset)
    assert any(isinstance(event, VisualGenerationProgress) and event.stage == "completed" for event in events)
    assert not list((library.root / ".generation-staging").iterdir())


def test_network_provider_requires_explicit_consent(tmp_path):
    provider = FakeProvider()
    provider.descriptor = descriptor(capabilities=VisualGenerationProviderCapabilities(
        output_formats=("png",), requires_network=True, requires_api_key=False,
    ))
    runtime = VisualGenerationRuntime(VisualAssetLibrary(tmp_path / "library"), [provider])
    with pytest.raises(VisualGenerationRuntimeError, match="network consent"):
        runtime.generate(request(), "fake-local")


def test_api_key_provider_requires_explicit_consent(tmp_path):
    provider = FakeProvider()
    provider.descriptor = descriptor(capabilities=VisualGenerationProviderCapabilities(
        output_formats=("png",), requires_network=False, requires_api_key=True,
    ))
    runtime = VisualGenerationRuntime(VisualAssetLibrary(tmp_path / "library"), [provider])
    with pytest.raises(VisualGenerationRuntimeError, match="API-key consent"):
        runtime.generate(request(), "fake-local")


def test_cancelled_request_never_imports_output(tmp_path):
    library = VisualAssetLibrary(tmp_path / "library")
    runtime = VisualGenerationRuntime(library, [FakeProvider(cancel=True)])
    with pytest.raises(VisualGenerationCancelled):
        runtime.generate(request(), "fake-local")
    assert library.load_catalog().assets == ()


def test_provider_cannot_return_path_outside_staging(tmp_path):
    runtime = VisualGenerationRuntime(VisualAssetLibrary(tmp_path / "library"), [FakeProvider(outside=True)])
    with pytest.raises(VisualGenerationRuntimeError, match="inside its staging"):
        runtime.generate(request(), "fake-local")


def test_provider_must_return_exact_requested_image_count(tmp_path):
    runtime = VisualGenerationRuntime(VisualAssetLibrary(tmp_path / "library"), [FakeProvider(output_count=2)])
    with pytest.raises(VisualGenerationRuntimeError, match="expected 1"):
        runtime.generate(request(), "fake-local")


def test_incompatible_request_is_reported_as_structured_error(tmp_path):
    runtime = VisualGenerationRuntime(VisualAssetLibrary(tmp_path / "library"), [FakeProvider()])
    with pytest.raises(VisualGenerationRuntimeError) as error:
        runtime.generate(request(width=1024), "fake-local")
    assert error.value.code == "incompatible_request"


def test_unknown_provider_has_stable_error_code(tmp_path):
    runtime = VisualGenerationRuntime(VisualAssetLibrary(tmp_path / "library"))
    with pytest.raises(VisualGenerationRuntimeError) as error:
        runtime.generate(request(), "missing")
    assert error.value.code == "provider_unavailable"
