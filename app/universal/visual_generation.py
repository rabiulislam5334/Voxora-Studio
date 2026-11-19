"""Provider-neutral visual generation contracts for scene authoring.

This module defines validated intent and provider capability metadata only.
It does not contact a service, load a model, create image files, or mutate a
project. Executable providers are added behind this boundary in later stages.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Tuple


VISUAL_GENERATION_REQUEST_VERSION = 1
VISUAL_GENERATION_PROVIDER_VERSION = 1
_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_ALLOWED_FORMATS = {"png", "jpeg"}
_MAX_DIMENSION = 8192
_MAX_PIXELS = 40_000_000
_MAX_IMAGES_PER_REQUEST = 4
_MAX_PROMPT_LENGTH = 12_000


class VisualGenerationValidationError(ValueError):
    """Raised when a visual generation request or provider declaration is invalid."""


def _text(value: Any, name: str, *, allow_empty: bool = False, max_length: int = 4096) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        requirement = "a string" if allow_empty else "a non-empty string"
        raise VisualGenerationValidationError(f"{name} must be {requirement}")
    if len(value) > max_length:
        raise VisualGenerationValidationError(f"{name} exceeds {max_length} characters")
    return value


def _identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise VisualGenerationValidationError(f"{name} has an invalid format")
    return value


def _string_tuple(value: Any, name: str) -> Tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise VisualGenerationValidationError(f"{name} must be a sequence of strings")
    try:
        result = tuple(_text(item, f"{name}[]", max_length=128) for item in value)
    except TypeError:
        raise VisualGenerationValidationError(f"{name} must be a sequence of strings") from None
    if len(set(result)) != len(result):
        raise VisualGenerationValidationError(f"{name} must not contain duplicates")
    return result


def _json_value(value: Any, path: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VisualGenerationValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise VisualGenerationValidationError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    raise VisualGenerationValidationError(f"{path} must contain JSON-compatible values only")


def _metadata(value: Any, name: str = "metadata") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualGenerationValidationError(f"{name} must be an object")
    return _json_value(value, name)


@dataclass(frozen=True)
class VisualGenerationRequest:
    """Immutable request for one scene's still-image visual assets."""

    request_id: str
    scene_id: str
    prompt: str
    negative_prompt: str = ""
    model_id: Optional[str] = None
    width: int = 1024
    height: int = 1024
    output_format: str = "png"
    image_count: int = 1
    seed: Optional[int] = None
    style_tags: Tuple[str, ...] = ()
    reference_asset_ids: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request_id", _MODEL_ID)
        _identifier(self.scene_id, "scene_id", _MODEL_ID)
        _text(self.prompt, "prompt", max_length=_MAX_PROMPT_LENGTH)
        _text(self.negative_prompt, "negative_prompt", allow_empty=True, max_length=_MAX_PROMPT_LENGTH)
        if self.model_id is not None:
            _identifier(self.model_id, "model_id", _MODEL_ID)
        for name in ("width", "height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= _MAX_DIMENSION:
                raise VisualGenerationValidationError(
                    f"{name} must be an integer between 64 and {_MAX_DIMENSION}"
                )
        if self.width * self.height > _MAX_PIXELS:
            raise VisualGenerationValidationError(
                f"requested image exceeds the {_MAX_PIXELS:,}-pixel safety limit"
            )
        if self.output_format not in _ALLOWED_FORMATS:
            raise VisualGenerationValidationError("output_format must be 'png' or 'jpeg'")
        if isinstance(self.image_count, bool) or not isinstance(self.image_count, int) or not 1 <= self.image_count <= _MAX_IMAGES_PER_REQUEST:
            raise VisualGenerationValidationError(
                f"image_count must be between 1 and {_MAX_IMAGES_PER_REQUEST}"
            )
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
            or not 0 <= self.seed <= 2**32 - 1
        ):
            raise VisualGenerationValidationError("seed must be a 32-bit unsigned integer or null")
        object.__setattr__(self, "style_tags", _string_tuple(self.style_tags, "style_tags"))
        object.__setattr__(self, "reference_asset_ids", _string_tuple(
            self.reference_asset_ids, "reference_asset_ids"
        ))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    @property
    def fingerprint(self) -> str:
        payload = self.to_dict()
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_version": VISUAL_GENERATION_REQUEST_VERSION,
            "request_id": self.request_id,
            "scene_id": self.scene_id,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "model_id": self.model_id,
            "width": self.width,
            "height": self.height,
            "output_format": self.output_format,
            "image_count": self.image_count,
            "seed": self.seed,
            "style_tags": list(self.style_tags),
            "reference_asset_ids": list(self.reference_asset_ids),
            "metadata": _metadata(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "VisualGenerationRequest":
        if not isinstance(data, Mapping):
            raise VisualGenerationValidationError("generation request must be an object")
        version = data.get("request_version", VISUAL_GENERATION_REQUEST_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version != VISUAL_GENERATION_REQUEST_VERSION:
            raise VisualGenerationValidationError("unsupported visual generation request version")
        return cls(
            request_id=data.get("request_id"),
            scene_id=data.get("scene_id"),
            prompt=data.get("prompt"),
            negative_prompt=data.get("negative_prompt", ""),
            model_id=data.get("model_id"),
            width=data.get("width", 1024),
            height=data.get("height", 1024),
            output_format=data.get("output_format", "png"),
            image_count=data.get("image_count", 1),
            seed=data.get("seed"),
            style_tags=data.get("style_tags", ()),
            reference_asset_ids=data.get("reference_asset_ids", ()),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class VisualGenerationProviderCapabilities:
    """Declared limits/features; these values never imply provider availability."""

    output_formats: Tuple[str, ...] = ("png",)
    max_width: int = 1024
    max_height: int = 1024
    max_images_per_request: int = 1
    supports_reference_images: bool = False
    supports_seed: bool = False
    requires_network: bool = True
    requires_api_key: bool = True
    estimated_memory_mb: Optional[int] = None

    def __post_init__(self) -> None:
        formats = _string_tuple(self.output_formats, "output_formats")
        if not formats or not set(formats).issubset(_ALLOWED_FORMATS):
            raise VisualGenerationValidationError("output_formats must contain png and/or jpeg")
        object.__setattr__(self, "output_formats", formats)
        for name in ("max_width", "max_height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= _MAX_DIMENSION:
                raise VisualGenerationValidationError(f"{name} must be between 64 and {_MAX_DIMENSION}")
        if isinstance(self.max_images_per_request, bool) or not isinstance(self.max_images_per_request, int) or not 1 <= self.max_images_per_request <= _MAX_IMAGES_PER_REQUEST:
            raise VisualGenerationValidationError("max_images_per_request is outside the supported range")
        for name in ("supports_reference_images", "supports_seed", "requires_network", "requires_api_key"):
            if not isinstance(getattr(self, name), bool):
                raise VisualGenerationValidationError(f"{name} must be a boolean")
        if self.estimated_memory_mb is not None and (
            isinstance(self.estimated_memory_mb, bool)
            or not isinstance(self.estimated_memory_mb, int)
            or self.estimated_memory_mb < 1
        ):
            raise VisualGenerationValidationError("estimated_memory_mb must be positive or null")


@dataclass(frozen=True)
class VisualGenerationProviderDescriptor:
    """Public, credential-free metadata for one explicitly selectable provider."""

    provider_id: str
    display_name: str
    version: str
    capabilities: VisualGenerationProviderCapabilities
    model_ids: Tuple[str, ...] = ()
    available: bool = False
    unavailable_reason: str = "No provider adapter is installed"

    def __post_init__(self) -> None:
        _identifier(self.provider_id, "provider_id", _PROVIDER_ID)
        _text(self.display_name, "display_name", max_length=128)
        _text(self.version, "version", max_length=64)
        if not isinstance(self.capabilities, VisualGenerationProviderCapabilities):
            raise VisualGenerationValidationError("capabilities must be VisualGenerationProviderCapabilities")
        if isinstance(self.model_ids, (str, bytes)):\n            raise VisualGenerationValidationError("model_ids must be a sequence of model IDs")\n        try:\n            models = tuple(_identifier(item, "model_id", _MODEL_ID) for item in self.model_ids)\n        except TypeError:\n            raise VisualGenerationValidationError("model_ids must be a sequence of model IDs") from None
        if len(set(models)) != len(models):
            raise VisualGenerationValidationError("model_ids must not contain duplicates")
        object.__setattr__(self, "model_ids", models)
        if not isinstance(self.available, bool):
            raise VisualGenerationValidationError("available must be a boolean")
        _text(self.unavailable_reason, "unavailable_reason", allow_empty=True, max_length=512)
        if self.available and self.unavailable_reason:
            raise VisualGenerationValidationError("available providers cannot have an unavailable_reason")

    def compatibility_issues(self, request: VisualGenerationRequest) -> Tuple[str, ...]:
        if not isinstance(request, VisualGenerationRequest):
            raise TypeError("request must be a VisualGenerationRequest")
        issues = []
        caps = self.capabilities
        if not self.available:
            issues.append(self.unavailable_reason or "Provider is unavailable")
        if request.model_id is not None and request.model_id not in self.model_ids:
            issues.append(f"Model '{request.model_id}' is not declared by provider '{self.provider_id}'")
        if request.width > caps.max_width or request.height > caps.max_height:
            issues.append(
                f"Requested {request.width}x{request.height} exceeds provider limit "
                f"{caps.max_width}x{caps.max_height}"
            )
        if request.output_format not in caps.output_formats:
            issues.append(f"Output format '{request.output_format}' is not supported")
        if request.image_count > caps.max_images_per_request:
            issues.append(
                f"Requested {request.image_count} images exceeds provider limit "
                f"{caps.max_images_per_request}"
            )
        if request.reference_asset_ids and not caps.supports_reference_images:
            issues.append("Provider does not support reference images")
        if request.seed is not None and not caps.supports_seed:
            issues.append("Provider does not support deterministic seeds")
        return tuple(issues)


class VisualGenerationProviderRegistry:
    """Metadata-only registry; selection is exact and never silently falls back."""

    def __init__(self, providers: Iterable[VisualGenerationProviderDescriptor] = ()) -> None:
        self._providers: dict[str, VisualGenerationProviderDescriptor] = {}
        for provider in providers:
            self.register(provider)

    def register(self, descriptor: VisualGenerationProviderDescriptor, *, replace: bool = False) -> None:
        if not isinstance(descriptor, VisualGenerationProviderDescriptor):
            raise TypeError("descriptor must be a VisualGenerationProviderDescriptor")
        if descriptor.provider_id in self._providers and not replace:
            raise ValueError(f"provider already registered: {descriptor.provider_id}")
        self._providers[descriptor.provider_id] = descriptor

    def get(self, provider_id: str) -> VisualGenerationProviderDescriptor:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise KeyError(f"unknown visual generation provider: {provider_id}") from None

    def list_providers(self, *, include_unavailable: bool = False) -> Tuple[VisualGenerationProviderDescriptor, ...]:
        values = (
            item for item in self._providers.values()
            if include_unavailable or item.available
        )
        return tuple(sorted(values, key=lambda item: item.provider_id))

    def find_compatible(
        self, request: VisualGenerationRequest, *, include_unavailable: bool = False
    ) -> Tuple[VisualGenerationProviderDescriptor, ...]:
        matches = []
        for provider in self.list_providers(include_unavailable=include_unavailable):
            if not provider.compatibility_issues(request):
                matches.append(provider)
        return tuple(matches)

    def resolve(self, provider_id: str, request: VisualGenerationRequest) -> VisualGenerationProviderDescriptor:
        provider = self.get(provider_id)
        issues = provider.compatibility_issues(request)
        if issues:
            raise VisualGenerationValidationError(
                f"provider '{provider_id}' cannot fulfill request: " + "; ".join(issues)
            )
        return provider
