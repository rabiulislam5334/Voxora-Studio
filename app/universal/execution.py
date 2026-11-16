"""Opt-in orchestration for one Universal ScenePlan execution.

This module composes plan resolution, the exact runtime adapter, and shared
segment normalization. It is intentionally not wired into the production
rendering pipeline.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

from app.core.exceptions import GenerationCancelled
from app.universal.normalizer import (
    NormalizedSegment,
    SegmentNormalizer,
    SegmentOutputSpec,
)
from app.universal.plan_resolver import (
    EnginePlanResolution,
    EnginePlanResolver,
    EnginePlanStatus,
)
from app.universal.requests import EngineRenderRequest, RawEngineOutput
from app.universal.runtime import EngineRuntimeRegistry
from app.universal.models import ScenePlan
from app.workers.cancel import CancelToken


ProgressCallback = Optional[Callable[[float], None]]


class SceneExecutionError(Exception):
    """Base error raised by the Universal scene execution coordinator."""


class SceneExecutionValidationError(SceneExecutionError):
    """Raised when explicit execution inputs cannot form a render request."""


class ScenePlanResolutionError(SceneExecutionError):
    """Raised when a scene plan is not explicitly and compatibly resolved."""

    def __init__(self, resolution: EnginePlanResolution) -> None:
        self.resolution = resolution
        detail = "; ".join(resolution.diagnostics) or resolution.status.value
        super().__init__(
            f"scene '{resolution.scene_id}' cannot execute "
            f"(plan status: {resolution.status.value}): {detail}"
        )


class SceneEngineExecutionError(SceneExecutionError):
    """Raised when the selected runtime adapter fails."""


class SceneNormalizationError(SceneExecutionError):
    """Raised when raw renderer output cannot be normalized."""


@dataclass(frozen=True)
class SceneExecutionContext:
    """Explicit render settings not inferred from project or channel defaults."""

    output_spec: SegmentOutputSpec
    destination: Path
    engine_params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.output_spec, SegmentOutputSpec):
            raise TypeError("output_spec must be a SegmentOutputSpec")
        if not isinstance(self.destination, (str, Path)) or not str(self.destination).strip():
            raise ValueError("destination must be a non-empty path")
        object.__setattr__(self, "destination", Path(self.destination))
        if not isinstance(self.engine_params, Mapping):
            raise TypeError("engine_params must be a mapping")
        if any(not isinstance(key, str) or not key.strip() for key in self.engine_params):
            raise ValueError("engine_params keys must be non-empty strings")
        object.__setattr__(
            self,
            "engine_params",
            MappingProxyType(copy.deepcopy(dict(self.engine_params))),
        )


@dataclass(frozen=True)
class SceneExecutionResult:
    """Successful execution details, including raw and normalized artifacts."""

    scene_id: str
    engine_id: str
    resolution: EnginePlanResolution
    raw_output: RawEngineOutput
    normalized: NormalizedSegment


class SceneExecutionCoordinator:
    """Execute one explicitly selected engine and normalize its raw output."""

    _RENDER_PROGRESS_WEIGHT = 0.8
    _NORMALIZE_PROGRESS_WEIGHT = 0.2
    _PROGRESS_BEFORE_SUCCESS = 0.999999

    def __init__(
        self,
        resolver: EnginePlanResolver,
        runtime: EngineRuntimeRegistry,
        normalizer: SegmentNormalizer,
    ) -> None:
        if not isinstance(resolver, EnginePlanResolver):
            raise TypeError("resolver must be an EnginePlanResolver")
        if not isinstance(runtime, EngineRuntimeRegistry):
            raise TypeError("runtime must be an EngineRuntimeRegistry")
        if not callable(getattr(normalizer, "normalize", None)):
            raise TypeError("normalizer must provide normalize()")
        self._resolver = resolver
        self._runtime = runtime
        self._normalizer = normalizer

    def execute(
        self,
        plan: ScenePlan,
        context: SceneExecutionContext,
        *,
        on_progress: ProgressCallback = None,
        cancel: Optional[CancelToken] = None,
    ) -> SceneExecutionResult:
        """Render and normalize one scene, forwarding cancellation unchanged.

        Progress is monotonic in [0, 1]. Rendering occupies [0, 0.8],
        normalization occupies [0.8, 0.999999], and 1.0 is emitted only after
        normalization returns successfully. Invalid progress values and
        exceptions raised by the observer are ignored.
        """
        if not isinstance(plan, ScenePlan):
            raise TypeError("plan must be a ScenePlan")
        if not isinstance(context, SceneExecutionContext):
            raise TypeError("context must be a SceneExecutionContext")
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable or None")

        # Resolve before touching the runtime registry: lazy adapter factories
        # must not initialize for invalid, ambiguous, or unselected plans.
        resolution = self._resolver.resolve(plan)
        if (
            resolution.status is not EnginePlanStatus.COMPATIBLE
            or resolution.selected_descriptor is None
        ):
            raise ScenePlanResolutionError(resolution)

        choice = plan.engine_choice
        engine_id = getattr(choice, "engine_id", None)
        if not isinstance(engine_id, str) or not engine_id.strip():
            raise SceneExecutionValidationError(
                "a compatible resolution must contain an explicit engine selection"
            )

        output_format = plan.requirements.get("output_format")
        if not isinstance(output_format, str) or not output_format.strip():
            raise SceneExecutionValidationError(
                "scene plan requires an explicit non-empty requirements.output_format"
            )

        try:
            request = EngineRenderRequest(
                scene_id=plan.scene_id,
                scene_kind=plan.kind,
                output_format=output_format,
                output_spec=context.output_spec,
                destination=context.destination,
                style_tags=tuple(plan.style_tags),
                asset_refs=tuple(plan.asset_refs),
                engine_params=context.engine_params,
            )
        except (TypeError, ValueError) as exc:
            raise SceneExecutionValidationError(
                f"could not build render request for scene '{plan.scene_id}': {exc}"
            ) from exc

        progress_state = {"value": 0.0}

        def report(value: Any, *, offset: float, weight: float, final_cap: float) -> None:
            if on_progress is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                return
            try:
                numeric = float(value)
            except (OverflowError, TypeError, ValueError):
                return
            if not math.isfinite(numeric):
                return
            mapped = offset + weight * min(1.0, max(0.0, numeric))
            mapped = min(final_cap, max(progress_state["value"], mapped))
            progress_state["value"] = mapped
            try:
                on_progress(mapped)
            except Exception:
                # Progress is observational; a broken UI callback must not
                # alter the render or normalization outcome.
                pass

        def render_progress(value: Any) -> None:
            report(
                value,
                offset=0.0,
                weight=self._RENDER_PROGRESS_WEIGHT,
                final_cap=self._RENDER_PROGRESS_WEIGHT,
            )

        def normalize_progress(value: Any) -> None:
            report(
                value,
                offset=self._RENDER_PROGRESS_WEIGHT,
                weight=self._NORMALIZE_PROGRESS_WEIGHT,
                final_cap=self._PROGRESS_BEFORE_SUCCESS,
            )

        try:
            raw_output = self._runtime.render(
                engine_id,
                request,
                on_progress=render_progress if on_progress is not None else None,
                cancel=cancel,
            )
        except GenerationCancelled:
            raise
        except Exception as exc:
            raise SceneEngineExecutionError(
                f"engine '{engine_id}' failed while rendering scene '{plan.scene_id}': {exc}"
            ) from exc

        if not isinstance(raw_output, RawEngineOutput):
            raise SceneEngineExecutionError(
                f"engine '{engine_id}' returned an invalid raw output contract"
            )

        try:
            normalized = self._normalizer.normalize(
                raw_output.path,
                context.destination,
                context.output_spec,
                on_progress=normalize_progress if on_progress is not None else None,
                cancel=cancel,
            )
        except GenerationCancelled:
            raise
        except Exception as exc:
            raise SceneNormalizationError(
                f"normalization failed for scene '{plan.scene_id}': {exc}"
            ) from exc

        if not isinstance(normalized, NormalizedSegment):
            raise SceneNormalizationError(
                "normalizer must return a verified NormalizedSegment"
            )

        if on_progress is not None:
            progress_state["value"] = 1.0
            try:
                on_progress(1.0)
            except Exception:
                pass

        return SceneExecutionResult(
            scene_id=plan.scene_id,
            engine_id=engine_id,
            resolution=resolution,
            raw_output=raw_output,
            normalized=normalized,
        )
