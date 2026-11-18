import copy
import math

import pytest

from app.universal import (
    CompositionCanvas,
    CompositionElement,
    CompositionValidationError,
    SceneComposition,
    VisualTransform,
)


def make_element(**overrides):
    values = {
        "element_id": "element-1",
        "asset_id": "asset-1",
        "transform": VisualTransform(x=0.1, y=0.2, width=0.4, height=0.5),
        "layer_order": 2,
        "fit_mode": "contain",
        "visible": True,
        "label": "Background image",
        "metadata": {"source": "user"},
    }
    values.update(overrides)
    return CompositionElement(**values)


def make_composition(**overrides):
    values = {
        "composition_id": "composition-1",
        "scene_id": "scene-1",
        "canvas": CompositionCanvas(1920, 1080),
        "elements": (make_element(),),
        "metadata": {"purpose": "test"},
    }
    values.update(overrides)
    return SceneComposition(**values)


def test_composition_round_trip_and_fingerprint_are_deterministic():
    composition = make_composition()
    restored = SceneComposition.from_dict(composition.to_dict())
    assert restored.to_dict() == composition.to_dict()
    assert restored.fingerprint == composition.fingerprint
    assert len(composition.fingerprint) == 64


def test_composition_preserves_unknown_top_level_and_element_fields():
    payload = make_composition().to_dict()
    payload["future_flag"] = {"enabled": True}
    payload["elements"][0]["future_element_field"] = "preserved"
    restored = SceneComposition.from_dict(payload)
    serialized = restored.to_dict()
    assert serialized["future_flag"] == {"enabled": True}
    assert serialized["elements"][0]["future_element_field"] == "preserved"


def test_composition_is_detached_from_input_metadata():
    metadata = {"nested": {"items": [1, 2]}}
    composition = make_composition(metadata=metadata)
    metadata["nested"]["items"].append(3)
    assert composition.metadata["nested"]["items"] == [1, 2]


def test_composition_rejects_duplicate_element_ids():
    with pytest.raises(CompositionValidationError, match="unique"):
        make_composition(elements=(make_element(), make_element()))


@pytest.mark.parametrize("version", [0, 2, 1.0, True, "1"])
def test_composition_rejects_unsupported_or_non_integer_versions(version):
    payload = make_composition().to_dict()
    payload["composition_version"] = version
    with pytest.raises(CompositionValidationError, match="version"):
        SceneComposition.from_dict(payload)


@pytest.mark.parametrize("kwargs", [
    {"x": -0.01},
    {"y": 1.01},
    {"width": 0},
    {"height": -0.1},
    {"x": 0.8, "width": 0.3},
    {"y": 0.8, "height": 0.3},
    {"opacity": 1.1},
    {"opacity": -0.1},
    {"anchor_x": 1.1},
    {"rotation_degrees": 361},
    {"rotation_degrees": -361},
    {"rotation_degrees": math.inf},
    {"rotation_degrees": math.nan},
    {"width": True},
])
def test_visual_transform_rejects_invalid_geometry_and_numbers(kwargs):
    with pytest.raises(CompositionValidationError):
        VisualTransform(**kwargs)


def test_visual_transform_accepts_normalized_geometry_and_rotation():
    transform = VisualTransform(
        x=0.25, y=0.1, width=0.5, height=0.6,
        anchor_x=0.0, anchor_y=1.0, rotation_degrees=-180, opacity=0.75,
    )
    assert transform.to_dict()["rotation_degrees"] == -180.0
    assert transform.to_dict()["opacity"] == 0.75


@pytest.mark.parametrize("fit_mode", ["contain", "cover", "stretch"])
def test_element_accepts_supported_fit_modes(fit_mode):
    assert make_element(fit_mode=fit_mode).fit_mode == fit_mode


@pytest.mark.parametrize("fit_mode", ["fill", "crop", "", None])
def test_element_rejects_unsupported_fit_modes(fit_mode):
    with pytest.raises(CompositionValidationError, match="fit_mode"):
        make_element(fit_mode=fit_mode)


@pytest.mark.parametrize("layer_order", [1.5, True, "1"])
def test_element_requires_integer_layer_order(layer_order):
    with pytest.raises(CompositionValidationError, match="layer_order"):
        make_element(layer_order=layer_order)


def test_element_requires_boolean_visibility():
    with pytest.raises(CompositionValidationError, match="visible"):
        make_element(visible=1)


@pytest.mark.parametrize("dimensions", [(0, 1080), (1920, 0), (16385, 1080), (True, 1080)])
def test_canvas_dimensions_are_bounded_positive_integers(dimensions):
    with pytest.raises(CompositionValidationError):
        CompositionCanvas(*dimensions)


def test_composition_rejects_non_json_metadata():
    with pytest.raises(CompositionValidationError, match="JSON-compatible"):
        make_composition(metadata={"bad": object()})


def test_composition_rejects_non_finite_metadata():
    with pytest.raises(CompositionValidationError, match="NaN or infinity"):
        make_composition(metadata={"bad": float("nan")})


def test_from_dict_rejects_non_array_elements_and_invalid_canvas():
    payload = make_composition().to_dict()
    payload["elements"] = "not-an-array"
    with pytest.raises(CompositionValidationError, match="array"):
        SceneComposition.from_dict(payload)
    with pytest.raises(CompositionValidationError, match="canvas.width"):
        CompositionCanvas.from_dict({"width": 0, "height": 1080})


def test_fingerprint_changes_when_composition_content_changes():
    original = make_composition()
    changed = make_composition(elements=(make_element(layer_order=3),))
    assert original.fingerprint != changed.fingerprint