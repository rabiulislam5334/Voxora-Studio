from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

STUDIO_SETTINGS_KEY = "studio"
STUDIO_FORMAT_VERSION = 1

ASPECTS = ("16:9", "9:16")
RESOLUTIONS = {"360p (draft)": 360, "720p": 720, "1080p": 1080}  # length of the SHORT side
MOTIONS = ("none", "zoom_in", "zoom_out", "pan_left", "pan_right")
FITS = ("fill", "fit")  # fill = crop to cover, fit = letterbox
TRANSITIONS = ("cut", "crossfade")


def _num(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(lo, min(hi, number))


def _opt_num(value: Any, lo: float, hi: float) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return max(lo, min(hi, number))


def _choice(value: Any, allowed, default):
    return value if value in allowed else default


def _opt_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value.strip() else None


def output_size(aspect: str, resolution: str) -> Tuple[int, int]:
    """Pixel size (width, height) for an aspect/resolution choice. Even
    numbers only, as H.264 with yuv420p requires."""
    short = RESOLUTIONS.get(resolution, 720)
    long_side = int(round(short * 16 / 9 / 2)) * 2
    return (long_side, short) if aspect != "9:16" else (short, long_side)


# ----------------------------------------------------------------------
# Audio
# ----------------------------------------------------------------------


@dataclass
class MusicTrack:
    path: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    volume_percent: int = 15
    fade_in_s: float = 2.0
    fade_out_s: float = 3.0
    offset_s: float = 0.0        # where the music starts on the project timeline
    trim_start_s: float = 0.0    # use only [trim_start, trim_end] of the file
    trim_end_s: Optional[float] = None
    loop: bool = True            # repeat the (trimmed) track to fill the narration
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "path": self.path, "volume_percent": self.volume_percent,
            "fade_in_s": self.fade_in_s, "fade_out_s": self.fade_out_s, "offset_s": self.offset_s,
            "trim_start_s": self.trim_start_s, "trim_end_s": self.trim_end_s,
            "loop": self.loop, "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["MusicTrack"]:
        if not isinstance(data, dict) or not _opt_str(data.get("path")):
            return None
        start = _num(data.get("trim_start_s"), 0.0, 0.0, 86400.0)
        end = _opt_num(data.get("trim_end_s"), 0.0, 86400.0)
        if end is not None and end <= start:
            end = None
        return cls(
            path=data["path"],
            id=_opt_str(data.get("id")) or uuid.uuid4().hex[:8],
            volume_percent=int(_num(data.get("volume_percent"), 15, 0, 200)),
            fade_in_s=_num(data.get("fade_in_s"), 2.0, 0.0, 600.0),
            fade_out_s=_num(data.get("fade_out_s"), 3.0, 0.0, 600.0),
            offset_s=_num(data.get("offset_s"), 0.0, 0.0, 86400.0),
            trim_start_s=start, trim_end_s=end,
            loop=bool(data.get("loop", True)), enabled=bool(data.get("enabled", True)),
        )


@dataclass
class AudioSettings:
    narration_volume_percent: int = 100
    limiter: bool = True  # guards against clipping when narration and music sum
    tracks: List[MusicTrack] = field(default_factory=list)

    def active_tracks(self) -> List[MusicTrack]:
        return [t for t in self.tracks if t.enabled]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "narration_volume_percent": self.narration_volume_percent,
            "limiter": self.limiter,
            "tracks": [t.to_dict() for t in self.tracks],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AudioSettings":
        if not isinstance(data, dict):
            return cls()
        tracks = [t for t in (MusicTrack.from_dict(x) for x in data.get("tracks", []) if True) if t]
        return cls(
            narration_volume_percent=int(_num(data.get("narration_volume_percent"), 100, 0, 200)),
            limiter=bool(data.get("limiter", True)),
            tracks=tracks,
        )


# ----------------------------------------------------------------------
# Video
# ----------------------------------------------------------------------


@dataclass
class SceneVideo:
    media_path: Optional[str] = None
    duration_s: Optional[float] = None  # None = automatic (narration length)
    motion: Optional[str] = None        # None = project default
    fit: Optional[str] = None           # None = project default

    def to_dict(self) -> Dict[str, Any]:
        return {"media_path": self.media_path, "duration_s": self.duration_s,
                "motion": self.motion, "fit": self.fit}

    @classmethod
    def from_dict(cls, data: Any) -> "SceneVideo":
        if not isinstance(data, dict):
            return cls()
        motion, fit = data.get("motion"), data.get("fit")
        return cls(
            media_path=_opt_str(data.get("media_path")),
            duration_s=_opt_num(data.get("duration_s"), 0.5, 3600.0),
            motion=motion if motion in MOTIONS else None,
            fit=fit if fit in FITS else None,
        )

    def is_empty(self) -> bool:
        return not self.media_path and self.duration_s is None and self.motion is None and self.fit is None


@dataclass
class VideoSettings:
    aspect: str = "16:9"
    resolution: str = "720p"
    fps: int = 30
    transition: str = "cut"
    transition_s: float = 0.5
    default_duration_s: float = 5.0
    default_motion: str = "zoom_in"
    default_fit: str = "fill"
    scenes: Dict[str, SceneVideo] = field(default_factory=dict)

    @property
    def size(self) -> Tuple[int, int]:
        return output_size(self.aspect, self.resolution)

    def scene(self, scene_id: str) -> SceneVideo:
        return self.scenes.get(scene_id) or SceneVideo()

    def set_scene(self, scene_id: str, value: SceneVideo) -> None:
        if value.is_empty():
            self.scenes.pop(scene_id, None)
        else:
            self.scenes[scene_id] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aspect": self.aspect, "resolution": self.resolution, "fps": self.fps,
            "transition": self.transition, "transition_s": self.transition_s,
            "default_duration_s": self.default_duration_s, "default_motion": self.default_motion,
            "default_fit": self.default_fit,
            "scenes": {sid: sv.to_dict() for sid, sv in self.scenes.items()},
        }

    @classmethod
    def from_dict(cls, data: Any) -> "VideoSettings":
        if not isinstance(data, dict):
            return cls()
        scenes_raw = data.get("scenes", {})
        scenes = {}
        if isinstance(scenes_raw, dict):
            for sid, raw in scenes_raw.items():
                if isinstance(sid, str):
                    value = SceneVideo.from_dict(raw)
                    if not value.is_empty():
                        scenes[sid] = value
        return cls(
            aspect=_choice(data.get("aspect"), ASPECTS, "16:9"),
            resolution=_choice(data.get("resolution"), RESOLUTIONS, "720p"),
            fps=int(_num(data.get("fps"), 30, 12, 60)),
            transition=_choice(data.get("transition"), TRANSITIONS, "cut"),
            transition_s=_num(data.get("transition_s"), 0.5, 0.1, 3.0),
            default_duration_s=_num(data.get("default_duration_s"), 5.0, 0.5, 600.0),
            default_motion=_choice(data.get("default_motion"), MOTIONS, "zoom_in"),
            default_fit=_choice(data.get("default_fit"), FITS, "fill"),
            scenes=scenes,
        )


# ----------------------------------------------------------------------
# Whole studio state, stored inside Project.settings (a free-form dict the
# existing .voxora serializer already round-trips, so no schema change is
# needed and Phase 3/4/5 project files open exactly as before).
# ----------------------------------------------------------------------


@dataclass
class StudioState:
    audio: AudioSettings = field(default_factory=AudioSettings)
    video: VideoSettings = field(default_factory=VideoSettings)

    def to_dict(self) -> Dict[str, Any]:
        return {"version": STUDIO_FORMAT_VERSION, "audio": self.audio.to_dict(), "video": self.video.to_dict()}

    @classmethod
    def from_dict(cls, data: Any) -> "StudioState":
        if not isinstance(data, dict):
            return cls()
        return cls(audio=AudioSettings.from_dict(data.get("audio")), video=VideoSettings.from_dict(data.get("video")))

    @classmethod
    def from_project_settings(cls, settings: Any) -> "StudioState":
        raw = settings.get(STUDIO_SETTINGS_KEY) if isinstance(settings, dict) else None
        return cls.from_dict(raw)

    def write_to(self, settings: Dict[str, Any]) -> None:
        settings[STUDIO_SETTINGS_KEY] = self.to_dict()

    def prune_scenes(self, valid_scene_ids) -> bool:
        """Drop media settings of scenes that no longer exist. Returns True if changed."""
        valid = set(valid_scene_ids)
        stale = [sid for sid in self.video.scenes if sid not in valid]
        for sid in stale:
            del self.video.scenes[sid]
        return bool(stale)