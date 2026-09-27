from __future__ import annotations


class ApplicationError(Exception):
    """Base class for all application-specific errors."""


class ConfigurationError(ApplicationError):
    """Raised when configuration is invalid or cannot be loaded."""


class ProjectError(ApplicationError):
    """Raised for project load/save/validation failures."""


class TTSProviderError(ApplicationError):
    """Raised when a TTS provider fails or is misconfigured."""


class AudioProcessingError(ApplicationError):
    """Raised for audio pipeline failures (mixing, normalization, etc.)."""


class FFmpegError(ApplicationError):
    """Raised when FFmpeg is missing or a command fails."""