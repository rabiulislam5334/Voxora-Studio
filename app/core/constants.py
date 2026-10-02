from __future__ import annotations

APP_NAME = "Voxora Studio"
APP_VERSION = "0.1.0"

SUPPORTED_LANGUAGES = ("bn", "en")

EXPORT_AUDIO_FORMATS = ("mp3", "wav")
EXPORT_SUBTITLE_FORMATS = ("srt",)
EXPORT_VIDEO_FORMATS = ("mp4",)

DIR_PROJECTS = "projects"
DIR_OUTPUT = "output"
DIR_CACHE = "cache"
DIR_TEMP = "temp"
DIR_LOGS = "logs"
DIR_ASSETS = "assets"

THEME_DARK = "dark"
THEME_LIGHT = "light"
DEFAULT_THEME = THEME_DARK

DEFAULT_WINDOW_SIZE = "1200x750"
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 600

# --- Phase 2: TTS defaults ---
DEFAULT_TTS_PROVIDER = "edge_tts"
DEFAULT_SPEED = 1.0
DEFAULT_OUTPUT_FORMAT = "mp3"
SPEED_PRESETS = (0.75, 0.85, 0.90, 1.00, 1.10, 1.25, 1.50)