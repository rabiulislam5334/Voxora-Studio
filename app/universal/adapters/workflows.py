"""Workflow-level adapters that bind a named production workflow to an engine.

These adapters orchestrate the Universal render boundary; they do not claim to
generate artwork, animation, maps, or documentary assets themselves.
"""
from __future__ import annotations

from abc import ABC
from typing import Optional

from app.universal.engines import UnknownEngineError
from app.universal.requests import (
    CancellationToken,
    EngineRenderRequest,
    ProgressCallback,
    RawEngineOutput,
)
from app.universal.runtime import EngineRuntimeRegistry


class WorkflowAdapterError(RuntimeError):
    """Base error for workflow adapter validation and execution."""


class WorkflowAdapterCompatibilityError(WorkflowAdapterError):
    """Raised when the configured engine does not declare this workflow family."""


class EngineBackedWorkflowAdapter(ABC):
    """Delegate a workflow request to one explicitly selected compatible engine.

    The adapter never chooses an engine, mutates the request, or falls back.
    Engine compatibility is checked against the engine's declared workflow
    family at construction; runtime capability checks still occur at render.
    """

    workflow_id: str = ""

    def __init__(self, runtime: EngineRuntimeRegistry, engine_id: str) -> None:
        if not isinstance(runtime, EngineRuntimeRegistry):
            raise TypeError("runtime must be an EngineRuntimeRegistry")
        if not isinstance(engine_id, str) or not engine_id.strip():
            raise ValueError("engine_id must be a non-empty string")
        if not self.workflow_id:
            raise TypeError("concrete workflow adapters must declare workflow_id")
        try:
            descriptor = runtime.metadata.get(engine_id)
        except UnknownEngineError:
            raise
        if self.workflow_id not in descriptor.capabilities.workflow_families:
            raise WorkflowAdapterCompatibilityError(
                f"engine '{engine_id}' does not declare workflow family '{self.workflow_id}'"
            )
        self._runtime = runtime
        self.engine_id = engine_id
        self._descriptor = descriptor

    @property
    def descriptor(self):
        """Exact engine metadata this adapter was explicitly bound to."""
        return self._descriptor

    def render(
        self,
        request: EngineRenderRequest,
        *,
        on_progress: ProgressCallback = None,
        cancel: CancellationToken = None,
    ) -> RawEngineOutput:
        if not isinstance(request, EngineRenderRequest):
            raise TypeError("request must be an EngineRenderRequest")
        output = self._runtime.render(
            self.engine_id,
            request,
            on_progress=on_progress,
            cancel=cancel,
        )
        metadata = dict(output.metadata)
        metadata.update({
            "workflow_id": self.workflow_id,
            "workflow_engine_id": self.engine_id,
        })
        return RawEngineOutput(path=output.path, metadata=metadata)


class TwoDStorytellingAdapter(EngineBackedWorkflowAdapter):
    """2D storytelling workflow adapter; delegates rendering to a 2D-capable engine."""

    workflow_id = "2d"


class DocumentaryWorkflowAdapter(EngineBackedWorkflowAdapter):
    """Documentary workflow adapter; delegates rendering to a documentary-capable engine."""

    workflow_id = "documentary"
