from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from app.models.voice import Voice


@dataclass(frozen=True)
class ProviderCapabilities:
    """Static capability declaration. Every field defaults to False/None
    so a provider that forgets to declare something fails closed, not open."""

    supports_speed: bool = False
    supports_pitch: bool = False
    supports_volume: bool = False
    supports_style: bool = False
    supports_emotion: bool = False
    supports_pronunciation: bool = False
    supports_ssml: bool = False
    supports_streaming: bool = False
    supports_voice_cloning: bool = False
    supports_multilingual: bool = False
    supports_word_timestamps: bool = False
    supports_speaker_control: bool = False
    max_chars_per_request: Optional[int] = None


@dataclass(frozen=True)
class SynthResult:
    audio_path: str
    duration_seconds: Optional[float] = None


class TTSProvider(ABC):
    """Contract every TTS provider adapter must implement.

    Phase 1 defines the interface only — no subclass exists yet, no network
    I/O happens here. Edge TTS lands in Phase 2 as the first concrete
    implementation (app/tts/edge_tts_provider.py).
    """

    provider_id: str = "base"

    @abstractmethod
    def get_provider_name(self) -> str:
        """Human-readable name, e.g. 'Microsoft Edge TTS'."""
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Static capability declaration for this provider."""
        raise NotImplementedError

    @abstractmethod
    async def list_voices(self, force_refresh: bool = False) -> List[Voice]:
        """Return the voices available from this provider."""
        raise NotImplementedError

    @abstractmethod
    async def generate(self, text: str, voice_id: str, **settings) -> SynthResult:
        """Synthesize speech. Implemented by concrete providers in Phase 2+."""
        raise NotImplementedError