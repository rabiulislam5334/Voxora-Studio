from __future__ import annotations


class ApplicationError(Exception):
    """Base class for all application-specific errors."""


class ConfigurationError(ApplicationError):
    """Raised when configuration is invalid or cannot be loaded."""


class ProjectError(ApplicationError):
    """Raised for project load/save/validation failures."""


class ProjectConflictError(ProjectError):
    """The project file on disk was changed (by another window or program)
    after this session last read or wrote it. Nothing was overwritten."""


class ProjectBackupError(ProjectError):
    """A rolling backup of the existing project file could not be created, so
    the save was not performed. The original file is untouched."""


class SnapshotSequenceExhausted(ProjectError):
    """The 12-digit snapshot sequence space has been exhausted."""


class TTSProviderError(ApplicationError):
    """Raised when a TTS provider fails or is misconfigured."""


class AudioProcessingError(ApplicationError):
    """Raised for audio pipeline failures (mixing, normalization, etc.)."""


class FFmpegError(ApplicationError):
    """Raised when FFmpeg is missing or a command fails."""


class NarrationError(ApplicationError):
    """Raised when long-form narration cannot be completed. `failed_chunk_ids`
    lists chunks that exhausted their retries (completed chunks stay cached)."""

    def __init__(self, message: str, failed_chunk_ids=None) -> None:
        super().__init__(message)
        self.failed_chunk_ids = list(failed_chunk_ids or [])


class GenerationCancelled(ApplicationError):
    """Raised when the user cancels a running generation. Not a failure:
    completed chunks are kept so the job can be resumed."""


class MediaError(ApplicationError):
    """A media file is missing, unreadable, or not a supported image/video/audio file."""


class ProductionError(ApplicationError):
    """Raised when audio mixing, video rendering or the end-to-end production
    pipeline cannot be completed. The message is written for end users."""