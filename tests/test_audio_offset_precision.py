from __future__ import annotations

from app.audio.mixer import _music_chain
from app.core.timebase import seconds_to_ticks
from app.studio.models import MusicTrack


def test_music_offset_is_preserved_at_output_sample_precision() -> None:
    track = MusicTrack(
        path="music.wav",
        id="music-1",
        offset_s=0.0005,
        fade_in_s=0.0,
        fade_out_s=0.0,
        loop=False,
    )

    chain = _music_chain(1, track, 10.0, 10.0, 48_000)

    # 0.5 ms is exactly 24 samples at 48 kHz. A millisecond-based
    # adelay would round this to 1 ms (48 samples), doubling the offset.
    assert seconds_to_ticks("0.0005") > 0
    assert "adelay=delays=24S:all=1" in chain


def test_music_offset_uses_the_selected_output_sample_rate() -> None:
    track = MusicTrack(
        path="music.wav",
        id="music-2",
        offset_s=0.001,
        fade_in_s=0.0,
        fade_out_s=0.0,
        loop=False,
    )

    chain_48k = _music_chain(1, track, 10.0, 10.0, 48_000)
    chain_44k = _music_chain(1, track, 10.0, 10.0, 44_100)

    assert "adelay=delays=48S:all=1" in chain_48k
    assert "adelay=delays=44S:all=1" in chain_44k


def test_zero_music_offset_does_not_add_delay_filter() -> None:
    track = MusicTrack(
        path="music.wav",
        id="music-3",
        offset_s=0.0,
        fade_in_s=0.0,
        fade_out_s=0.0,
        loop=False,
    )

    chain = _music_chain(1, track, 10.0, 10.0, 48_000)

    assert "adelay=" not in chain
