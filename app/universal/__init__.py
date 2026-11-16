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
from app.universal.requests import EngineRenderRequest, RawEngineOutput
from app.universal.runtime import (
    EngineAdapter,
    EngineBindingError,
    EngineInitializationError,
    EngineRenderError,
    EngineRuntimeError,
    EngineRuntimeRegistry,
)

__all__ = [
    "AssetRef",
    "EngineAdapter",
    "EngineBindingError",
    "EngineCapabilities",
    "EngineChoice",
    "EngineCompatibilityError",
    "EngineDescriptor",
    "EngineInitializationError",
    "EngineRegistry",
    "EngineRegistryError",
    "EngineRenderError",
    "EngineRenderRequest",
    "EngineRuntimeError",
    "EngineRuntimeRegistry",
    "EngineUnavailableError",
    "NormalizedSegment",
    "RawEngineOutput",
    "ScenePlan",
    "SegmentNormalizer",
    "SegmentOutputSpec",
    "UnknownEngineError",
    "UniversalState",
]
