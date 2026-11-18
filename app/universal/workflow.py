"""Reusable, metadata-only workflow families for Universal Core.

Workflow families describe production intent (2D, 2.5D, maps, etc.). They are
not channel-specific and do not create or execute rendering engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Protocol, Tuple

from app.universal.engines import (
    EngineDescriptor,
    EngineRegistry,
    EngineUnavailableError,
    UnknownEngineError,
)
from app.universal.requests import (
    CancellationToken,
    EngineRenderRequest,
    ProgressCallback,
    RawEngineOutput,
)


class WorkflowFamily(str, Enum):
    TWO_D = "2d"
    TWO_POINT_FIVE_D = "2.5d"
    THREE_D_FOUR_D = "3d_4d"
    REAL_MAP = "real_map"
    DOCUMENTARY = "documentary"
    CHARACTER_PERFORMANCE = "character_performance"
    SKETCH_ILLUSTRATION = "sketch_illustration"
    STICKMAN = "stickman"


@dataclass(frozen=True)
class WorkflowDescriptor:
    """Stable declaration for one reusable production workflow family."""

    workflow_id: str
    display_name: str
    description: str
    family: WorkflowFamily
    default_scene_kinds: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("workflow_id", "display_name", "description"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.workflow_id != self.workflow_id.strip() or any(
            char.isspace() for char in self.workflow_id
        ):
            raise ValueError("workflow_id must not contain whitespace")
        if not isinstance(self.family, WorkflowFamily):
            raise TypeError("family must be a WorkflowFamily")
        values = _normalise_strings("default_scene_kinds", self.default_scene_kinds)
        object.__setattr__(self, "default_scene_kinds", values)


def _normalise_strings(name: str, values: Iterable[str]) -> Tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be an iterable of strings, not a string")
    try:
        result = tuple(values)
    except TypeError:
        raise ValueError(f"{name} must be an iterable of strings") from None
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError(f"{name} must contain only non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


class WorkflowRegistry:
    """Deterministic metadata catalog; it never imports or initializes adapters."""

    def __init__(self, descriptors: Iterable[WorkflowDescriptor] = ()) -> None:
        self._workflows = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: WorkflowDescriptor, *, replace: bool = False) -> None:
        if not isinstance(descriptor, WorkflowDescriptor):
            raise TypeError("descriptor must be a WorkflowDescriptor")
        if descriptor.workflow_id in self._workflows and not replace:
            raise ValueError(f"workflow already registered: {descriptor.workflow_id}")
        self._workflows[descriptor.workflow_id] = descriptor

    def get(self, workflow_id: str) -> WorkflowDescriptor:
        try:
            return self._workflows[workflow_id]
        except KeyError:
            raise UnknownWorkflowError(f"unknown workflow: {workflow_id}") from None

    def list_workflows(self) -> Tuple[WorkflowDescriptor, ...]:
        return tuple(self._workflows[key] for key in sorted(self._workflows))


class UnknownWorkflowError(LookupError):
    """Raised when a workflow family is not present in the catalog."""


class WorkflowAdapter(Protocol):
    """Optional family-specific adapter using the Universal render boundary."""

    @property
    def workflow_id(self) -> str: ...

    def render(
        self,
        request: EngineRenderRequest,
        *,
        on_progress: ProgressCallback = None,
        cancel: CancellationToken = None,
    ) -> RawEngineOutput: ...


class WorkflowResolutionStatus(str, Enum):
    SELECTION_REQUIRED = "selection_required"
    COMPATIBLE = "compatible"
    UNKNOWN_WORKFLOW = "unknown_workflow"
    UNKNOWN_ENGINE = "unknown_engine"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    ENGINE_INCOMPATIBLE = "engine_incompatible"


@dataclass(frozen=True)
class WorkflowResolution:
    workflow_id: str
    status: WorkflowResolutionStatus
    selected_engine_id: Optional[str] = None
    selected_descriptor: Optional[EngineDescriptor] = None
    compatible_candidates: Tuple[EngineDescriptor, ...] = ()
    diagnostics: Tuple[str, ...] = ()


class WorkflowResolver:
    """Resolve workflow family requirements without selecting or substituting engines."""

    def __init__(self, workflows: WorkflowRegistry, engines: EngineRegistry) -> None:
        if not isinstance(workflows, WorkflowRegistry):
            raise TypeError("workflows must be a WorkflowRegistry")
        if not isinstance(engines, EngineRegistry):
            raise TypeError("engines must be an EngineRegistry")
        self._workflows = workflows
        self._engines = engines

    def resolve(
        self,
        workflow_id: str,
        *,
        selected_engine_id: Optional[str] = None,
        scene_kind: Optional[str] = None,
        style_tags: Iterable[str] = (),
        asset_kinds: Iterable[str] = (),
        output_format: Optional[str] = None,
    ) -> WorkflowResolution:
        try:
            workflow = self._workflows.get(workflow_id)
        except UnknownWorkflowError as exc:
            return WorkflowResolution(
                workflow_id=str(workflow_id),
                status=WorkflowResolutionStatus.UNKNOWN_WORKFLOW,
                selected_engine_id=selected_engine_id,
                diagnostics=(str(exc),),
            )

        if scene_kind is None and len(workflow.default_scene_kinds) == 1:
            scene_kind = workflow.default_scene_kinds[0]
        try:
            styles = _normalise_strings("style_tags", style_tags)
            assets = _normalise_strings("asset_kinds", asset_kinds)
            candidates = tuple(
                item for item in self._engines.list_engines()
                if workflow.family.value in item.capabilities.workflow_families
                and (scene_kind is None or scene_kind in item.capabilities.scene_kinds)
                and set(styles).issubset(item.capabilities.style_tags)
                and set(assets).issubset(item.capabilities.asset_kinds)
                and (output_format is None or output_format in item.capabilities.output_formats)
            )
        except (TypeError, ValueError) as exc:
            return WorkflowResolution(
                workflow_id=workflow_id,
                status=WorkflowResolutionStatus.ENGINE_INCOMPATIBLE,
                selected_engine_id=selected_engine_id,
                diagnostics=(f"Invalid workflow requirements: {exc}",),
            )

        if selected_engine_id is None:
            return WorkflowResolution(
                workflow_id=workflow_id,
                status=WorkflowResolutionStatus.SELECTION_REQUIRED,
                compatible_candidates=candidates,
                diagnostics=("No engine is selected; choose one explicitly to continue.",),
            )
        if not isinstance(selected_engine_id, str) or not selected_engine_id.strip():
            return WorkflowResolution(
                workflow_id=workflow_id,
                status=WorkflowResolutionStatus.ENGINE_INCOMPATIBLE,
                diagnostics=("selected_engine_id must be a non-empty string.",),
            )
        try:
            descriptor = self._engines.get(selected_engine_id)
        except UnknownEngineError as exc:
            status = WorkflowResolutionStatus.UNKNOWN_ENGINE
            return WorkflowResolution(workflow_id, status, selected_engine_id,
                                      compatible_candidates=candidates, diagnostics=(str(exc),))
        if not descriptor.available:
            return WorkflowResolution(
                workflow_id, WorkflowResolutionStatus.ENGINE_UNAVAILABLE, selected_engine_id,
                compatible_candidates=candidates,
                diagnostics=(descriptor.unavailable_reason or "Selected engine is unavailable.",),
            )
        if descriptor not in candidates:
            return WorkflowResolution(
                workflow_id, WorkflowResolutionStatus.ENGINE_INCOMPATIBLE, selected_engine_id,
                compatible_candidates=candidates,
                diagnostics=(f"Engine '{selected_engine_id}' does not declare workflow family "
                             f"'{workflow.family.value}' and all requested capabilities.",),
            )
        return WorkflowResolution(
            workflow_id, WorkflowResolutionStatus.COMPATIBLE, selected_engine_id,
            selected_descriptor=descriptor, compatible_candidates=candidates,
        )


BUILTIN_WORKFLOW_DESCRIPTORS = (
    WorkflowDescriptor("2d_storytelling", "2D Storytelling",
                       "Scene-based 2D illustration and cartoon storytelling.",
                       WorkflowFamily.TWO_D, ("illustration", "cartoon")),
    WorkflowDescriptor("2_5d_motion", "2.5D Motion",
                       "Layered illustration, parallax, and camera-driven motion.",
                       WorkflowFamily.TWO_POINT_FIVE_D, ("motion_graphics", "illustration")),
    WorkflowDescriptor("3d_4d_visualization", "3D/4D Visualization",
                       "Spatial, scientific, and time-based 3D/4D visualization.",
                       WorkflowFamily.THREE_D_FOUR_D, ("visualization", "simulation")),
    WorkflowDescriptor("real_map", "Real Map Visualization",
                       "Geographically grounded maps and location-aware visual storytelling.",
                       WorkflowFamily.REAL_MAP, ("map", "geography")),
    WorkflowDescriptor("documentary", "Documentary",
                       "Evidence-led documentary scenes, timelines, and visual explanations.",
                       WorkflowFamily.DOCUMENTARY, ("documentary", "explainer")),
    WorkflowDescriptor("character_performance", "Character Performance",
                       "Reusable character expression, gesture, movement, and lip-sync workflows.",
                       WorkflowFamily.CHARACTER_PERFORMANCE, ("character", "performance")),
    WorkflowDescriptor("sketch_illustration", "Sketch & Illustration",
                       "Hand-drawn, sketch, and editorial illustration workflows.",
                       WorkflowFamily.SKETCH_ILLUSTRATION, ("illustration", "sketch")),
    WorkflowDescriptor("stickman", "Stickman Explainer",
                       "Minimal character-led educational and explanatory animation.",
                       WorkflowFamily.STICKMAN, ("stickman", "explainer")),
)

BUILTIN_WORKFLOW_REGISTRY = WorkflowRegistry(BUILTIN_WORKFLOW_DESCRIPTORS)
