"""Sequential, fail-fast orchestration for ordered Universal scene batches."""
from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Tuple

from app.core.exceptions import GenerationCancelled
from app.universal.execution import SceneExecutionContext, SceneExecutionCoordinator, SceneExecutionResult
from app.universal.models import ScenePlan
from app.workers.cancel import CancelToken


ProgressCallback = Optional[Callable[[float], None]]


@dataclass(frozen=True)
class MultiSceneExecutionRequest:
    """Validated ordered scene plans and their explicit per-scene contexts."""

    scene_plans: Tuple[ScenePlan, ...]
    contexts: Mapping[str, SceneExecutionContext]

    def __post_init__(self) -> None:
        if isinstance(self.scene_plans, (str, bytes)):
            raise TypeError("scene_plans must be an iterable of ScenePlan values")
        try:
            plans = tuple(self.scene_plans)
        except TypeError:
            raise TypeError("scene_plans must be an iterable of ScenePlan values") from None
        if not plans:
            raise ValueError("scene_plans must not be empty")
        if any(not isinstance(plan, ScenePlan) for plan in plans):
            raise TypeError("scene_plans must contain only ScenePlan values")

        scene_ids = []
        for plan in plans:
            if not isinstance(plan.scene_id, str) or not plan.scene_id.strip():
                raise ValueError("every scene plan must have a non-empty scene_id")
            scene_ids.append(plan.scene_id)
        if len(set(scene_ids)) != len(scene_ids):
            raise ValueError("scene_plans must not contain duplicate scene IDs")

        if not isinstance(self.contexts, Mapping):
            raise TypeError("contexts must be a mapping of scene IDs to SceneExecutionContext")
        copied_contexts = dict(self.contexts)
        if any(not isinstance(key, str) or not key.strip() for key in copied_contexts):
            raise ValueError("context keys must be non-empty scene ID strings")
        invalid_values = [
            key for key, value in copied_contexts.items()
            if not isinstance(value, SceneExecutionContext)
        ]
        if invalid_values:
            raise TypeError(
                "every context value must be a SceneExecutionContext "
                f"(invalid keys: {', '.join(invalid_values)})"
            )

        expected, supplied = set(scene_ids), set(copied_contexts)
        missing, unexpected = expected - supplied, supplied - expected
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing contexts: {', '.join(sorted(missing))}")
            if unexpected:
                details.append(f"unexpected contexts: {', '.join(sorted(unexpected))}")
            raise ValueError("; ".join(details))

        object.__setattr__(self, "scene_plans", plans)
        object.__setattr__(self, "contexts", MappingProxyType(copied_contexts))


@dataclass(frozen=True)
class MultiSceneExecutionResult:
    """Successful batch result, preserving caller-supplied scene order."""

    results: Tuple[SceneExecutionResult, ...]
    completed_count: int

    @property
    def scene_ids(self) -> Tuple[str, ...]:
        return tuple(result.scene_id for result in self.results)


class MultiSceneExecutionError(Exception):
    """Batch failure with the failed scene and fully completed prior scenes."""

    def __init__(
        self,
        failed_scene_id: str,
        failed_scene_index: int,
        completed_results: Tuple[SceneExecutionResult, ...],
    ) -> None:
        self.failed_scene_id = failed_scene_id
        self.failed_scene_index = failed_scene_index
        self.completed_results = tuple(completed_results)
        super().__init__(
            f"multi-scene execution failed at index {failed_scene_index} "
            f"for scene '{failed_scene_id}'"
        )


class MultiSceneExecutionCoordinator:
    """Execute a scene batch sequentially through the single-scene coordinator."""

    _FINAL_PROGRESS_CAP = 0.999999

    def __init__(self, scene_coordinator: SceneExecutionCoordinator) -> None:
        if not callable(getattr(scene_coordinator, "execute", None)):
            raise TypeError("scene_coordinator must provide execute()")
        self._scene_coordinator = scene_coordinator

    def execute(
        self,
        request: MultiSceneExecutionRequest,
        *,
        on_progress: ProgressCallback = None,
        cancel: Optional[CancelToken] = None,
    ) -> MultiSceneExecutionResult:
        if not isinstance(request, MultiSceneExecutionRequest):
            raise TypeError("request must be a MultiSceneExecutionRequest")
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable or None")

        total = len(request.scene_plans)
        completed = []
        progress_value = 0.0

        def emit(value: object) -> None:
            nonlocal progress_value
            if on_progress is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                return
            try:
                numeric = float(value)
            except (OverflowError, TypeError, ValueError):
                return
            if not math.isfinite(numeric):
                return
            numeric = min(1.0, max(progress_value, numeric))
            progress_value = numeric
            try:
                on_progress(numeric)
            except Exception:
                # Progress is observational and must not change batch outcome.
                pass

        for index, plan in enumerate(request.scene_plans):
            if cancel is not None:
                cancel.raise_if_cancelled()
            offset = index / total
            weight = 1.0 / total
            final_cap = self._FINAL_PROGRESS_CAP if index == total - 1 else (index + 1) / total

            def scene_progress(value: object, *, _offset=offset, _weight=weight, _cap=final_cap) -> None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return
                try:
                    numeric = float(value)
                except (OverflowError, TypeError, ValueError):
                    return
                if not math.isfinite(numeric):
                    return
                mapped = _offset + _weight * min(1.0, max(0.0, numeric))
                emit(min(_cap, mapped))

            try:
                result = self._scene_coordinator.execute(
                    plan,
                    request.contexts[plan.scene_id],
                    on_progress=scene_progress if on_progress is not None else None,
                    cancel=cancel,
                )
            except GenerationCancelled:
                raise
            except Exception as exc:
                raise MultiSceneExecutionError(
                    plan.scene_id, index, tuple(completed)
                ) from exc

            completed.append(result)
            # A completed scene advances the batch boundary even if an adapter
            # did not report its final progress callback.
            if index < total - 1:
                emit((index + 1) / total)

        if on_progress is not None:
            emit(1.0)
        results = tuple(completed)
        return MultiSceneExecutionResult(results, len(results))
