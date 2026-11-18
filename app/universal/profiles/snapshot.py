"""Versioned, data-only snapshots of channel profiles stored with projects."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from app.universal.profiles.models import ChannelProfile, ProfileValidationError

PROFILE_SNAPSHOT_VERSION = 1


@dataclass(frozen=True)
class ProfileSnapshot:
    """Immutable envelope preserving the profile definition selected by a project."""

    profile_data: Mapping[str, Any]
    selected_preset_id: Optional[str] = None
    snapshot_version: int = PROFILE_SNAPSHOT_VERSION
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)
    read_only: bool = False
    raw_payload: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.snapshot_version, bool) or not isinstance(self.snapshot_version, int) or self.snapshot_version < 1:
            raise ProfileValidationError("profile snapshot version must be a positive integer")
        if self.read_only:
            object.__setattr__(self, "raw_payload", copy.deepcopy(self.raw_payload))
            return
        profile = ChannelProfile.from_dict(self.profile_data)
        if profile.read_only:
            raise ProfileValidationError("future profile schemas cannot be written into a current snapshot")
        if self.selected_preset_id is not None and self.selected_preset_id not in {
            preset.preset_id for preset in profile.presets
        }:
            raise ProfileValidationError("selected_preset_id must identify a preset in the profile")
        object.__setattr__(self, "profile_data", copy.deepcopy(profile.to_dict()))
        object.__setattr__(self, "extra", copy.deepcopy(dict(self.extra)))

    @property
    def profile_id(self) -> str:
        if self.read_only:
            raw = self.raw_payload if isinstance(self.raw_payload, Mapping) else {}
            profile = raw.get("profile_data", {})
            value = profile.get("profile_id") if isinstance(profile, Mapping) else None
            return value if isinstance(value, str) else "unsupported"
        return str(self.profile_data["profile_id"])

    def to_dict(self) -> dict[str, Any]:
        if self.read_only:
            return copy.deepcopy(self.raw_payload)
        result = {
            "snapshot_version": PROFILE_SNAPSHOT_VERSION,
            "profile_data": copy.deepcopy(dict(self.profile_data)),
            "selected_preset_id": self.selected_preset_id,
        }
        for key, value in self.extra.items():
            if key not in result:
                result[key] = copy.deepcopy(value)
        return result

    @classmethod
    def from_profile(cls, profile: ChannelProfile, *, selected_preset_id: Optional[str] = None) -> "ProfileSnapshot":
        if not isinstance(profile, ChannelProfile):
            raise ProfileValidationError("profile must be a ChannelProfile")
        if profile.read_only:
            raise ProfileValidationError("a read-only future profile cannot be snapshotted")
        return cls(profile_data=profile.to_dict(), selected_preset_id=selected_preset_id)

    @classmethod
    def from_dict(cls, data: Any) -> "ProfileSnapshot":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("profile_snapshot must be an object")
        version = data.get("snapshot_version", PROFILE_SNAPSHOT_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ProfileValidationError("profile_snapshot.snapshot_version must be a positive integer")
        if version > PROFILE_SNAPSHOT_VERSION:
            return cls(profile_data={}, snapshot_version=version, read_only=True, raw_payload=copy.deepcopy(dict(data)))
        known = {"snapshot_version", "profile_data", "selected_preset_id"}
        profile_data = data.get("profile_data")
        if not isinstance(profile_data, Mapping):
            raise ProfileValidationError("profile_snapshot.profile_data must be an object")
        selected = data.get("selected_preset_id")
        if selected is not None and not isinstance(selected, str):
            raise ProfileValidationError("profile_snapshot.selected_preset_id must be a string or null")
        return cls(
            profile_data=profile_data,
            selected_preset_id=selected,
            snapshot_version=version,
            extra={key: copy.deepcopy(value) for key, value in data.items() if key not in known},
        )
