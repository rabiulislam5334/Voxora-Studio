from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.core.timebase import TICKS_PER_SECOND
from app.studio.models import AudioSettings, MusicTrack
from app.universal.composition_timeline import (
    CompositionTimelinePlan,
    TimelinePlanDiagnostic,
)
from app.universal.composition_audio_mux import (
    CompositionAudioMuxError,
    build_composition_audio_mix_args,
    build_composition_video_mux_args,
    composition_video_duration,
)


def _plan(*, frames: int = 240, diagnostics=()) -> CompositionTimelinePlan:
    return CompositionTimelinePlan(
        project_id="project-a",
        fps=24,
        width=1920,
        height=1080,
        transition="cut",
        transition_ticks=0,
        total_ticks=10 * TICKS_PER_SECOND,
        total_frames=frames,
        slots=(),
        diagnostics=tuple(diagnostics),
        input_fingerprint="input",
        plan_fingerprint="plan",
    )


def test_video_duration_uses_frame_quantized_timeline_not_raw_ticks():
    plan = _plan(frames=241)
    ticks, seconds = composition_video_duration(plan)
    assert ticks == round(241 * TICKS_PER_SECOND / 24)
    assert seconds == pytest.approx(241 / 24)


def test_mix_command_reuses_studio_music_mixer_and_video_sample_rate(tmp_path: Path):
    audio = AudioSettings(
        narration_volume_percent=85,
        limiter=True,
        tracks=[MusicTrack(
            path="music.mp3", id="bgm-1", volume_percent=20,
            offset_s=1.25, fade_in_s=0.5, fade_out_s=1.0,
        )],
    )
    args = build_composition_audio_mix_args(
        Path("ffmpeg"), Path("narration.wav"), _plan(), audio,
        {"bgm-1": 30.0}, tmp_path / "mixed.wav",
    )
    assert args[0] == "ffmpeg"
    assert "music.mp3" in args
    assert str(constants.VIDEO_AUDIO_SAMPLE_RATE) in args
    graph = args[args.index("-filter_complex") + 1]
    assert "amix=inputs=2:normalize=0" in graph
    assert "adelay=delays=" in graph
    assert args[-1].endswith("mixed.wav")


def test_mux_command_copies_video_and_encodes_aac_with_exact_frame_limit(tmp_path: Path):
    args = build_composition_video_mux_args(
        Path("ffmpeg"), Path("silent.mp4"), Path("mixed.wav"),
        _plan(frames=241), tmp_path / "final.mp4",
    )
    assert args[args.index("-c:v") + 1] == "copy"
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-frames:v") + 1] == "241"
    assert args[args.index("-t") + 1] == "10.042"
    assert args[-1].endswith("final.mp4")


def test_invalid_timeline_blocks_audio_mix_and_mux():
    invalid = _plan(diagnostics=(
        TimelinePlanDiagnostic("MISSING_COMPOSITION", "error", "missing"),
    ))
    with pytest.raises(CompositionAudioMuxError, match="blocking diagnostics"):
        composition_video_duration(invalid)
    with pytest.raises(CompositionAudioMuxError, match="blocking diagnostics"):
        build_composition_video_mux_args(
            Path("ffmpeg"), Path("silent.mp4"), Path("audio.wav"),
            invalid, Path("final.mp4"),
        )


def test_audio_mix_requires_explicit_track_duration_for_music(tmp_path: Path):
    audio = AudioSettings(tracks=[MusicTrack(path="music.mp3", id="missing")])
    with pytest.raises(Exception, match="could not be read"):
        build_composition_audio_mix_args(
            Path("ffmpeg"), Path("narration.wav"), _plan(), audio, {},
            tmp_path / "mixed.wav",
        )
