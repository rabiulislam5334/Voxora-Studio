"""Structured engine capability and advisory resource resolution.

This layer inspects declared metadata only. It never probes hardware, starts
engines, schedules work, changes an engine choice, or enables concurrency.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from app.universal.engines import (
    EngineCompatibilityError,
    EngineDescriptor,
    EngineRegistry,
    EngineUnavailableError,
    UnknownEngineError,
)


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class EngineDiagnostic:
    """Stable, UI-friendly diagnostic emitted by capability/resource inspection."""

    code: str
    severity: DiagnosticSeverity
    message: str
    engine_id: Optional[str] = None
    requirement: Optional[str] = None
    requested: Optional[str] = None
    supported: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineResourceContext:
    """Optional caller-supplied resource facts; no machine probing is performed."""

    available_memory_mb: Optional[int] = None
    gpu_available: Optional[bool] = None
    requested_concurrency: int = 1

    def __post_init__(self) -> None:
        if self.available_memory_mb is not None and (
            isinstance(self.available_memory_mb, bool)
            or not isinstance(self.available_memory_mb, int)
            or self.available_memory_mb < 1
        ):
            raise ValueError("available_memory_mb must be a positive integer or null")
        if self.gpu_available is not None and not isinstance(self.gpu_available, bool):
            raise ValueError("gpu_available must be a boolean or null")
        if (
            isinstance(self.requested_concurrency, bool)
            or not isinstance(self.requested_concurrency, int)
            or self.requested_concurrency < 1
        ):
            raise ValueError("requested_concurrency must be a positive integer")


@dataclass(frozen=True)
class EngineResourceAssessment:
    """Advisory comparison of declared engine estimates with supplied context."""

    status: str
    estimated_memory_mb: Optional[int]
    available_memory_mb: Optional[int]
    requires_gpu: bool
    gpu_available: Optional[bool]
    requested_concurrency: int
    max_concurrent_jobs: Optional[int]
    diagnostics: Tuple[EngineDiagnostic, ...] = ()


@dataclass(frozen=True)
class EngineCapabilityResolution:
    """Exact selection inspection plus alternatives; never chooses an engine."""

    requested_engine_id: Optional[str]
    status: str
    selected_descriptor: Optional[EngineDescriptor] = None
    compatible_candidates: Tuple[EngineDescriptor, ...] = ()
    resource_assessment: Optional[EngineResourceAssessment] = None
    diagnostics: Tuple[EngineDiagnostic, ...] = ()


class EngineCapabilityResolver:
    """Resolve declared capabilities for one exact engine ID without fallback."""

    def __init__(self, registry: EngineRegistry) -> None:
        if not isinstance(registry, EngineRegistry):
            raise TypeError("registry must be an EngineRegistry")
        self._registry = registry

    def resolve(
        self,
        engine_id: Optional[str],
        *,
        scene_kind: Optional[str] = None,
        style_tags=(),
        asset_kinds=(),
        output_format: Optional[str] = None,
        resource_context: Optional[EngineResourceContext] = None,
    ) -> EngineCapabilityResolution:
        if resource_context is not None and not isinstance(
            resource_context, EngineResourceContext
        ):
            raise TypeError("resource_context must be an EngineResourceContext or null")
        try:
            query = {
                "scene_kind": scene_kind,
                "style_tags": style_tags if isinstance(style_tags, (str, bytes)) else tuple(style_tags),
                "asset_kinds": asset_kinds if isinstance(asset_kinds, (str, bytes)) else tuple(asset_kinds),
                "output_format": output_format,
            }
            candidates = self._registry.find_compatible(**query)
        except (TypeError, ValueError) as exc:
            return EngineCapabilityResolution(
                requested_engine_id=engine_id if isinstance(engine_id, str) else None,
                status="invalid_request",
                diagnostics=(EngineDiagnostic(
                    code="engine.invalid_requirements",
                    severity=DiagnosticSeverity.ERROR,
                    message=f"Invalid capability requirements: {exc}",
                ),),
            )

        if engine_id is None:
            return EngineCapabilityResolution(
                requested_engine_id=None,
                status="selection_required",
                compatible_candidates=candidates,
                diagnostics=(EngineDiagnostic(
                    code="engine.selection_required",
                    severity=DiagnosticSeverity.INFO,
                    message="No engine is selected; choose one of the compatible candidates.",
                ),),
            )
        if not isinstance(engine_id, str) or not engine_id.strip():
            return EngineCapabilityResolution(
                requested_engine_id=None,
                status="invalid_request",
                compatible_candidates=candidates,
                diagnostics=(EngineDiagnostic(
                    code="engine.invalid_id",
                    severity=DiagnosticSeverity.ERROR,
                    message="engine_id must be a non-empty string or null.",
                ),),
            )

        try:
            descriptor = self._registry.resolve(engine_id, **query)
        except UnknownEngineError as exc:
            return EngineCapabilityResolution(
                requested_engine_id=engine_id,
                status="unknown_engine",
                compatible_candidates=candidates,
                diagnostics=(EngineDiagnostic(
                    code="engine.unknown",
                    severity=DiagnosticSeverity.ERROR,
                    message=str(exc),
                    engine_id=engine_id,
                ),),
            )
        except EngineUnavailableError as exc:
            try:
                unavailable = self._registry.get(engine_id)
            except UnknownEngineError:
                unavailable = None
            resource = self._assess_resources(unavailable, resource_context) if unavailable else None
            return EngineCapabilityResolution(
                requested_engine_id=engine_id,
                status="unavailable",
                compatible_candidates=candidates,
                resource_assessment=resource,
                diagnostics=(EngineDiagnostic(
                    code="engine.unavailable",
                    severity=DiagnosticSeverity.ERROR,
                    message=str(exc),
                    engine_id=engine_id,
                ),),
            )
        except EngineCompatibilityError as exc:
            descriptor = self._registry.get(engine_id)
            diagnostics = self._compatibility_diagnostics(
                descriptor, scene_kind, style_tags, asset_kinds, output_format, str(exc)
            )
            resource = self._assess_resources(descriptor, resource_context)
            return EngineCapabilityResolution(
                requested_engine_id=engine_id,
                status="incompatible",
                compatible_candidates=candidates,
                resource_assessment=resource,
                diagnostics=diagnostics,
            )

        resource = self._assess_resources(descriptor, resource_context)
        diagnostics = (EngineDiagnostic(
            code="engine.compatible",
            severity=DiagnosticSeverity.INFO,
            message="The explicitly requested engine declares all requested capabilities.",
            engine_id=engine_id,
        ),)
        return EngineCapabilityResolution(
            requested_engine_id=engine_id,
            status="compatible",
            selected_descriptor=descriptor,
            compatible_candidates=candidates,
            resource_assessment=resource,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _compatibility_diagnostics(
        descriptor, scene_kind, style_tags, asset_kinds, output_format, fallback_message
    ):
        caps = descriptor.capabilities
        issues = []
        if scene_kind is not None and scene_kind not in caps.scene_kinds:
            issues.append(("scene_kind", scene_kind, caps.scene_kinds))
        for tag in style_tags:
            if tag not in caps.style_tags:
                issues.append(("style_tag", tag, caps.style_tags))
        for kind in asset_kinds:
            if kind not in caps.asset_kinds:
                issues.append(("asset_kind", kind, caps.asset_kinds))
        if output_format is not None and output_format not in caps.output_formats:
            issues.append(("output_format", output_format, caps.output_formats))
        if not issues:
            return (EngineDiagnostic(
                code="engine.incompatible",
                severity=DiagnosticSeverity.ERROR,
                message=fallback_message,
                engine_id=descriptor.engine_id,
                requirement="capabilities",
            ),)
        return tuple(EngineDiagnostic(
            code="engine.capability_missing",
            severity=DiagnosticSeverity.ERROR,
            message=f"Engine '{descriptor.engine_id}' does not declare support for {name}: {value}.",
            engine_id=descriptor.engine_id,
            requirement=name,
            requested=value,
            supported=tuple(supported),
        ) for name, value, supported in issues)

    @staticmethod
    def _assess_resources(descriptor, context):
        if descriptor is None:
            return None
        caps = descriptor.capabilities
        memory = context.available_memory_mb if context else None
        gpu = context.gpu_available if context else None
        concurrency = context.requested_concurrency if context else 1
        diagnostics = []

        if caps.requires_gpu:
            if gpu is False:
                diagnostics.append(EngineDiagnostic(
                    code="resource.gpu_unavailable",
                    severity=DiagnosticSeverity.WARNING,
                    message="This engine declares a GPU requirement, but the supplied context reports no GPU.",
                    engine_id=descriptor.engine_id,
                    requirement="gpu",
                    requested="available",
                    supported=("unavailable",),
                ))
            elif gpu is None:
                diagnostics.append(EngineDiagnostic(
                    code="resource.gpu_unknown",
                    severity=DiagnosticSeverity.INFO,
                    message="GPU availability was not supplied; the engine requirement is unverified.",
                    engine_id=descriptor.engine_id,
                    requirement="gpu",
                ))

        if caps.estimated_memory_mb is None:
            diagnostics.append(EngineDiagnostic(
                code="resource.memory_estimate_unknown",
                severity=DiagnosticSeverity.INFO,
                message="The engine has no declared memory estimate.",
                engine_id=descriptor.engine_id,
                requirement="memory_mb",
            ))
        elif memory is None:
            diagnostics.append(EngineDiagnostic(
                code="resource.memory_capacity_unknown",
                severity=DiagnosticSeverity.INFO,
                message="Available memory was not supplied; the declared estimate cannot be compared.",
                engine_id=descriptor.engine_id,
                requirement="memory_mb",
                requested=str(caps.estimated_memory_mb),
            ))
        elif caps.estimated_memory_mb > memory:
            diagnostics.append(EngineDiagnostic(
                code="resource.memory_estimate_exceeds_available",
                severity=DiagnosticSeverity.WARNING,
                message="The declared memory estimate exceeds the supplied available-memory value.",
                engine_id=descriptor.engine_id,
                requirement="memory_mb",
                requested=str(caps.estimated_memory_mb),
                supported=(str(memory),),
            ))

        if caps.max_concurrent_jobs is None and concurrency > 1:
            diagnostics.append(EngineDiagnostic(
                code="resource.concurrency_limit_unknown",
                severity=DiagnosticSeverity.INFO,
                message="No concurrency limit is declared; this is not permission to enable parallel rendering.",
                engine_id=descriptor.engine_id,
                requirement="concurrency",
                requested=str(concurrency),
            ))
        elif caps.max_concurrent_jobs is not None and concurrency > caps.max_concurrent_jobs:
            diagnostics.append(EngineDiagnostic(
                code="resource.concurrency_exceeds_declared_limit",
                severity=DiagnosticSeverity.WARNING,
                message="Requested concurrency exceeds the engine's declared maximum.",
                engine_id=descriptor.engine_id,
                requirement="concurrency",
                requested=str(concurrency),
                supported=(str(caps.max_concurrent_jobs),),
            ))

        if any(item.severity is DiagnosticSeverity.WARNING for item in diagnostics):
            status = "warning"
        elif diagnostics:
            status = "unknown"
        else:
            status = "within_estimate"
        return EngineResourceAssessment(
            status=status,
            estimated_memory_mb=caps.estimated_memory_mb,
            available_memory_mb=memory,
            requires_gpu=caps.requires_gpu,
            gpu_available=gpu,
            requested_concurrency=concurrency,
            max_concurrent_jobs=caps.max_concurrent_jobs,
            diagnostics=tuple(diagnostics),
        )
