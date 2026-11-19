import pytest

from app.universal.transitions import (
    TRANSITION_EFFECTS,
    TransitionSpec,
    TransitionValidationError,
    transition_boundary,
    transition_progress,
)


def test_transition_spec_round_trip_and_fingerprint_are_stable():
    spec = TransitionSpec(
        effect="dip_to_color",
        duration_ticks=141120000,
        easing="ease_in_out",
        color_rgb=(12, 34, 56),
        extra={"future_hint": "preserve"},
    )

    restored = TransitionSpec.from_dict(spec.to_dict())

    assert restored.to_dict() == spec.to_dict()
    assert restored.fingerprint == spec.fingerprint
    assert restored.extra["future_hint"] == "preserve"


@pytest.mark.parametrize("effect", TRANSITION_EFFECTS)
def test_transition_effects_have_valid_specs(effect):
    if effect == "cut":
        spec = TransitionSpec(effect=effect, duration_ticks=0)
    elif effect == "dip_to_color":
        spec = TransitionSpec(effect=effect, duration_ticks=1, color_rgb=(0, 0, 0))
    else:
        spec = TransitionSpec(effect=effect, duration_ticks=1)
    assert spec.effect == effect


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"effect": "unknown", "duration_ticks": 1}, "unsupported transition effect"),
        ({"effect": "cut", "duration_ticks": 1}, "zero duration"),
        ({"effect": "crossfade", "duration_ticks": 0}, "positive duration"),
        ({"effect": "dip_to_color", "duration_ticks": 1}, "requires an RGB color"),
        ({"effect": "dip_to_color", "duration_ticks": 1, "color_rgb": (0, 0, 256)}, "between 0 and 255"),
        ({"effect": "wipe_left", "duration_ticks": 1, "color_rgb": (0, 0, 0)}, "only valid"),
        ({"effect": "wipe_left", "duration_ticks": -1}, ">= 0"),
        ({"effect": "wipe_left", "duration_ticks": 1, "easing": "bounce"}, "easing must be"),
    ],
)
def test_transition_spec_rejects_invalid_values(kwargs, message):
    with pytest.raises(TransitionValidationError, match=message):
        TransitionSpec(**kwargs)


def test_transition_progress_has_exact_endpoints_and_easing():
    assert [transition_progress(i, 5) for i in range(5)] == [
        0.0, 0.25, 0.5, 0.75, 1.0,
    ]
    assert transition_progress(1, 3, easing="ease_in") == pytest.approx(0.25)
    assert transition_progress(1, 3, easing="ease_out") == pytest.approx(0.75)
    assert transition_progress(1, 3, easing="ease_in_out") == pytest.approx(0.5)


@pytest.mark.parametrize(
    "frame_index, frame_count",
    [(-1, 3), (3, 3), (0, 1), (0, 0)],
)
def test_transition_progress_rejects_invalid_frame_intervals(frame_index, frame_count):
    with pytest.raises(TransitionValidationError):
        transition_progress(frame_index, frame_count)


def test_transition_boundary_uses_round_half_up_and_clamps_exact_endpoints():
    assert transition_boundary(5, 0.0) == 0
    assert transition_boundary(5, 0.5) == 3
    assert transition_boundary(5, 1.0) == 5


@pytest.mark.parametrize("progress", [-0.01, 1.01, float("nan"), float("inf")])
def test_transition_boundary_rejects_invalid_progress(progress):
    with pytest.raises(TransitionValidationError):
        transition_boundary(10, progress)
