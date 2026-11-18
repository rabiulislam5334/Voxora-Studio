"""Opt-in execution bridge from an applied storyboard to workflow adapters.

This module prepares runtime-only ScenePlans and delegates sequential execution
to the existing Universal scene coordinator. It never generates visual assets.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.models.project import Project
from app.universal.adapters.workflows import EngineBackedWorkflowAdapter
from app.universal.engines import EngineDescriptor, EngineRegistry
from app.universal.execution import SceneExecutionContext, SceneExecutionCoordinator
from app.universal.models import EngineChoice, ScenePlan, UniversalState
from app.universal.multi_execution import (
    MultiSceneExecutionCoordinator,
    MultiSceneExecutionRequest,
    MultiSceneExecutionResult,
)
from app.universal.normalizer import SegmentNormalizer, SegmentOutputSpec
from app.universal.plan_resolver import EnginePlanResolver
from app.universal.runtime import EngineRuntimeRegistry
from app.universal.storyboard import (
    NarrationSource,
    ProposalReviewStatus,
    StoryboardProposal,
    StoryboardValidationError,
)
from app.universal.storyboard_apply import (
    StoryboardApplyPreview,
    preview_storyboard_apply,
)
from app.universal.workflow import (
    BUILTIN_WORKFLOW_REGISTRY,
    WorkflowRegistry,
    UnknownWorkflowError,
    WorkflowResolutionStatus,
    WorkflowResolver,
)
from app.workers.cancel import CancelToken


class StoryboardExecutionError(RuntimeError):
    """Base error for opt-in storyboard execution."""


class StoryboardExecutionApprovalError(StoryboardExecutionError):
    """Raised when execution was not explicitly approved."""


class StoryboardExecutionReadinessError(StoryboardExecutionError):
    """Raised when the applied storyboard or selected workflow is not ready."""


class _WorkflowRuntimeBridge:
    """Present one explicit workflow adapter as the exact selected engine."""

    def __init__(self, descriptor: EngineDescriptor, adapter) -> None:
        self.descriptor = descriptor
        self._adapter = adapter

    def render(self, request, *, on_progress=None, cancel=None):
        return self._adapter.render(
            request, on_progress=on_progress, cancel=cancel
        )


class StoryboardWorkflowExecutionCoordinator:
    """Execute an already-applied storyboard through one explicitly chosen adapter.

    A fresh runtime registry is built around the supplied workflow adapter so
    the existing SceneExecutionCoordinator and normalizer remain authoritative.
    The selected adapter is never replaced or automatically initialized here.
    """

    def __init__(
        self,
        *,
        workflow_registry: WorkflowRegistry = BUILTIN_WORKFLOW_REGISTRY,
        normalizer: SegmentNormalizer,
    ) -> None:
        if not isinstance(workflow_registry, WorkflowRegistry):
            raise TypeError("workflow_registry must be a WorkflowRegistry")
        if not callable(getattr(normalizer, "normalize", None)):
            raise TypeError("normalizer must provide normalize()")
        self._workflows = workflow_registry
        self._normalizer = normalizer

    def execute(
        self,
        project,
        proposal: StoryboardProposal,
        source: NarrationSource,
        preview: StoryboardApplyPreview,
        *,
        approved: bool = False,
        workflow_id: str,
        selected_engine_id: str,
        engine_descriptor: EngineDescriptor,
        workflow_adapter: EngineBackedWorkflowAdapter,
        scene_kind: str,
        style_tags: Sequence[str],
        output_format: str,
        output_directory: str | Path,
        width: int,
        height: int,
        fps: int,
        engine_params: Optional[dict] = None,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[CancelToken] = None,
    ) -> MultiSceneExecutionResult:
        """Execute storyboard scenes sequentially; rendering starts only here."""
        if approved is not True:
            raise StoryboardExecutionApprovalError(
                "explicit execution approval is required"
            )
        if not isinstance(proposal, StoryboardProposal):
            raise TypeError("proposal must be a StoryboardProposal")
        if not isinstance(source, NarrationSource):
            raise TypeError("source must be a NarrationSource")
        if not isinstance(preview, StoryboardApplyPreview):
            raise TypeError("preview must be a StoryboardApplyPreview")
        if not preview.is_valid:
            raise StoryboardExecutionReadinessError(
                "storyboard preview contains blocking diagnostics"
            )
        if proposal.review_status is not ProposalReviewStatus.NEEDS_REVIEW:
            raise StoryboardExecutionReadinessError(
                "proposal must retain its reviewed needs_review state"
            )
        try:
            proposal.validate_against(source)
        except StoryboardValidationError as exc:
            raise StoryboardExecutionReadinessError(
                f"storyboard source validation failed: {exc}"
            ) from exc
        if (
            preview.proposal_id != proposal.proposal_id
            or preview.source_id != proposal.source_id
            or preview.source_fingerprint != proposal.source_fingerprint
            or preview.project_id != getattr(project, "id", None)
        ):
            raise StoryboardExecutionReadinessError(
                "preview does not belong to the supplied storyboard proposal"
            )
        if not isinstance(project, Project) or not isinstance(project.settings, dict):
            raise TypeError("project must be a valid Project")

        regenerated_preview = preview_storyboard_apply(project, proposal, source)
        if regenerated_preview.scenes != preview.scenes:
            raise StoryboardExecutionReadinessError(
                "preview scene content does not match the applied proposal"
            )

        state = UniversalState.from_project_settings(project.settings)
        if state.read_only:
            raise StoryboardExecutionReadinessError(
                "Universal project data is read-only; execution is blocked"
            )
        applied_ids = state.extra.get("storyboard_applied_proposal_ids", [])
        if not isinstance(applied_ids, list) or proposal.proposal_id not in applied_ids:
            raise StoryboardExecutionReadinessError(
                "storyboard proposal must be explicitly applied to this Project first"
            )
        if len(preview.scenes) != len(proposal.beats) or not preview.scenes:
            raise StoryboardExecutionReadinessError(
                "preview scene count does not match the non-empty storyboard"
            )

        try:
            workflow = self._workflows.get(workflow_id)
        except UnknownWorkflowError as exc:
            raise StoryboardExecutionReadinessError(
                f"unknown workflow: {workflow_id}"
            ) from exc
        if not isinstance(engine_descriptor, EngineDescriptor):
            raise TypeError("engine_descriptor must be an EngineDescriptor")
        if not engine_descriptor.available:
            raise StoryboardExecutionReadinessError(
                engine_descriptor.unavailable_reason or "selected engine is unavailable"
            )
        if not isinstance(selected_engine_id, str) or not selected_engine_id.strip():
            raise ValueError("selected_engine_id must be a non-empty string")
        if engine_descriptor.engine_id != selected_engine_id:
            raise StoryboardExecutionReadinessError(
                "engine descriptor does not match the explicitly selected engine ID"
            )
        if not isinstance(workflow_adapter, EngineBackedWorkflowAdapter):
            raise TypeError("workflow_adapter must be an EngineBackedWorkflowAdapter")
        if workflow_adapter.descriptor != engine_descriptor:
            raise StoryboardExecutionReadinessError(
                "workflow adapter descriptor does not match the supplied engine descriptor"
            )
        if workflow_adapter.engine_id != selected_engine_id:
            raise StoryboardExecutionReadinessError(
                "workflow adapter is bound to a different engine than the explicit selection"
            )
        if workflow_adapter.workflow_id != workflow.family.value:
            raise StoryboardExecutionReadinessError(
                "workflow adapter family does not match the selected workflow"
            )
        if not isinstance(scene_kind, str) or not scene_kind.strip():
            raise ValueError("scene_kind must be a non-empty string")
        if not isinstance(output_format, str) or not output_format.strip():
            raise ValueError("output_format must be a non-empty string")
        if isinstance(style_tags, (str, bytes)):
            raise ValueError("style_tags must be a sequence of strings")
        styles = tuple(style_tags)
        if any(not isinstance(item, str) or not item.strip() for item in styles):
            raise ValueError("style_tags must contain non-empty strings")
        if len(set(styles)) != len(styles):
            raise ValueError("style_tags must not contain duplicates")

        resolver = WorkflowResolver(
            self._workflows, EngineRegistry((engine_descriptor,))
        )
        workflow_resolution = resolver.resolve(
            workflow_id,
            selected_engine_id=selected_engine_id,
            scene_kind=scene_kind,
            style_tags=styles,
            output_format=output_format,
        )
        if workflow_resolution.status is not WorkflowResolutionStatus.COMPATIBLE:
            detail = "; ".join(workflow_resolution.diagnostics) or workflow_resolution.status.value
            raise StoryboardExecutionReadinessError(
                f"selected workflow/engine is not compatible: {detail}"
            )

        destination_root = Path(output_directory)
        if not str(destination_root).strip():
            raise ValueError("output_directory must be a non-empty path")
        if isinstance(width, bool) or not isinstance(width, int) or width < 2 or width % 2:
            raise ValueError("width must be a positive even integer")
        if isinstance(height, bool) or not isinstance(height, int) or height < 2 or height % 2:
            raise ValueError("height must be a positive even integer")
        if isinstance(fps, bool) or not isinstance(fps, int) or fps < 1:
            raise ValueError("fps must be a positive integer")
        if engine_params is not None and not isinstance(engine_params, dict):
            raise TypeError("engine_params must be a dict")

        runtime = EngineRuntimeRegistry(EngineRegistry((engine_descriptor,)))
        runtime.register(
            engine_descriptor,
            _WorkflowRuntimeBridge(engine_descriptor, workflow_adapter),
        )
        scene_coordinator = SceneExecutionCoordinator(
            EnginePlanResolver(runtime.metadata), runtime, self._normalizer
        )
        batch = MultiSceneExecutionCoordinator(scene_coordinator)

        plans = []
        contexts = {}
        destinations = [
            destination_root / f"{item.scene_id}.mp4" for item in preview.scenes
        ]
        existing_outputs = [str(path) for path in destinations if path.exists()]
        if existing_outputs:
            raise StoryboardExecutionReadinessError(
                "execution would overwrite existing output files: "
                + ", ".join(existing_outputs)
            )
        for item, beat in zip(preview.scenes, proposal.beats):
            scene = project.get_scene(item.scene_id)
            persisted = state.scene_plans.get(item.scene_id)
            if scene is None or persisted is None:
                raise StoryboardExecutionReadinessError(
                    f"applied storyboard scene or ScenePlan is missing: {item.scene_id}"
                )
            storyboard_metadata = persisted.requirements.get("storyboard")
            if (
                scene.title != item.title
                or scene.text != item.narration_text
                or scene.visual_prompt != item.visual_prompt
                or scene.notes != item.notes
                or persisted.plan_status != "approved"
                or not isinstance(storyboard_metadata, dict)
                or storyboard_metadata.get("proposal_id") != proposal.proposal_id
                or storyboard_metadata.get("beat_id") != beat.beat_id
                or storyboard_metadata.get("narration_unit_ids") != list(beat.narration_unit_ids)
                or storyboard_metadata.get("continuity_reference_ids") != list(beat.continuity_reference_ids)
                or storyboard_metadata.get("timing") != {
                    "start_ms": beat.timing.start_ms,
                    "end_ms": beat.timing.end_ms,
                    "basis": beat.timing.basis.value,
                }
            ):
                raise StoryboardExecutionReadinessError(
                    f"applied storyboard scene changed after review: {item.scene_id}"
                )
            plan = copy.deepcopy(persisted)
            plan.kind = scene_kind
            plan.style_tags = list(styles)
            plan.requirements = {"output_format": output_format}
            plan.engine_choice = EngineChoice(
                engine_id=selected_engine_id,
                fallback_chain=[],
                reason="Explicit user selection for storyboard execution",
                chosen_by="user",
            )
            plan.plan_status = "approved"
            plans.append(plan)
            destination = destination_root / f"{item.scene_id}.mp4"
            contexts[item.scene_id] = SceneExecutionContext(
                output_spec=SegmentOutputSpec(
                    duration_s=(item.end_ms - item.start_ms) / 1000.0,
                    width=width,
                    height=height,
                    fps=fps,
                ),
                destination=destination,
                engine_params=engine_params or {},
            )

        request = MultiSceneExecutionRequest(tuple(plans), contexts)
        return batch.execute(request, on_progress=on_progress, cancel=cancel)
