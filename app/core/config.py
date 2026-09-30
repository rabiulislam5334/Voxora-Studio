from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.core import constants


def _app_root() -> Path:
    # app/core/config.py -> app/core -> app -> project root
    return Path(__file__).resolve().parents[2]


@dataclass
class AppConfig:
    app_name: str = constants.APP_NAME
    app_version: str = constants.APP_VERSION

    root_dir: Path = field(default_factory=_app_root)

    projects_dir: Path = field(init=False)
    output_dir: Path = field(init=False)
    cache_dir: Path = field(init=False)
    previews_dir: Path = field(init=False)
    generated_audio_dir: Path = field(init=False)
    temp_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    assets_dir: Path = field(init=False)

    default_language: str = "en"
    default_theme: str = constants.DEFAULT_THEME

    default_tts_provider: str = constants.DEFAULT_TTS_PROVIDER
    default_voice_id: Optional[str] = None
    default_speed: float = constants.DEFAULT_SPEED

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir)
        self.projects_dir = self.root_dir / constants.DIR_PROJECTS
        self.output_dir = self.root_dir / constants.DIR_OUTPUT
        self.cache_dir = self.root_dir / constants.DIR_CACHE
        self.previews_dir = self.cache_dir / "previews"
        # Phase 2.1: every "Generate" writes here, and ONLY here -- see
        # app/audio/session.py for why this single deterministic location
        # is the fix for the old output-directory mismatch.
        self.generated_audio_dir = self.cache_dir / "generated"
        self.temp_dir = self.root_dir / constants.DIR_TEMP
        self.logs_dir = self.root_dir / constants.DIR_LOGS
        self.assets_dir = self.root_dir / constants.DIR_ASSETS

    def required_directories(self) -> List[Path]:
        return [
            self.projects_dir,
            self.output_dir,
            self.cache_dir,
            self.previews_dir,
            self.generated_audio_dir,
            self.temp_dir,
            self.logs_dir,
        ]

    def ensure_directories(self) -> None:
        for directory in self.required_directories():
            directory.mkdir(parents=True, exist_ok=True)


_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Process-wide config singleton. Created once, directories ensured once."""
    global _config
    if _config is None:
        _config = AppConfig()
        _config.ensure_directories()
    return _config