"""Lazy runtime bindings for Universal Core engine adapters.

EngineRegistry remains the metadata/discovery authority. This module binds
those descriptors to executable adapters without importing renderer packages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol, Union

from app.universal.engines import EngineDescriptor, EngineRegistry, UnknownEngineError
from app.universal.requests import (
    CancellationToken,
    EngineRenderRequest,
    ProgressCallback,
    RawEngineOutput,
)


class EngineRuntimeError(Exception):
    """Base error for runtime adapter binding and execution."""


class EngineBindingError(EngineRuntimeError):
    """Raised when a descriptor cannot be bound to its adapter."""


class EngineInitializationError(EngineRuntimeError):
    """Raised when a lazy adapter factory fails or returns an invalid adapter."""


class EngineRenderError(EngineRuntimeError):
    """Raised when an adapter violates the runtime output contract."""


class EngineAdapter(Protocol):
    """Minimal executable contract implemented by renderer adapters."""

    @property
    def descriptor(self) -> EngineDescriptor: ...

    def render(
        self,
        request: EngineRenderRequest,
        *,
        on_progress: ProgressCallback = None,
        cancel: CancellationToken = None,
    ) -> RawEngineOutput: ...


AdapterFactory = Callable[[], EngineAdapter]
AdapterSource = Union[EngineAdapter, AdapterFactory]


@dataclass
class _Binding:
    descriptor: EngineDescriptor
    source: AdapterSource
    instance: Optional[EngineAdapter] = None


class EngineRuntimeRegistry:
    """Exact-ID adapter bindings layered over the metadata-only EngineRegistry.

    Factories are invoked only when an engine is resolved for execution. No
    alternative engine is selected when a binding is missing or unavailable.
    """

    def __init__(self, metadata: Optional[EngineRegistry] = None) -> None:
        self.metadata = metadata if metadata is not None else EngineRegistry()
        self._bindings: Dict[str, _Binding] = {}

    def register(
        self,
        descriptor: EngineDescriptor,
        adapter: AdapterSource,
        *,
        replace: bool = False,
    ) -> None:
        if not isinstance(descriptor, EngineDescriptor):
            raise TypeError("descriptor must be an EngineDescriptor")
        if descriptor.engine_id in self._bindings and not replace:
            raise ValueError(f"runtime engine already registered: {descriptor.engine_id}")
        if replace and descriptor.engine_id not in self._bindings:
            raise ValueError(f"cannot replace unregistered runtime engine: {descriptor.engine_id}")

        instance = None
        if callable(adapter):
            source = adapter
        else:
            instance = self._validate_adapter(descriptor.engine_id, adapter)
            source = adapter

        # Reuse a matching metadata descriptor supplied at construction. Reject
        # conflicts unless the caller explicitly replaces an existing binding.
        try:
            existing = self.metadata.get(descriptor.engine_id)
        except UnknownEngineError:
            existing = None

        if existing is not None:
            if existing != descriptor and not replace:
                raise ValueError(
                    f"metadata descriptor already registered with different values: "
                    f"{descriptor.engine_id}"
                )
            if existing != descriptor or replace:
                self.metadata.register(descriptor, replace=True)
        else:
            self.metadata.register(descriptor)

        self._bindings[descriptor.engine_id] = _Binding(
            descriptor=descriptor, source=source, instance=instance
        )

    @staticmethod
    def _validate_adapter(engine_id: str, adapter: object) -> EngineAdapter:
        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(descriptor, EngineDescriptor):
            raise EngineBindingError(f"adapter '{engine_id}' must expose an EngineDescriptor")
        if descriptor.engine_id != engine_id:
            raise EngineBindingError(
                f"adapter descriptor ID '{descriptor.engine_id}' does not match binding '{engine_id}'"
            )
        if not callable(getattr(adapter, "render", None)):
            raise EngineBindingError(f"adapter '{engine_id}' must implement render()")
        return adapter  # type: ignore[return-value]

    def list_engines(self, *, include_unavailable: bool = False):
        return self.metadata.list_engines(include_unavailable=include_unavailable)

    def resolve(
        self,
        engine_id: str,
        *,
        scene_kind: Optional[str] = None,
        style_tags=(),
        asset_kinds=(),
        output_format: Optional[str] = None,
    ) -> EngineAdapter:
        self.metadata.resolve(
            engine_id,
            scene_kind=scene_kind,
            style_tags=style_tags,
            asset_kinds=asset_kinds,
            output_format=output_format,
        )
        binding = self._bindings.get(engine_id)
        if binding is None:
            raise EngineBindingError(f"engine '{engine_id}' has metadata but no runtime binding")
        if binding.instance is None:
            try:
                candidate = binding.source()
                binding.instance = self._validate_adapter(engine_id, candidate)
            except EngineRuntimeError:
                raise
            except Exception as exc:
                raise EngineInitializationError(
                    f"could not initialize engine '{engine_id}': {exc}"
                ) from exc
        return binding.instance

    def render(
        self,
        engine_id: str,
        request: EngineRenderRequest,
        *,
        on_progress: ProgressCallback = None,
        cancel: CancellationToken = None,
    ) -> RawEngineOutput:
        if not isinstance(request, EngineRenderRequest):
            raise TypeError("request must be an EngineRenderRequest")
        adapter = self.resolve(
            engine_id,
            scene_kind=request.scene_kind,
            style_tags=request.style_tags,
            asset_kinds=tuple(asset.kind for asset in request.asset_refs),
            output_format=request.output_format,
        )
        result = adapter.render(request, on_progress=on_progress, cancel=cancel)
        if not isinstance(result, RawEngineOutput):
            raise EngineRenderError(f"engine '{engine_id}' must return a RawEngineOutput")
        if not result.path.is_file() or result.path.stat().st_size <= 0:
            raise EngineRenderError(
                f"engine '{engine_id}' returned a missing or empty output: {result.path}"
            )
        if result.path.resolve() == request.destination.resolve():
            raise EngineRenderError(
                "raw engine output and normalized destination must be different files"
            )
        return result
