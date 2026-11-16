"""Universal Core domain contracts."""

from app.universal.execution import (\n    SceneEngineExecutionError,\n    SceneExecutionContext,\n    SceneExecutionCoordinator,\n    SceneExecutionError,\n    SceneExecutionResult,\n    SceneExecutionValidationError,\n    SceneNormalizationError,\n    ScenePlanResolutionError,\n)\nfrom app.universal.engines import (
    EngineCapabilities,
    EngineCompatibilityError,
    EngineDescriptor,
    EngineRegistry,
    EngineRegistryError,
    EngineUnavailableError,
    UnknownEngineError,
)
from app.universal.normalizer import NormalizedSegment, SegmentNormalizer, SegmentOutputSpec
from app.universal.plan_resolver import EnginePlanResolution, EnginePlanResolver, EnginePlanStatus
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
    "EnginePlanResolution",
    "EnginePlanResolver",
    "EnginePlanStatus",
    "EngineRuntimeError",
    "EngineRuntimeRegistry",
    "EngineUnavailableError",
    "NormalizedSegment",
    "RawEngineOutput",
    "SceneEngineExecutionError",\n    "SceneExecutionContext",\n    "SceneExecutionCoordinator",\n    "SceneExecutionError",\n    "SceneExecutionResult",\n    "SceneExecutionValidationError",\n    "SceneNormalizationError",\n    "ScenePlanResolutionError",\n    "ScenePlan",
    "SegmentNormalizer",
    "SegmentOutputSpec",
    "UnknownEngineError",
    "UniversalState",
]
