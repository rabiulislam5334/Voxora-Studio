from app.universal.builtins import BUILTIN_ENGINE_IDS, build_builtin_engine_runtime_registry
from app.universal.capability_resolution import (
    DiagnosticSeverity,
    EngineCapabilityResolution,
    EngineCapabilityResolver,
    EngineDiagnostic,
    EngineResourceAssessment,
    EngineResourceContext,
)
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
from app.universal.profile_authoring import (
    ProfiledScenePlanProposal,
    apply_profiled_scene_plan_proposal,
    build_profiled_scene_plan_proposal,
)
from app.universal.profile_preference_resolution import (
    EnginePreference,
    EnginePreferenceStatus,
    ProfilePreferenceResolution,
    ProfilePreferenceResolver,
)
from app.universal.requests import EngineRenderRequest, RawEngineOutput
from app.universal.workflow import (\n    BUILTIN_WORKFLOW_DESCRIPTORS,\n    BUILTIN_WORKFLOW_REGISTRY,\n    UnknownWorkflowError,\n    WorkflowAdapter,\n    WorkflowDescriptor,\n    WorkflowFamily,\n    WorkflowRegistry,\n    WorkflowResolution,\n    WorkflowResolutionStatus,\n    WorkflowResolver,\n)\nfrom app.universal.runtime import (
    EngineAdapter,
    EngineBindingError,
    EngineInitializationError,
    EngineRenderError,
    EngineRuntimeError,
    EngineRuntimeRegistry,
)

__all__ = [
    "AssetRef",\n    "BUILTIN_WORKFLOW_DESCRIPTORS",\n    "BUILTIN_WORKFLOW_REGISTRY",
    "BUILTIN_ENGINE_IDS",
    "build_builtin_engine_runtime_registry",
    "DiagnosticSeverity",
    "EngineAdapter",
    "EngineCapabilityResolution",
    "EngineCapabilityResolver",
    "EngineDiagnostic",
    "EngineBindingError",
    "EngineCapabilities",
    "EngineChoice",
    "EngineCompatibilityError",
    "EngineDescriptor",
    "EngineInitializationError",
    "EnginePreference",
    "EnginePreferenceStatus",
    "EngineRegistry",
    "EngineRegistryError",
    "EngineRenderError",
    "EngineRenderRequest",
    "EngineResourceAssessment",
    "EngineResourceContext",
    "EnginePlanResolution",
    "EnginePlanResolver",
    "EnginePlanStatus",
    "ProfilePreferenceResolution",
    "ProfilePreferenceResolver",
    "EngineRuntimeError",
    "EngineRuntimeRegistry",
    "EngineUnavailableError",
    "MultiSceneExecutionCoordinator",
    "MultiSceneExecutionError",
    "MultiSceneExecutionRequest",
    "MultiSceneExecutionResult",
    "NormalizedSegment",
    "ProfiledScenePlanProposal",
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
    "UniversalState",\n    "UnknownWorkflowError",\n    "WorkflowAdapter",\n    "WorkflowDescriptor",\n    "WorkflowFamily",\n    "WorkflowRegistry",\n    "WorkflowResolution",\n    "WorkflowResolutionStatus",\n    "WorkflowResolver",
    "apply_profiled_scene_plan_proposal",
    "build_profiled_scene_plan_proposal",
]
