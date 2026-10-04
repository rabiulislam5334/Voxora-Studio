from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import edge_tts

try:
    from edge_tts.exceptions import NoAudioReceived
except ImportError:  # pragma: no cover - defensive across edge-tts versions
    NoAudioReceived = None  # type: ignore[assignment,misc]

from app.core.exceptions import TTSProviderError
from app.core.logger import get_logger
from app.models.voice import Voice
from app.tts.base import ProviderCapabilities, SynthResult, TTSProvider

logger = get_logger("tts.edge")

_MIN_PERCENT = -90
_MAX_PERCENT = 200


def speed_to_rate_string(speed: float) -> str:
    """Convert a 0.5-2.0 style multiplier into edge-tts's '+N%'/'-N%' rate
    string, e.g. 1.25 -> '+25%', 0.75 -> '-25%', 1.0 -> '+0%'."""
    percent = round((speed - 1.0) * 100)
    percent = max(_MIN_PERCENT, min(_MAX_PERCENT, percent))
    sign = "+" if percent >= 0 else ""
    return f"{sign}{percent}%"


def pitch_hz_to_string(pitch_hz: int) -> str:
    """Convert an integer Hz offset into edge-tts's '+NHz'/'-NHz' pitch
    string, e.g. 20 -> '+20Hz', -20 -> '-20Hz', 0 -> '+0Hz'."""
    pitch_hz = int(round(pitch_hz))
    sign = "+" if pitch_hz >= 0 else ""
    return f"{sign}{pitch_hz}Hz"


def volume_percent_to_string(volume_percent: int) -> str:
    """Convert an integer percent offset into edge-tts's '+N%'/'-N%' volume
    string, e.g. 20 -> '+20%', -20 -> '-20%', 0 -> '+0%'. This is a speech
    SYNTHESIS parameter (baked into the generated audio) -- distinct from
    the audio player's playback volume control, which is applied at
    playback time and never touches the generated file."""
    volume_percent = int(round(volume_percent))
    sign = "+" if volume_percent >= 0 else ""
    return f"{sign}{volume_percent}%"


class EdgeTTSProvider(TTSProvider):
    provider_id = "edge_tts"

    def __init__(self) -> None:
        self._voice_cache: Optional[List[Voice]] = None

    def get_provider_name(self) -> str:
        return "Microsoft Edge TTS"

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_speed=True,
            supports_pitch=True,
            supports_volume=True,
            supports_style=False,
            supports_emotion=False,
            supports_pronunciation=False,
            supports_ssml=False,
            supports_streaming=True,
            supports_voice_cloning=False,
            supports_multilingual=True,
            supports_word_timestamps=True,
            supports_speaker_control=False,
            max_chars_per_request=8000,  # soft safety cap; real chunking is Phase 5
        )

    async def list_voices(self, force_refresh: bool = False) -> List[Voice]:
        if self._voice_cache is not None and not force_refresh:
            return self._voice_cache

        try:
            raw_voices = await edge_tts.list_voices()
        except Exception as exc:
            logger.exception("Failed to fetch Edge TTS voice list")
            raise TTSProviderError(
                "Could not retrieve the Edge TTS voice list. "
                "Check your internet connection and try again."
            ) from exc

        voices: List[Voice] = []
        for entry in raw_voices:
            short_name = entry.get("ShortName")
            locale = entry.get("Locale")
            if not short_name or not locale:
                continue
            gender = entry.get("Gender")
            friendly = entry.get("FriendlyName") or short_name
            voices.append(
                Voice(
                    id=short_name,
                    name=friendly,
                    provider=self.provider_id,
                    language=locale,
                    gender=gender,
                    metadata={
                        "locale": locale,
                        "status": entry.get("Status", ""),
                        "voice_tag": entry.get("VoiceTag", {}),
                    },
                )
            )

        voices.sort(key=lambda v: (v.language, v.name))
        self._voice_cache = voices
        logger.info("Loaded %d Edge TTS voices", len(voices))
        return voices

    async def generate(self, text: str, voice_id: str, **settings) -> SynthResult:
        if not text or not text.strip():
            raise TTSProviderError("Cannot generate speech from empty text.")
        if not voice_id:
            raise TTSProviderError("No voice selected.")
        if "output_path" not in settings:
            raise TTSProviderError("Internal error: no output path was provided.")

        output_path: Path = Path(settings["output_path"])
        speed: float = settings.get("speed", 1.0)
        pitch_hz: int = settings.get("pitch_hz", 0)
        volume_percent: int = settings.get("volume_percent", 0)
        rate = speed_to_rate_string(speed)
        pitch = pitch_hz_to_string(pitch_hz)
        volume = volume_percent_to_string(volume_percent)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TTSProviderError(
                f"Could not create output directory '{output_path.parent}': {exc}"
            ) from exc

        try:
            communicator = edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch, volume=volume)
            await communicator.save(str(output_path))
        except Exception as exc:
            if NoAudioReceived is not None and isinstance(exc, NoAudioReceived):
                raise TTSProviderError(
                    "Edge TTS returned no audio for this request. "
                    "The voice ID may be invalid, or the text may be unsupported."
                ) from exc
            logger.exception("Edge TTS generation failed for voice %s", voice_id)
            raise TTSProviderError(f"Speech generation failed: {exc}") from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise TTSProviderError("Edge TTS produced an empty audio file.")

        return SynthResult(audio_path=str(output_path), duration_seconds=None)

    async def preview_voice(
        self,
        voice_id: str,
        output_path: Path,
        sample_text: Optional[str] = None,
        **settings,
    ) -> SynthResult:
        text = sample_text or self._default_sample_text(voice_id)
        settings.setdefault("speed", 1.0)
        return await self.generate(text, voice_id, output_path=output_path, **settings)

    @staticmethod
    def _default_sample_text(voice_id: str) -> str:
        if voice_id.lower().startswith("bn"):
            return (
                "এটি একটি ভয়েস প্রিভিউ। আপনার কনটেন্টের জন্য এই কণ্ঠস্বরটি "
                "কেমন শোনাচ্ছে তা শুনুন।"
            )
        return "This is a voice preview. Listen to how this voice sounds for your content."