"""Executable, provider-neutral runtime for visual generation.

Providers are injected explicitly by the host application. This module never
downloads models, discovers credentials, or silently contacts a network
service. Provider output is staged, checked, then imported into the local
content-addressed VisualAssetLibrary.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Protocol, runtime_checkable
from uuid import uuid4

from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.visual_assets import AssetProvenance, VisualAsset
from app.universal.visual_generation import (
    VisualGenerationProviderDescriptor,
    VisualGenerationProviderRegistry,
    VisualGenerationRequest,
    VisualGenerationValidationError,
)


class VisualGenerationRuntimeError(RuntimeError):
    """A structured runtime failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, request_id: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


class VisualGenerationCancelled(VisualGenerationRuntimeError):
    def __init__(self, request_id: str):
        super().__init__("cancelled", "Visual generation was cancelled", request_id=request_id)


@dataclass(frozen=True)
class VisualGenerationProgress:
    request_id: str
    stage: str
    completed: int = 0
    total: int = 0
    message: str = ""


@dataclass(frozen=True)
class VisualGenerationResult:
    request_id: str
    provider_id: str
    request_fingerprint: str
    assets: tuple[VisualAsset, ...]


@runtime_checkable
class VisualGenerationProvider(Protocol):
    """Provider adapter contract; write images only inside output_dir.

    Implementations should periodically inspect cancel_event and may call
    progress(completed, total, message). They must return paths to generated
    raster files and must not mutate the project or asset catalog themselves.
    """

    descriptor: VisualGenerationProviderDescriptor

    def generate(
        self,
        request: VisualGenerationRequest,
        output_dir: Path,
        cancel_event: threading.Event,
        progress: Callable[[int, int, str], None],
    ) -> Iterable[Path]:
        ...


class VisualGenerationRuntime:
    """Runs one explicit provider and safely imports its verified outputs."""

    def __init__(
        self,
        asset_library: VisualAssetLibrary,
        providers: Iterable[VisualGenerationProvider] = (),
        *,
        max_output_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        if not isinstance(asset_library, VisualAssetLibrary):
            raise TypeError("asset_library must be a VisualAssetLibrary")
        if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be a positive integer")
        self.asset_library = asset_library
        self.max_output_bytes = max_output_bytes
        self._providers: dict[str, VisualGenerationProvider] = {}
        self._descriptors = VisualGenerationProviderRegistry()
        self._lock = threading.RLock()
        for provider in providers:
            self.register_provider(provider)

    def register_provider(self, provider: VisualGenerationProvider, *, replace: bool = False) -> None:
        if not isinstance(provider, VisualGenerationProvider):
            raise TypeError("provider must implement descriptor and generate()")
        descriptor = provider.descriptor
        if not isinstance(descriptor, VisualGenerationProviderDescriptor):
            raise TypeError("provider.descriptor must be a VisualGenerationProviderDescriptor")
        with self._lock:
            if descriptor.provider_id in self._providers and not replace:
                raise ValueError(f"provider already registered: {descriptor.provider_id}")
            self._providers[descriptor.provider_id] = provider
            self._descriptors.register(descriptor, replace=replace)

    def list_providers(self, *, include_unavailable: bool = False):
        return self._descriptors.list_providers(include_unavailable=include_unavailable)

    def generate(
        self,
        request: VisualGenerationRequest,
        provider_id: str,
        *,
        cancel_event: Optional[threading.Event] = None,
        progress: Optional[Callable[[VisualGenerationProgress], None]] = None,
        allow_network: bool = False,
        allow_api_key: bool = False,
    ) -> VisualGenerationResult:
        if not isinstance(request, VisualGenerationRequest):
            raise TypeError("request must be a VisualGenerationRequest")
        cancel = cancel_event or threading.Event()
        emit = progress or (lambda event: None)
        try:
            descriptor = self._descriptors.get(provider_id)
            provider = self._providers[provider_id]
        except KeyError:
            raise VisualGenerationRuntimeError(
                "provider_unavailable", f"Unknown or uninstalled provider: {provider_id}",
                request_id=getattr(request, "request_id", None),
            ) from None

        if descriptor.capabilities.requires_network and not allow_network:
            raise VisualGenerationRuntimeError(
                "network_consent_required", "This provider requires explicit network consent",
                request_id=request.request_id,
            )
        if descriptor.capabilities.requires_api_key and not allow_api_key:
            raise VisualGenerationRuntimeError(
                "credential_consent_required", "This provider requires explicit API-key consent",
                request_id=request.request_id,
            )
        try:
            self._descriptors.resolve(provider_id, request)
        except VisualGenerationValidationError as exc:
            raise VisualGenerationRuntimeError(
                "incompatible_request", str(exc), request_id=request.request_id
            ) from exc
        if cancel.is_set():
            raise VisualGenerationCancelled(request.request_id)

        staging_root = self.asset_library.root / ".generation-staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        if staging_root.is_symlink():
            raise VisualGenerationRuntimeError(
                "unsafe_staging", "Generation staging directory must not be a symbolic link",
                request_id=request.request_id,
            )
        run_dir = staging_root / uuid4().hex
        run_dir.mkdir()
        try:
            emit(VisualGenerationProgress(request.request_id, "started", 0, request.image_count))
            def provider_progress(done: int, total: int, message: str = "") -> None:
                if cancel.is_set():
                    raise VisualGenerationCancelled(request.request_id)
                if (isinstance(done, bool) or not isinstance(done, int) or done < 0
                        or isinstance(total, bool) or not isinstance(total, int) or total < 0):
                    raise VisualGenerationRuntimeError(
                        "invalid_progress", "Provider emitted invalid progress values",
                        request_id=request.request_id,
                    )
                emit(VisualGenerationProgress(request.request_id, "generating", done, total, str(message)[:512]))

            try:
                outputs = provider.generate(request, run_dir, cancel, provider_progress)
                paths = tuple(Path(item) for item in outputs)
            except VisualGenerationRuntimeError:
                raise
            except Exception as exc:
                raise VisualGenerationRuntimeError(
                    "provider_failed", f"Provider '{provider_id}' failed: {exc}",
                    request_id=request.request_id,
                ) from exc

            if cancel.is_set():
                raise VisualGenerationCancelled(request.request_id)
            if len(paths) != request.image_count:
                raise VisualGenerationRuntimeError(
                    "output_count_mismatch",
                    f"Provider returned {len(paths)} files; expected {request.image_count}",
                    request_id=request.request_id,
                )

            verified: list[Path] = []
            allowed_suffix = ".png" if request.output_format == "png" else ".jpg"
            for path in paths:
                if cancel.is_set():
                    raise VisualGenerationCancelled(request.request_id)
                if path.is_symlink():
                    raise VisualGenerationRuntimeError(
                        "unsafe_output", "Provider output must not be a symbolic link",
                        request_id=request.request_id,
                    )
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(run_dir.resolve())
                except (OSError, ValueError):
                    raise VisualGenerationRuntimeError(
                        "unsafe_output", "Provider output must be a regular file inside its staging directory",
                        request_id=request.request_id,
                    ) from None
                if not resolved.is_file() or resolved.suffix.lower() not in (
                    (".png",) if request.output_format == "png" else (".jpg", ".jpeg")
                ):
                    raise VisualGenerationRuntimeError(
                        "invalid_output", "Provider returned an unsupported or mismatched image file",
                        request_id=request.request_id,
                    )
                if resolved.stat().st_size <= 0 or resolved.stat().st_size > self.max_output_bytes:
                    raise VisualGenerationRuntimeError(
                        "invalid_output_size", "Generated image is empty or exceeds the configured size limit",
                        request_id=request.request_id,
                    )
                verified.append(resolved)

            emit(VisualGenerationProgress(request.request_id, "importing", 0, len(verified)))
            assets = []
            provenance = AssetProvenance(
                source=f"generated:{provider_id}",
                metadata={
                    "request_id": request.request_id,
                    "request_fingerprint": request.fingerprint,
                    "provider_version": descriptor.version,
                },
            )
            for index, path in enumerate(verified, start=1):
                if cancel.is_set():
                    raise VisualGenerationCancelled(request.request_id)
                asset_id = f"generated-{request.request_id}-{index}"
                try:
                    asset = self.asset_library.import_file(
                        path, kind="generated-image", asset_id=asset_id,
                        tags=tuple(request.style_tags), provenance=provenance,
                    )
                except AssetImportError as exc:
                    raise VisualGenerationRuntimeError(
                        "asset_import_failed", str(exc), request_id=request.request_id
                    ) from exc
                assets.append(asset)
                emit(VisualGenerationProgress(
                    request.request_id, "importing", index, len(verified)
                ))
            result = VisualGenerationResult(
                request_id=request.request_id,
                provider_id=provider_id,
                request_fingerprint=request.fingerprint,
                assets=tuple(assets),
            )
            emit(VisualGenerationProgress(request.request_id, "completed", len(assets), len(assets)))
            return result
        except VisualGenerationRuntimeError:
            raise
        except Exception as exc:
            raise VisualGenerationRuntimeError(
                "runtime_failed", str(exc), request_id=request.request_id
            ) from exc
        finally:
            for child in run_dir.iterdir():
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    import shutil
                    shutil.rmtree(child, ignore_errors=True)
            run_dir.rmdir()
