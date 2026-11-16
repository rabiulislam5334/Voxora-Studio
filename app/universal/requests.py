"""Validated, renderer-independent requests and raw output contracts."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Tuple

from app.universal.models import AssetRef
from app.universal.normalizer import SegmentOutputSpec
from app.workers.cancel import CancelToken


def _string_tuple(name: str, values: Tuple[str, ...]) -> Tuple[str, ...]:
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


def _freeze_mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise ValueError(f"{name} keys must be non-empty strings")
    return MappingProxyType(copy.deepcopy(dict(value)))


@dataclass(frozen=True)
class EngineRenderRequest:
    """Immutable input for one scene render; callbacks and cancellation stay out."""

    scene_id: str
    scene_kind: str
    output_format: str
    output_spec: SegmentOutputSpec
    destination: Path
    style_tags: Tuple[str, ...] = ()
    asset_refs: Tuple[AssetRef, ...] = ()
    engine_params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("scene_id", "scene_kind", "output_format"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.output_spec, SegmentOutputSpec):
            raise TypeError("output_spec must be a SegmentOutputSpec")
        if not isinstance(self.destination, (str, Path)) or not str(self.destination).strip():
            raise ValueError("destination must be a non-empty path")
        object.__setattr__(self, "destination", Path(self.destination))
        object.__setattr__(self, "style_tags", _string_tuple("style_tags", self.style_tags))
        if isinstance(self.asset_refs, (str, bytes)):
            raise ValueError("asset_refs must be an iterable of AssetRef values")
        try:
            assets = tuple(self.asset_refs)
        except TypeError:
            raise ValueError("asset_refs must be an iterable of AssetRef values") from None
        if any(not isinstance(asset, AssetRef) for asset in assets):
            raise TypeError("asset_refs must contain only AssetRef values")
        if len({asset.asset_id for asset in assets}) != len(assets):
            raise ValueError("asset_refs must not contain duplicate asset IDs")
        object.__setattr__(self, "asset_refs", assets)
        object.__setattr__(self, "engine_params", _freeze_mapping(self.engine_params, "engine_params"))


@dataclass(frozen=True)
class RawEngineOutput:
    """A renderer-produced artifact awaiting the shared SegmentNormalizer."""

    path: Path
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.path, (str, Path)) or not str(self.path).strip():
            raise ValueError("raw output path must be a non-empty path")
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))


ProgressCallback = Optional[Callable[[float], None]]
CancellationToken = Optional[CancelToken]
