from __future__ import annotations

from app.core.timebase import seconds_to_ticks
from app.studio.models import MusicTrack, SceneVideo, StudioState


def test_studio_serializes_duration_values_as_decimal_tick_strings():
    state = StudioState()
    track = MusicTrack(
        path="music.mp3",
        fade_in_s=1.25,
        fade_out_s=2.5,
        offset_s=3.125,
        trim_start_s=0.25,
        trim_end_s=12.75,
    )
    state.audio.tracks.append(track)
    state.video.transition_s = 0.75
    state.video.default_duration_s = 6.25
    state.video.set_scene("scene-1", SceneVideo(duration_s=8.125))

    data = state.to_dict()
    saved_track = data["audio"]["tracks"][0]
    saved_scene = data["video"]["scenes"]["scene-1"]

    assert data["version"] == 2
    assert saved_track["offset_ticks"] == str(seconds_to_ticks("3.125"))
    assert saved_track["trim_end_ticks"] == str(seconds_to_ticks("12.75"))
    assert saved_scene["duration_ticks"] == str(seconds_to_ticks("8.125"))
    assert data["video"]["transition_ticks"] == str(seconds_to_ticks("0.75"))
    assert data["video"]["default_duration_ticks"] == str(seconds_to_ticks("6.25"))


def test_studio_prefers_exact_tick_fields_when_legacy_seconds_disagree():
    state = StudioState.from_dict({
        "version": 1,
        "audio": {
            "tracks": [{
                "path": "music.mp3",
                "offset_s": 99.0,
                "offset_ticks": str(seconds_to_ticks("1.25")),
            }],
        },
        "video": {
            "transition_s": 99.0,
            "transition_ticks": str(seconds_to_ticks("0.75")),
            "scenes": {
                "scene-1": {
                    "duration_s": 99.0,
                    "duration_ticks": str(seconds_to_ticks("4.5")),
                },
            },
        },
    })

    assert state.audio.tracks[0].offset_s == 1.25
    assert state.video.transition_s == 0.75
    assert state.video.scene("scene-1").duration_s == 4.5


def test_legacy_seconds_only_studio_settings_still_load_and_gain_tick_fields():
    state = StudioState.from_dict({
        "version": 1,
        "audio": {"tracks": [{"path": "music.mp3", "offset_s": 2.5}]},
        "video": {"transition_s": 1.5, "scenes": {"s": {"duration_s": 7.25}}},
    })

    data = state.to_dict()
    assert data["audio"]["tracks"][0]["offset_s"] == 2.5
    assert data["audio"]["tracks"][0]["offset_ticks"] == str(seconds_to_ticks("2.5"))
    assert data["video"]["transition_ticks"] == str(seconds_to_ticks("1.5"))
    assert data["video"]["scenes"]["s"]["duration_ticks"] == str(seconds_to_ticks("7.25"))
