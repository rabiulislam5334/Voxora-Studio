from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from app.core.constants import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.studio.models import StudioState

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    message: str
    scene_id: Optional[str] = None


def media_kind_from_extension(path: str) -> Optional[str]:
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    return None


def validate_production(
    scenes: Iterable,
    studio: StudioState,
    *,
    ffmpeg_ready: bool,
    voice_selected: bool,
    render_video: bool,
    export_audio: bool,
) -> List[ValidationIssue]:
    """Pre-flight checks for a production run. `scenes` are objects with
    id / title / text. Errors block the run; warnings do not."""
    issues: List[ValidationIssue] = []
    scene_list = list(scenes)
    narrated = [s for s in scene_list if (s.text or "").strip()]

    if not ffmpeg_ready:
        issues.append(ValidationIssue(ERROR, "FFmpeg is not available. Check it on the Voice & Narration tab."))
    if not scene_list:
        issues.append(ValidationIssue(ERROR, "The project has no scenes. Add scenes on the Script page."))
    elif not narrated:
        issues.append(ValidationIssue(ERROR, "No scene has any text to narrate."))
    if narrated and not voice_selected:
        issues.append(ValidationIssue(ERROR, "No voice is selected. Pick one on the Voice & Narration tab."))
    if not render_video and not export_audio:
        issues.append(ValidationIssue(ERROR, "Choose at least one output: video (MP4) or audio (MP3/WAV)."))

    for track in studio.audio.active_tracks():
        name = Path(track.path).name
        if not Path(track.path).is_file():
            issues.append(ValidationIssue(ERROR, f"Music file is missing: {name}"))
        elif media_kind_from_extension(track.path) not in ("audio", "video"):
            issues.append(ValidationIssue(ERROR, f"Unsupported music file type: {name}"))
        if track.trim_end_s is not None and track.trim_end_s <= track.trim_start_s:
            issues.append(ValidationIssue(ERROR, f"Music trim end must be after start: {name}"))

    if render_video:
        for scene in scene_list:
            video = studio.video.scene(scene.id)
            label = f"Scene '{scene.title}'"
            if video.media_path:
                kind = media_kind_from_extension(video.media_path)
                if not Path(video.media_path).is_file():
                    issues.append(ValidationIssue(ERROR, f"{label}: media file is missing ({Path(video.media_path).name}).", scene.id))
                elif kind not in ("image", "video"):
                    issues.append(ValidationIssue(ERROR, f"{label}: unsupported media type ({Path(video.media_path).name}).", scene.id))
            else:
                issues.append(ValidationIssue(WARNING, f"{label}: no media assigned; it will render as a black screen.", scene.id))
            if not (scene.text or "").strip() and not video.media_path:
                issues.append(ValidationIssue(INFO, f"{label}: no text and no media; it will be a {studio.video.default_duration_s:g}s black scene.", scene.id))
    return issues


def has_errors(issues: Iterable[ValidationIssue]) -> bool:
    return any(i.severity == ERROR for i in issues)