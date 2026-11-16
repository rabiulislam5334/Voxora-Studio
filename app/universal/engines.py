"""Explicit engine descriptors and registry for Universal Core.

The registry is intentionally framework- and renderer-independent. It stores
metadata only; it does not import, initialize, or execute rendering engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple


def _validate_optional_requirement(name: str, value: Optional[str]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be a non-empty string or null")


def _normalise_values(name: str, values: Iterable[str]) -> Tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be an iterable of strings, not a string")
    try:
        result = tuple(values)
    except TypeError:
        raise ValueError(f"{name} must be an iterable of strings") from None
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError(f"{name} must contain only non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicate values")
    return result


@dataclass(frozen=True)
class EngineCapabilities:
    """Declared features an engine can support; empty lists mean none declared."""

    scene_kinds: Tuple[str, ...] = ()
    style_tags: Tuple[str, ...] = ()
    asset_kinds: Tuple[str, ...] = ()
    output_formats: Tuple[str, ...] = ()
    requires_gpu: bool = False
    supports_draft_render: bool = False
    max_concurrent_jobs: Optional[int] = None
    estimated_memory_mb: Optional[int] = None

    def __post_init__(self) -> None:
        for field_name in ("scene_kinds", "style_tags", "asset_kinds", "output_formats"):
            object.__setattr__(
                self, field_name, _normalise_values(field_name, getattr(self, field_name))
            )
        if not isinstance(self.requires_gpu, bool):
            raise ValueError("requires_gpu must be a boolean")
        if not isinstance(self.supports_draft_render, bool):
            raise ValueError("supports_draft_render must be a boolean")
        for field_name in ("max_concurrent_jobs", "estimated_memory_mb"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValueError(f"{field_name} must be a positive integer or null")


@dataclass(frozen=True)
class EngineDescriptor:
    """Stable public metadata for one rendering engine implementation."""

    engine_id: str
    display_name: str
    version: str
    capabilities: EngineCapabilities
    available: bool = True
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.engine_id, str) or not self.engine_id.strip():
            raise ValueError("engine_id must be a non-empty string")
        if self.engine_id != self.engine_id.strip() or any(
            char.isspace() for char in self.engine_id
        ):
            raise ValueError("engine_id must not contain whitespace")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_name must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")
        if not isinstance(self.capabilities, EngineCapabilities):
            raise ValueError("capabilities must be an EngineCapabilities instance")
        if not isinstance(self.available, bool):
            raise ValueError("available must be a boolean")
        if not isinstance(self.unavailable_reason, str):
            raise ValueError("unavailable_reason must be a string")
        if self.available and self.unavailable_reason:
            raise ValueError("available engines cannot have an unavailable_reason")


class EngineRegistryError(Exception):
    """Base error for explicit engine registry resolution."""


class UnknownEngineError(EngineRegistryError):
    """Raised when a requested engine ID is not registered."""


class EngineUnavailableError(EngineRegistryError):
    """Raised when a registered engine is not currently available."""


class EngineCompatibilityError(EngineRegistryError):
    """Raised when an engine does not declare the requested capabilities."""


class EngineRegistry:
    """In-memory registry with deterministic discovery and strict resolution.

    The registry never silently substitutes another engine. Callers may show
    compatible alternatives to a user, but must make any fallback explicit.
    """

    def __init__(self, descriptors: Iterable[EngineDescriptor] = ()) -> None:
        self._engines: Dict[str, EngineDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: EngineDescriptor, *, replace: bool = False) -> None:
        if not isinstance(descriptor, EngineDescriptor):
            raise TypeError("descriptor must be an EngineDescriptor")
        if descriptor.engine_id in self._engines and not replace:
            raise ValueError(f"engine already registered: {descriptor.engine_id}")
        self._engines[descriptor.engine_id] = descriptor

    def unregister(self, engine_id: str) -> EngineDescriptor:
        try:
            return self._engines.pop(engine_id)
        except KeyError:
            raise UnknownEngineError(f"unknown engine: {engine_id}") from None

    def get(self, engine_id: str) -> EngineDescriptor:
        try:
            return self._engines[engine_id]
        except KeyError:
            raise UnknownEngineError(f"unknown engine: {engine_id}") from None

    def list_engines(self, *, include_unavailable: bool = False) -> Tuple[EngineDescriptor, ...]:
        engines = (
            descriptor
            for descriptor in self._engines.values()
            if include_unavailable or descriptor.available
        )
        return tuple(sorted(engines, key=lambda item: item.engine_id))

    def find_compatible(
        self,
        *,
        scene_kind: Optional[str] = None,
        style_tags: Iterable[str] = (),
        asset_kinds: Iterable[str] = (),
        output_format: Optional[str] = None,
        include_unavailable: bool = False,
    ) -> Tuple[EngineDescriptor, ...]:
        """Return every declared match; this method does not choose an engine."""
        _validate_optional_requirement("scene_kind", scene_kind)
        _validate_optional_requirement("output_format", output_format)
        requested_styles = set(_normalise_values("style_tags", style_tags))
        requested_assets = set(_normalise_values("asset_kinds", asset_kinds))
        matches = []
        for descriptor in self.list_engines(include_unavailable=include_unavailable):
            caps = descriptor.capabilities
            if scene_kind is not None and scene_kind not in caps.scene_kinds:
                continue
            if not requested_styles.issubset(caps.style_tags):
                continue
            if not requested_assets.issubset(caps.asset_kinds):
                continue
            if output_format is not None and output_format not in caps.output_formats:
                continue
            matches.append(descriptor)
        return tuple(matches)

    def resolve(
        self,
        engine_id: str,
        *,
        scene_kind: Optional[str] = None,
        style_tags: Iterable[str] = (),
        asset_kinds: Iterable[str] = (),
        output_format: Optional[str] = None,
    ) -> EngineDescriptor:
        """Resolve exactly the requested engine or raise a specific error."""
        descriptor = self.get(engine_id)
        if not descriptor.available:
            detail = f": {descriptor.unavailable_reason}" if descriptor.unavailable_reason else ""
            raise EngineUnavailableError(f"engine unavailable: {engine_id}{detail}")
        caps = descriptor.capabilities
        _validate_optional_requirement("scene_kind", scene_kind)
        _validate_optional_requirement("output_format", output_format)
        requested_styles = set(_normalise_values("style_tags", style_tags))
        requested_assets = set(_normalise_values("asset_kinds", asset_kinds))
        compatible = (
            (scene_kind is None or scene_kind in caps.scene_kinds)
            and requested_styles.issubset(caps.style_tags)
            and requested_assets.issubset(caps.asset_kinds)
            and (output_format is None or output_format in caps.output_formats)
        )
        if not compatible:
            raise EngineCompatibilityError(
                f"engine '{engine_id}' does not declare all requested capabilities"
            )
        return descriptor
