from copy import deepcopy

import pytest

from app.models.project import Project
from app.models.scene import Scene
from app.universal.composition import CompositionElement, SceneComposition, VisualTransform
from app.universal.generated_image_composition import (
    GeneratedImageCompositionError,
    append_bound_generated_images,
)
from app.universal.generated_image_scene_workflow import (
    apply_generated_image_binding,
    preview_generated_image_binding,
)
from app.universal.visual_assets import AssetProvenance, VisualAsset, VisualAssetCatalog


def make_project():
    return Project(
        id="project-01",
        scenes=[Scene(id="scene-01", title="Opening", visual_prompt="A quiet dawn.")],
    )


def make_catalog(count=2):
    assets = tuple(
        VisualAsset(
            f"generated-{index:02d}",
            "generated-image",
            f"assets/generated/{index:02d}.png",
            f"{index:064x}",
            "image/png",
            512,
            512,
            provenance=AssetProvenance(
                source="generated:stable-diffusion.cpp",
                metadata={"request_id": f"request-{index:02d}"},
            ),
        )
        for index in range(1, count + 1)
    )
    return VisualAssetCatalog("library-01", assets=assets)


def bind_all(project, catalog):
    preview = preview_generated_image_binding(
        project, catalog, "scene-01",
        [asset.asset_id for asset in catalog.assets],
    )
    apply_generated_image_binding(project, catalog, preview, approved=True)


def empty_composition():
    return SceneComposition("composition-01", "scene-01")


def test_appends_only_scene_bound_generated_images_in_grid():
    project, catalog = make_project(), make_catalog(2)
    bind_all(project, catalog)

    result = append_bound_generated_images(project, catalog, empty_composition())

    assert [item.asset_id for item in result.elements] == [
        "generated-01", "generated-02"
    ]
    assert [item.layer_order for item in result.elements] == [0, 1]
    assert all(item.fit_mode == "contain" for item in result.elements)
    assert all(item.metadata["layout"] == "auto-grid" for item in result.elements)
    assert result.elements[0].transform.x < result.elements[1].transform.x


def test_preserves_existing_elements_and_avoids_duplicate_asset_entries():
    project, catalog = make_project(), make_catalog(2)
    bind_all(project, catalog)
    existing = CompositionElement(
        "existing-01", "generated-01",
        transform=VisualTransform(x=0.1, y=0.1, width=0.4, height=0.4),
        layer_order=7,
        label="User layout",
    )
    composition = SceneComposition("composition-01", "scene-01", elements=(existing,))

    result = append_bound_generated_images(project, catalog, composition)

    assert result.elements[0] == existing
    assert [item.asset_id for item in result.elements].count("generated-01") == 1
    assert [item.asset_id for item in result.elements].count("generated-02") == 1
    assert result.elements[1].layer_order == 8


def test_rejects_unbound_generated_images():
    with pytest.raises(GeneratedImageCompositionError, match="bind generated images"):
        append_bound_generated_images(make_project(), make_catalog(), empty_composition())


def test_rejects_invalid_or_missing_provenance_for_bound_generated_reference():
    project, catalog = make_project(), make_catalog(1)
    bind_all(project, catalog)
    bad_asset = VisualAsset(
        "generated-01", "image", "assets/generated/01.png",
        "1" * 64, "image/png", 512, 512,
        provenance=AssetProvenance(source="user-upload"),
    )
    replaced = VisualAssetCatalog("library-01", assets=(bad_asset,))
    with pytest.raises(GeneratedImageCompositionError, match="invalid provenance"):
        append_bound_generated_images(project, replaced, empty_composition())


def test_rejects_when_no_new_generated_images_remain():
    project, catalog = make_project(), make_catalog(1)
    bind_all(project, catalog)
    already_present = CompositionElement("generated-0001", "generated-01")
    composition = SceneComposition(
        "composition-01", "scene-01", elements=(already_present,)
    )
    with pytest.raises(GeneratedImageCompositionError, match="no new verified"):
        append_bound_generated_images(project, catalog, composition)


def test_enforces_layout_batch_limit_without_mutating_inputs():
    project, catalog = make_project(), make_catalog(2)
    bind_all(project, catalog)
    before = deepcopy(project.settings)
    composition = empty_composition()
    with pytest.raises(GeneratedImageCompositionError, match="add at most 1"):
        append_bound_generated_images(project, catalog, composition, max_assets=1)
    assert project.settings == before
    assert composition.elements == ()


def test_rejects_invalid_batch_limit_and_missing_scene():
    project, catalog = make_project(), make_catalog(1)
    bind_all(project, catalog)
    with pytest.raises(GeneratedImageCompositionError, match="between 1 and 48"):
        append_bound_generated_images(project, catalog, empty_composition(), max_assets=0)
    missing_scene = SceneComposition("composition-02", "missing-scene")
    with pytest.raises(GeneratedImageCompositionError, match="does not exist"):
        append_bound_generated_images(project, catalog, missing_scene)
