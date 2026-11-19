from __future__ import annotations

import asyncio
import wave
from pathlib import Path

import pytest
from PIL import Image

from app.audio.assembler import wav_duration_ticks
from app.audio.ffmpeg_tool import FFmpegTool
from app.core.settings_store import SettingsStore
from app.models.project import Project
from app.models.scene import Scene
from app.studio.models import StudioState, VideoSettings
from app.universal import production_workflow
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import CompositionCanvas, CompositionElement, SceneComposition
from app.universal.composition_workflow import apply_scene_composition, preview_scene_composition
from app.universal.models import AssetRef, ScenePlan, UniversalState
from app.workers.narration import NarrationResult, SceneAudio, SceneRequest


def _make_project(tmp_path: Path):
    library = VisualAssetLibrary(tmp_path / "library")
    assets = {}
    for scene_id, color in (
        ("scene-1", (220, 40, 30, 255)),
        ("scene-2", (30, 80, 220, 255)),
    ):
        source = tmp_path / f"{scene_id}.png"
        Image.new("RGBA", (64, 64), color).save(source)
        assets[scene_id] = library.import_file(
            source, asset_id=f"asset-{scene_id}",
        )

    project = Project(
        id="universal-e2e-project",
        name="Universal E2E",
        scenes=[
            Scene(id="scene-1", title="Scene 1", text="The first scene.", order=0),
            Scene(id="scene-2", title="Scene 2", text="The second scene.", order=1),
        ],
    )
    state = UniversalState()
    state.scene_plans = {
        scene_id: ScenePlan(
            scene_id=scene_id,
            asset_refs=[AssetRef(
                asset.asset_id, "image", path=asset.location,
                identity=asset.content_sha256,
            )],
        )
        for scene_id, asset in assets.items()
    }
    project.settings = state.apply_to_project_settings(project.settings)

    for index, scene_id in enumerate(("scene-1", "scene-2"), start=1):
        composition = SceneComposition(
            composition_id=f"composition-{index}",
            scene_id=scene_id,
            canvas=CompositionCanvas(width=640, height=360),
            elements=(CompositionElement(
                element_id=f"element-{index}",
                asset_id=f"asset-{scene_id}",
            ),),
        )
        preview = preview_scene_composition(project, composition)
        assert preview.is_valid
        apply_scene_composition(project, composition, preview, approved=True)

    studio = StudioState(video=VideoSettings(
        fps=12, resolution="360p (draft)", transition="crossfade",
        transition_s=0.25, default_duration_s=0.5,
    ))
    studio.write_to(project.settings)
    return project, library


def _write_narration(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * 2400)
    return wav_duration_ticks(path)


def _request(scene_id: str, scene_index: int) -> SceneRequest:
    return SceneRequest(
        scene_id=scene_id, scene_index=scene_index, title=f"Scene {scene_index}",
        text=f"Narration for scene {scene_index}.", voice_id="en-US-BrianNeural",
        rate=1.0, pitch_hz=0, volume_percent=100,
        sentence_pause_ms=0, paragraph_pause_ms=0, scene_pause_ms=0,
    )


class _NarrationJob:
    def __init__(self, wav_paths: dict[str, Path]):
        self.wav_paths = wav_paths

    async def run(self, requests, *, output_dir, basename, cancel, on_progress):
        scene_audio = []
        for request in requests:
            wav_path = self.wav_paths[request.scene_id]
            duration = wav_duration_ticks(wav_path)
            scene_audio.append(SceneAudio(
                request.scene_id, wav_path, 0.1, 0, duration,
            ))
        total_ticks = sum(item.duration_ticks for item in scene_audio)
        first_wav = scene_audio[0].wav_path
        return NarrationResult(
            mp3_path=output_dir / f"{basename}.mp3",
            wav_path=first_wav,
            duration_seconds=sum(item.duration_s for item in scene_audio),
            scene_timings=[],
            chunk_count=len(scene_audio),
            cached_chunks=0,
            synthesized_chunks=len(scene_audio),
            scene_audio=scene_audio,
            duration_ticks=total_ticks,
        )


def test_universal_produce_does_not_publish_video_when_render_fails(tmp_path, monkeypatch):
    async def scenario():
        project, library = _make_project(tmp_path)
        narration_wav = tmp_path / "narration" / "scene-1.wav"
        _write_narration(narration_wav)
        destination = tmp_path / "output" / "final.mp4"
        destination.parent.mkdir(parents=True)

        def fail_render(*args, **kwargs):
            raise production_workflow.ProjectMotionProductionError(
                "simulated encoder validation failure"
            )

        monkeypatch.setattr(
            production_workflow, "render_project_motion_production", fail_render,
        )

        with pytest.raises(
            production_workflow.ProjectMotionProductionError,
            match="simulated encoder",
        ):
            await production_workflow.run_universal_production(
                _NarrationJob({"scene-1": narration_wav}), [_request("scene-1", 1)],
                project, ffmpeg=object(), asset_library=library,
                narration_output_dir=tmp_path / "narration",
                basename="final", video_destination=destination,
            )

        assert not destination.exists()
        assert not list(destination.parent.glob(".final.voxora-*.mp4"))

    asyncio.run(scenario())


def test_universal_produce_renders_two_scenes_with_crossfade_and_aligned_narration(tmp_path):
    async def scenario():
        project, library = _make_project(tmp_path)
        narration_paths = {
            scene_id: _write_narration(tmp_path / "narration" / f"{scene_id}.wav")
            for scene_id in ("scene-1", "scene-2")
        }
        destination = tmp_path / "output" / "real-render.mp4"
        ffmpeg = FFmpegTool(SettingsStore(tmp_path / "settings.json"))
        status = ffmpeg.detect()
        assert status.available, status.message

        requests = [_request("scene-1", 1), _request("scene-2", 2)]
        result = await production_workflow.run_universal_production(
            _NarrationJob(narration_paths), requests, project,
            ffmpeg=ffmpeg, asset_library=library,
            narration_output_dir=tmp_path / "narration",
            basename="real-render", video_destination=destination,
        )

        assert destination.is_file()
        assert destination.stat().st_size > 0
        assert result.render.destination == destination
        assert result.render.frame_count == 12
        assert result.render.fps == 12
        assert result.render.audio.video_codec == "h264"
        assert result.render.audio.audio_codec == "aac"

        media = ffmpeg.probe_structured(destination, count_packets=True)
        video = next(stream for stream in media.streams if stream.codec_type == "video")
        audio = next(stream for stream in media.streams if stream.codec_type == "audio")
        assert video.width == 640
        assert video.height == 360
        assert video.packet_count == 12
        assert video.avg_frame_rate == "12/1"
        assert audio.codec_name == "aac"
        assert media.format_duration_s == pytest.approx(1.0, abs=0.04)
        assert not list(destination.parent.glob(".real-render.voxora-*.mp4"))
        assert not list(destination.parent.glob(".voxora-universal-produce-*"))

    asyncio.run(scenario())
