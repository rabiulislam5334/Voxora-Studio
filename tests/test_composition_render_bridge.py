from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.project import Project
from app.models.scene import Scene
from app.universal.composition import (
    CompositionCanvas, CompositionElement, SceneComposition, VisualTransform,
)
from app.universal.composition_render_bridge import (
    CompositionRenderApprovalError,
    CompositionRenderBridge,
    CompositionRenderBridgeError,
    CompositionRenderCapabilities,
    CompositionRenderUnsupportedError,
)
from app.universal.composition_workflow import preview_scene_composition
from app.universal.engines import EngineCapabilities, EngineDescriptor
from app.universal.models import AssetRef, ScenePlan


def make_project(asset_path):
    plan = ScenePlan(
        scene_id="scene-1",
        asset_refs=[AssetRef("asset-1", "image", path=str(asset_path))],
    )
    return Project(
        id="project-1",
        name="Composition bridge",
        scenes=[Scene(id="scene-1", title="Scene 1", text="Narration", order=0)],
        settings={"universal": {
            "format_version": 1,
            "profile_id": None,
            "scene_plans": {"scene-1": plan.to_dict()},
        }},
    )


def make_composition():
    return SceneComposition(
        composition_id="composition-1",
        scene_id="scene-1",
        canvas=CompositionCanvas(640, 360),
        elements=(CompositionElement(
            element_id="element-1",
            asset_id="asset-1",
            transform=VisualTransform(x=0.1, y=0.1, width=0.8, height=0.8),
        ),),
    )


class FakeCompositionRenderer:
    def __init__(self, *, engine_id="fake-compositor", capabilities=None):
        self.descriptor = EngineDescriptor(
            engine_id=engine_id,
            display_name="Fake compositor",
            version="test",
            capabilities=EngineCapabilities(
                scene_kinds=("image",), asset_kinds=("image",), output_formats=("mp4",)
            ),
        )
        self.composition_capabilities = capabilities or CompositionRenderCapabilities()
        self.calls = []

    def render_composition(
        self, composition, *, asset_paths, destination, output_format,
        on_progress=None, cancel=None,
    ):
        self.calls.append((composition, dict(asset_paths), output_format))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-rendered-composition")
        if on_progress:
            on_progress(1.0)
        return destination


def test_ffmpeg_segment_engine_is_not_assumed_to_support_compositions():
    bridge = CompositionRenderBridge()
    result = bridge.inspect("ffmpeg")
    assert not result.supported
    assert "No composition renderer" in result.reason


def test_renderer_must_be_registered_under_exact_engine_id():
    renderer = FakeCompositionRenderer()
    bridge = CompositionRenderBridge({"other-id": renderer})
    result = bridge.inspect("other-id")
    assert not result.supported
    assert "does not match" in result.reason


def test_renderer_must_declare_layer_and_transform_support():
    renderer = FakeCompositionRenderer(capabilities=CompositionRenderCapabilities(
        supports_layers=False,
    ))
    result = CompositionRenderBridge({"fake-compositor": renderer}).inspect("fake-compositor")
    assert not result.supported
    assert "layered composition and element transforms" in result.reason


def test_declared_composition_renderer_is_supported():
    renderer = FakeCompositionRenderer()
    result = CompositionRenderBridge({"fake-compositor": renderer}).inspect("fake-compositor")
    assert result.supported
    assert result.output_formats == ("mp4",)


def test_render_requires_explicit_approval(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    bridge = CompositionRenderBridge({"fake-compositor": FakeCompositionRenderer()})

    with pytest.raises(CompositionRenderApprovalError):
        bridge.render(
            "fake-compositor", project, composition, preview,
            asset_paths={"asset-1": asset}, destination=tmp_path / "out.mp4",
        )


def test_render_invokes_only_declared_adapter_and_checks_output(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")
    destination = tmp_path / "out.mp4"
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    renderer = FakeCompositionRenderer()
    bridge = CompositionRenderBridge({"fake-compositor": renderer})

    output = bridge.render(
        "fake-compositor", project, composition, preview,
        asset_paths={"asset-1": asset}, destination=destination, approved=True,
    )

    assert output == destination
    assert output.read_bytes() == b"fake-rendered-composition"
    assert len(renderer.calls) == 1


def test_unsupported_engine_never_falls_back_or_creates_output(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    destination = tmp_path / "out.mp4"
    bridge = CompositionRenderBridge({"fake-compositor": FakeCompositionRenderer()})

    with pytest.raises(CompositionRenderUnsupportedError):
        bridge.render(
            "ffmpeg", project, composition, preview,
            asset_paths={"asset-1": asset}, destination=destination, approved=True,
        )
    assert not destination.exists()


def test_render_rejects_stale_preview(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    project.scenes[0].title = "Changed"
    renderer = FakeCompositionRenderer()
    bridge = CompositionRenderBridge({"fake-compositor": renderer})

    with pytest.raises(CompositionRenderBridgeError, match="stale"):
        bridge.render(
            "fake-compositor", project, composition, preview,
            asset_paths={"asset-1": asset}, destination=tmp_path / "out.mp4", approved=True,
        )
    assert renderer.calls == []


def test_render_requires_exact_visible_asset_set(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    bridge = CompositionRenderBridge({"fake-compositor": FakeCompositionRenderer()})

    with pytest.raises(CompositionRenderBridgeError, match="exactly"):
        bridge.render(
            "fake-compositor", project, composition, preview,
            asset_paths={}, destination=tmp_path / "out.mp4", approved=True,
        )


def test_render_rejects_missing_asset_file(tmp_path):
    asset = tmp_path / "asset.png"
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    bridge = CompositionRenderBridge({"fake-compositor": FakeCompositionRenderer()})

    with pytest.raises(CompositionRenderBridgeError, match="regular local file"):
        bridge.render(
            "fake-compositor", project, composition, preview,
            asset_paths={"asset-1": asset}, destination=tmp_path / "out.mp4", approved=True,
        )


def test_render_rejects_undeclared_output_format(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")
    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    renderer = FakeCompositionRenderer(capabilities=CompositionRenderCapabilities(
        output_formats=("webm",),
    ))
    bridge = CompositionRenderBridge({"fake-compositor": renderer})

    with pytest.raises(CompositionRenderUnsupportedError, match="does not declare"):
        bridge.render(
            "fake-compositor", project, composition, preview,
            asset_paths={"asset-1": asset}, destination=tmp_path / "out.mp4",
            output_format="mp4", approved=True,
        )


def test_renderer_output_must_match_requested_destination(tmp_path):
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"image")

    class WrongDestinationRenderer(FakeCompositionRenderer):
        def render_composition(self, composition, *, asset_paths, destination,
                               output_format, on_progress=None, cancel=None):
            other = destination.with_name("wrong.mp4")
            other.write_bytes(b"wrong")
            return other

    project = make_project(asset)
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    bridge = CompositionRenderBridge({"fake-compositor": WrongDestinationRenderer()})

    with pytest.raises(CompositionRenderBridgeError, match="exact requested destination"):
        bridge.render(
            "fake-compositor", project, composition, preview,
            asset_paths={"asset-1": asset}, destination=tmp_path / "out.mp4", approved=True,
        )
