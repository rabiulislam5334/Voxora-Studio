from pathlib import Path

import pytest
from PIL import Image

from app.models.project import Project
from app.models.scene import Scene
from app.universal.adapters.raster import RasterCompositionAdapter
from app.universal.composition import (
    CompositionCanvas, CompositionElement, SceneComposition, VisualTransform,
)
from app.universal.composition_builtins import (
    BUILTIN_COMPOSITION_RENDERER_IDS, build_builtin_composition_render_bridge,
)
from app.universal.composition_render_bridge import (
    CompositionRenderApprovalError, CompositionRenderBridge,
    CompositionRenderCapabilities, CompositionRenderUnsupportedError,
)
from app.universal.composition_workflow import preview_scene_composition
from app.universal.engines import EngineCapabilities, EngineDescriptor
from app.universal.models import AssetRef, ScenePlan
from app.universal.raster_renderer import RasterCompositionRenderer


def _fixture(tmp_path: Path):
    asset_path = tmp_path / "asset.png"
    Image.new("RGBA", (8, 4), (230, 40, 20, 255)).save(asset_path)
    asset_ref = AssetRef(
        asset_id="asset-1", kind="image", path=str(asset_path),
        identity="test-content-identity",
    )
    plan = ScenePlan(scene_id="scene-1", asset_refs=[asset_ref])
    project = Project(
        id="project-1",
        scenes=[Scene(id="scene-1", title="Scene 1")],
        settings={"universal": {
            "format_version": 1, "profile_id": None,
            "scene_plans": {"scene-1": plan.to_dict()},
        }},
    )
    composition = SceneComposition(
        composition_id="composition-1",
        scene_id="scene-1",
        canvas=CompositionCanvas(32, 16),
        elements=(CompositionElement(
            element_id="element-1",
            asset_id="asset-1",
            transform=VisualTransform(x=0, y=0, width=1, height=1),
            layer_order=0,
            fit_mode="stretch",
        ),),
    )
    preview = preview_scene_composition(project, composition)
    assert preview.is_valid
    return project, composition, preview, {"asset-1": asset_path}


def test_raster_adapter_declares_png_only_cpu_composition_capabilities():
    adapter = RasterCompositionAdapter()
    assert adapter.descriptor.engine_id == "raster"
    assert adapter.descriptor.capabilities.output_formats == ("png",)
    assert adapter.descriptor.capabilities.asset_kinds == ("image",)
    assert adapter.descriptor.capabilities.requires_gpu is False
    assert adapter.composition_capabilities == CompositionRenderCapabilities(
        output_formats=("png",), asset_kinds=("image",),
        supports_layers=True, supports_transforms=True,
        supports_opacity=True, supports_rotation=True,
    )


def test_builtin_bridge_registers_only_raster_and_is_lazy_cpu_local():
    bridge = build_builtin_composition_render_bridge()
    assert BUILTIN_COMPOSITION_RENDERER_IDS == ("raster",)
    assert bridge.inspect("raster").supported
    assert bridge.inspect("raster").output_formats == ("png",)
    assert not bridge.inspect("ffmpeg").supported
    assert "No composition renderer" in bridge.inspect("ffmpeg").reason


def test_bridge_renders_real_png_after_explicit_approval(tmp_path):
    project, composition, preview, assets = _fixture(tmp_path)
    bridge = build_builtin_composition_render_bridge()
    destination = tmp_path / "composed.png"
    progress = []

    output = bridge.render(
        "raster", project, composition, preview,
        asset_paths=assets, destination=destination,
        output_format="png", approved=True, on_progress=progress.append,
    )

    assert output == destination
    assert output.is_file() and output.stat().st_size > 0
    assert progress[0] == 0.0 and progress[-1] == 1.0
    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.size == (32, 16)
        assert image.getpixel((16, 8)) == (230, 40, 20, 255)


def test_bridge_requires_explicit_approval(tmp_path):
    project, composition, preview, assets = _fixture(tmp_path)
    bridge = build_builtin_composition_render_bridge()
    with pytest.raises(CompositionRenderApprovalError):
        bridge.render(
            "raster", project, composition, preview,
            asset_paths=assets, destination=tmp_path / "not-approved.png",
            output_format="png",
        )


def test_bridge_rejects_mp4_without_fallback(tmp_path):
    project, composition, preview, assets = _fixture(tmp_path)
    bridge = build_builtin_composition_render_bridge()
    with pytest.raises(CompositionRenderUnsupportedError):
        bridge.render(
            "raster", project, composition, preview,
            asset_paths=assets, destination=tmp_path / "not-video.mp4",
            output_format="mp4", approved=True,
        )
    assert not (tmp_path / "not-video.mp4").exists()


def test_bridge_rejects_stale_preview(tmp_path):
    project, composition, preview, assets = _fixture(tmp_path)
    changed = SceneComposition(
        composition_id=composition.composition_id,
        scene_id=composition.scene_id,
        canvas=CompositionCanvas(64, 32),
        elements=composition.elements,
    )
    bridge = build_builtin_composition_render_bridge()
    with pytest.raises(Exception, match="stale"):
        bridge.render(
            "raster", project, changed, preview,
            asset_paths=assets, destination=tmp_path / "stale.png",
            output_format="png", approved=True,
        )
    assert not (tmp_path / "stale.png").exists()


def test_bridge_requires_exact_visible_asset_set(tmp_path):
    project, composition, preview, assets = _fixture(tmp_path)
    bridge = build_builtin_composition_render_bridge()
    with pytest.raises(Exception, match="exactly"):
        bridge.render(
            "raster", project, composition, preview,
            asset_paths={}, destination=tmp_path / "missing.png",
            output_format="png", approved=True,
        )


def test_bridge_does_not_accept_wrong_adapter_descriptor_id():
    adapter = RasterCompositionAdapter()
    adapter.descriptor = EngineDescriptor(
        engine_id="other", display_name="Wrong", version="1",
        capabilities=EngineCapabilities(output_formats=("png",)),
    )
    bridge = CompositionRenderBridge({"raster": adapter})
    resolution = bridge.inspect("raster")
    assert not resolution.supported
    assert "does not match" in resolution.reason


def test_adapter_rejects_unadvertised_output_format(tmp_path):
    adapter = RasterCompositionAdapter()
    _, composition, _, assets = _fixture(tmp_path)
    with pytest.raises(ValueError, match="only supports PNG"):
        adapter.render_composition(
            composition, asset_paths=assets,
            destination=tmp_path / "wrong.jpg", output_format="jpg",
        )
