"""Machine-local settings for the optional Stable Diffusion.cpp workflow.

Only executable/model paths and conservative CPU settings are stored. No
credentials, prompts, generated assets, or project data are written here.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


SETTINGS_VERSION = 1


class VisualGenerationSettingsError(ValueError):
    """Raised when local image-generation settings cannot be read or saved."""


@dataclass(frozen=True)
class LocalImageGenerationSettings:
    executable_path: str = ""
    model_path: str = ""
    threads: int = 4
    steps: int = 20

    def __post_init__(self) -> None:
        for name in ("executable_path", "model_path"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 4096:
                raise VisualGenerationSettingsError(f"{name} must be a path string up to 4096 characters")
        if isinstance(self.threads, bool) or not isinstance(self.threads, int) or not 1 <= self.threads <= 32:
            raise VisualGenerationSettingsError("threads must be an integer between 1 and 32")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or not 1 <= self.steps <= 100:
            raise VisualGenerationSettingsError("steps must be an integer between 1 and 100")

    def to_dict(self) -> dict[str, Any]:
        return {"version": SETTINGS_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LocalImageGenerationSettings":
        if not isinstance(value, Mapping) or value.get("version") != SETTINGS_VERSION:
            raise VisualGenerationSettingsError("Unsupported local image-generation settings format")
        return cls(
            executable_path=value.get("executable_path", ""),
            model_path=value.get("model_path", ""),
            threads=value.get("threads", 4),
            steps=value.get("steps", 20),
        )


def load_local_image_generation_settings(path: str | os.PathLike[str]) -> LocalImageGenerationSettings:
    settings_path = Path(path).expanduser()
    if settings_path.is_symlink():
        raise VisualGenerationSettingsError("Settings file must not be a symbolic link")
    if not settings_path.exists():
        return LocalImageGenerationSettings()
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VisualGenerationSettingsError(f"Cannot read local image-generation settings: {exc}") from exc
    return LocalImageGenerationSettings.from_dict(payload)


def save_local_image_generation_settings(
    path: str | os.PathLike[str], settings: LocalImageGenerationSettings
) -> None:
    if not isinstance(settings, LocalImageGenerationSettings):
        raise TypeError("settings must be LocalImageGenerationSettings")
    settings_path = Path(path).expanduser()
    if settings_path.is_symlink():
        raise VisualGenerationSettingsError("Settings file must not be a symbolic link")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=settings_path.parent,
            prefix=f".{settings_path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(settings.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, settings_path)
    except OSError as exc:
        raise VisualGenerationSettingsError(f"Cannot save local image-generation settings: {exc}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
