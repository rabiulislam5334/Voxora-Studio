import copy

import pytest

from app.models.project import Project
from app.models.scene import Scene
from app.universal import (
    AssetRef,
    CompositionCanvas,
    CompositionElement,
    SceneComposition,
    ScenePlan,
    UniversalState,
    VisualTransform,
    apply_scene_composition,
    preview_scene_composition,
)
from app.universal.composition_workflow import (
    SceneCompositionWorkflowError,
)


def make_project(*, universal_override=None):
    plan = ScenePlan(
        scene_id="scene-1",
        asset_refs=[AssetRef(asset_id="asset-1", kind="image", path="assets/one.png")],
    )
    universal = {
        "format_version": 1,
        "profile_id": None,
        "scene_plans": {"scene-1": plan.to_dict()},
        "unrelated_future_metadata": {"keep": True},
    }
    if universal_override is not None:
        universal = universal_override
    return Project(
        id="project-1",
        name="Composition test",
        scenes=[Scene(id="scene-1", title="Scene 1", text="Narration", order=0)],
        settings={"universal": universal, "other_setting": {"keep": "yes"}},
    )


def make_composition(*, elements=None, scene_id="scene-1"):
    if elements is None:
        elements = (
            CompositionElement(
                element_id="element-1",
                asset_id="asset-1",
                transform=VisualTransform(x=0.1, y=0.2, width=0.4, height=0.5),
                layer_order=2,
            ),
        )
    return SceneComposition(
        composition_id="composition-1",
        scene_id=scene_id,
        canvas=CompositionCanvas(1000, 500),
        elements=tuple(elements),
    )


def test_preview_resolves_scene_asset_binding_and_pixel_geometry():
    project = make_project()
    composition = make_composition()
    preview = preview_scene_composition(project, composition)

    assert preview.is_valid
    assert preview.canvas_width == 1000
    assert preview.canvas_height == 500
    assert preview.elements[0].x_px == 100
    assert preview.elements[0].y_px == 100
    assert preview.elements[0].width_px == 400
    assert preview.elements[0].height_px == 250
    assert preview.diagnostics == ()


def test_preview_rejects_assets_not_bound_to_the_scene():
    project = make_project()
    composition = make_composition(elements=(
        CompositionElement(element_id="e1", asset_id="missing-asset"),
    ))
    preview = preview_scene_composition(project, composition)

    assert not preview.is_valid
    assert any(item.code == "ELEMENT_ASSET_NOT_BOUND" for item in preview.diagnostics)


def test_preview_rejects_composition_for_missing_scene():
    preview = preview_scene_composition(make_project(), make_composition(scene_id="missing"))
    assert not preview.is_valid
    assert any(item.code == "SCENE_NOT_FOUND" for item in preview.diagnostics)


def test_preview_reports_empty_composition():
    preview = preview_scene_composition(make_project(), make_composition(elements=()))
    assert not preview.is_valid
    assert any(item.code == "EMPTY_COMPOSITION" for item in preview.diagnostics)


def test_preview_orders_elements_by_layer_then_id_and_reports_overlap():
    project = make_project()
    composition = make_composition(elements=(
        CompositionElement(
            element_id="top", asset_id="asset-1",
            transform=VisualTransform(x=0.2, y=0.2, width=0.5, height=0.5),
            layer_order=3,
        ),
        CompositionElement(
            element_id="bottom", asset_id="asset-1",
            transform=VisualTransform(x=0.1, y=0.1, width=0.5, height=0.5),
            layer_order=1,
        ),
        CompositionElement(
            element_id="same-layer", asset_id="asset-1",
            transform=VisualTransform(x=0.3, y=0.3, width=0.2, height=0.2),
            layer_order=1,
        ),
    ))
    preview = preview_scene_composition(project, composition)

    assert [item.element_id for item in preview.elements] == [
        "bottom", "same-layer", "top"
    ]
    assert sum(item.code == "ELEMENT_OVERLAP" for item in preview.diagnostics) == 3
    assert any(item.code == "OVERLAP_SAME_LAYER_ORDER" for item in preview.diagnostics)


def test_preview_reports_hidden_and_transparent_elements_without_blocking():
    project = make_project()
    composition = make_composition(elements=(
        CompositionElement(element_id="hidden", asset_id="asset-1", visible=False),
        CompositionElement(
            element_id="transparent", asset_id="asset-1",
            transform=VisualTransform(opacity=0),
        ),
    ))
    preview = preview_scene_composition(project, composition)

    assert preview.is_valid
    assert any(item.code == "ELEMENT_HIDDEN" for item in preview.diagnostics)
    assert any(item.code == "ELEMENT_FULLY_TRANSPARENT" for item in preview.diagnostics)


def test_preview_is_read_only_and_deterministic():
    project = make_project()
    composition = make_composition()
    before = copy.deepcopy(project.settings)
    first = preview_scene_composition(project, composition)
    second = preview_scene_composition(project, composition)

    assert first == second
    assert project.settings == before


def test_apply_requires_explicit_approval_and_persists_additively():
    project = make_project()
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    original_scenes = copy.deepcopy(project.scenes)

    with pytest.raises(SceneCompositionWorkflowError, match="explicit approval"):
        apply_scene_composition(project, composition, preview)

    apply_scene_composition(project, composition, preview, approved=True)

    state = UniversalState.from_project_settings(project.settings)
    stored = state.extra["scene_compositions"]["scene-1"]
    assert stored["storage_version"] == 1
    assert stored["composition"] == composition.to_dict()
    assert stored["composition_fingerprint"] == composition.fingerprint
    assert state.extra["unrelated_future_metadata"] == {"keep": True}
    assert project.settings["other_setting"] == {"keep": "yes"}
    assert project.scenes == original_scenes
    assert project.schema_version == 4


def test_apply_rejects_stale_preview_after_scene_or_plan_changes():
    project = make_project()
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    project.scenes[0].title = "Changed after preview"

    with pytest.raises(SceneCompositionWorkflowError, match="stale"):
        apply_scene_composition(project, composition, preview, approved=True)


def test_apply_rejects_preview_from_another_project():
    project = make_project()
    composition = make_composition()
    preview = preview_scene_composition(project, composition)
    other = make_project()
    other.id = "another-project"

    with pytest.raises(SceneCompositionWorkflowError, match="different project"):
        apply_scene_composition(other, composition, preview, approved=True)


def test_apply_can_replace_a_valid_existing_scene_composition():
    project = make_project()
    first = make_composition()
    first_preview = preview_scene_composition(project, first)
    apply_scene_composition(project, first, first_preview, approved=True)

    replacement = make_composition(elements=(
        CompositionElement(element_id="replacement", asset_id="asset-1"),
    ))
    replacement_preview = preview_scene_composition(project, replacement)
    apply_scene_composition(project, replacement, replacement_preview, approved=True)

    state = UniversalState.from_project_settings(project.settings)
    assert state.extra["scene_compositions"]["scene-1"]["composition"] == replacement.to_dict()


def test_apply_blocks_future_read_only_universal_state():
    project = make_project(universal_override={
        "format_version": 999,
        "future_payload": {"must": "not be overwritten"},
    })
    composition = make_composition()
    preview = preview_scene_composition(project, composition)

    assert not preview.is_valid
    with pytest.raises(SceneCompositionWorkflowError, match="blocking diagnostics"):
        apply_scene_composition(project, composition, preview, approved=True)
    assert project.settings["universal"]["future_payload"] == {"must": "not be overwritten"}


def test_apply_blocks_malformed_existing_composition_storage():
    project = make_project()
    project.settings["universal"]["scene_compositions"] = {
        "scene-1": {"storage_version": 1, "composition": "not-an-object"}
    }
    composition = make_composition()
    preview = preview_scene_composition(project, composition)

    with pytest.raises(SceneCompositionWorkflowError, match="malformed"):
        apply_scene_composition(project, composition, preview, approved=True)
