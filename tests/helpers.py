"""Small test doubles shared by the Phase 6-8 tests (no Tk, no network)."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.models.voice import Voice
from app.tts.base import ProviderCapabilities, SynthResult, TTSProvider
from app.core.exceptions import TTSProviderError
from app.workers.narration import SceneRequest


class FakeTTS:
    """Stands in for TTSManager inside NarrationJob: copies a tone MP3 as the
    'synthesized' audio and records every text it was asked to speak."""

    def __init__(self, tone: Path, fail_texts=(), fail_times=0, delay=0.0):
        self.tone = tone
        self.calls = []
        self.fail_texts = set(fail_texts)
        self.fail_times = fail_times
        self.delay = delay
        self._attempts = {}
        self.active = 0
        self.max_active = 0

    def active_provider_id(self):
        return "edge_tts"

    async def generate(self, text, voice_id, output_path, provider_id=None, speed=1.0, **extra):
        self.calls.append(text)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            self._attempts[text] = self._attempts.get(text, 0) + 1
            if text in self.fail_texts and self._attempts[text] <= self.fail_times:
                raise TTSProviderError("simulated network error")
            shutil.copyfile(self.tone, output_path)
        finally:
            self.active -= 1


def make_request(text, index=1, **kw):
    """A SceneRequest with sensible defaults; override any field by keyword."""
    base = dict(scene_id=f"s{index}", scene_index=index, title=f"Scene {index}", text=text,
                voice_id="v", rate=1.0, pitch_hz=0, volume_percent=0,
                sentence_pause_ms=250, paragraph_pause_ms=600, scene_pause_ms=1000)
    base.update(kw)
    return SceneRequest(**base)


class FakeProvider(TTSProvider):
    """A real TTSProvider (so it can be registered with TTSManager) whose
    voice list is one fake voice and whose audio is a copied tone MP3."""

    provider_id = "fake"

    def __init__(self, tone: Path, delay: float = 0.0):
        self.tone = tone
        self.delay = delay
        self.texts = []

    def get_provider_name(self):
        return "Fake"

    def get_capabilities(self):
        return ProviderCapabilities(supports_speed=True)

    async def list_voices(self, force_refresh=False):
        return [Voice(id="fake-voice", name="Fake Voice", provider="fake", language="en-US", gender="Female")]

    async def generate(self, text, voice_id, **settings):
        self.texts.append(text)
        if self.delay:
            await asyncio.sleep(self.delay)
        out = Path(settings["output_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.tone, out)
        return SynthResult(audio_path=str(out))