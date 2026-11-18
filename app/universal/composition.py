"""Renderer-independent scene visual composition domain contracts."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

COMPOSITION_VERSION = 1
COMPOSITION_FIT_MODES = ("contain", "cover", "stretch")


class CompositionValidationError(ValueError):
    """Raised when scene composition data is invalid."""


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise CompositionValidationError(f"{name} must be a non-empty identifier (max 128 characters)")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompositionValidationError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise CompositionValidationError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise CompositionValidationError(f"{name} must be a finite number")
    return result


def _normalized(value: Any, name: str, *, allow_zero: bool = True) -> float:
    result = _finite_number(value, name)
    if result < 0 or result > 1 or (not allow_zero and result == 0):
        qualifier = "greater than 0 and at most 1" if not allow_zero else "between 0 and 1"
        raise CompositionValidationError(f"{name} must be {qualifier}")
    return result


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 16384:
        raise CompositionValidationError(f"{name} must be a positive integer no greater than 16384")
    return value


def _json_value(value: Any, path: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return copy.deepcopy(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CompositionValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CompositionValidationError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    raise CompositionValidationError(f"{path} must contain JSON-compatible values only")


def _metadata(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CompositionValidationError(f"{name} must be an object")
    return _json_value(value, name)


def _unknown(data: Mapping[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in data.items() if key not in known}


def _merge(data: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
    return data


@dataclass(frozen=True)
class CompositionCanvas:
    """Fixed output canvas dimensions in pixels; element geometry is normalized."""

    width: int = 1920
    height: int = 1080

    def __post_init__(self) -> None:
        _positive_int(self.width, "canvas.width")
        _positive_int(self.height, "canvas.height")

    def to_dict(self) -> dict[str, int]:
        return {"width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Any) -> "CompositionCanvas":
        if not isinstance(data, Mapping):
            raise CompositionValidationError("canvas must be an object")
        return cls(data.get("width", 1920), data.get("height", 1080))


@dataclass(frozen=True)
class VisualTransform:
    """Normalized rectangle and visual transform using a top-left frame origin."""

    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    anchor_x: float = 0.5
    anchor_y: float = 0.5
    rotation_degrees: float = 0.0
    opacity: float = 1.0

    def __post_init__(self) -> None:
        x = _normalized(self.x, "transform.x")
        y = _normalized(self.y, "transform.y")
        width = _normalized(self.width, "transform.width", allow_zero=False)
        height = _normalized(self.height, "transform.height", allow_zero=False)
        if x + width > 1 or y + height > 1:
            raise CompositionValidationError("transform rectangle must remain within the normalized canvas")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "anchor_x", _normalized(self.anchor_x, "transform.anchor_x"))
        object.__setattr__(self, "anchor_y", _normalized(self.anchor_y, "transform.anchor_y"))
        rotation = _finite_number(self.rotation_degrees, "transform.rotation_degrees")
        if rotation < -360 or rotation > 360:
            raise CompositionValidationError("transform.rotation_degrees must be between -360 and 360")
        object.__setattr__(self, "rotation_degrees", rotation)
        object.__setattr__(self, "opacity", _normalized(self.opacity, "transform.opacity"))

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "anchor_x": self.anchor_x, "anchor_y": self.anchor_y,
            "rotation_degrees": self.rotation_degrees, "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "VisualTransform":
        if not isinstance(data, Mapping):
            raise CompositionValidationError("transform must be an object")
        return cls(
            data.get("x", 0.0), data.get("y", 0.0),
            data.get("width", 1.0), data.get("height", 1.0),
            data.get("anchor_x", 0.5), data.get("anchor_y", 0.5),
            data.get("rotation_degrees", 0.0), data.get("opacity", 1.0),
        )


@dataclass(frozen=True)
class CompositionElement:
    """One positioned reference to an asset already bound to the scene."""

    element_id: str
    asset_id: str
    transform: VisualTransform = field(default_factory=VisualTransform)
    layer_order: int = 0
    fit_mode: str = "contain"
    visible: bool = True
    label: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.element_id, "element_id")
        _identifier(self.asset_id, "asset_id")
        if not isinstance(self.transform, VisualTransform):
            raise CompositionValidationError("element.transform must be VisualTransform")
        if isinstance(self.layer_order, bool) or not isinstance(self.layer_order, int):
            raise CompositionValidationError("element.layer_order must be an integer")
        if self.fit_mode not in COMPOSITION_FIT_MODES:
            raise CompositionValidationError("element.fit_mode must be contain, cover, or stretch")
        if not isinstance(self.visible, bool):
            raise CompositionValidationError("element.visible must be a boolean")
        if self.label is not None and not isinstance(self.label, str):
            raise CompositionValidationError("element.label must be a string or null")
        object.__setattr__(self, "metadata", _metadata(self.metadata, "element.metadata"))
        object.__setattr__(self, "extra", _metadata(self.extra, "element.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "element_id": self.element_id, "asset_id": self.asset_id,
            "transform": self.transform.to_dict(), "layer_order": self.layer_order,
            "fit_mode": self.fit_mode, "visible": self.visible, "label": self.label,
            "metadata": _metadata(self.metadata, "element.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "CompositionElement":
        if not isinstance(data, Mapping):
            raise CompositionValidationError("composition element must be an object")
        known = {"element_id", "asset_id", "transform", "layer_order", "fit_mode", "visible", "label", "metadata"}
        return cls(
            data.get("element_id"), data.get("asset_id"),
            VisualTransform.from_dict(data.get("transform", {})),
            data.get("layer_order", 0), data.get("fit_mode", "contain"),
            data.get("visible", True), data.get("label"), data.get("metadata", {}),
            _unknown(data, known),
        )


@dataclass(frozen=True)
class SceneComposition:
    """Versioned composition proposal for one scene; it does not mutate a Project."""

    composition_id: str
    scene_id: str
    canvas: CompositionCanvas = field(default_factory=CompositionCanvas)
    elements: Tuple[CompositionElement, ...] = ()
    composition_version: int = COMPOSITION_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.composition_id, "composition_id")
        _identifier(self.scene_id, "scene_id")
        if not isinstance(self.canvas, CompositionCanvas):
            raise CompositionValidationError("composition.canvas must be CompositionCanvas")
        if isinstance(self.composition_version, bool) or not isinstance(self.composition_version, int) or self.composition_version != COMPOSITION_VERSION:
            raise CompositionValidationError("unsupported composition version")
        elements = tuple(self.elements)
        if not all(isinstance(item, CompositionElement) for item in elements):
            raise CompositionValidationError("composition.elements must contain CompositionElement values")
        ids = [item.element_id for item in elements]
        if len(ids) != len(set(ids)):
            raise CompositionValidationError("composition element IDs must be unique")
        object.__setattr__(self, "elements", elements)
        object.__setattr__(self, "metadata", _metadata(self.metadata, "composition.metadata"))
        object.__setattr__(self, "extra", _metadata(self.extra, "composition.extra"))

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "composition_version": COMPOSITION_VERSION,
            "composition_id": self.composition_id, "scene_id": self.scene_id,
            "canvas": self.canvas.to_dict(),
            "elements": [item.to_dict() for item in self.elements],
            "metadata": _metadata(self.metadata, "composition.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "SceneComposition":
        if not isinstance(data, Mapping):
            raise CompositionValidationError("scene composition must be an object")
        version = data.get("composition_version", COMPOSITION_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version != COMPOSITION_VERSION:
            raise CompositionValidationError("unsupported composition version")
        raw_elements = data.get("elements", [])
        if not isinstance(raw_elements, (list, tuple)):
            raise CompositionValidationError("composition.elements must be an array")
        known = {"composition_version", "composition_id", "scene_id", "canvas", "elements", "metadata"}
        return cls(
            data.get("composition_id"), data.get("scene_id"),
            CompositionCanvas.from_dict(data.get("canvas", {})),
            tuple(CompositionElement.from_dict(item) for item in raw_elements),
            version, data.get("metadata", {}), _unknown(data, known),
        )
