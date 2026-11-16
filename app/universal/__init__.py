"""Universal Core domain contracts."""

from app.universal.execution import (
    SceneEngineExecutionError,
    SceneExecutionContext,
    SceneExecutionCoordinator,
    SceneExecutionError,
    SceneExecutionResult,
    SceneExecutionValidationError,
    SceneNormalizationError,
    ScenePlanResolutionError,
)
from app.universal.engines import (
    EngineCapabilities,
    EngineCompatibilityError,
    EngineDescriptor,
    EngineRegistry,
    EngineRegistryError,
    EngineUnavailableError,
    UnknownEngineError,
)
from app.universal.multi_execution import (
    MultiSceneExecutionCoordinator,
    MultiSceneExecutionError,
    MultiSceneExecutionRequest,
    MultiSceneExecutionResult,
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
    "MultiSceneExecutionCoordinator",
    "MultiSceneExecutionError",
    "MultiSceneExecutionRequest",
    "MultiSceneExecutionResult",
    "NormalizedSegment",
    "RawEngineOutput",
    "SceneEngineExecutionError",
    "SceneExecutionContext",
    "SceneExecutionCoordinator",
    "SceneExecutionError",
    "SceneExecutionResult",
    "SceneExecutionValidationError",
    "SceneNormalizationError",
    "ScenePlanResolutionError",
    "ScenePlan",
    "SegmentNormalizer",
    "SegmentOutputSpec",
    "UnknownEngineError",
    "UniversalState",
]
