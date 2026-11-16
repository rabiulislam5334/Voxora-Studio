from __future__ import annotations

import wave
from pathlib import Path

import pytest

from app.audio.assembler import WavBuilder, wav_duration_ticks
from app.core.timebase import samples_to_ticks, seconds_to_ticks, ticks_to_samples


@pytest.mark.parametrize("sample_rate", [24_000, 44_100, 48_000])
def test_wav_builder_duration_is_exact_sample_count(tmp_path: Path, sample_rate: int) -> None:
    path = tmp_path / "samples.wav"
    expected_frames = sample_rate + 137

    with WavBuilder(path, sample_rate) as builder:
        builder.add_silence_samples(expected_frames)
        assert builder.frames == expected_frames
        assert builder.duration_ticks == samples_to_ticks(expected_frames, sample_rate)
        assert builder.duration_seconds == pytest.approx(expected_frames / sample_rate)

    with wave.open(str(path), "rb") as reader:
        assert reader.getnframes() == expected_frames
        assert wav_duration_ticks(path) == samples_to_ticks(expected_frames, sample_rate)


@pytest.mark.parametrize("sample_rate", [24_000, 44_100, 48_000])
def test_tick_silence_maps_to_exact_whole_samples(tmp_path: Path, sample_rate: int) -> None:
    path = tmp_path / "tick-silence.wav"
    samples = sample_rate // 2
    ticks = samples_to_ticks(samples, sample_rate)

    with WavBuilder(path, sample_rate) as builder:
        builder.add_silence_ticks(ticks)
        assert builder.frames == samples
        assert builder.duration_ticks == ticks

    assert wav_duration_ticks(path) == ticks
    assert ticks_to_samples(ticks, sample_rate, rounding="exact") == samples


def test_tick_silence_rejects_duration_not_representable_as_samples(tmp_path: Path) -> None:
    path = tmp_path / "not-whole-sample.wav"
    with WavBuilder(path, 24_000) as builder:
        with pytest.raises(ValueError, match="not exact"):
            builder.add_silence_ticks(1)


def test_legacy_millisecond_silence_keeps_sample_count_behavior(tmp_path: Path) -> None:
    path = tmp_path / "legacy.wav"
    with WavBuilder(path, 24_000) as builder:
        builder.add_silence(125)
        assert builder.frames == 3_000
