from __future__ import annotations

from app.tts.base import ProviderCapabilities


def test_capabilities_default_all_false():
    caps = ProviderCapabilities()
    assert caps.supports_speed is False
    assert caps.supports_pitch is False
    assert caps.supports_style is False
    assert caps.supports_emotion is False
    assert caps.supports_ssml is False
    assert caps.supports_voice_cloning is False
    assert caps.max_chars_per_request is None


def test_capabilities_can_be_overridden():
    caps = ProviderCapabilities(supports_speed=True, max_chars_per_request=3000)
    assert caps.supports_speed is True
    assert caps.max_chars_per_request == 3000