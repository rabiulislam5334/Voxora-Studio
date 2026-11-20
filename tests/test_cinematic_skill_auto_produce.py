from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audio.ffmpeg_tool import FFmpegTool
from app.core.settings_store import SettingsStore
from app.universal.cinematic_skill_adapter import CinematicSkillRenderResult
from app.universal.cinematic_skill_auto_produce import (
    CinematicSkillAutoProduceError,
    CinematicSkillAutoProduceWorkflow,
    SuppliedNarrationMuxer,
)


class _Aligner:
    def __init__(self, doc):
        self.doc = doc
        self.calls = []

    def align(self, **kwargs):
        self.calls.append(kwargs)
        return self.doc


class _Builder:
    def __init__(self, film):
        self.film = film
        self.calls = []

    def build(self, doc, **kwargs):
        self.calls.append((doc, kwargs))
        return self.film


class _Renderer:
    def __init__(self):
        self.calls = []

    def render(self, film, destination, **kwargs):
        self.calls.append((film, Path(destination), kwargs))
        return CinematicSkillRenderResult(
            destination=Path(destination), frame_count=48, fps=24,
            width=1280, height=720, duration_seconds=2.0,
            output_sha256="a" * 64, audio_included=True,
        )


def _ffmpeg(tmp_path):
    return FFmpegTool(SettingsStore(tmp_path / "settings.json"))


def test_supplied_script_and_audio_are_orchestrated_without_tts(tmp_path, monkeypatch):
    audio = tmp_path / "narration.mp3"
    audio.write_bytes(b"audio")
    doc = SimpleNamespace(lines={
        1: SimpleNamespace(word_timings=(1, 2, 3)),
        2: SimpleNamespace(word_timings=(4, 5)),
    })
    film = SimpleNamespace(duration=2.0, fps=24)
    ffmpeg = _ffmpeg(tmp_path)
    monkeypatch.setattr(
        ffmpeg, "probe",
        lambda path, cancel=None: SimpleNamespace(has_audio=True, duration_s=2.0),
    )
    aligner, builder, renderer = _Aligner(doc), _Builder(film), _Renderer()
    workflow = CinematicSkillAutoProduceWorkflow(
        ffmpeg, aligner=aligner, film_builder=builder, renderer=renderer,
    )
    progress = []
    destination = tmp_path / "out" / "finished.mp4"

    result = workflow.run(
        script="The first line.\nThe second line.",
        narration_audio=audio,
        language="en",
        project_dir=tmp_path / "project",
        destination=destination,
        fps=24,
        width=1280,
        height=720,
        on_progress=lambda fraction, message: progress.append((fraction, message)),
    )

    assert result.render.destination == destination
    assert result.narration_duration_seconds == 2.0
    assert result.aligned_line_count == 2
    assert result.aligned_word_count == 5
    assert result.language == "en"
    assert aligner.calls[0]["script"] == "The first line.\nThe second line."
    assert aligner.calls[0]["audio_path"] == audio.resolve()
    assert aligner.calls[0]["language"] == "en"
    assert builder.calls == [(doc, {"look": "studio", "fps": 24})]
    render_kwargs = renderer.calls[0][2]
    assert render_kwargs["narration_wav"] == audio.resolve()
    assert render_kwargs["timeline_plan"].total_frames == 48
    assert render_kwargs["audio_muxer"].__class__ is SuppliedNarrationMuxer
    assert progress[0][1] == "Inspecting supplied narration"
    assert progress[-1][1] == "Cinematic Skill MP4 complete"
    assert not list((tmp_path / "project").glob("voxora-auto-produce-*"))


def test_workflow_rejects_audio_without_audio_stream(tmp_path, monkeypatch):
    audio = tmp_path / "empty.mp3"
    audio.write_bytes(b"not audio")
    ffmpeg = _ffmpeg(tmp_path)
    monkeypatch.setattr(
        ffmpeg, "probe",
        lambda path, cancel=None: SimpleNamespace(has_audio=False, duration_s=2.0),
    )
    renderer = _Renderer()
    workflow = CinematicSkillAutoProduceWorkflow(
        ffmpeg, aligner=_Aligner(object()), film_builder=_Builder(object()), renderer=renderer,
    )

    with pytest.raises(CinematicSkillAutoProduceError, match="no readable audio"):
        workflow.run(
            script="A valid script.", narration_audio=audio, language="en",
            project_dir=tmp_path / "project", destination=tmp_path / "out.mp4",
        )
    assert not renderer.calls


def test_muxer_uses_supplied_audio_and_pads_only_tail_to_frame_duration(tmp_path, monkeypatch):
    ffmpeg = _ffmpeg(tmp_path)
    silent = tmp_path / "silent.mp4"
    narration = tmp_path / "narration.wav"
    destination = tmp_path / "final.mp4"
    silent.write_bytes(b"silent")
    narration.write_bytes(b"narration")
    captured = {}

    monkeypatch.setattr(ffmpeg, "require", lambda: Path("ffmpeg.exe"))

    def run_args(args, cancel=None, timeout=600.0):
        captured["args"] = args
        Path(args[-1]).write_bytes(b"muxed")

    monkeypatch.setattr(ffmpeg, "run_args", run_args)
    monkeypatch.setattr(
        ffmpeg, "probe_structured",
        lambda path, cancel=None: SimpleNamespace(streams=(
            SimpleNamespace(codec_type="video", codec_name="h264", duration_s=2.0),
            SimpleNamespace(codec_type="audio", codec_name="aac", duration_s=2.0),
        )),
    )

    result = SuppliedNarrationMuxer(ffmpeg).render(
        silent, narration, object(), destination,
        SimpleNamespace(fps=24, total_frames=48),
    )

    assert destination.read_bytes() == b"muxed"
    assert result.video_codec == "h264"
    assert result.audio_codec == "aac"
    args = captured["args"]
    assert str(narration) in args
    assert args[args.index("-map") + 1] == "0:v:0"
    assert "1:a:0" in args
    assert "copy" in args
    assert "apad" in args
    assert "-shortest" not in args
    assert not list(tmp_path.glob("*.part.mp4"))


def test_muxer_rejects_invalid_final_streams_and_cleans_temp(tmp_path, monkeypatch):
    ffmpeg = _ffmpeg(tmp_path)
    silent = tmp_path / "silent.mp4"
    narration = tmp_path / "narration.wav"
    destination = tmp_path / "final.mp4"
    silent.write_bytes(b"silent")
    narration.write_bytes(b"narration")
    monkeypatch.setattr(ffmpeg, "require", lambda: Path("ffmpeg.exe"))

    def run_args(args, cancel=None, timeout=600.0):
        Path(args[-1]).write_bytes(b"muxed")

    monkeypatch.setattr(ffmpeg, "run_args", run_args)
    monkeypatch.setattr(
        ffmpeg, "probe_structured",
        lambda path, cancel=None: SimpleNamespace(streams=(
            SimpleNamespace(codec_type="video", codec_name="mpeg4", duration_s=2.0),
        )),
    )
    with pytest.raises(CinematicSkillAutoProduceError, match="both video and narration"):
        SuppliedNarrationMuxer(ffmpeg).render(
            silent, narration, object(), destination,
            SimpleNamespace(fps=24, total_frames=48),
        )
    assert not destination.exists()
    assert not list(tmp_path.glob("*.part.mp4"))
