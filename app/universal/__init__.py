"""Universal Core domain contracts."""

from app.universal.engines import (
    EngineCapabilities,
    EngineCompatibilityError,
    EngineDescriptor,
    EngineRegistry,
    EngineRegistryError,
    EngineUnavailableError,
    UnknownEngineError,
)
from app.universal.normalizer import NormalizedSegment, SegmentNormalizer, SegmentOutputSpec
from app.universal.models import (
    AssetRef,
    EngineChoice,
    ScenePlan,
    UniversalState,
)

__all__ = [
    "AssetRef",
    "EngineCapabilities",
    "EngineChoice",
    "EngineCompatibilityError",
    "EngineDescriptor",
    "EngineRegistry",
    "EngineRegistryError",
    "EngineUnavailableError",
    "NormalizedSegment",
    "ScenePlan",
    "SegmentNormalizer",
    "SegmentOutputSpec",
    "UnknownEngineError",
    "UniversalState",
]
