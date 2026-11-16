from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from app.core.exceptions import ProjectLockError
from app.persistence.file_lock import ProjectFileLock


def _hold_lock(target: str, ready, release) -> None:
    with ProjectFileLock(Path(target), timeout_s=5):
        ready.set()
        release.wait(5)


def test_lock_file_is_stable_and_reusable_after_release(tmp_path):
    target = tmp_path / "episode.voxora"

    with ProjectFileLock(target):
        lock_path = tmp_path / ".episode.voxora.lock"
        assert lock_path.is_file()

    # The persistent sidecar is reused rather than unlinked on release.
    assert lock_path.is_file()
    with ProjectFileLock(target):
        assert lock_path.is_file()


def test_second_process_cannot_enter_while_first_process_holds_lock(tmp_path):
    target = tmp_path / "episode.voxora"
    ready = multiprocessing.Event()
    release = multiprocessing.Event()
    process = multiprocessing.Process(target=_hold_lock, args=(str(target), ready, release))
    process.start()
    try:
        assert ready.wait(5), "child process did not acquire the project lock"
        with pytest.raises(ProjectLockError, match="Another Voxora instance"):
            with ProjectFileLock(target, timeout_s=0.15):
                pass
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0


def test_lock_can_be_acquired_after_another_process_releases(tmp_path):
    target = tmp_path / "episode.voxora"
    ready = multiprocessing.Event()
    release = multiprocessing.Event()
    process = multiprocessing.Process(target=_hold_lock, args=(str(target), ready, release))
    process.start()
    try:
        assert ready.wait(5), "child process did not acquire the project lock"
        release.set()
        process.join(5)
        assert process.exitcode == 0
        with ProjectFileLock(target, timeout_s=1):
            pass
    finally:
        if process.is_alive():
            release.set()
            process.terminate()
            process.join(5)
