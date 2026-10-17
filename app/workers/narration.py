from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from app.audio.assembler import WavBuilder, wav_duration_seconds
from app.audio.ffmpeg_tool import FFmpegTool
from app.cache.manager import NarrationCache
from app.core import constants
from app.core.exceptions import (
    ConfigurationError,
    FFmpegError,
    GenerationCancelled,
    NarrationError,
    TTSProviderError,
)
from app.core.filenames import safe_filename
from app.core.logger import get_logger
from app.models.scene import Scene
from app.models.voice_preset import VoicePreset, validate_preset
from app.text.narration_plan import Chunk, ScenePlan, Silence, plan_scene
from app.tts.manager import TTSManager
from app.workers.cancel import CancelToken

logger = get_logger("workers.narration")


# ----------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SceneRequest:
    """Everything needed to narrate one scene, with every per-scene override
    already resolved against the Voice page settings."""

    scene_id: str
    scene_index: int  # 1-based position in the project; used in chunk ids
    title: str
    text: str
    voice_id: str
    rate: float
    pitch_hz: int
    volume_percent: int
    sentence_pause_ms: int
    paragraph_pause_ms: int
    scene_pause_ms: int


@dataclass(frozen=True)
class ProgressEvent:
    done: int
    total: int
    message: str

    @property
    def fraction(self) -> float:
        return 0.0 if self.total <= 0 else min(1.0, self.done / self.total)


@dataclass(frozen=True)
class SceneTiming:
    """Where each scene sits in the final narration (seconds). Recorded now
    so subtitles/timeline phases can use it without re-measuring audio."""

    scene_id: str
    title: str
    start_seconds: float
    end_seconds: float


@dataclass
class NarrationResult:
    mp3_path: Path
    wav_path: Path
    duration_seconds: float
    scene_timings: List[SceneTiming]
    chunk_count: int
    cached_chunks: int
    synthesized_chunks: int
    warnings: List[str] = field(default_factory=list)


def build_scene_request(
    scene: Scene, *, scene_index: int, default_voice_id: Optional[str], settings: VoicePreset
) -> SceneRequest:
    """Resolve a Scene against the live Voice page settings.

    A per-scene override (Phase 4 fields, None = unset) wins over the Voice
    page. The scene pause falls back to the legacy `pause_ms` if it is set,
    then to the Voice page. `Scene.speed` is not used: its default (1.0) is
    indistinguishable from "unset", so rate always comes from the Voice page.
    """
    voice_id = scene.voice_id or default_voice_id
    if not voice_id:
        raise ConfigurationError("No voice selected. Pick a voice in the Voice Library first.")

    def pick(override, fallback):
        return override if override is not None else fallback

    scene_pause = scene.scene_pause_ms
    if scene_pause is None:
        scene_pause = scene.pause_ms if scene.pause_ms and scene.pause_ms > 0 else settings.scene_pause_ms

    request = SceneRequest(
        scene_id=scene.id,
        scene_index=scene_index,
        title=scene.title,
        text=scene.text,
        voice_id=voice_id,
        rate=settings.rate,
        pitch_hz=pick(scene.pitch_hz, settings.pitch_hz),
        volume_percent=pick(scene.volume_percent, settings.volume_percent),
        sentence_pause_ms=pick(scene.sentence_pause_ms, settings.sentence_pause_ms),
        paragraph_pause_ms=pick(scene.paragraph_pause_ms, settings.paragraph_pause_ms),
        scene_pause_ms=scene_pause,
    )
    try:
        validate_preset(
            VoicePreset(
                name="scene", rate=request.rate, pitch_hz=request.pitch_hz,
                volume_percent=request.volume_percent,
                sentence_pause_ms=request.sentence_pause_ms,
                paragraph_pause_ms=request.paragraph_pause_ms,
                scene_pause_ms=request.scene_pause_ms,
            )
        )
    except ConfigurationError as exc:
        raise ConfigurationError(f"Scene '{scene.title}': {exc}") from exc
    return request


# ----------------------------------------------------------------------
# Job
# ----------------------------------------------------------------------


class NarrationJob:
    """Scene-by-scene long-form narration.

    plan (parse markers, chunk) -> synthesize missing chunks (cached,
    concurrent, retried) -> assemble each scene WAV with real silence ->
    join scenes -> encode MP3. Resume is automatic: every finished chunk
    and scene is cached, so re-running only does the missing work.
    """

    def __init__(
        self,
        tts_manager: TTSManager,
        ffmpeg: FFmpegTool,
        cache: NarrationCache,
        temp_dir: Path,
        *,
        concurrency: int = constants.NARRATION_CONCURRENCY,
        max_attempts: int = constants.NARRATION_MAX_ATTEMPTS,
        retry_base_delay: float = constants.NARRATION_RETRY_BASE_DELAY,
        max_chunk_chars: int = constants.NARRATION_MAX_CHUNK_CHARS,
        sample_rate: int = constants.NARRATION_SAMPLE_RATE,
    ) -> None:
        self._tts = tts_manager
        self._ffmpeg = ffmpeg
        self._cache = cache
        self._temp_dir = Path(temp_dir)
        self._concurrency = max(1, concurrency)
        self._max_attempts = max(1, max_attempts)
        self._retry_base_delay = max(0.0, retry_base_delay)
        self._max_chunk_chars = max_chunk_chars
        self._sample_rate = sample_rate

    async def run(
        self,
        requests: Sequence[SceneRequest],
        *,
        output_dir: Path,
        basename: str,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> NarrationResult:
        """on_progress may be called from background threads; it must be
        thread-safe (the UI wraps it in AsyncBridge.dispatch)."""
        cancel = cancel or CancelToken()
        emit = on_progress or (lambda event: None)

        # 1. Fail early and clearly if FFmpeg is unusable.
        await asyncio.to_thread(self._ffmpeg.require)
        self._cache.remove_stale_parts()

        # 2. Plan.
        provider_id = self._tts.active_provider_id() or "unknown"
        plans: List[ScenePlan] = []
        scene_requests: List[SceneRequest] = []
        warnings: List[str] = []
        style_tags: List[str] = []
        for request in requests:
            plan = plan_scene(
                request.text, request.scene_index,
                sentence_pause_ms=request.sentence_pause_ms,
                paragraph_pause_ms=request.paragraph_pause_ms,
                max_chars=self._max_chunk_chars,
            )
            for w in plan.warnings:
                warnings.append(f"Scene '{request.title}': {w}")
            for tag in plan.style_tags:
                if tag not in style_tags:
                    style_tags.append(tag)
            if not plan.chunks:
                warnings.append(f"Scene '{request.title}' has no speakable text and was skipped.")
                continue
            plans.append(plan)
            scene_requests.append(request)
        if not plans:
            raise NarrationError("There is no speakable text to narrate.")
        if style_tags:
            warnings.append(
                "Style tags (" + ", ".join(style_tags) + ") were removed from the spoken text. "
                "Edge TTS does not support voice styles, so they have no effect."
            )

        # 3. Work out which chunks need synthesizing (identical chunks are done once).
        keys_by_chunk: Dict[str, str] = {}
        unique: Dict[str, tuple] = {}  # key -> (chunk, request)
        total_chunks = 0
        for plan, request in zip(plans, scene_requests):
            for chunk in plan.chunks:
                total_chunks += 1
                key = self._cache.chunk_key(
                    provider_id, request.voice_id, chunk.text,
                    request.rate, request.pitch_hz, request.volume_percent,
                )
                keys_by_chunk[chunk.id] = key
                unique.setdefault(key, (chunk, request))

        pending = [k for k in unique if not self._cache.has_chunk(k)]
        cached_count = len(unique) - len(pending)
        total_steps = len(unique) + len(plans) + 1  # chunks + scene assemblies + MP3 encode
        progress = {"done": cached_count}

        def report(message: str) -> None:
            emit(ProgressEvent(progress["done"], total_steps, message))

        report(f"{cached_count} of {len(unique)} chunks already cached; {len(pending)} to generate.")

        # 4. Synthesize.
        await self._synthesize(pending, unique, provider_id, cancel, progress, report, len(unique))
        cancel.raise_if_cancelled()

        # 5. Assemble (blocking file work -> worker thread).
        work_dir = self._temp_dir / f"narration_{uuid.uuid4().hex[:8]}"
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(safe_filename(basename, "wav")).stem
        wav_path = output_dir / f"{stem}.wav"
        mp3_path = output_dir / f"{stem}.mp3"

        try:
            def assemble() -> NarrationResult:
                scene_wavs: List[Path] = []
                for n, (plan, request) in enumerate(zip(plans, scene_requests), start=1):
                    cancel.raise_if_cancelled()
                    scene_wavs.append(self._build_scene_wav(plan, keys_by_chunk, work_dir, cancel))
                    progress["done"] += 1
                    report(f"Assembled scene {n} of {len(plans)}: {request.title}")

                cancel.raise_if_cancelled()
                timings: List[SceneTiming] = []
                with WavBuilder(wav_path, self._sample_rate) as builder:
                    for i, (request, scene_wav) in enumerate(zip(scene_requests, scene_wavs)):
                        start = builder.duration_seconds
                        builder.add_wav(scene_wav)
                        timings.append(SceneTiming(request.scene_id, request.title, start, builder.duration_seconds))
                        if i < len(scene_wavs) - 1:
                            builder.add_silence(request.scene_pause_ms)

                report("Encoding MP3...")
                part_mp3 = mp3_path.with_name(mp3_path.name + ".part")
                try:
                    self._ffmpeg.encode_mp3(wav_path, part_mp3, constants.NARRATION_MP3_BITRATE, cancel)
                    os.replace(part_mp3, mp3_path)
                finally:
                    part_mp3.unlink(missing_ok=True)
                progress["done"] += 1
                report("Narration ready.")
                return NarrationResult(
                    mp3_path=mp3_path,
                    wav_path=wav_path,
                    duration_seconds=wav_duration_seconds(wav_path),
                    scene_timings=timings,
                    chunk_count=total_chunks,
                    cached_chunks=cached_count,
                    synthesized_chunks=len(pending),
                    warnings=warnings,
                )

            try:
                result = await asyncio.to_thread(assemble)
            except BaseException:
                wav_path.unlink(missing_ok=True)
                mp3_path.unlink(missing_ok=True)
                raise
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        self._cache.prune_scene_wavs()
        return result

    # ------------------------------------------------------------------
    # Synthesis (concurrent, retried, cancellable)
    # ------------------------------------------------------------------

    async def _synthesize(self, pending, unique, provider_id, cancel, progress, report, total_unique) -> None:
        if not pending:
            return
        semaphore = asyncio.Semaphore(self._concurrency)
        failures: Dict[str, str] = {}
        state = {"consecutive": 0, "aborted": False}

        async def work(key: str) -> None:
            chunk, request = unique[key]
            async with semaphore:
                if cancel.cancelled or state["aborted"]:
                    return
                try:
                    await self._synthesize_one(key, chunk, request, provider_id, cancel)
                except GenerationCancelled:
                    return
                except Exception as exc:  # noqa: BLE001 - isolated per chunk, reported at the end
                    failures[chunk.id] = str(exc)
                    state["consecutive"] += 1
                    if state["consecutive"] >= constants.NARRATION_MAX_CONSECUTIVE_FAILURES:
                        state["aborted"] = True
                    logger.error("Chunk %s failed after retries: %s", chunk.id, exc)
                    return
                state["consecutive"] = 0
                progress["done"] += 1
                report(f"Generated {progress['done'] - (total_unique - len(pending))} of {len(pending)} chunks ({chunk.id})")

        tasks = {asyncio.create_task(work(key)) for key in pending}
        remaining = set(tasks)
        while remaining:
            _, remaining = await asyncio.wait(remaining, timeout=0.2)
            if cancel.cancelled:
                for task in remaining:
                    task.cancel()
                await asyncio.gather(*remaining, return_exceptions=True)
                break

        if cancel.cancelled:
            saved = sum(1 for k in unique if self._cache.has_chunk(k))
            raise GenerationCancelled(
                f"Cancelled. {saved} of {total_unique} chunks are saved; generate again to resume."
            )

        if failures:
            first_id, first_error = next(iter(failures.items()))
            prefix = (
                "Stopped after repeated failures (check your internet connection). "
                if state["aborted"] else ""
            )
            raise NarrationError(
                f"{prefix}{len(failures)} chunk(s) failed after {self._max_attempts} attempts "
                f"(first: {first_id}: {first_error}). Finished chunks are saved; "
                "generate again to retry only the missing ones.",
                failed_chunk_ids=list(failures),
            )

    async def _synthesize_one(self, key, chunk: Chunk, request: SceneRequest, provider_id, cancel) -> None:
        last_error: Optional[BaseException] = None
        for attempt in range(1, self._max_attempts + 1):
            cancel.raise_if_cancelled()
            part = self._cache.part_path(key)
            try:
                await self._tts.generate(
                    chunk.text, request.voice_id, part,
                    provider_id=provider_id, speed=request.rate,
                    pitch_hz=request.pitch_hz, volume_percent=request.volume_percent,
                )
                self._cache.commit_chunk(part, key)
                return
            except asyncio.CancelledError:
                part.unlink(missing_ok=True)
                raise
            except Exception as exc:  # noqa: BLE001 - retried below
                part.unlink(missing_ok=True)
                last_error = exc
                logger.warning("Chunk %s attempt %d/%d failed: %s", chunk.id, attempt, self._max_attempts, exc)
                if attempt < self._max_attempts:
                    delay = min(self._retry_base_delay * (2 ** (attempt - 1)), constants.NARRATION_RETRY_MAX_DELAY)
                    await self._cancellable_sleep(delay, cancel)
        raise TTSProviderError(str(last_error)) from last_error

    @staticmethod
    async def _cancellable_sleep(seconds: float, cancel: CancelToken) -> None:
        waited = 0.0
        while waited < seconds and not cancel.cancelled:
            step = min(0.1, seconds - waited)
            await asyncio.sleep(step)
            waited += step

    # ------------------------------------------------------------------
    # Scene assembly (runs in a worker thread)
    # ------------------------------------------------------------------

    def _build_scene_wav(self, plan: ScenePlan, keys_by_chunk: Dict[str, str], work_dir: Path, cancel: CancelToken) -> Path:
        signature = [
            ["c", keys_by_chunk[i.id]] if isinstance(i, Chunk) else ["s", i.ms]
            for i in plan.items
        ]
        scene_key = self._cache.scene_key([self._sample_rate, signature])
        dest = self._cache.scene_wav_path(scene_key)
        if self._cache.has_scene(scene_key):
            self._cache.touch_scene(scene_key)
            return dest

        decoded = work_dir / f"decode_{uuid.uuid4().hex[:6]}.wav"
        try:
            with WavBuilder(dest, self._sample_rate) as builder:
                for item in plan.items:
                    cancel.raise_if_cancelled()
                    if isinstance(item, Silence):
                        builder.add_silence(item.ms)
                        continue
                    source = self._cache.chunk_path(keys_by_chunk[item.id])
                    if not source.is_file():
                        raise NarrationError(
                            f"Cached audio for {item.id} is missing; generate again to recreate it.",
                            failed_chunk_ids=[item.id],
                        )
                    try:
                        self._ffmpeg.decode_to_wav(source, decoded, self._sample_rate, cancel)
                    except FFmpegError:
                        source.unlink(missing_ok=True)  # corrupt cache entry: drop so a rerun regenerates it
                        raise
                    builder.add_wav(decoded)
                    decoded.unlink(missing_ok=True)
        finally:
            decoded.unlink(missing_ok=True)
        return dest