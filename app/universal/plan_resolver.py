"""Deterministic, metadata-only engine resolution for Universal Scene Plans.

This module never initializes adapters or executes rendering engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from app.universal.engines import (
    EngineCompatibilityError,
    EngineDescriptor,
    EngineRegistry,
    EngineUnavailableError,
    UnknownEngineError,
)
from app.universal.models import ScenePlan


class EnginePlanStatus(str, Enum):
    COMPATIBLE = "compatible"
    SELECTION_REQUIRED = "selection_required"
    FALLBACK_REVIEW_REQUIRED = "fallback_review_required"
    UNKNOWN_ENGINE = "unknown_engine"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    ENGINE_INCOMPATIBLE = "engine_incompatible"
    INVALID_PLAN = "invalid_plan"
    UNSUPPORTED_REQUIREMENTS = "unsupported_requirements"


@dataclass(frozen=True)
class EnginePlanResolution:
    """Immutable explanation of the engine options for one scene plan."""

    scene_id: str
    requested_engine_id: str | None
    plan_status: str
    status: EnginePlanStatus
    selected_descriptor: EngineDescriptor | None = None
    compatible_candidates: Tuple[EngineDescriptor, ...] = ()
    fallback_candidates: Tuple[EngineDescriptor, ...] = ()
    diagnostics: Tuple[str, ...] = ()


class EnginePlanResolver:
    """Resolve a ScenePlan against registered engine metadata, without choosing."""

    _SUPPORTED_REQUIREMENT_KEYS = frozenset({"output_format", "asset_kinds"})

    def __init__(self, registry: EngineRegistry) -> None:
        if not isinstance(registry, EngineRegistry):
            raise TypeError("registry must be an EngineRegistry")
        self._registry = registry

    def resolve(self, plan: ScenePlan) -> EnginePlanResolution:
        if not isinstance(plan, ScenePlan):
            raise TypeError("plan must be a ScenePlan")

        diagnostics = []
        scene_id = plan.scene_id if isinstance(plan.scene_id, str) else ""
        requested_id = None
        choice = plan.engine_choice
        if choice is not None:
            requested_id = getattr(choice, "engine_id", None)

        invalid = self._validate_plan(plan, diagnostics)
        if invalid:
            return self._result(
                plan, requested_id, EnginePlanStatus.INVALID_PLAN,
                diagnostics=diagnostics,
            )

        unknown_keys = sorted(set(plan.requirements) - self._SUPPORTED_REQUIREMENT_KEYS)
        if unknown_keys:
            diagnostics.extend(
                f"Unsupported requirement key: {key}" for key in unknown_keys
            )
            return self._result(
                plan, requested_id, EnginePlanStatus.UNSUPPORTED_REQUIREMENTS,
                diagnostics=diagnostics,
            )

        asset_kinds = tuple(asset.kind for asset in plan.asset_refs)
        declared_asset_kinds = plan.requirements.get("asset_kinds")
        if declared_asset_kinds is not None:
            if (
                not isinstance(declared_asset_kinds, (list, tuple))
                or any(not isinstance(item, str) or not item.strip() for item in declared_asset_kinds)
            ):
                diagnostics.append("requirements.asset_kinds must be a list of non-empty strings")
                return self._result(
                    plan, requested_id, EnginePlanStatus.INVALID_PLAN,
                    diagnostics=diagnostics,
                )
            if set(declared_asset_kinds) != set(asset_kinds):
                diagnostics.append(
                    "requirements.asset_kinds contradict asset_refs; asset_refs is the source of truth"
                )
                return self._result(
                    plan, requested_id, EnginePlanStatus.INVALID_PLAN,
                    diagnostics=diagnostics,
                )

        output_format = plan.requirements.get("output_format")
        if output_format is not None and (
            not isinstance(output_format, str) or not output_format.strip()
        ):
            diagnostics.append("requirements.output_format must be a non-empty string")
            return self._result(
                plan, requested_id, EnginePlanStatus.INVALID_PLAN,
                diagnostics=diagnostics,
            )

        query = {
            "scene_kind": plan.kind,
            "style_tags": tuple(plan.style_tags),
            "asset_kinds": asset_kinds,
            "output_format": output_format,
        }
        try:
            candidates = self._registry.find_compatible(**query)
        except (TypeError, ValueError) as exc:
            diagnostics.append(f"Invalid scene requirements: {exc}")
            return self._result(
                plan, requested_id, EnginePlanStatus.INVALID_PLAN,
                diagnostics=diagnostics,
            )

        fallback_candidates = self._inspect_fallbacks(
            getattr(choice, "fallback_chain", ()) if choice is not None else (),
            query,
            diagnostics,
        )

        if not requested_id:
            status = (
                EnginePlanStatus.FALLBACK_REVIEW_REQUIRED
                if fallback_candidates
                else EnginePlanStatus.SELECTION_REQUIRED
            )
            diagnostics.append("No engine is explicitly selected; user/director selection is required")
            return self._result(
                plan, None, status, compatible_candidates=candidates,
                fallback_candidates=fallback_candidates, diagnostics=diagnostics,
            )

        if not isinstance(requested_id, str):
            diagnostics.append("engine_choice.engine_id must be a non-empty string or null")
            return self._result(
                plan, None, EnginePlanStatus.INVALID_PLAN,
                compatible_candidates=candidates, diagnostics=diagnostics,
            )

        try:
            selected = self._registry.resolve(requested_id, **query)
        except UnknownEngineError as exc:
            diagnostics.append(str(exc))
            status = EnginePlanStatus.UNKNOWN_ENGINE
        except EngineUnavailableError as exc:
            diagnostics.append(str(exc))
            status = EnginePlanStatus.ENGINE_UNAVAILABLE
        except EngineCompatibilityError as exc:
            diagnostics.append(str(exc))
            status = EnginePlanStatus.ENGINE_INCOMPATIBLE
        else:
            return self._result(
                plan, requested_id, EnginePlanStatus.COMPATIBLE,
                selected_descriptor=selected,
                compatible_candidates=candidates,
                fallback_candidates=fallback_candidates,
                diagnostics=diagnostics,
            )

        if fallback_candidates:
            status = EnginePlanStatus.FALLBACK_REVIEW_REQUIRED
            diagnostics.append(
                "One or more explicitly listed fallback engines are compatible; approval is required"
            )
        return self._result(
            plan, requested_id, status, compatible_candidates=candidates,
            fallback_candidates=fallback_candidates, diagnostics=diagnostics,
        )

    def _inspect_fallbacks(self, fallback_ids, query, diagnostics):
        if not isinstance(fallback_ids, (list, tuple)):
            diagnostics.append("engine_choice.fallback_chain must be a list of engine IDs")
            return ()
        eligible = []
        for engine_id in fallback_ids:
            if not isinstance(engine_id, str) or not engine_id.strip():
                diagnostics.append("Fallback chain contains an invalid engine ID")
                continue
            try:
                descriptor = self._registry.resolve(engine_id, **query)
            except UnknownEngineError:
                diagnostics.append(f"Fallback engine is unknown: {engine_id}")
            except EngineUnavailableError:
                diagnostics.append(f"Fallback engine is unavailable: {engine_id}")
            except EngineCompatibilityError:
                diagnostics.append(f"Fallback engine is incompatible: {engine_id}")
            else:
                eligible.append(descriptor)
        return tuple(eligible)

    @staticmethod
    def _validate_plan(plan, diagnostics):
        if not isinstance(plan.scene_id, str) or not plan.scene_id.strip():
            diagnostics.append("scene_id must be a non-empty string")
        if not isinstance(plan.kind, str) or not plan.kind.strip():
            diagnostics.append("kind must be a non-empty string")
        if not isinstance(plan.style_tags, (list, tuple)) or any(
            not isinstance(tag, str) or not tag.strip() for tag in plan.style_tags
        ):
            diagnostics.append("style_tags must contain only non-empty strings")
        if not isinstance(plan.requirements, dict):
            diagnostics.append("requirements must be an object")
        if not isinstance(plan.asset_refs, (list, tuple)) or any(
            not hasattr(asset, "kind") or not isinstance(asset.kind, str) or not asset.kind.strip()
            for asset in plan.asset_refs
        ):
            diagnostics.append("asset_refs must contain valid asset references")
        if not isinstance(plan.plan_status, str) or not plan.plan_status:
            diagnostics.append("plan_status must be a non-empty string")
        if plan.engine_choice is not None:
            engine_id = getattr(plan.engine_choice, "engine_id", None)
            if engine_id is not None and (
                not isinstance(engine_id, str) or not engine_id.strip()
            ):
                diagnostics.append("engine_choice.engine_id must be a non-empty string or null")
        return bool(diagnostics)
    
    @staticmethod
    def _result(
        plan, requested_id, status, *, selected_descriptor=None,
        compatible_candidates=(), fallback_candidates=(), diagnostics=(),
    ):
        return EnginePlanResolution(
            scene_id=plan.scene_id if isinstance(plan.scene_id, str) else "",
            requested_engine_id=requested_id if isinstance(requested_id, str) else None,
            plan_status=plan.plan_status if isinstance(plan.plan_status, str) else "",
            status=status,
            selected_descriptor=selected_descriptor,
            compatible_candidates=tuple(compatible_candidates),
            fallback_candidates=tuple(fallback_candidates),
            diagnostics=tuple(diagnostics),
        )
