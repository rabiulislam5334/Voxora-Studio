from pathlib import Path

import pytest
from PIL import Image

from app.models.project import Project
from app.models.scene import Scene
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import (
    CompositionCanvas, CompositionElement, SceneComposition, VisualTransform,
)
from app.universal.models import AssetRef, ScenePlan
from app.universal.raster_renderer import (
    RasterCompositionRenderer,
    RasterRenderCancelledError,
    RasterRenderError,
    RasterRenderLimits,
    render_bound_scene_composition,
    resolve_scene_composition_assets,
)


def make_composition(*elements, width=16, height=16):
    return SceneComposition(
        composition_id="composition-1",
        scene_id="scene-1",
        canvas=CompositionCanvas(width, height),
        elements=tuple(elements),
    )


def make_element(element_id, asset_id, *, x=0, y=0, width=1, height=1,
                 layer=0, fit="stretch", opacity=1, rotation=0, visible=True):
    return CompositionElement(
        element_id=element_id,
        asset_id=asset_id,
        transform=VisualTransform(
            x=x, y=y, width=width, height=height,
            opacity=opacity, rotation_degrees=rotation,
        ),
        layer_order=layer,
        fit_mode=fit,
        visible=visible,
    )


def save_image(path: Path, color, size=(4, 4), image_format="PNG"):
    Image.new("RGBA", size, color).save(path, format=image_format)
    return path


def test_renders_real_png_at_composition_canvas_dimensions(tmp_path):
    source = save_image(tmp_path / "red.png", (255, 0, 0, 255))
    destination = tmp_path / "render.png"
    composition = make_composition(make_element("red-layer", "red"), width=24, height=12)

    result = RasterCompositionRenderer().render(
        composition, asset_paths={"red": source}, destination=destination,
    )

    assert result.destination == destination
    assert result.width == 24 and result.height == 12
    assert result.rendered_element_ids == ("red-layer",)
    with Image.open(destination) as output:
        assert output.format == "PNG"
        assert output.size == (24, 12)
        assert output.convert("RGBA").getpixel((12, 6)) == (255, 0, 0, 255)


def test_layer_order_is_deterministic_and_higher_layer_is_on_top(tmp_path):
    red = save_image(tmp_path / "red.png", (255, 0, 0, 255))
    blue = save_image(tmp_path / "blue.png", (0, 0, 255, 255))
    composition = make_composition(
        make_element("blue", "blue", layer=20),
        make_element("red", "red", layer=10),
    )
    output = tmp_path / "layers.png"

    result = RasterCompositionRenderer().render(
        composition, asset_paths={"red": red, "blue": blue}, destination=output,
    )

    assert result.rendered_element_ids == ("red", "blue")
    with Image.open(output) as image:
        assert image.getpixel((8, 8)) == (0, 0, 255, 255)


def test_contain_preserves_aspect_ratio_and_transparent_letterbox(tmp_path):
    source = save_image(tmp_path / "wide.png", (20, 200, 40, 255), size=(4, 2))
    composition = make_composition(make_element(
        "wide", "wide", width=1, height=1, fit="contain",
    ))
    output = tmp_path / "contain.png"
    RasterCompositionRenderer().render(composition, asset_paths={"wide": source}, destination=output)

    with Image.open(output) as image:
        assert image.getpixel((8, 1))[3] == 0
        assert image.getpixel((8, 8)) == (20, 200, 40, 255)


def test_cover_fills_target_box_without_letterboxing(tmp_path):
    source = save_image(tmp_path / "tall.png", (20, 200, 40, 255), size=(2, 4))
    composition = make_composition(make_element(
        "cover", "cover", width=1, height=0.5, fit="cover",
    ))
    output = tmp_path / "cover.png"
    RasterCompositionRenderer().render(composition, asset_paths={"cover": source}, destination=output)

    with Image.open(output) as image:
        assert image.getpixel((8, 4)) == (20, 200, 40, 255)
        assert image.getpixel((8, 12))[3] == 0


def test_opacity_and_rotation_are_applied(tmp_path):
    source = save_image(tmp_path / "white.png", (255, 255, 255, 255), size=(4, 2))
    composition = make_composition(make_element(
        "rotated", "white", x=0.25, y=0.25, width=0.5, height=0.25,
        opacity=0.5, rotation=90,
    ))
    output = tmp_path / "rotated.png"
    RasterCompositionRenderer().render(composition, asset_paths={"white": source}, destination=output)

    with Image.open(output) as image:
        pixels = image.convert("RGBA")
        assert max(pixel[3] for pixel in pixels.getdata()) in (127, 128)
        assert sum(1 for pixel in pixels.getdata() if pixel[3] > 0) > 0


def test_hidden_elements_are_not_loaded_or_required(tmp_path):
    composition = make_composition(
        make_element("hidden", "missing", visible=False),
    )
    output = tmp_path / "hidden.png"
    result = RasterCompositionRenderer().render(
        composition, asset_paths={}, destination=output,
    )
    assert result.rendered_element_ids == ()
    with Image.open(output) as image:
        assert image.getpixel((0, 0)) == (0, 0, 0, 0)


def test_exact_visible_asset_set_is_required(tmp_path):
    source = save_image(tmp_path / "asset.png", (1, 2, 3, 255))
    composition = make_composition(make_element("visible", "asset"))
    with pytest.raises(RasterRenderError, match="exactly"):
        RasterCompositionRenderer().render(
            composition, asset_paths={}, destination=tmp_path / "bad.png",
        )
    with pytest.raises(RasterRenderError, match="exactly"):
        RasterCompositionRenderer().render(
            composition, asset_paths={"asset": source, "extra": source},
            destination=tmp_path / "bad2.png",
        )


def test_corrupt_image_is_rejected_without_output(tmp_path):
    source = tmp_path / "corrupt.png"
    source.write_bytes(b"not a png")
    composition = make_composition(make_element("bad", "bad"))
    destination = tmp_path / "bad-output.png"
    with pytest.raises(RasterRenderError, match="decode"):
        RasterCompositionRenderer().render(
            composition, asset_paths={"bad": source}, destination=destination,
        )
    assert not destination.exists()


def test_canvas_and_asset_limits_are_enforced(tmp_path):
    source = save_image(tmp_path / "asset.png", (1, 2, 3, 255))
    composition = make_composition(make_element("asset", "asset"), width=20, height=20)
    renderer = RasterCompositionRenderer(RasterRenderLimits(
        max_width=10, max_height=10, max_canvas_pixels=100,
    ))
    with pytest.raises(RasterRenderError, match="width or height"):
        renderer.render(composition, asset_paths={"asset": source}, destination=tmp_path / "limit.png")

    renderer = RasterCompositionRenderer(RasterRenderLimits(max_asset_file_bytes=1))
    with pytest.raises(RasterRenderError, match="byte limit"):
        renderer.render(composition, asset_paths={"asset": source}, destination=tmp_path / "limit2.png")


def test_output_is_not_overwritten_without_explicit_permission(tmp_path):
    source = save_image(tmp_path / "asset.png", (1, 2, 3, 255))
    composition = make_composition(make_element("asset", "asset"))
    destination = tmp_path / "existing.png"
    destination.write_bytes(b"keep-me")

    with pytest.raises(RasterRenderError, match="already exists"):
        RasterCompositionRenderer().render(
            composition, asset_paths={"asset": source}, destination=destination,
        )
    assert destination.read_bytes() == b"keep-me"

    RasterCompositionRenderer().render(
        composition, asset_paths={"asset": source}, destination=destination, overwrite=True,
    )
    with Image.open(destination) as image:
        assert image.size == (16, 16)


def test_cancelled_render_does_not_commit_partial_output(tmp_path):
    source = save_image(tmp_path / "asset.png", (1, 2, 3, 255))
    composition = make_composition(make_element("asset", "asset"))
    destination = tmp_path / "cancelled.png"

    with pytest.raises(RasterRenderCancelledError):
        RasterCompositionRenderer().render(
            composition, asset_paths={"asset": source}, destination=destination, cancel=True,
        )
    assert not destination.exists()
    assert not list(tmp_path.glob(".voxora-render-*.png"))


def test_progress_reports_completion(tmp_path):
    source = save_image(tmp_path / "asset.png", (1, 2, 3, 255))
    composition = make_composition(make_element("asset", "asset"))
    progress = []
    RasterCompositionRenderer().render(
        composition, asset_paths={"asset": source}, destination=tmp_path / "progress.png",
        on_progress=progress.append,
    )
    assert progress[0] == 0.0
    assert progress[-1] == 1.0


def test_bound_render_resolves_catalog_identity_and_writes_png(tmp_path):
    source = save_image(tmp_path / "original.png", (40, 80, 120, 255))
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source, asset_id="asset-1")
    plan = ScenePlan(
        scene_id="scene-1",
        asset_refs=[AssetRef(
            asset_id=asset.asset_id, kind="image", path=asset.location,
            identity=asset.content_sha256,
        )],
    )
    project = Project(
        id="project-1",
        scenes=[Scene(id="scene-1", title="Scene 1")],
        settings={"universal": {
            "format_version": 1, "profile_id": None,
            "scene_plans": {"scene-1": plan.to_dict()},
        }},
    )
    composition = make_composition(make_element("asset", "asset-1"))

    paths = resolve_scene_composition_assets(project, composition, library)
    assert paths == {"asset-1": library.resolve_asset_path(asset)}
    result = render_bound_scene_composition(
        project, composition, library, tmp_path / "bound.png",
    )
    assert result.output_sha256
    with Image.open(result.destination) as image:
        assert image.getpixel((8, 8)) == (40, 80, 120, 255)


def test_bound_render_rejects_unbound_or_modified_catalog_asset(tmp_path):
    source = save_image(tmp_path / "original.png", (40, 80, 120, 255))
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source, asset_id="asset-1")
    plan = ScenePlan(scene_id="scene-1", asset_refs=[])
    project = Project(
        id="project-1", scenes=[Scene(id="scene-1")],
        settings={"universal": {
            "format_version": 1, "profile_id": None,
            "scene_plans": {"scene-1": plan.to_dict()},
        }},
    )
    composition = make_composition(make_element("asset", "asset-1"))
    with pytest.raises(RasterRenderError, match="not bound"):
        resolve_scene_composition_assets(project, composition, library)

    plan.asset_refs.append(AssetRef("asset-1", "image", path=asset.location, identity="0" * 64))
    project.settings["universal"]["scene_plans"]["scene-1"] = plan.to_dict()
    with pytest.raises(RasterRenderError, match="identity"):
        resolve_scene_composition_assets(project, composition, library)
