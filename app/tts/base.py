from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
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

    The UI and GenerationQueue (future phase) never talk to a concrete
    provider directly -- they go through TTSManager, which in turn only
    knows this interface. That is what lets ElevenLabs/OpenAI/Azure/Piper
    be added later without touching UI code.
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
        """Synthesize speech. `settings` is expected to include at least
        `output_path: Path` and may include `speed`, `pitch`, `volume`,
        `style`, etc. -- providers ignore settings they don't support."""
        raise NotImplementedError

    async def preview_voice(
        self,
        voice_id: str,
        output_path: Path,
        sample_text: Optional[str] = None,
        **settings,
    ) -> SynthResult:
        """Default preview implementation: generate a short sample using
        the normal generate() path. Providers may override this if their
        API offers a lighter-weight/dedicated preview mechanism.

        Phase 4: forwards **settings (speed/pitch_hz/volume_percent) so a
        preview reflects the currently selected voice settings/preset
        rather than always using flat defaults; speed defaults to 1.0
        only when the caller doesn't supply one."""
        text = sample_text or "This is a short voice preview."
        settings.setdefault("speed", 1.0)
        return await self.generate(text, voice_id, output_path=output_path, **settings)