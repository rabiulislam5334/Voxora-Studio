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
from app.universal.profiles.registry import (
    BUILTIN_PROFILE_REGISTRY,
    BuiltinProfileRegistry,
    get_builtin_profile,
    list_builtin_profiles,
)

__all__ = [
    "PROFILE_SCHEMA_VERSION",
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
