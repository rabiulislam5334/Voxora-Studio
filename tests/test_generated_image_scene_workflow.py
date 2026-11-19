from copy import deepcopy

import pytest

from app.models.project import Project
from app.models.scene import Scene
from app.universal.models import UniversalState
from app.universal.generated_image_scene_workflow import (
    apply_generated_image_binding,
    preview_generated_image_binding,
)
from app.universal.scene_asset_bindings import SceneBindingError
from app.universal.visual_assets import AssetProvenance, VisualAsset, VisualAssetCatalog


def make_catalog(*, include_upload=False):
    generated = VisualAsset(
        "generated-01", "generated-image", "assets/generated/one.png",
        "a" * 64, "image/png", 512, 512,
        provenance=AssetProvenance(
            source="generated:stable-diffusion.cpp",
            metadata={"request_id": "request-01"},
        ),
    )
    assets = [generated]
    if include_upload:
        assets.append(VisualAsset(
            "upload-01", "image", "assets/uploads/one.png", "b" * 64,
            "image/png", 512, 512,
            provenance=AssetProvenance(source="user-upload"),
        ))
    return VisualAssetCatalog("library-01", assets=tuple(assets))


def make_project():
    return Project(
        id="project-01",
        scenes=[Scene(id="scene-01", title="Opening", visual_prompt="A quiet dawn.")],
    )


def test_preview_generated_image_binding_is_read_only_and_scene_scoped():
    project, catalog = make_project(), make_catalog()
    before = deepcopy(project.settings)
    preview = preview_generated_image_binding(
        project, catalog, "scene-01", ["generated-01"], role="background"
    )
    assert preview.is_valid
    assert preview.scene_id == "scene-01"
    assert preview.asset_bindings[0].role == "background"
    assert project.settings == before


def test_apply_requires_explicit_approval_and_persists_scene_asset_reference():
    project, catalog = make_project(), make_catalog()
    preview = preview_generated_image_binding(project, catalog, "scene-01", ["generated-01"])
    with pytest.raises(SceneBindingError, match="explicit approval"):
        apply_generated_image_binding(project, catalog, preview)
    apply_generated_image_binding(project, catalog, preview, approved=True)
    state = UniversalState.from_project_settings(project.settings)
    ref = state.scene_plans["scene-01"].asset_refs[0]
    assert ref.asset_id == "generated-01"
    assert ref.metadata["role"] == "visual"


def test_preview_rejects_user_uploads_and_missing_assets():
    project, catalog = make_project(), make_catalog(include_upload=True)
    with pytest.raises(SceneBindingError, match="not a verified generated image"):
        preview_generated_image_binding(project, catalog, "scene-01", ["upload-01"])
    with pytest.raises(SceneBindingError, match="not in the catalog"):
        preview_generated_image_binding(project, catalog, "scene-01", ["missing"])


def test_preview_rejects_empty_duplicate_and_invalid_scene_selection():
    project, catalog = make_project(), make_catalog()
    with pytest.raises(SceneBindingError, match="at least one"):
        preview_generated_image_binding(project, catalog, "scene-01", [])
    with pytest.raises(SceneBindingError, match="duplicates"):
        preview_generated_image_binding(project, catalog, "scene-01", ["generated-01", "generated-01"])
    with pytest.raises(SceneBindingError, match="unknown scene"):
        preview_generated_image_binding(project, catalog, "missing", ["generated-01"])


def test_apply_rejects_stale_preview_after_project_changes():
    project, catalog = make_project(), make_catalog()
    preview = preview_generated_image_binding(project, catalog, "scene-01", ["generated-01"])
    project.scenes[0].title = "Changed"
    with pytest.raises(SceneBindingError, match="stale"):
        apply_generated_image_binding(project, catalog, preview, approved=True)


def test_apply_revalidates_generated_asset_provenance():
    project, catalog = make_project(), make_catalog()
    preview = preview_generated_image_binding(project, catalog, "scene-01", ["generated-01"])
    replaced = VisualAssetCatalog("library-01", assets=(
        VisualAsset("generated-01", "image", "assets/other.png", "a" * 64, "image/png"),
    ))
    with pytest.raises(SceneBindingError, match="no longer a generated image"):
        apply_generated_image_binding(project, replaced, preview, approved=True)
