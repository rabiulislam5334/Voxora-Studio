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


# --- Phase 5: long-form narration ---
NARRATION_SAMPLE_RATE = 24000          # Edge TTS native rate; all intermediates are 24 kHz mono 16-bit
NARRATION_MAX_CHUNK_CHARS = 1000       # upper bound for one provider request (resume granularity)
NARRATION_CONCURRENCY = 3              # simultaneous provider requests
NARRATION_MAX_ATTEMPTS = 3             # per chunk: first try + retries
NARRATION_RETRY_BASE_DELAY = 1.0       # seconds; doubles each retry (1s, 2s, ...)
NARRATION_RETRY_MAX_DELAY = 10.0
NARRATION_MAX_CONSECUTIVE_FAILURES = 5 # stop scheduling new chunks after this many failures in a row
NARRATION_MP3_BITRATE = "128k"
NARRATION_PIPELINE_VERSION = 1         # bump to invalidate every cached chunk/scene

DEFAULT_EXPLICIT_PAUSE_MS = 700        # bare [pause]
MAX_EXPLICIT_PAUSE_MS = 60000

# Style tags are recognised and REMOVED from the spoken text. Edge TTS has no
# style support, so they are only kept as metadata (never claimed as applied).
RECOGNIZED_STYLE_TAGS = (
    "whisper", "excited", "calm", "serious", "cheerful",
    "sad", "angry", "friendly", "narration",
)