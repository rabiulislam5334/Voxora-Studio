from __future__ import annotations

from app.cache import manager as cache_manager
from app.cache.manager import NarrationCache


def test_scene_cache_version_invalidates_assembled_wavs_only(monkeypatch, tmp_path):
    cache = NarrationCache(tmp_path / "chunks", tmp_path / "scenes")
    signature = [24000, [["c", "chunk-key"], ["s", 700]]]

    old_scene_key = cache.scene_key(signature)
    chunk_key_before = cache.chunk_key(
        "edge_tts", "en-US-BrianNeural", "Hello world", 1.0, 0, 100
    )

    monkeypatch.setattr(
        cache_manager,
        "NARRATION_SCENE_PIPELINE_VERSION",
        cache_manager.NARRATION_SCENE_PIPELINE_VERSION + 1,
    )

    new_scene_key = cache.scene_key(signature)
    chunk_key_after = cache.chunk_key(
        "edge_tts", "en-US-BrianNeural", "Hello world", 1.0, 0, 100
    )

    assert new_scene_key != old_scene_key
    assert chunk_key_after == chunk_key_before


def test_scene_cache_key_changes_when_sample_rate_changes(tmp_path):
    cache = NarrationCache(tmp_path / "chunks", tmp_path / "scenes")

    at_24khz = cache.scene_key([24000, [["s", 700]]])
    at_48khz = cache.scene_key([48000, [["s", 700]]])

    assert at_24khz != at_48khz
