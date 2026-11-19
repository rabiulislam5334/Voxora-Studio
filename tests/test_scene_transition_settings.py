from app.studio.models import StudioState
from app.universal.transitions import TransitionSpec


def test_scene_transition_overrides_round_trip_through_studio_settings():
    payload = {
        "version": 2,
        "audio": {"narration_volume_percent": 100, "limiter": True, "tracks": []},
        "video": {
            "aspect": "16:9",
            "resolution": "720p",
            "fps": 30,
            "transition": "crossfade",
            "transition_s": 0.75,
            "default_duration_s": 5.0,
            "default_motion": "zoom_in",
            "default_fit": "fill",
            "scenes": {},
            "scene_transitions": {
                "version": 1,
                "scenes": {
                    "scene-1": {
                        "version": 1,
                        "effect": "wipe_left",
                        "duration_ticks": 52920000,
                        "easing": "ease_in_out",
                    }
                },
            },
        },
    }

    state = StudioState.from_dict(payload)
    assert not state.read_only
    assert state.video.extra["scene_transitions"]["scenes"]["scene-1"]["effect"] == "wipe_left"

    restored = StudioState.from_dict(state.to_dict())
    stored = restored.video.extra["scene_transitions"]["scenes"]["scene-1"]
    assert TransitionSpec.from_dict(stored).effect == "wipe_left"
    assert TransitionSpec.from_dict(stored).easing == "ease_in_out"


def test_unknown_scene_transition_metadata_is_preserved():
    payload = {
        "version": 2,
        "audio": {"narration_volume_percent": 100, "limiter": True, "tracks": []},
        "video": {
            "transition": "crossfade",
            "transition_s": 0.5,
            "scenes": {},
            "scene_transitions": {
                "version": 1,
                "scenes": {},
                "future_editor_hint": {"mode": "advanced"},
            },
        },
    }
    state = StudioState.from_dict(payload)
    round_trip = StudioState.from_dict(state.to_dict())
    assert round_trip.video.extra["scene_transitions"]["future_editor_hint"] == {
        "mode": "advanced"
    }
