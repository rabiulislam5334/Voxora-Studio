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
    "ScenePlan",
    "UnknownEngineError",
    "UniversalState",
]
