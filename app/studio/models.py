from __future__ import annotations

import copy
import uuid

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.timebase import deserialize_ticks, seconds_to_ticks, serialize_ticks, ticks_to_seconds

STUDIO_SETTINGS_KEY = "studio"
STUDIO_FORMAT_VERSION = 2

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


def _read_time(data: Dict[str, Any], ticks_key: str, seconds_key: str, default: Any) -> Any:
    if ticks_key in data:
        try:
            return float(ticks_to_seconds(deserialize_ticks(data[ticks_key])))
        except (TypeError, ValueError):
            pass
    return data.get(seconds_key, default)


def _ticks(value: Any) -> str:
    return serialize_ticks(seconds_to_ticks(value))


def _split_extra(data: Dict[str, Any], known: frozenset) -> Dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in data.items() if k not in known}


def _with_extra(known_values: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in extra.items():
        if key not in known_values:
            known_values[key] = copy.deepcopy(value)
    return known_values


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_audio_shape(data: Dict[str, Any]) -> bool:
    if "narration_volume_percent" in data and not _is_number(data["narration_volume_percent"]):
        return False
    if "limiter" in data and not isinstance(data["limiter"], bool):
        return False
    tracks = data.get("tracks", [])
    if not isinstance(tracks, list):
        return False
    numeric_track_keys = ("volume_percent", "fade_in_s", "fade_out_s", "offset_s", "trim_start_s", "trim_end_s")
    for track in tracks:
        if not isinstance(track, dict) or not _opt_str(track.get("path")):
            return False
        if "id" in track and not isinstance(track["id"], str):
            return False
        if any(key in track and track[key] is not None and not _is_number(track[key]) for key in numeric_track_keys):
            return False
        if any(key in track and not isinstance(track[key], bool) for key in ("loop", "enabled")):
            return False
    return True


def _valid_video_shape(data: Dict[str, Any]) -> bool:
    enum_fields = {"aspect": ASPECTS, "resolution": tuple(RESOLUTIONS), "transition": TRANSITIONS,
                   "default_motion": MOTIONS, "default_fit": FITS}
    for key, allowed in enum_fields.items():
        if key in data and data[key] not in allowed:
            return False
    numeric_fields = ("fps", "transition_s", "default_duration_s")
    if any(key in data and not _is_number(data[key]) for key in numeric_fields):
        return False
    scenes = data.get("scenes", {})
    if not isinstance(scenes, dict):
        return False
    for entry in scenes.values():
        if not isinstance(entry, dict):
            return False
        if "media_path" in entry and entry["media_path"] is not None and not isinstance(entry["media_path"], str):
            return False
        if "duration_s" in entry and entry["duration_s"] is not None and not _is_number(entry["duration_s"]):
            return False
        if "motion" in entry and entry["motion"] is not None and entry["motion"] not in MOTIONS:
            return False
        if "fit" in entry and entry["fit"] is not None and entry["fit"] not in FITS:
            return False
    return True


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
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _with_extra({
            "id": self.id, "path": self.path, "volume_percent": self.volume_percent,
            "fade_in_s": self.fade_in_s, "fade_out_s": self.fade_out_s, "offset_s": self.offset_s,
            "trim_start_s": self.trim_start_s, "trim_end_s": self.trim_end_s,
            "fade_in_ticks": _ticks(self.fade_in_s), "fade_out_ticks": _ticks(self.fade_out_s),
            "offset_ticks": _ticks(self.offset_s), "trim_start_ticks": _ticks(self.trim_start_s),
            "trim_end_ticks": _ticks(self.trim_end_s) if self.trim_end_s is not None else None,
            "loop": self.loop, "enabled": self.enabled,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> Optional["MusicTrack"]:
        if not isinstance(data, dict) or not _opt_str(data.get("path")):
            return None
        start = _num(_read_time(data, "trim_start_ticks", "trim_start_s", 0.0), 0.0, 0.0, 86400.0)
        end = _opt_num(_read_time(data, "trim_end_ticks", "trim_end_s", None), 0.0, 86400.0)
        if end is not None and end <= start:
            end = None
        return cls(
            path=data["path"],
            id=_opt_str(data.get("id")) or uuid.uuid4().hex[:8],
            volume_percent=int(_num(data.get("volume_percent"), 15, 0, 200)),
            fade_in_s=_num(_read_time(data, "fade_in_ticks", "fade_in_s", 2.0), 2.0, 0.0, 600.0),
            fade_out_s=_num(_read_time(data, "fade_out_ticks", "fade_out_s", 3.0), 3.0, 0.0, 600.0),
            offset_s=_num(_read_time(data, "offset_ticks", "offset_s", 0.0), 0.0, 0.0, 86400.0),
            trim_start_s=start, trim_end_s=end,
            loop=bool(data.get("loop", True)), enabled=bool(data.get("enabled", True)),
            extra=_split_extra(data, _MUSIC_TRACK_KEYS),
        )


@dataclass
class AudioSettings:
    narration_volume_percent: int = 100
    limiter: bool = True  # guards against clipping when narration and music sum
    tracks: List[MusicTrack] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    invalid_tracks: List[Any] = field(default_factory=list)
    raw_tracks: Any = None
    has_raw_tracks: bool = False

    def active_tracks(self) -> List[MusicTrack]:
        return [t for t in self.tracks if t.enabled]

    def to_dict(self) -> Dict[str, Any]:
        tracks = copy.deepcopy(self.raw_tracks) if self.has_raw_tracks else ([t.to_dict() for t in self.tracks] + copy.deepcopy(self.invalid_tracks))
        return _with_extra({
            "narration_volume_percent": self.narration_volume_percent,
            "limiter": self.limiter,
            "tracks": tracks,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "AudioSettings":
        if not isinstance(data, dict):
            return cls()
        raw_tracks = data.get("tracks", [])
        tracks, invalid_tracks = [], []
        has_raw_tracks = not isinstance(raw_tracks, list)
        if isinstance(raw_tracks, list):
            for item in raw_tracks:
                parsed = MusicTrack.from_dict(item)
                if parsed is None:
                    invalid_tracks.append(copy.deepcopy(item))
                else:
                    tracks.append(parsed)
        has_raw_tracks = has_raw_tracks or bool(invalid_tracks)
        return cls(
            narration_volume_percent=int(_num(data.get("narration_volume_percent"), 100, 0, 200)),
            limiter=bool(data.get("limiter", True)),
            tracks=tracks,
            extra=_split_extra(data, _AUDIO_KEYS),
            invalid_tracks=invalid_tracks,
            raw_tracks=copy.deepcopy(raw_tracks) if has_raw_tracks else None,
            has_raw_tracks=has_raw_tracks,
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
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _with_extra({"media_path": self.media_path, "duration_s": self.duration_s,
                "duration_ticks": _ticks(self.duration_s) if self.duration_s is not None else None,
                "motion": self.motion, "fit": self.fit}, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "SceneVideo":
        if not isinstance(data, dict):
            return cls()
        motion, fit = data.get("motion"), data.get("fit")
        return cls(
            media_path=_opt_str(data.get("media_path")),
            duration_s=_opt_num(_read_time(data, "duration_ticks", "duration_s", None), 0.5, 3600.0),
            motion=motion if motion in MOTIONS else None,
            fit=fit if fit in FITS else None,
            extra=_split_extra(data, _SCENE_VIDEO_KEYS),
        )

    def is_empty(self) -> bool:
        return not self.media_path and self.duration_s is None and self.motion is None and self.fit is None and not self.extra


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
    extra: Dict[str, Any] = field(default_factory=dict)
    invalid_scene_entries: Dict[str, Any] = field(default_factory=dict)
    raw_scenes: Any = None
    has_raw_scenes: bool = False

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
        scenes = copy.deepcopy(self.raw_scenes) if self.has_raw_scenes else {sid: sv.to_dict() for sid, sv in self.scenes.items()}
        if not self.has_raw_scenes:
            for sid, raw in self.invalid_scene_entries.items():
                if sid not in scenes:
                    scenes[sid] = copy.deepcopy(raw)
        return _with_extra({
            "aspect": self.aspect, "resolution": self.resolution, "fps": self.fps,
            "transition": self.transition, "transition_s": self.transition_s,
            "transition_ticks": _ticks(self.transition_s),
            "default_duration_s": self.default_duration_s,
            "default_duration_ticks": _ticks(self.default_duration_s), "default_motion": self.default_motion,
            "default_fit": self.default_fit,
            "scenes": scenes,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "VideoSettings":
        if not isinstance(data, dict):
            return cls()
        scenes_raw = data.get("scenes", {})
        scenes, invalid_scene_entries = {}, {}
        if isinstance(scenes_raw, dict):
            for sid, raw in scenes_raw.items():
                if isinstance(sid, str):
                    if not isinstance(raw, dict):
                        invalid_scene_entries[sid] = copy.deepcopy(raw)
                        continue
                    value = SceneVideo.from_dict(raw)
                    if not value.is_empty():
                        scenes[sid] = value
        return cls(
            aspect=_choice(data.get("aspect"), ASPECTS, "16:9"),
            resolution=_choice(data.get("resolution"), RESOLUTIONS, "720p"),
            fps=int(_num(data.get("fps"), 30, 12, 60)),
            transition=_choice(data.get("transition"), TRANSITIONS, "cut"),
            transition_s=_num(_read_time(data, "transition_ticks", "transition_s", 0.5), 0.5, 0.1, 3.0),
            default_duration_s=_num(_read_time(data, "default_duration_ticks", "default_duration_s", 5.0), 5.0, 0.5, 600.0),
            default_motion=_choice(data.get("default_motion"), MOTIONS, "zoom_in"),
            default_fit=_choice(data.get("default_fit"), FITS, "fill"),
            scenes=scenes,
            extra=_split_extra(data, _VIDEO_KEYS),
            invalid_scene_entries=invalid_scene_entries,
            raw_scenes=copy.deepcopy(scenes_raw) if not isinstance(scenes_raw, dict) and "scenes" in data else None,
            has_raw_scenes=not isinstance(scenes_raw, dict) and "scenes" in data,
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
    extra: Dict[str, Any] = field(default_factory=dict)
    format_version: Any = STUDIO_FORMAT_VERSION
    raw_audio: Any = None
    raw_video: Any = None
    raw_studio: Any = None
    has_raw_audio: bool = False
    has_raw_video: bool = False
    has_raw_studio: bool = False

    @property
    def read_only(self) -> bool:
        version_invalid = isinstance(self.format_version, bool) or not isinstance(self.format_version, int) or self.format_version < 1
        return (self.has_raw_studio or self.has_raw_audio or self.has_raw_video or self.audio.has_raw_tracks
                or self.video.has_raw_scenes or bool(self.video.invalid_scene_entries) or version_invalid
                or self.format_version > STUDIO_FORMAT_VERSION)

    def to_dict(self) -> Dict[str, Any]:
        if self.has_raw_studio:
            return copy.deepcopy(self.raw_studio)
        audio = copy.deepcopy(self.raw_audio) if self.has_raw_audio else self.audio.to_dict()
        video = copy.deepcopy(self.raw_video) if self.has_raw_video else self.video.to_dict()
        return _with_extra({"version": self.format_version, "audio": audio, "video": video}, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "StudioState":
        if not isinstance(data, dict):
            return cls(raw_studio=copy.deepcopy(data), has_raw_studio=True)
        version = data.get("version", STUDIO_FORMAT_VERSION)
        version_invalid = isinstance(version, bool) or not isinstance(version, int) or version < 1
        if version_invalid or version > STUDIO_FORMAT_VERSION:
            return cls(format_version=copy.deepcopy(version), raw_studio=copy.deepcopy(data), has_raw_studio=True)
        raw_audio, raw_video = data.get("audio"), data.get("video")
        bad_audio = not isinstance(raw_audio, dict) or not _valid_audio_shape(raw_audio)
        bad_video = not isinstance(raw_video, dict) or not _valid_video_shape(raw_video)
        return cls(
            audio=AudioSettings.from_dict(raw_audio), video=VideoSettings.from_dict(raw_video),
            extra=_split_extra(data, _STUDIO_KEYS), format_version=copy.deepcopy(version),
            raw_audio=copy.deepcopy(raw_audio) if bad_audio and "audio" in data else None,
            raw_video=copy.deepcopy(raw_video) if bad_video and "video" in data else None,
            has_raw_audio=bad_audio and "audio" in data,
            has_raw_video=bad_video and "video" in data,
        )

    @classmethod
    def from_project_settings(cls, settings: Any) -> "StudioState":
        if not isinstance(settings, dict) or STUDIO_SETTINGS_KEY not in settings:
            return cls()
        return cls.from_dict(settings.get(STUDIO_SETTINGS_KEY))

    def write_to(self, settings: Dict[str, Any]) -> None:
        settings[STUDIO_SETTINGS_KEY] = self.to_dict()

    def prune_scenes(self, valid_scene_ids) -> bool:
        """Drop media settings of scenes that no longer exist. Returns True if changed."""
        valid = set(valid_scene_ids)
        stale = [sid for sid in self.video.scenes if sid not in valid]
        for sid in stale:
            del self.video.scenes[sid]
        return bool(stale)

# Known keys are derived from the writers above to keep preservation in sync.
_MUSIC_TRACK_KEYS = frozenset({"id", "path", "volume_percent", "fade_in_s", "fade_out_s", "offset_s", "trim_start_s", "trim_end_s", "fade_in_ticks", "fade_out_ticks", "offset_ticks", "trim_start_ticks", "trim_end_ticks", "loop", "enabled"})
_AUDIO_KEYS = frozenset({"narration_volume_percent", "limiter", "tracks"})
_SCENE_VIDEO_KEYS = frozenset({"media_path", "duration_s", "duration_ticks", "motion", "fit"})
_VIDEO_KEYS = frozenset({"aspect", "resolution", "fps", "transition", "transition_s", "transition_ticks", "default_duration_s", "default_duration_ticks", "default_motion", "default_fit", "scenes"})
_STUDIO_KEYS = frozenset({"version", "audio", "video"})
