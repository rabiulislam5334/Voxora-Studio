from app.universal.builtins import BUILTIN_ENGINE_IDS, build_builtin_engine_runtime_registry
from app.universal.adapters.workflows import (
    DocumentaryWorkflowAdapter,
    EngineBackedWorkflowAdapter,
    WorkflowAdapterCompatibilityError,
    WorkflowAdapterError,
    TwoDStorytellingAdapter,
)
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
from app.universal.composition import (
    COMPOSITION_FIT_MODES,
    CompositionCanvas,
    CompositionElement,
    CompositionValidationError,
    SceneComposition,
    VisualTransform,
)
from app.universal.models import (
    AssetRef,
    EngineChoice,
    ScenePlan,
    UniversalState,
)
from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.visual_assets import (
    AssetProvenance,
    CharacterAppearance,
    CharacterDefinition,
    VisualAsset,
    VisualAssetCatalog,
    VisualAssetValidationError,
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
from app.universal.narration_segmentation import (
    NarrationSegmentationConfig,
    segment_narration,
)
from app.universal.storyboard_diagnostics import (
    StoryboardDiagnostic,
    StoryboardDiagnosticSeverity,
    diagnose_storyboard,
)
from app.universal.storyboard_builder import (
    StoryboardBuilderConfig,
    build_storyboard_proposal,
)
from app.universal.storyboard_apply import (
    StoryboardApplyPreview,
    StoryboardPreviewDiagnostic,
    StoryboardScenePreview,
    apply_storyboard_proposal,
    preview_storyboard_apply,
)
from app.universal.storyboard_execution import (
    StoryboardExecutionApprovalError,
    StoryboardExecutionError,
    StoryboardExecutionReadinessError,
    StoryboardWorkflowExecutionCoordinator,
)
from app.universal.storyboard import (
    ContinuityKind,
    ContinuityReference,
    NarrationSource,
    NarrationTextUnit,
    ProposalReviewStatus,
    StoryboardBeat,
    StoryboardProposal,
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)
from app.universal.workflow import (
    BUILTIN_WORKFLOW_DESCRIPTORS,
    BUILTIN_WORKFLOW_REGISTRY,
    UnknownWorkflowError,
    WorkflowAdapter,
    WorkflowDescriptor,
    WorkflowFamily,
    WorkflowRegistry,
    WorkflowResolution,
    WorkflowResolutionStatus,
    WorkflowResolver,
)
from app.universal.runtime import (
    EngineAdapter,
    EngineBindingError,
    EngineInitializationError,
    EngineRenderError,
    EngineRuntimeError,
    EngineRuntimeRegistry,
)

__all__ = [
    "COMPOSITION_FIT_MODES",
    "CompositionCanvas",
    "CompositionElement",
    "CompositionValidationError",
    "SceneComposition",
    "VisualTransform",
    "AssetImportError",
    "VisualAssetLibrary",
    "SceneAssetBinding",
    "SceneBindingError",
    "SceneBindingPreview",
    "SceneCharacterBinding",
    "SceneBindingDiagnostic",
    "apply_scene_bindings",
    "preview_scene_bindings",
    "AssetContinuityDiagnostic",
    "AssetContinuityReport",
    "AssetReuseGroup",
    "CharacterContinuityGroup",
    "analyze_asset_continuity",
    "AssetRef",
    "AssetProvenance",
    "CharacterAppearance",
    "CharacterDefinition",
    "VisualAsset",
    "VisualAssetCatalog",
    "VisualAssetValidationError",
    "DocumentaryWorkflowAdapter",
    "EngineBackedWorkflowAdapter",
    "WorkflowAdapterCompatibilityError",
    "WorkflowAdapterError",
    "TwoDStorytellingAdapter",
    "BUILTIN_WORKFLOW_DESCRIPTORS",
    "BUILTIN_WORKFLOW_REGISTRY",
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
    "UniversalState",
    "UnknownWorkflowError",
    "WorkflowAdapter",
    "WorkflowDescriptor",
    "WorkflowFamily",
    "WorkflowRegistry",
    "WorkflowResolution",
    "WorkflowResolutionStatus",
    "WorkflowResolver",
    "NarrationSegmentationConfig",
    "segment_narration",
    "ContinuityKind",
    "ContinuityReference",
    "NarrationSource",
    "NarrationTextUnit",
    "ProposalReviewStatus",
    "StoryboardBeat",
    "StoryboardDiagnostic",
    "StoryboardDiagnosticSeverity",
    "diagnose_storyboard",
    "StoryboardBuilderConfig",
    "build_storyboard_proposal",
    "StoryboardApplyPreview",
    "StoryboardPreviewDiagnostic",
    "StoryboardScenePreview",
    "apply_storyboard_proposal",
    "preview_storyboard_apply",
    "StoryboardExecutionApprovalError",
    "StoryboardExecutionError",
    "StoryboardExecutionReadinessError",
    "StoryboardWorkflowExecutionCoordinator",
    "StoryboardProposal",
    "StoryboardValidationError",
    "TimingBasis",
    "TimingInterval",
    "apply_profiled_scene_plan_proposal",
    "build_profiled_scene_plan_proposal",
]

from app.universal.scene_asset_bindings import (
    SceneAssetBinding, SceneBindingError, SceneBindingPreview,
    SceneCharacterBinding, SceneBindingDiagnostic, apply_scene_bindings,
    preview_scene_bindings,
)
from app.universal.asset_continuity import (
    AssetContinuityDiagnostic, AssetContinuityReport, AssetReuseGroup,
    CharacterContinuityGroup, analyze_asset_continuity,
)

from app.universal.composition_workflow import (
    CompositionDiagnostic,
    CompositionElementPreview,
    SceneCompositionPreview,
    SceneCompositionWorkflowError,
    apply_scene_composition,
    preview_scene_composition,
)

__all__ += [
    "CompositionDiagnostic",
    "CompositionElementPreview",
    "SceneCompositionPreview",
    "SceneCompositionWorkflowError",
    "apply_scene_composition",
    "preview_scene_composition",
]
