"""Channel profile domain contracts and built-in profile registry."""

from app.universal.profiles.models import (
    PROFILE_SCHEMA_VERSION,
    ChannelProfile,
    ProductionDefaults,
    ProductionPreset,
    ProductionRule,
    ProfileValidationError,
    VisualDefaults,
)
from app.universal.profiles.snapshot import PROFILE_SNAPSHOT_VERSION, ProfileSnapshot
from app.universal.profiles.evaluator import ProfileDiagnostic, evaluate_profile_rules
from app.universal.profiles.registry import (
    BUILTIN_PROFILE_REGISTRY,
    BuiltinProfileRegistry,
    get_builtin_profile,
    list_builtin_profiles,
)

__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "PROFILE_SNAPSHOT_VERSION",
    "ProfileSnapshot",
    "ProfileDiagnostic",
    "evaluate_profile_rules",
    "BUILTIN_PROFILE_REGISTRY",
    "BuiltinProfileRegistry",
    "ChannelProfile",
    "ProductionDefaults",
    "ProductionPreset",
    "ProductionRule",
    "ProfileValidationError",
    "VisualDefaults",
    "get_builtin_profile",
    "list_builtin_profiles",
]
