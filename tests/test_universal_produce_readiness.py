from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.models.project import Project
from app.models.scene import Scene
from app.studio.models import StudioState, VideoSettings
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import CompositionElement, SceneComposition
from app.universal.composition_workflow import apply_scene_composition, preview_scene_composition
from app.universal.models import AssetRef, ScenePlan, UniversalState
from app.universal.produce_readiness import inspect_universal_produce_readiness


def make_project(tmp_path: Path, *, import_asset: bool = True, duration_s: float = 0.5):
    source = tmp_path / "source.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(source)
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source, asset_id="asset-1") if import_asset else None

    project = Project(
        id="readiness-project",
        name="Readiness",
        scenes=[Scene(id="scene-1", title="Scene 1", text="Narration", order=0)],
    )
    state = UniversalState()
    state.scene_plans = {
        "scene-1": ScenePlan(
            scene_id="scene-1",
            asset_refs=[AssetRef(
                "asset-1", "image",
                path=asset.location if asset else "assets/missing.png",
                identity=asset.content_sha256 if asset else "a" * 64,
            )],
        ),
    }
    project.settings = state.apply_to_project_settings(project.settings)
    composition = SceneComposition(
        composition_id="composition-1",
        scene_id="scene-1",
        elements=(CompositionElement(element_id="element-1", asset_id="asset-1"),),
    )
    preview = preview_scene_composition(project, composition)
    assert preview.is_valid
    apply_scene_composition(project, composition, preview, approved=True)

    studio = StudioState(video=VideoSettings(
        fps=24, transition="cut", default_duration_s=duration_s,
    ))
    studio.write_to(project.settings)
    return project, library


def test_readiness_passes_for_verified_local_assets_without_mutating_project(tmp_path):
    project, library = make_project(tmp_path)
    before = project.to_dict()

    report = inspect_universal_produce_readiness(project, library)

    assert report.is_ready
    assert report.error_count == 0
    assert report.scene_count == 1
    assert report.asset_count == 1
    assert report.total_frames == 12
    assert project.to_dict() == before


def test_readiness_reports_missing_local_catalog_asset(tmp_path):
    project, library = make_project(tmp_path, import_asset=False)

    report = inspect_universal_produce_readiness(project, library)

    assert not report.is_ready
    assert any(
        issue.code == "SCENE_ASSET_NOT_READY"
        and "missing from the local visual catalog" in issue.message
        for issue in report.issues
    )


def test_readiness_reports_cpu_frame_limit_before_rendering(tmp_path):
    project, library = make_project(tmp_path, duration_s=40.0)

    report = inspect_universal_produce_readiness(project, library)

    assert not report.is_ready
    issue = next(item for item in report.issues if item.code == "SCENE_FRAME_LIMIT_EXCEEDED")
    assert "960 frames" in issue.message
    assert "900 frames" in issue.message


def test_readiness_rejects_invalid_frame_limit_argument(tmp_path):
    project, library = make_project(tmp_path)

    try:
        inspect_universal_produce_readiness(project, library, max_frames_per_scene=0)
    except ValueError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("invalid frame limit should be rejected")
