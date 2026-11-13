"""Immutable, file-backed snapshot generations (Step 5.2).

The caller injects a session directory. This module deliberately does not
create sessions, acquire OS locks, start workers, or enable autosave/recovery.
Those belong to the separately gated session and worker steps.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.core.exceptions import ProjectError
from app.persistence.atomic import atomic_write_bytes
from app.persistence.snapshot_control import (
    CommitDecision,
    Job,
    SaveRecord,
    SealOutcome,
    SnapshotControl,
)
from app.persistence.stamps import read_stamped

MAX_SEQUENCE = 999_999_999_999
GENERATION_PREFIX = "snapshot-"
GENERATION_SUFFIX = ".json"
META_SUFFIX = ".meta.json"
CURRENT_NAME = "current.json"


@dataclass(frozen=True)
class SnapshotGeneration:
    seq: int
    epoch: int
    revision: int
    created_at: str
    payload: bytes
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class SnapshotScan:
    generations: Tuple[SnapshotGeneration, ...]
    highest_valid: int
    highest_seen: int
    current: Optional[SnapshotGeneration]


class SnapshotStore:
    """File operations for immutable generations; disabled unless opted in.

    One generation is a payload file plus a metadata file. The pair becomes
    recoverable only after both files have been written and verified.
    current.json is merely a pointer hint; recovery always scans generations.
    """

    def __init__(
        self,
        session_dir: Path,
        control: SnapshotControl,
        *,
        enabled: bool = False,
        retention: int = 3,
    ) -> None:
        if retention < 1:
            raise ValueError("Snapshot retention must be at least one generation.")
        self.session_dir = Path(session_dir)
        self.control = control
        self.enabled = bool(enabled)
        self.retention = retention

    @staticmethod
    def _payload_name(seq: int) -> str:
        return f"{GENERATION_PREFIX}{seq:012d}{GENERATION_SUFFIX}"

    @staticmethod
    def _meta_name(seq: int) -> str:
        return f"{GENERATION_PREFIX}{seq:012d}{META_SUFFIX}"

    def _payload_path(self, seq: int) -> Path:
        return self.session_dir / self._payload_name(seq)

    def _meta_path(self, seq: int) -> Path:
        return self.session_dir / self._meta_name(seq)

    def _read_generation(self, seq: int) -> Optional[SnapshotGeneration]:
        try:
            payload = self._payload_path(seq).read_bytes()
            metadata = json.loads(self._meta_path(seq).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(metadata, dict):
            return None
        if type(metadata.get("seq")) is not int or metadata["seq"] != seq:
            return None
        if type(metadata.get("epoch")) is not int or metadata["epoch"] < 1:
            return None
        if type(metadata.get("revision")) is not int:
            return None
        if type(metadata.get("size")) is not int or metadata["size"] != len(payload):
            return None
        digest = hashlib.sha256(payload).hexdigest()
        if metadata.get("sha256") != digest:
            return None
        created_at = metadata.get("created_at")
        if not isinstance(created_at, str):
            return None
        return SnapshotGeneration(
            seq=seq,
            epoch=metadata["epoch"],
            revision=metadata["revision"],
            created_at=created_at,
            payload=payload,
            metadata=metadata,
        )

    def scan(self, *, restored_seq: int = 0) -> SnapshotScan:
        """Validate all generation pairs; current.json never decides validity."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        seen = set()
        for path in self.session_dir.glob(f"{GENERATION_PREFIX}*"):
            stem = path.name[len(GENERATION_PREFIX):]
            digits = stem[:12]
            if len(digits) == 12 and digits.isdigit():
                seen.add(int(digits))
        generations = []
        for seq in sorted(seen):
            generation = self._read_generation(seq)
            if generation is not None:
                generations.append(generation)
        current = self._read_current(generations)
        highest_valid = max((item.seq for item in generations), default=0)
        highest_seen = max(seen, default=0)
        self.control.restore_sequence_state(
            highest_valid=highest_valid,
            highest_seen=highest_seen,
            restored_seq=restored_seq,
        )
        return SnapshotScan(
            generations=tuple(sorted(generations, key=lambda item: item.seq, reverse=True)),
            highest_valid=highest_valid,
            highest_seen=highest_seen,
            current=current,
        )

    def _read_current(
        self, generations: Tuple[SnapshotGeneration, ...] | list[SnapshotGeneration]
    ) -> Optional[SnapshotGeneration]:
        try:
            pointer = json.loads((self.session_dir / CURRENT_NAME).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (
            not isinstance(pointer, dict)
            or type(pointer.get("seq")) is not int
            or type(pointer.get("epoch")) is not int
            or type(pointer.get("revision")) is not int
        ):
            return None
        for generation in generations:
            if (
                generation.seq == pointer["seq"]
                and generation.epoch == pointer.get("epoch")
                and generation.revision == pointer.get("revision")
            ):
                return generation
        return None

    def commit(self, job: Job) -> CommitDecision:
        """Publish a generation. A validated pair survives pointer-write failure."""
        if not self.enabled:
            raise RuntimeError("Snapshot storage is disabled; no snapshot was written.")
        if type(job.seq) is not int or not 1 <= job.seq <= MAX_SEQUENCE:
            from app.core.exceptions import SnapshotSequenceExhausted
            raise SnapshotSequenceExhausted("Snapshot sequence is outside the 12-digit range.")

        self.session_dir.mkdir(parents=True, exist_ok=True)
        if not self.control.acquire_write():
            raise ProjectError("Could not acquire the snapshot commit lock.")
        validated = False
        try:
            decision = self.control.decide_commit(job)
            if decision is not CommitDecision.COMMIT:
                return decision

            payload_path = self._payload_path(job.seq)
            meta_path = self._meta_path(job.seq)
            if payload_path.exists() or meta_path.exists():
                raise ProjectError(f"Snapshot sequence {job.seq} already exists; refusing to overwrite it.")

            digest = hashlib.sha256(job.payload).hexdigest()
            created_at = datetime.now(timezone.utc).isoformat()
            metadata = {
                "seq": job.seq,
                "epoch": job.epoch,
                "revision": job.revision,
                "sha256": digest,
                "size": len(job.payload),
                "created_at": created_at,
            }
            try:
                atomic_write_bytes(payload_path, job.payload)
                meta_bytes = json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")
                atomic_write_bytes(meta_path, meta_bytes)
                generation = self._read_generation(job.seq)
                if generation is None:
                    raise ProjectError("The newly written snapshot failed payload/metadata validation.")
                validated = True
                pointer = {
                    "seq": job.seq,
                    "epoch": job.epoch,
                    "revision": job.revision,
                }
                atomic_write_bytes(
                    self.session_dir / CURRENT_NAME,
                    json.dumps(pointer, sort_keys=True).encode("utf-8"),
                )
                self.control.note_committed(job)
                self._prune_epoch(job.epoch)
                return CommitDecision.COMMIT
            except Exception as exc:
                if not validated:
                    self._unlink(payload_path)
                    self._unlink(meta_path)
                if isinstance(exc, ProjectError):
                    raise
                raise ProjectError(f"Could not commit snapshot {job.seq}: {exc}") from exc
        finally:
            try:
                self.control.apply_pending()
                self._drop_pointer_at_or_below_barrier()
            finally:
                self.control.release_write()

    def seal_save(self, record: SaveRecord) -> SealOutcome:
        """Apply the Save barrier; pointer invalidation is immediate, pruning is not."""
        outcome = self.control.on_save_success(record)
        if outcome is SealOutcome.SEALED:
            if self.control.acquire_write(0):
                try:
                    self._drop_pointer_at_or_below_barrier()
                finally:
                    self.control.release_write()
        return outcome

    def cleanup_after_save(self, record: SaveRecord) -> bool:
        """Perform deferred cleanup only if the saved file still has its stamp."""
        if not self.enabled:
            return False
        if not self.control.acquire_write():
            return False
        try:
            # Re-verify under the commit mutex immediately before any deletion.
            try:
                _, current_stamp = read_stamped(record.path)
            except OSError:
                return False
            if not current_stamp.same_content(record.stamp):
                return False
            if record.epoch != self.control.epoch:
                return False
            barrier = self.control.barrier_revision
            if barrier < record.revision:
                return False
            generations = self._valid_generations()
            replacement = next(
                (
                    item for item in generations
                    if item.epoch == record.epoch and item.revision > barrier
                ),
                None,
            )
            pointer_path = self.session_dir / CURRENT_NAME
            pointer = self._read_pointer()
            if (
                pointer
                and type(pointer.get("epoch")) is int
                and pointer.get("epoch") == record.epoch
                and type(pointer.get("revision")) is int
                and pointer["revision"] <= barrier
            ):
                if replacement is None:
                    if not self._unlink(pointer_path):
                        return False
                else:
                    self._write_pointer(replacement)

            removed = False
            for item in generations:
                if item.epoch == record.epoch and item.revision <= barrier:
                    if self._unlink(self._meta_path(item.seq)):
                        self._unlink(self._payload_path(item.seq))
                        removed = True
            return removed
        finally:
            self.control.release_write()

    def discard_epoch(self, epoch: int) -> int:
        """Explicitly discard one epoch; pointer is removed before its files."""
        if not self.enabled:
            return 0
        if not self.control.acquire_write():
            raise ProjectError("Could not acquire the snapshot commit lock.")
        try:
            pointer = self._read_pointer()
            if pointer and type(pointer.get("epoch")) is int and pointer.get("epoch") == epoch:
                if not self._unlink(self.session_dir / CURRENT_NAME):
                    return 0
            removed = 0
            for item in self._valid_generations():
                if item.epoch == epoch:
                    if self._unlink(self._meta_path(item.seq)):
                        self._unlink(self._payload_path(item.seq))
                        removed += 1
            return removed
        finally:
            self.control.release_write()

    def load_generation(self, seq: int) -> SnapshotGeneration:
        generation = self._read_generation(seq)
        if generation is None:
            raise ProjectError(f"Snapshot generation {seq} is missing or invalid.")
        return generation

    def begin_replace(self, timeout: Optional[float] = None) -> bool:
        return self.control.begin_replace(timeout=timeout)

    def commit_replace(self) -> None:
        self.control.commit_replace()

    def abort_replace(self) -> None:
        self.control.abort_replace()

    def end_replace(self) -> None:
        self.control.end_replace()

    def cleanup_replaced_epoch(self, old_epoch: int, restored_seq: int) -> int:
        """Delete old-epoch generations only after the first restored generation validates."""
        if not self.enabled:
            return 0
        restored = self.load_generation(restored_seq)
        if restored.epoch != self.control.epoch:
            raise ProjectError("The first restored snapshot does not belong to the current epoch.")
        return self.discard_epoch(old_epoch)

    def _valid_generations(self) -> list[SnapshotGeneration]:
        seen = set()
        for path in self.session_dir.glob(f"{GENERATION_PREFIX}*"):
            digits = path.name[len(GENERATION_PREFIX):][:12]
            if len(digits) == 12 and digits.isdigit():
                seen.add(int(digits))
        return [
            generation
            for seq in sorted(seen)
            if (generation := self._read_generation(seq)) is not None
        ]

    def _prune_epoch(self, epoch: int) -> None:
        generations = sorted(
            (item for item in self._valid_generations() if item.epoch == epoch),
            key=lambda item: item.seq,
            reverse=True,
        )
        pointer = self._read_pointer()
        keep = {item.seq for item in generations[: self.retention]}
        if (
            pointer
            and type(pointer.get("epoch")) is int
            and pointer.get("epoch") == epoch
            and type(pointer.get("seq")) is int
        ):
            keep.add(pointer["seq"])
        for item in generations:
            if item.seq not in keep:
                if self._unlink(self._meta_path(item.seq)):
                    self._unlink(self._payload_path(item.seq))

    def _read_pointer(self) -> Optional[Dict[str, Any]]:
        try:
            value = json.loads((self.session_dir / CURRENT_NAME).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _write_pointer(self, generation: SnapshotGeneration) -> None:
        value = {
            "seq": generation.seq,
            "epoch": generation.epoch,
            "revision": generation.revision,
        }
        atomic_write_bytes(
            self.session_dir / CURRENT_NAME,
            json.dumps(value, sort_keys=True).encode("utf-8"),
        )

    def _drop_pointer_at_or_below_barrier(self) -> None:
        pointer = self._read_pointer()
        if not pointer:
            return
        if type(pointer.get("epoch")) is not int or pointer.get("epoch") != self.control.epoch:
            return
        revision = pointer.get("revision")
        if type(revision) is int and revision <= self.control.barrier_revision:
            self._unlink(self.session_dir / CURRENT_NAME)

    @staticmethod
    def _unlink(path: Path) -> bool:
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            # Never delete a payload if its metadata/pointer could not be removed.
            return False
