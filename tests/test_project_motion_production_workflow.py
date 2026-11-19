from __future__ import annotations

import wave
from copy import deepcopy
from pathlib import Path

import pytest

from app.core.timebase import seconds_to_ticks
from app.models.project import Project
from app.models.scene import Scene
from app.studio.models import StudioState, VideoSettings
from app.universal.composition import CompositionElement, SceneComposition
from app.universal.composition_timeline import build_composition_timeline_plan
from app.universal.composition_workflow import apply_scene_composition, preview_scene_composition
from app.universal.models import AssetRef, ScenePlan, UniversalState
from app.universal.production_workflow import (
    ProjectMotionProductionError,
    assemble_aligned_narration_wav,
    build_automatic_motion_plan,
    build_project_motion_production_plan,
)


def _project(*, transition="cut"):
    project = Project(name="Automatic motion", scenes=[
        Scene(id="scene-a", title="First", text="First narration", order=0, pause_ms=100),
        Scene(id="scene-b", title="Second", text="Second narration", order=1, pause_ms=100),
    ])
    state = UniversalState()
    state.scene_plans = {
        "scene-a": ScenePlan(
            scene_id="scene-a",
            asset_refs=[AssetRef("asset-a", "image", path="assets/a.png", identity="sha256-a")],
        ),
        "scene-b": ScenePlan(
            scene_id="scene-b",
            asset_refs=[AssetRef("asset-b", "image", path="assets/b.png", identity="sha256-b")],
        ),
    }
    project.settings = state.apply_to_project_settings(project.settings)
    for scene_id, asset_id in (("scene-a", "asset-a"), ("scene-b", "asset-b")):
        composition = SceneComposition(
            composition_id=f"composition-{scene_id}",
            scene_id=scene_id,
            elements=(CompositionElement(element_id=f"element-{scene_id}", asset_id=asset_id),),
        )
        preview = preview_scene_composition(project, composition)
        assert preview.is_valid
        apply_scene_composition(project, composition, preview, approved=True)
    studio = StudioState(video=VideoSettings(
        fps=24, transition=transition, transition_s=0.25, default_duration_s=0.5,
    ))
    studio.write_to(project.settings)
    return project


def _write_wav(path: Path, *, frames=2400, sample_rate=24000):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x01\x00" * frames)
    return path


def test_automatic_motion_plan_is_deterministic_and_matches_scene_frame_slots():
    project = _project()
    before = deepcopy(project.settings)
    durations = {"scene-a": seconds_to_ticks(0.1), "scene-b": seconds_to_ticks(0.2)}
    pauses = {"scene-a": seconds_to_ticks(0.1), "scene-b": seconds_to_ticks(0.1)}

    first = build_project_motion_production_plan(
        project, durations, narration_pause_ticks=pauses,
    )
    second = build_project_motion_production_plan(
        project, durations, narration_pause_ticks=pauses,
    )

    assert first == second
    assert project.settings == before
    assert [scene_id for scene_id, _ in first.automatic_motion.scene_motions] == [
        "scene-a", "scene-b",
    ]
    assert first.scene_motions["scene-a"].duration_frames == (
        first.composition_plan.slots[0].segment_frame_end
        - first.composition_plan.slots[0].frame_start
    )
    assert first.scene_motions["scene-a"].extra["preset"] == "zoom_in"
    assert first.scene_motions["scene-b"].extra["preset"] == "pan_left"
    assert first.motion_plan.transition == "cut"


def test_automatic_motion_uses_exact_crossfade_overlap_frame_counts():
    project = _project(transition="crossfade")
    durations = {"scene-a": seconds_to_ticks(0.5), "scene-b": seconds_to_ticks(0.5)}
    pauses = {"scene-a": seconds_to_ticks(0.1), "scene-b": seconds_to_ticks(0.1)}

    plan = build_project_motion_production_plan(
        project, durations, narration_pause_ticks=pauses,
    )

    assert plan.motion_plan.transition == "crossfade"
    assert plan.motion_plan.transition_frames[0] > 0
    assert plan.scene_motions["scene-a"].duration_frames == (
        plan.composition_plan.slots[0].segment_frame_end
        - plan.composition_plan.slots[0].frame_start
    )


def test_automatic_motion_rejects_stale_composition_snapshot():
    project = _project()
    durations = {"scene-a": seconds_to_ticks(0.1), "scene-b": seconds_to_ticks(0.2)}
    composition_plan = build_composition_timeline_plan(project, durations)
    state = UniversalState.from_project_settings(project.settings)
    state.extra["scene_compositions"]["scene-a"]["composition_fingerprint"] = "0" * 64
    project.settings = state.apply_to_project_settings(project.settings)

    with pytest.raises(ProjectMotionProductionError, match="changed after timeline planning"):
        build_automatic_motion_plan(project, composition_plan)


def test_aligned_narration_pads_each_scene_to_its_timeline_slot_and_final_video_duration(tmp_path):
    project = _project()
    duration_a = seconds_to_ticks(0.1)
    duration_b = seconds_to_ticks(0.2)
    pauses = {"scene-a": seconds_to_ticks(0.1), "scene-b": seconds_to_ticks(0.1)}
    plan = build_composition_timeline_plan(
        project, {"scene-a": duration_a, "scene-b": duration_b},
        narration_pause_ticks=pauses,
    )
    audio_a = _write_wav(tmp_path / "a.wav", frames=2400)
    audio_b = _write_wav(tmp_path / "b.wav", frames=4800)
    output = tmp_path / "aligned.wav"

    assemble_aligned_narration_wav(
        plan,
        {"scene-a": audio_a, "scene-b": audio_b},
        {"scene-a": duration_a, "scene-b": duration_b},
        output,
    )

    with wave.open(str(output), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == 24000
        output_samples = reader.getnframes()
    assert output_samples >= 24000
    assert output_samples == round(
        seconds_to_ticks(1.0) * 24000 / 141120000
    )


def test_aligned_narration_rounds_cumulative_slot_boundaries_to_samples(tmp_path):
    project = _project()
    studio = StudioState(video=VideoSettings(
        fps=24, transition="cut", default_duration_s=0.777777,
    ))
    studio.write_to(project.settings)
    plan = build_composition_timeline_plan(project, {})
    output = tmp_path / "rounded.wav"

    assemble_aligned_narration_wav(plan, {}, {}, output)

    with wave.open(str(output), "rb") as reader:
        samples = reader.getnframes()
    expected = round(plan.total_ticks * 24000 / 141120000)
    assert samples == expected


def test_aligned_narration_inserts_silence_for_unspoken_scenes(tmp_path):
    project = _project()
    duration_a = seconds_to_ticks(0.1)
    plan = build_composition_timeline_plan(project, {"scene-a": duration_a})
    audio_a = _write_wav(tmp_path / "a.wav", frames=2400)
    output = tmp_path / "aligned.wav"

    assemble_aligned_narration_wav(
        plan, {"scene-a": audio_a}, {"scene-a": duration_a}, output,
    )

    with wave.open(str(output), "rb") as reader:
        assert reader.getnframes() >= 24000


def test_aligned_narration_rejects_missing_or_changed_scene_audio(tmp_path):
    project = _project()
    duration = seconds_to_ticks(0.1)
    plan = build_composition_timeline_plan(project, {"scene-a": duration})
    output = tmp_path / "aligned.wav"

    with pytest.raises(ProjectMotionProductionError, match="no scene WAV"):
        assemble_aligned_narration_wav(
            plan, {}, {"scene-a": duration}, output,
        )

    audio = _write_wav(tmp_path / "short.wav", frames=1200)
    with pytest.raises(ProjectMotionProductionError, match="duration changed"):
        assemble_aligned_narration_wav(
            plan, {"scene-a": audio}, {"scene-a": duration}, output,
        )


def test_project_production_plan_rejects_missing_scene_composition():
    project = _project()
    state = UniversalState.from_project_settings(project.settings)
    state.extra["scene_compositions"].pop("scene-b")
    project.settings = state.apply_to_project_settings(project.settings)

    with pytest.raises(ProjectMotionProductionError, match="not ready"):
        build_project_motion_production_plan(project, {})
