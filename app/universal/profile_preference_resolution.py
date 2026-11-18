"""Advisory resolution of channel-profile preferred engines.

Profile preferences are suggestions only. This module never changes a scene
plan, project, registry, or explicitly selected engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from app.universal.capability_resolution import (
    EngineCapabilityResolution,
    EngineCapabilityResolver,
    EngineDiagnostic,
    EngineResourceContext,
)
from app.universal.engines import EngineDescriptor, EngineRegistry
from app.universal.profiles.models import ChannelProfile


class EnginePreferenceStatus(str, Enum):
    COMPATIBLE = "compatible"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EnginePreference:
    """One declared profile preference and its current registry assessment."""

    engine_id: str
    status: EnginePreferenceStatus
    descriptor: Optional[EngineDescriptor] = None
    diagnostics: Tuple[EngineDiagnostic, ...] = ()


@dataclass(frozen=True)
class ProfilePreferenceResolution:
    """Profile suggestions plus an independent inspection of explicit selection."""

    profile_id: str
    selected_engine_id: Optional[str]
    selected_engine_resolution: Optional[EngineCapabilityResolution]
    preferences: Tuple[EnginePreference, ...]
    compatible_preferred_engines: Tuple[EngineDescriptor, ...]
    requires_user_confirmation: bool
    supported: bool = True
    diagnostics: Tuple[str, ...] = ()


class ProfilePreferenceResolver:
    """Resolve ordered profile preferences without making or changing a choice."""

    def __init__(self, registry: EngineRegistry) -> None:
        if not isinstance(registry, EngineRegistry):
            raise TypeError("registry must be an EngineRegistry")
        self._capabilities = EngineCapabilityResolver(registry)

    def resolve(
        self,
        profile: ChannelProfile,
        *,
        selected_engine_id: Optional[str] = None,
        scene_kind: Optional[str] = None,
        style_tags=(),
        asset_kinds=(),
        output_format: Optional[str] = None,
        resource_context: Optional[EngineResourceContext] = None,
    ) -> ProfilePreferenceResolution:
        if not isinstance(profile, ChannelProfile):
            raise TypeError("profile must be a ChannelProfile")

        if profile.read_only:
            return ProfilePreferenceResolution(
                profile_id=profile.profile_id,
                selected_engine_id=selected_engine_id,
                selected_engine_resolution=None,
                preferences=(),
                compatible_preferred_engines=(),
                requires_user_confirmation=False,
                supported=False,
                diagnostics=("Future profile schema is read-only; preferences were not interpreted.",),
            )

        selected = self._capabilities.resolve(
            selected_engine_id,
            scene_kind=scene_kind,
            style_tags=style_tags,
            asset_kinds=asset_kinds,
            output_format=output_format,
            resource_context=resource_context,
        )

        preferences = []
        compatible = []
        for engine_id in profile.preferred_engines:
            result = self._capabilities.resolve(
                engine_id,
                scene_kind=scene_kind,
                style_tags=style_tags,
                asset_kinds=asset_kinds,
                output_format=output_format,
                resource_context=resource_context,
            )
            status_map = {
                "compatible": EnginePreferenceStatus.COMPATIBLE,
                "unavailable": EnginePreferenceStatus.UNAVAILABLE,
                "incompatible": EnginePreferenceStatus.INCOMPATIBLE,
                "unknown_engine": EnginePreferenceStatus.UNKNOWN,
            }
            status = status_map.get(result.status, EnginePreferenceStatus.UNKNOWN)
            descriptor = result.selected_descriptor
            if status is EnginePreferenceStatus.COMPATIBLE and descriptor is not None:
                compatible.append(descriptor)
            preferences.append(EnginePreference(
                engine_id=engine_id,
                status=status,
                descriptor=descriptor,
                diagnostics=result.diagnostics,
            ))

        return ProfilePreferenceResolution(
            profile_id=profile.profile_id,
            selected_engine_id=selected_engine_id,
            selected_engine_resolution=selected,
            preferences=tuple(preferences),
            compatible_preferred_engines=tuple(compatible),
            requires_user_confirmation=bool(compatible),
        )
