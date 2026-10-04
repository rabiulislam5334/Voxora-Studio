from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.core.exceptions import ConfigurationError

# Valid ranges -- enforced by validate_preset(). Rate deliberately matches
# the narrower Phase 4 range (0.75x-1.25x), not the wider 0.5-1.5x the
# Voice page's old standalone Speed control used to allow.
RATE_MIN = 0.75
RATE_MAX = 1.25
PITCH_HZ_MIN = -50
PITCH_HZ_MAX = 50
VOLUME_PERCENT_MIN = -20
VOLUME_PERCENT_MAX = 20
PAUSE_MS_MIN = 0
PAUSE_MS_MAX = 5000


@dataclass
class VoicePreset:
    """A named, reusable bundle of narration settings.

    Used two ways in the app: as the Voice page's CURRENT live settings
    (mutated directly as the user drags sliders) and as a SAVED, named
    template (built-in or custom) that can populate those live settings.
    Both cases are the same shape, so one model covers both -- no
    separate "VoiceSettings" class, per the instruction to avoid
    duplicate models where one already fits.

    voice_id is optional: built-in presets don't pin a specific voice
    (available voices vary by provider/locale), but a user's custom
    preset may choose to remember one.
    """

    name: str
    voice_id: Optional[str] = None
    rate: float = 1.0
    pitch_hz: int = 0
    volume_percent: int = 0
    sentence_pause_ms: int = 250
    paragraph_pause_ms: int = 600
    scene_pause_ms: int = 1000
    is_builtin: bool = False

    def copy_with(self, **overrides) -> "VoicePreset":
        """Return a new VoicePreset with the given fields replaced --
        used when a user starts from a preset and then tweaks a slider,
        so the built-in preset object itself is never mutated."""
        data = {
            "name": self.name,
            "voice_id": self.voice_id,
            "rate": self.rate,
            "pitch_hz": self.pitch_hz,
            "volume_percent": self.volume_percent,
            "sentence_pause_ms": self.sentence_pause_ms,
            "paragraph_pause_ms": self.paragraph_pause_ms,
            "scene_pause_ms": self.scene_pause_ms,
            "is_builtin": self.is_builtin,
        }
        data.update(overrides)
        return VoicePreset(**data)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "voice_id": self.voice_id,
            "rate": self.rate,
            "pitch_hz": self.pitch_hz,
            "volume_percent": self.volume_percent,
            "sentence_pause_ms": self.sentence_pause_ms,
            "paragraph_pause_ms": self.paragraph_pause_ms,
            "scene_pause_ms": self.scene_pause_ms,
        }

    @classmethod
    def from_dict(cls, data: dict, is_builtin: bool = False) -> "VoicePreset":
        return cls(
            name=data.get("name") or "Untitled Preset",
            voice_id=data.get("voice_id"),
            rate=data.get("rate", 1.0),
            pitch_hz=data.get("pitch_hz", 0),
            volume_percent=data.get("volume_percent", 0),
            sentence_pause_ms=data.get("sentence_pause_ms", 250),
            paragraph_pause_ms=data.get("paragraph_pause_ms", 600),
            scene_pause_ms=data.get("scene_pause_ms", 1000),
            is_builtin=is_builtin,
        )


def validate_preset(preset: VoicePreset) -> None:
    """Raises ConfigurationError (reused from the existing exception
    hierarchy -- this is exactly a configuration-validity problem) with a
    clear, specific message on the first invalid field found."""
    if not (RATE_MIN <= preset.rate <= RATE_MAX):
        raise ConfigurationError(
            f"Rate must be between {RATE_MIN}x and {RATE_MAX}x (got {preset.rate}x)."
        )
    if not (PITCH_HZ_MIN <= preset.pitch_hz <= PITCH_HZ_MAX):
        raise ConfigurationError(
            f"Pitch must be between {PITCH_HZ_MIN}Hz and {PITCH_HZ_MAX}Hz (got {preset.pitch_hz}Hz)."
        )
    if not (VOLUME_PERCENT_MIN <= preset.volume_percent <= VOLUME_PERCENT_MAX):
        raise ConfigurationError(
            f"Volume must be between {VOLUME_PERCENT_MIN}% and {VOLUME_PERCENT_MAX}% "
            f"(got {preset.volume_percent}%)."
        )
    for label, value in (
        ("Sentence", preset.sentence_pause_ms),
        ("Paragraph", preset.paragraph_pause_ms),
        ("Scene", preset.scene_pause_ms),
    ):
        if not (PAUSE_MS_MIN <= value <= PAUSE_MS_MAX):
            raise ConfigurationError(
                f"{label} pause must be between {PAUSE_MS_MIN}ms and {PAUSE_MS_MAX}ms (got {value}ms)."
            )
    if not preset.name or not preset.name.strip():
        raise ConfigurationError("Preset name cannot be empty.")


def _builtin_presets() -> List[VoicePreset]:
    return [
        VoicePreset(
            name="Normal Narrator",
            rate=1.00, pitch_hz=0, volume_percent=0,
            sentence_pause_ms=250, paragraph_pause_ms=600, scene_pause_ms=1000,
            is_builtin=True,
        ),
        VoicePreset(
            name="Sleep Story / Calm Narrator",
            rate=0.88, pitch_hz=-5, volume_percent=0,
            sentence_pause_ms=350, paragraph_pause_ms=800, scene_pause_ms=1200,
            is_builtin=True,
        ),
        VoicePreset(
            name="Storytelling",
            rate=1.00, pitch_hz=0, volume_percent=0,
            sentence_pause_ms=300, paragraph_pause_ms=700, scene_pause_ms=1000,
            is_builtin=True,
        ),
        VoicePreset(
            name="Documentary",
            rate=0.97, pitch_hz=0, volume_percent=0,
            sentence_pause_ms=250, paragraph_pause_ms=600, scene_pause_ms=1000,
            is_builtin=True,
        ),
    ]


BUILTIN_PRESETS: List[VoicePreset] = _builtin_presets()