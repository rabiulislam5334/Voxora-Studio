from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from app.core.exceptions import TTSProviderError
from app.core.logger import get_logger
from app.models.voice import Voice
from app.tts.base import ProviderCapabilities, SynthResult, TTSProvider

logger = get_logger("tts.manager")


class TTSManager:
    """Single point of contact between the UI and TTS providers.

    UI code never imports a concrete provider (EdgeTTSProvider, etc.)
    directly -- everything goes through this manager so providers stay
    swappable, per the Phase 0 provider-abstraction requirement.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, TTSProvider] = {}
        self._active_provider_id: Optional[str] = None

    def register(self, provider: TTSProvider, set_active: bool = False) -> None:
        self._providers[provider.provider_id] = provider
        logger.info("Registered TTS provider: %s", provider.provider_id)
        if set_active or self._active_provider_id is None:
            self._active_provider_id = provider.provider_id

    def provider_ids(self) -> List[str]:
        return list(self._providers.keys())

    def get_provider(self, provider_id: Optional[str] = None) -> TTSProvider:
        pid = provider_id or self._active_provider_id
        if pid is None or pid not in self._providers:
            raise TTSProviderError(f"TTS provider '{pid}' is not registered.")
        return self._providers[pid]

    def set_active_provider(self, provider_id: str) -> None:
        if provider_id not in self._providers:
            raise TTSProviderError(f"TTS provider '{provider_id}' is not registered.")
        self._active_provider_id = provider_id

    def active_provider_id(self) -> Optional[str]:
        return self._active_provider_id

    def get_provider_name(self, provider_id: Optional[str] = None) -> str:
        return self.get_provider(provider_id).get_provider_name()

    def capabilities_for(self, provider_id: Optional[str] = None) -> ProviderCapabilities:
        return self.get_provider(provider_id).get_capabilities()

    async def list_voices(
        self, provider_id: Optional[str] = None, force_refresh: bool = False
    ) -> List[Voice]:
        return await self.get_provider(provider_id).list_voices(force_refresh=force_refresh)

    async def generate(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        provider_id: Optional[str] = None,
        speed: float = 1.0,
        **extra_settings,
    ) -> SynthResult:
        provider = self.get_provider(provider_id)
        return await provider.generate(
            text, voice_id, output_path=output_path, speed=speed, **extra_settings
        )

    async def preview_voice(
        self,
        voice_id: str,
        output_path: Path,
        provider_id: Optional[str] = None,
        sample_text: Optional[str] = None,
    ) -> SynthResult:
        provider = self.get_provider(provider_id)
        return await provider.preview_voice(voice_id, output_path, sample_text=sample_text)