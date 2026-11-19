from __future__ import annotations

import wave
from pathlib import Path

import pytest
from PIL import Image

from app.models.project import Project
from app.models.scene import Scene
from app.studio.models import StudioState, VideoSettings
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import CompositionElement, SceneComposition
from app.universal.composition_workflow import apply_scene_composition, preview_scene_composition
from app.universal.models import AssetRef, ScenePlan, UniversalState
from app.universal import production_workflow
from app.workers.narration import NarrationResult, SceneAudio, SceneRequest
from app.audio.assembler import wav_duration_ticks


def _make_project(tmp_path: Path):
    source = tmp_path / "source.png"
    Image.new("RGBA", (64, 64), (220, 40, 30, 255)).save(source)
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source, asset_id="asset-1")

    project = Project(
        id="universal-e2e-project",
        name="Universal E2E",
        scenes=[Scene(id="scene-1", title="Scene 1", text="A short narration.", order=0)],
    )
    state = UniversalState()
    state.scene_plans = {
        "scene-1": ScenePlan(
            scene_id="scene-1",
            asset_refs=[AssetRef(
                "asset-1", "image", path=asset.location,
                identity=asset.content_sha256,
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
        fps=24, transition="cut", default_duration_s=0.5,
    ))
    studio.write_to(project.settings)
    return project, library


def _write_narration(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\\x00\\x00" * 2400)
    return wav_duration_ticks(path)


class _NarrationJob:
    def __init__(self, wav_path: Path):
        self.wav_path = wav_path

    async def run(self, requests, *, output_dir, basename, cancel, on_progress):
        duration = wav_duration_ticks(self.wav_path)
        return NarrationResult(
            mp3_path=output_dir / f"{basename}.mp3",
            wav_path=self.wav_path,
            duration_seconds=0.1,
            scene_timings=[],
            chunk_count=1,
            cached_chunks=0,
            synthesized_chunks=1,
            scene_audio=[
                SceneAudio("scene-1", self.wav_path, 0.1, 0, duration),
            ],
            duration_ticks=duration,
        )


@pytest.mark.asyncio
async def test_universal_produce_does_not_publish_video_when_render_fails(tmp_path, monkeypatch):
    project, library = _make_project(tmp_path)
    narration_wav = tmp_path / "narration" / "scene-1.wav"
    _write_narration(narration_wav)
    destination = tmp_path / "output" / "final.mp4"
    destination.parent.mkdir(parents=True)

    def fail_render(*args, **kwargs):
        raise production_workflow.ProjectMotionProductionError("simulated encoder validation failure")

    monkeypatch.setattr(
        production_workflow, "render_project_motion_production", fail_render,
    )

    request = SceneRequest(
        scene_id="scene-1", scene_index=1, title="Scene 1",
        text="A short narration.", voice_id="en-US-BrianNeural",
        rate=1.0, pitch_hz=0, volume_percent=100,
        sentence_pause_ms=0, paragraph_pause_ms=0, scene_pause_ms=0,
    )

    with pytest.raises(production_workflow.ProjectMotionProductionError, match="simulated encoder"):
        await production_workflow.run_universal_production(
            _NarrationJob(narration_wav), [request], project,
            ffmpeg=object(), asset_library=library,
            narration_output_dir=tmp_path / "narration",
            basename="final", video_destination=destination,
        )

    assert not destination.exists()
    assert not list(destination.parent.glob(".final.voxora-*.mp4"))
