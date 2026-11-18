"""Deterministic, renderer-independent motion and camera animation contracts.

Motion is evaluated on integer output frames. This module only produces
immutable evaluated values; it does not render, mutate a composition, or
change the legacy ProductionJob pipeline.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

MOTION_VERSION = 1
MOTION_INTERPOLATIONS = ("hold", "linear", "ease_in", "ease_out", "ease_in_out")
_ELEMENT_PROPERTIES = frozenset({
    "x", "y", "width", "height", "anchor_x", "anchor_y",
    "rotation_degrees", "opacity",
})
_CAMERA_PROPERTIES = frozenset({"pan_x", "pan_y", "zoom", "rotation_degrees"})


class MotionValidationError(ValueError):
    """Raised when persisted scene motion data is invalid."""


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise MotionValidationError(f"{name} must be a non-empty identifier (max 128 characters)")
    return value


def _frame(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MotionValidationError(f"{name} must be a non-negative integer frame")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MotionValidationError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise MotionValidationError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise MotionValidationError(f"{name} must be a finite number")
    return result


@dataclass(frozen=True)
class MotionKeyframe:
    """One scalar property value at an integer frame.

    interpolation controls the segment from this keyframe to the next one.
    """

    frame: int
    value: float
    interpolation: str = "linear"

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame", _frame(self.frame, "keyframe.frame"))
        object.__setattr__(self, "value", _finite(self.value, "keyframe.value"))
        if self.interpolation not in MOTION_INTERPOLATIONS:
            raise MotionValidationError(
                "keyframe.interpolation must be hold, linear, ease_in, ease_out, or ease_in_out"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "value": self.value,
            "interpolation": self.interpolation,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MotionKeyframe":
        if not isinstance(data, Mapping):
            raise MotionValidationError("keyframe must be an object")
        return cls(
            data.get("frame"),
            data.get("value"),
            data.get("interpolation", "linear"),
        )


@dataclass(frozen=True)
class MotionTrack:
    """A scalar animation track targeting one element or the scene camera."""

    track_id: str
    target_type: str
    target_id: str
    property_name: str
    keyframes: Tuple[MotionKeyframe, ...]
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.track_id, "track_id")
        if self.target_type not in ("element", "camera"):
            raise MotionValidationError("track.target_type must be element or camera")
        _identifier(self.target_id, "target_id")
        if self.target_type == "camera":
            if self.target_id != "camera":
                raise MotionValidationError("camera tracks must use target_id='camera'")
            allowed = _CAMERA_PROPERTIES
        else:
            allowed = _ELEMENT_PROPERTIES
        if self.property_name not in allowed:
            raise MotionValidationError(
                f"unsupported {self.target_type} motion property: {self.property_name}"
            )
        frames = tuple(self.keyframes)
        if not frames or not all(isinstance(item, MotionKeyframe) for item in frames):
            raise MotionValidationError("track.keyframes must contain at least one MotionKeyframe")
        positions = [item.frame for item in frames]
        if positions != sorted(positions) or len(positions) != len(set(positions)):
            raise MotionValidationError("track keyframes must be ordered by unique frame numbers")
        for keyframe in frames:
            value = keyframe.value
            if self.target_type == "element":
                if self.property_name in {"x", "y", "width", "height", "anchor_x", "anchor_y", "opacity"}:
                    minimum = 0.0 if self.property_name in {"width", "height"} else 0.0
                    if value < minimum or value > 1.0 or (self.property_name in {"width", "height"} and value == 0.0):
                        raise MotionValidationError(
                            f"element {self.property_name} motion values must be in the normalized range"
                        )
                elif not -360.0 <= value <= 360.0:
                    raise MotionValidationError("element rotation_degrees must be between -360 and 360")
            else:
                if self.property_name == "zoom" and not 0.01 <= value <= 16.0:
                    raise MotionValidationError("camera zoom must be between 0.01 and 16")
                if self.property_name in {"pan_x", "pan_y"} and not -4.0 <= value <= 4.0:
                    raise MotionValidationError("camera pan values must be between -4 and 4")
                if self.property_name == "rotation_degrees" and not -360.0 <= value <= 360.0:
                    raise MotionValidationError("camera rotation_degrees must be between -360 and 360")
        object.__setattr__(self, "keyframes", frames)
        if not isinstance(self.extra, Mapping):
            raise MotionValidationError("track.extra must be an object")
        object.__setattr__(self, "extra", copy.deepcopy(dict(self.extra)))

    def to_dict(self) -> dict[str, Any]:
        result = {
            "track_id": self.track_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "property_name": self.property_name,
            "keyframes": [item.to_dict() for item in self.keyframes],
        }
        for key, value in self.extra.items():
            if key not in result:
                result[key] = copy.deepcopy(value)
        return result

    @classmethod
    def from_dict(cls, data: Any) -> "MotionTrack":
        if not isinstance(data, Mapping):
            raise MotionValidationError("motion track must be an object")
        known = {"track_id", "target_type", "target_id", "property_name", "keyframes"}
        raw = data.get("keyframes", [])
        if not isinstance(raw, (list, tuple)):
            raise MotionValidationError("track.keyframes must be an array")
        return cls(
            data.get("track_id"),
            data.get("target_type"),
            data.get("target_id"),
            data.get("property_name"),
            tuple(MotionKeyframe.from_dict(item) for item in raw),
            {key: copy.deepcopy(value) for key, value in data.items() if key not in known},
        )


@dataclass(frozen=True)
class SceneMotion:
    """Versioned, immutable animation data for one scene."""

    scene_id: str
    duration_frames: int
    tracks: Tuple[MotionTrack, ...] = ()
    motion_version: int = MOTION_VERSION
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.scene_id, "scene_id")
        duration = _frame(self.duration_frames, "duration_frames")
        if duration <= 0:
            raise MotionValidationError("duration_frames must be greater than zero")
        if (
            isinstance(self.motion_version, bool)
            or not isinstance(self.motion_version, int)
            or self.motion_version != MOTION_VERSION
        ):
            raise MotionValidationError("unsupported scene motion version")
        tracks = tuple(self.tracks)
        if not all(isinstance(item, MotionTrack) for item in tracks):
            raise MotionValidationError("scene motion tracks must contain MotionTrack values")
        track_ids = [item.track_id for item in tracks]
        targets = [(item.target_type, item.target_id, item.property_name) for item in tracks]
        if len(track_ids) != len(set(track_ids)):
            raise MotionValidationError("scene motion track IDs must be unique")
        if len(targets) != len(set(targets)):
            raise MotionValidationError("a target property can only have one motion track")
        for track in tracks:
            if track.keyframes[-1].frame >= duration:
                raise MotionValidationError("keyframe frame must be inside the scene duration")
        object.__setattr__(self, "tracks", tracks)
        if not isinstance(self.extra, Mapping):
            raise MotionValidationError("scene motion extra must be an object")
        object.__setattr__(self, "extra", copy.deepcopy(dict(self.extra)))

    def to_dict(self) -> dict[str, Any]:
        result = {
            "motion_version": self.motion_version,
            "scene_id": self.scene_id,
            "duration_frames": self.duration_frames,
            "tracks": [item.to_dict() for item in self.tracks],
        }
        for key, value in self.extra.items():
            if key not in result:
                result[key] = copy.deepcopy(value)
        return result

    @classmethod
    def from_dict(cls, data: Any) -> "SceneMotion":
        if not isinstance(data, Mapping):
            raise MotionValidationError("scene motion must be an object")
        version = data.get("motion_version", MOTION_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version != MOTION_VERSION:
            raise MotionValidationError("unsupported scene motion version")
        raw_tracks = data.get("tracks", [])
        if not isinstance(raw_tracks, (list, tuple)):
            raise MotionValidationError("scene motion tracks must be an array")
        known = {"motion_version", "scene_id", "duration_frames", "tracks"}
        return cls(
            data.get("scene_id"),
            data.get("duration_frames"),
            tuple(MotionTrack.from_dict(item) for item in raw_tracks),
            version,
            {key: copy.deepcopy(value) for key, value in data.items() if key not in known},
        )


@dataclass(frozen=True)
class EvaluatedMotionValue:
    track_id: str
    target_type: str
    target_id: str
    property_name: str
    value: float


@dataclass(frozen=True)
class EvaluatedMotionFrame:
    scene_id: str
    frame: int
    values: Tuple[EvaluatedMotionValue, ...]

    def value_for(
        self, target_type: str, target_id: str, property_name: str,
    ) -> Optional[float]:
        for item in self.values:
            if (
                item.target_type == target_type
                and item.target_id == target_id
                and item.property_name == property_name
            ):
                return item.value
        return None


def _eased(progress: float, interpolation: str) -> float:
    if interpolation == "hold":
        return 0.0
    if interpolation == "ease_in":
        return progress * progress
    if interpolation == "ease_out":
        return 1.0 - (1.0 - progress) ** 2
    if interpolation == "ease_in_out":
        return progress * progress * (3.0 - 2.0 * progress)
    return progress


def _evaluate_track(track: MotionTrack, frame: int) -> float:
    keyframes = track.keyframes
    if frame <= keyframes[0].frame:
        return keyframes[0].value
    if frame >= keyframes[-1].frame:
        return keyframes[-1].value
    for left, right in zip(keyframes, keyframes[1:]):
        if left.frame <= frame <= right.frame:
            if frame == right.frame:
                return right.value
            progress = (frame - left.frame) / (right.frame - left.frame)
            amount = _eased(progress, left.interpolation)
            return left.value + (right.value - left.value) * amount
    return keyframes[-1].value


def evaluate_scene_motion(
    motion: SceneMotion,
    frame: int,
    *,
    composition=None,
) -> EvaluatedMotionFrame:
    """Evaluate all tracks at one frame without mutating the source composition.

    If a composition is supplied, it is used to validate that every element
    target exists. Camera tracks are independent of element membership.
    """
    if not isinstance(motion, SceneMotion):
        raise MotionValidationError("motion must be a SceneMotion")
    frame = _frame(frame, "frame")
    if frame >= motion.duration_frames:
        raise MotionValidationError("frame must be inside the scene motion duration")
    if composition is not None:
        from app.universal.composition import SceneComposition
        if not isinstance(composition, SceneComposition):
            raise MotionValidationError("composition must be a SceneComposition")
        if composition.scene_id != motion.scene_id:
            raise MotionValidationError("motion and composition scene IDs do not match")
        element_ids = {item.element_id for item in composition.elements}
        missing = sorted({
            item.target_id for item in motion.tracks
            if item.target_type == "element" and item.target_id not in element_ids
        })
        if missing:
            raise MotionValidationError(
                "motion references missing composition elements: " + ", ".join(missing)
            )
    values = tuple(
        EvaluatedMotionValue(
            track.track_id, track.target_type, track.target_id,
            track.property_name, _evaluate_track(track, frame),
        )
        for track in sorted(
            motion.tracks,
            key=lambda item: (item.target_type, item.target_id, item.property_name, item.track_id),
        )
    )
    return EvaluatedMotionFrame(motion.scene_id, frame, values)
