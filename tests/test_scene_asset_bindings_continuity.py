from copy import deepcopy
import pytest
from app.models.project import Project
from app.models.scene import Scene
from app.universal.asset_continuity import analyze_asset_continuity
from app.universal.models import ScenePlan, UniversalState
from app.universal.scene_asset_bindings import (
    SceneAssetBinding, SceneBindingError, apply_scene_bindings, preview_scene_bindings,
)
from app.universal.visual_assets import CharacterAppearance, CharacterDefinition, VisualAsset, VisualAssetCatalog

def catalog_fixture():
    asset = VisualAsset("bg-01", "background", "assets/aa/bg.png", "a"*64, "image/png", 100, 80)
    character = CharacterDefinition("hero", "Hero", "", CharacterAppearance(
        "hero-v1", "Red coat", ("bg-01",), ("2d",)))
    return VisualAssetCatalog("test-library", assets=(asset,), characters=(character,))

def project_fixture():
    return Project(id="project-1", scenes=[Scene(id="scene-1"), Scene(id="scene-2")])

def test_preview_is_read_only_and_resolves_catalog_items():
    project, catalog = project_fixture(), catalog_fixture()
    before = deepcopy(project.settings)
    preview = preview_scene_bindings(project, catalog, "scene-1",
        asset_bindings=(SceneAssetBinding("bg-01", "background"),), character_ids=("hero",))
    assert preview.is_valid and preview.character_bindings[0].appearance_id == "hero-v1"
    assert project.settings == before

def test_preview_rejects_missing_catalog_references():
    preview = preview_scene_bindings(project_fixture(), catalog_fixture(), "scene-1",
        asset_bindings=(SceneAssetBinding("missing"),), character_ids=("ghost",))
    assert not preview.is_valid
    assert {d.code for d in preview.diagnostics} == {"ASSET_NOT_IN_CATALOG", "CHARACTER_NOT_IN_CATALOG"}

def test_apply_requires_approval_and_writes_asset_and_character_bindings():
    project, catalog = project_fixture(), catalog_fixture()
    preview = preview_scene_bindings(project, catalog, "scene-1",
        asset_bindings=(SceneAssetBinding("bg-01", "background"),), character_ids=("hero",))
    with pytest.raises(SceneBindingError, match="explicit approval"):
        apply_scene_bindings(project, catalog, preview)
    apply_scene_bindings(project, catalog, preview, approved=True)
    plan = UniversalState.from_project_settings(project.settings).scene_plans["scene-1"]
    assert plan.asset_refs[0].identity == "a"*64
    assert plan.asset_refs[0].metadata["role"] == "background"
    assert plan.requirements["character_bindings"][0]["character_id"] == "hero"

def test_stale_preview_rejected_and_existing_plan_data_preserved():
    project, catalog = project_fixture(), catalog_fixture()
    project.settings["universal"] = {"format_version": 1, "profile_id": "quasivanta",
        "custom": {"keep": True}, "scene_plans": {"scene-1": ScenePlan(
            scene_id="scene-1", notes="keep", style_tags=["existing"]).to_dict()}}
    preview = preview_scene_bindings(project, catalog, "scene-1",
        asset_bindings=(SceneAssetBinding("bg-01"),))
    project.scenes[0].title = "edited"
    with pytest.raises(SceneBindingError, match="stale"):
        apply_scene_bindings(project, catalog, preview, approved=True)
    project.scenes[0].title = "Untitled Scene"
    preview = preview_scene_bindings(project, catalog, "scene-1",
        asset_bindings=(SceneAssetBinding("bg-01"),))
    apply_scene_bindings(project, catalog, preview, approved=True)
    state = UniversalState.from_project_settings(project.settings)
    assert state.scene_plans["scene-1"].notes == "keep"
    assert state.extra["custom"] == {"keep": True}

def test_duplicate_binding_is_blocked():
    project, catalog = project_fixture(), catalog_fixture()
    preview = preview_scene_bindings(project, catalog, "scene-1",
        asset_bindings=(SceneAssetBinding("bg-01"),))
    apply_scene_bindings(project, catalog, preview, approved=True)
    duplicate = preview_scene_bindings(project, catalog, "scene-1",
        asset_bindings=(SceneAssetBinding("bg-01"),))
    assert not duplicate.is_valid
    with pytest.raises(SceneBindingError, match="valid"):
        apply_scene_bindings(project, catalog, duplicate, approved=True)

def test_continuity_reports_asset_reuse_and_character_appearance_drift():
    project, catalog = project_fixture(), catalog_fixture()
    for sid in ("scene-1", "scene-2"):
        p = preview_scene_bindings(project, catalog, sid,
            asset_bindings=(SceneAssetBinding("bg-01"),), character_ids=("hero",))
        apply_scene_bindings(project, catalog, p, approved=True)
    report = analyze_asset_continuity(project, catalog)
    assert any(group.asset_ids == ("bg-01",) for group in report.asset_reuse_groups)
    assert report.character_groups[0].scene_ids == ("scene-1", "scene-2")
    changed = CharacterDefinition("hero", "Hero", "", CharacterAppearance(
        "hero-v2", "Green coat", ("bg-01",), ("2d",)))
    new_catalog = VisualAssetCatalog("test-library", assets=catalog.assets, characters=(changed,))
    assert any(d.code == "CHARACTER_APPEARANCE_CHANGED"
               for d in analyze_asset_continuity(project, new_catalog).diagnostics)

def test_continuity_detects_inconsistent_character_appearance_and_missing_refs():
    project, catalog = project_fixture(), catalog_fixture()
    p = preview_scene_bindings(project, catalog, "scene-1", character_ids=("hero",))
    apply_scene_bindings(project, catalog, p, approved=True)
    state = UniversalState.from_project_settings(project.settings)
    state.scene_plans["scene-2"] = ScenePlan(scene_id="scene-2", requirements={
        "character_bindings": [{"character_id":"hero", "appearance_id":"old",
        "appearance_fingerprint":"f"*64, "reference_asset_ids":["missing"], "style_tags":[]}]})
    project.settings = state.apply_to_project_settings(project.settings)
    codes = {d.code for d in analyze_asset_continuity(project, catalog).diagnostics}
    assert "CHARACTER_APPEARANCE_INCONSISTENT" in codes
    assert "CHARACTER_REFERENCE_ASSET_MISSING" in codes

def test_continuity_future_state_is_read_only():
    project = project_fixture()
    project.settings["universal"] = {"format_version": 999}
    before = deepcopy(project.settings)
    report = analyze_asset_continuity(project, catalog_fixture())
    assert report.diagnostics[0].code == "UNIVERSAL_STATE_READ_ONLY"
    assert project.settings == before
