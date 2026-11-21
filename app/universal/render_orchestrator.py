"""Deterministic sequential execution for dependency-aware render stages.

This is the first VXP-09 orchestration foundation. It deliberately executes
one stage at a time, forwards the shared cancellation token, and reports
monotonic aggregate progress. Caching, retries, resource estimates and
parallel scheduling are intentionally not implied by this initial contract.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple


class _Cancellation(Protocol):
    def raise_if_cancelled(self, *args, **kwargs) -> None: ...


StageProgress = Callable[[float, str], None]
StageExecutor = Callable[
    [Any, Mapping[str, Any], Optional[_Cancellation], Optional[StageProgress]],
    Any,
]


class RenderGraphError(ValueError):
    """Raised when a render graph is malformed or cannot be ordered."""


@dataclass(frozen=True)
class RenderStage:
    """One deterministic stage in a render dependency graph."""

    stage_id: str
    execute: StageExecutor
    dependencies: Tuple[str, ...] = ()
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.stage_id, str) or not self.stage_id.strip():
            raise RenderGraphError("stage_id must be a non-empty string")
        if self.stage_id != self.stage_id.strip():
            raise RenderGraphError("stage_id must not contain surrounding whitespace")
        if not callable(self.execute):
            raise TypeError("stage execute must be callable")
        if isinstance(self.dependencies, (str, bytes)):
            raise RenderGraphError("dependencies must be an iterable of stage IDs")
        try:
            dependencies = tuple(self.dependencies)
        except TypeError:
            raise RenderGraphError("dependencies must be an iterable of stage IDs") from None
        if any(
            not isinstance(item, str) or not item.strip() or item == self.stage_id
            for item in dependencies
        ):
            raise RenderGraphError("dependencies must contain valid IDs other than the stage itself")
        if len(set(dependencies)) != len(dependencies):
            raise RenderGraphError("stage dependencies must not contain duplicates")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise RenderGraphError("stage weight must be a positive finite number")
        if not math.isfinite(float(self.weight)) or float(self.weight) <= 0:
            raise RenderGraphError("stage weight must be a positive finite number")
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "weight", float(self.weight))


@dataclass(frozen=True)
class RenderGraph:
    """Immutable graph whose topological order is stable across runs."""

    stages: Tuple[RenderStage, ...]

    def __post_init__(self) -> None:
        if isinstance(self.stages, (str, bytes)):
            raise RenderGraphError("stages must be an iterable of RenderStage values")
        try:
            stages = tuple(self.stages)
        except TypeError:
            raise RenderGraphError("stages must be an iterable of RenderStage values") from None
        if not stages:
            raise RenderGraphError("render graph must contain at least one stage")
        if any(not isinstance(stage, RenderStage) for stage in stages):
            raise TypeError("stages must contain only RenderStage values")
        ids = [stage.stage_id for stage in stages]
        if len(set(ids)) != len(ids):
            raise RenderGraphError("render graph stage IDs must be unique")
        known = set(ids)
        for stage in stages:
            missing = [item for item in stage.dependencies if item not in known]
            if missing:
                raise RenderGraphError(
                    f"stage '{stage.stage_id}' depends on unknown stage(s): {', '.join(missing)}"
                )
        object.__setattr__(self, "stages", stages)

    def ordered_stages(self) -> Tuple[RenderStage, ...]:
        """Return a stable topological ordering; preserve declaration order on ties."""
        by_id = {stage.stage_id: stage for stage in self.stages}
        completed: set[str] = set()
        ordered = []
        while len(ordered) < len(self.stages):
            ready = [
                stage for stage in self.stages
                if stage.stage_id not in completed
                and all(dependency in completed for dependency in stage.dependencies)
            ]
            if not ready:
                blocked = [
                    stage.stage_id for stage in self.stages
                    if stage.stage_id not in completed
                ]
                raise RenderGraphError(
                    "render graph contains a dependency cycle involving: " + ", ".join(blocked)
                )
            stage = ready[0]
            ordered.append(stage)
            completed.add(stage.stage_id)
        return tuple(ordered)


@dataclass(frozen=True)
class RenderOrchestratorResult:
    """Outputs from completed stages, in deterministic execution order."""

    stage_order: Tuple[str, ...]
    outputs: Mapping[str, Any]


class SequentialRenderOrchestrator:
    """Execute a render graph sequentially with cancellation and progress.

    No worker pool is created. Every stage sees read-only outputs from its
    dependencies and the same cancellation token supplied by the caller.
    Stage failures propagate unchanged; later stages are never started.
    """

    def run(
        self,
        graph: RenderGraph,
        context: Any,
        *,
        cancel: Optional[_Cancellation] = None,
        on_progress: Optional[StageProgress] = None,
    ) -> RenderOrchestratorResult:
        if not isinstance(graph, RenderGraph):
            raise TypeError("graph must be a RenderGraph")
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable or None")
        ordered = graph.ordered_stages()
        total_weight = sum(stage.weight for stage in ordered)
        completed_weight = 0.0
        outputs: dict[str, Any] = {}
        last_progress = 0.0

        def report(value: float, message: str) -> None:
            nonlocal last_progress
            if on_progress is None:
                return
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return
            numeric = float(value)
            if not math.isfinite(numeric):
                return
            numeric = min(1.0, max(last_progress, min(1.0, numeric)))
            last_progress = numeric
            try:
                on_progress(numeric, message)
            except Exception:
                # UI observers must not change production success or failure.
                pass

        for stage in ordered:
            if cancel is not None:
                cancel.raise_if_cancelled()
            stage_base = completed_weight / total_weight
            stage_weight = stage.weight / total_weight

            def stage_progress(fraction: float, message: str, *, _base=stage_base, _weight=stage_weight) -> None:
                if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
                    return
                numeric = float(fraction)
                if not math.isfinite(numeric):
                    return
                aggregate = _base + _weight * min(1.0, max(0.0, numeric))
                report(aggregate, message or stage.stage_id)

            report(stage_base, f"Starting: {stage.stage_id}")
            visible_outputs = MappingProxyType(dict(outputs))
            output = stage.execute(
                context,
                visible_outputs,
                cancel,
                stage_progress if on_progress is not None else None,
            )
            if cancel is not None:
                cancel.raise_if_cancelled()
            outputs[stage.stage_id] = output
            completed_weight += stage.weight
            report(completed_weight / total_weight, f"Completed: {stage.stage_id}")

        return RenderOrchestratorResult(
            stage_order=tuple(stage.stage_id for stage in ordered),
            outputs=MappingProxyType(dict(outputs)),
        )
