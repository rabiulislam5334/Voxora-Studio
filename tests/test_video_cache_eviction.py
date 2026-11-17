from __future__ import annotations

import os

from app.cache.video_cache import VideoCache


def _write_cache_file(path, size: int, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


def test_segment_prune_evicts_oldest_entries_until_under_budget(tmp_path):
    cache = VideoCache(tmp_path / "cache")
    oldest = cache.segment_path("oldest")
    newer = cache.segment_path("newer")
    newest = cache.segment_path("newest")
    _write_cache_file(oldest, 4, 100)
    _write_cache_file(newer, 4, 200)
    _write_cache_file(newest, 4, 950)

    cache.prune(max_bytes=8, image_max_bytes=100, now=1000, grace_seconds=60)

    assert not oldest.exists()
    assert newer.exists()
    assert newest.exists()


def test_segment_cache_hit_refreshes_lru_timestamp_and_preserves_recent_entry(tmp_path):
    cache = VideoCache(tmp_path / "cache")
    recently_used = cache.segment_path("recently-used")
    least_recent = cache.segment_path("least-recent")
    _write_cache_file(recently_used, 4, 100)
    _write_cache_file(least_recent, 4, 200)

    cache.touch_segment("recently-used")
    cache.prune(max_bytes=4, image_max_bytes=100, grace_seconds=0)

    assert recently_used.exists()
    assert not least_recent.exists()


def test_image_prune_has_independent_budget_and_leaves_part_files(tmp_path):
    cache = VideoCache(tmp_path / "cache")
    old_image = cache.images_dir / "old.png"
    recent_image = cache.images_dir / "recent.png"
    part_file = cache.images_dir / "unfinished.png.part"
    _write_cache_file(old_image, 5, 100)
    _write_cache_file(recent_image, 5, 950)
    _write_cache_file(part_file, 100, 50)

    cache.prune(max_bytes=100, image_max_bytes=5, now=1000, grace_seconds=60)

    assert not old_image.exists()
    assert recent_image.exists()
    assert part_file.exists()


def test_prune_does_not_remove_recent_files_even_when_budget_is_exceeded(tmp_path):
    cache = VideoCache(tmp_path / "cache")
    active_candidate = cache.segment_path("recently-written")
    _write_cache_file(active_candidate, 20, 950)

    cache.prune(max_bytes=0, image_max_bytes=0, now=1000, grace_seconds=120)

    assert active_candidate.exists()


def test_image_cache_hit_refreshes_lru_timestamp(tmp_path):
    cache = VideoCache(tmp_path / "cache")
    image = cache.images_dir / "preview.png"
    _write_cache_file(image, 4, 100)

    cache.touch_image(image)

    assert image.stat().st_mtime > 100
