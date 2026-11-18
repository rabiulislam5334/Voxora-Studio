"""Renderer-independent visual asset and character continuity contracts.

These records describe assets and recurring characters. They do not load files,
generate artwork, contact providers, or mutate Project/.voxora data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple


VISUAL_ASSET_CATALOG_VERSION = 1
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


class VisualAssetValidationError(ValueError):
    """Raised when visual asset or character data is invalid."""


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise VisualAssetValidationError(f"{name} must be a stable non-empty identifier")
    return value


def _string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise VisualAssetValidationError(
            f"{name} must be a {'string' if allow_empty else 'non-empty string'}"
        )
    return value


def _json_value(value: Any, path: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return copy.deepcopy(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VisualAssetValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise VisualAssetValidationError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    raise VisualAssetValidationError(f"{path} must contain JSON-compatible values only")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualAssetValidationError(f"{name} must be an object")
    return _json_value(value, name)


def _string_tuple(value: Any, name: str) -> Tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise VisualAssetValidationError(f"{name} must be a sequence of strings")
    try:
        result = tuple(_string(item, f"{name}[]") for item in value)
    except TypeError:
        raise VisualAssetValidationError(f"{name} must be a sequence of strings") from None
    if len(set(result)) != len(result):
        raise VisualAssetValidationError(f"{name} must not contain duplicates")
    return result


def _unknown(data: Mapping[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in data.items() if key not in known}


def _merge(data: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
    return data


@dataclass(frozen=True)
class AssetProvenance:
    """Origin and licensing facts supplied by the asset owner or importer."""

    source: str
    license: Optional[str] = None
    attribution: Optional[str] = None
    source_uri: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _string(self.source, "provenance.source")
        for name in ("license", "attribution", "source_uri"):
            value = getattr(self, name)
            if value is not None:
                _string(value, f"provenance.{name}")
        object.__setattr__(self, "metadata", _mapping(self.metadata, "provenance.metadata"))
        object.__setattr__(self, "extra", _mapping(self.extra, "provenance.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "source": self.source, "license": self.license,
            "attribution": self.attribution, "source_uri": self.source_uri,
            "metadata": _mapping(self.metadata, "provenance.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "AssetProvenance":
        if not isinstance(data, Mapping):
            raise VisualAssetValidationError("asset provenance must be an object")
        known = {"source", "license", "attribution", "source_uri", "metadata"}
        return cls(data.get("source"), data.get("license"), data.get("attribution"),
                   data.get("source_uri"), data.get("metadata", {}), _unknown(data, known))


@dataclass(frozen=True)
class VisualAsset:
    """A stable pointer to a visual file; the contract never reads that file."""

    asset_id: str
    kind: str
    location: str
    content_sha256: Optional[str] = None
    media_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    tags: Tuple[str, ...] = ()
    provenance: Optional[AssetProvenance] = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _id(self.asset_id, "asset_id")
        _string(self.kind, "asset.kind")
        _string(self.location, "asset.location")
        if self.content_sha256 is not None and (
            not isinstance(self.content_sha256, str)
            or not _SHA256_PATTERN.fullmatch(self.content_sha256)
        ):
            raise VisualAssetValidationError("asset.content_sha256 must be a 64-character SHA-256 hex digest")
        if self.media_type is not None:
            _string(self.media_type, "asset.media_type")
        for name in ("width", "height"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise VisualAssetValidationError(f"asset.{name} must be a positive integer or null")
        object.__setattr__(self, "tags", _string_tuple(self.tags, "asset.tags"))
        if self.provenance is not None and not isinstance(self.provenance, AssetProvenance):
            raise VisualAssetValidationError("asset.provenance must be AssetProvenance or null")
        object.__setattr__(self, "metadata", _mapping(self.metadata, "asset.metadata"))
        object.__setattr__(self, "extra", _mapping(self.extra, "asset.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "asset_id": self.asset_id, "kind": self.kind, "location": self.location,
            "content_sha256": self.content_sha256, "media_type": self.media_type,
            "width": self.width, "height": self.height, "tags": list(self.tags),
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "metadata": _mapping(self.metadata, "asset.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "VisualAsset":
        if not isinstance(data, Mapping):
            raise VisualAssetValidationError("visual asset must be an object")
        known = {"asset_id", "kind", "location", "content_sha256", "media_type",
                 "width", "height", "tags", "provenance", "metadata"}
        raw_provenance = data.get("provenance")
        return cls(
            data.get("asset_id"), data.get("kind"), data.get("location"),
            data.get("content_sha256"), data.get("media_type"), data.get("width"),
            data.get("height"), tuple(data.get("tags", ())),
            AssetProvenance.from_dict(raw_provenance) if raw_provenance is not None else None,
            data.get("metadata", {}), _unknown(data, known),
        )


@dataclass(frozen=True)
class CharacterAppearance:
    """One versioned visual identity shared by every scene using a character."""

    appearance_id: str
    visual_description: str
    reference_asset_ids: Tuple[str, ...] = ()
    style_tags: Tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _id(self.appearance_id, "appearance_id")
        _string(self.visual_description, "appearance.visual_description")
        object.__setattr__(self, "reference_asset_ids",
                           _string_tuple(self.reference_asset_ids, "appearance.reference_asset_ids"))
        object.__setattr__(self, "style_tags", _string_tuple(self.style_tags, "appearance.style_tags"))
        object.__setattr__(self, "attributes", _mapping(self.attributes, "appearance.attributes"))
        object.__setattr__(self, "extra", _mapping(self.extra, "appearance.extra"))

    @property
    def appearance_fingerprint(self) -> str:
        payload = {
            "appearance_id": self.appearance_id,
            "visual_description": self.visual_description,
            "reference_asset_ids": list(self.reference_asset_ids),
            "style_tags": list(self.style_tags),
            "attributes": _mapping(self.attributes, "appearance.attributes"),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "appearance_id": self.appearance_id,
            "visual_description": self.visual_description,
            "reference_asset_ids": list(self.reference_asset_ids),
            "style_tags": list(self.style_tags),
            "attributes": _mapping(self.attributes, "appearance.attributes"),
            "appearance_fingerprint": self.appearance_fingerprint,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "CharacterAppearance":
        if not isinstance(data, Mapping):
            raise VisualAssetValidationError("character appearance must be an object")
        known = {"appearance_id", "visual_description", "reference_asset_ids",
                 "style_tags", "attributes", "appearance_fingerprint"}
        result = cls(data.get("appearance_id"), data.get("visual_description"),
                     tuple(data.get("reference_asset_ids", ())),
                     tuple(data.get("style_tags", ())), data.get("attributes", {}),
                     _unknown(data, known))
        fingerprint = data.get("appearance_fingerprint")
        if fingerprint is not None and fingerprint != result.appearance_fingerprint:
            raise VisualAssetValidationError("character appearance fingerprint does not match its content")
        return result


@dataclass(frozen=True)
class CharacterDefinition:
    """Reusable character identity; scenes reference its stable character_id."""

    character_id: str
    display_name: str
    description: str
    appearance: CharacterAppearance
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _id(self.character_id, "character_id")
        _string(self.display_name, "character.display_name")
        _string(self.description, "character.description", allow_empty=True)
        if not isinstance(self.appearance, CharacterAppearance):
            raise VisualAssetValidationError("character.appearance must be CharacterAppearance")
        object.__setattr__(self, "metadata", _mapping(self.metadata, "character.metadata"))
        object.__setattr__(self, "extra", _mapping(self.extra, "character.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "character_id": self.character_id, "display_name": self.display_name,
            "description": self.description, "appearance": self.appearance.to_dict(),
            "metadata": _mapping(self.metadata, "character.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "CharacterDefinition":
        if not isinstance(data, Mapping):
            raise VisualAssetValidationError("character definition must be an object")
        known = {"character_id", "display_name", "description", "appearance", "metadata"}
        return cls(data.get("character_id"), data.get("display_name"), data.get("description", ""),
                   CharacterAppearance.from_dict(data.get("appearance")),
                   data.get("metadata", {}), _unknown(data, known))


@dataclass(frozen=True)
class VisualAssetCatalog:
    """Versioned, deterministic catalog with validated character-to-asset links."""

    catalog_id: str
    assets: Tuple[VisualAsset, ...] = ()
    characters: Tuple[CharacterDefinition, ...] = ()
    catalog_version: int = VISUAL_ASSET_CATALOG_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _id(self.catalog_id, "catalog_id")
        if isinstance(self.catalog_version, bool) or not isinstance(self.catalog_version, int) or self.catalog_version < 1:
            raise VisualAssetValidationError("catalog_version must be a positive integer")
        assets, characters = tuple(self.assets), tuple(self.characters)
        if not all(isinstance(item, VisualAsset) for item in assets):
            raise VisualAssetValidationError("catalog.assets must contain VisualAsset values")
        if not all(isinstance(item, CharacterDefinition) for item in characters):
            raise VisualAssetValidationError("catalog.characters must contain CharacterDefinition values")
        asset_ids = [item.asset_id for item in assets]
        character_ids = [item.character_id for item in characters]
        if len(set(asset_ids)) != len(asset_ids):
            raise VisualAssetValidationError("catalog asset IDs must be unique")
        if len(set(character_ids)) != len(character_ids):
            raise VisualAssetValidationError("catalog character IDs must be unique")
        known_assets = set(asset_ids)
        for character in characters:
            missing = set(character.appearance.reference_asset_ids) - known_assets
            if missing:
                raise VisualAssetValidationError(
                    f"character '{character.character_id}' references unknown assets: {', '.join(sorted(missing))}"
                )
        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "characters", characters)
        object.__setattr__(self, "metadata", _mapping(self.metadata, "catalog.metadata"))
        object.__setattr__(self, "extra", _mapping(self.extra, "catalog.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "catalog_version": VISUAL_ASSET_CATALOG_VERSION,
            "catalog_id": self.catalog_id,
            "assets": [item.to_dict() for item in self.assets],
            "characters": [item.to_dict() for item in self.characters],
            "metadata": _mapping(self.metadata, "catalog.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "VisualAssetCatalog":
        if not isinstance(data, Mapping):
            raise VisualAssetValidationError("visual asset catalog must be an object")
        version = data.get("catalog_version", VISUAL_ASSET_CATALOG_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise VisualAssetValidationError("catalog_version must be a positive integer")
        if version > VISUAL_ASSET_CATALOG_VERSION:
            raise VisualAssetValidationError("unsupported future visual asset catalog version")
        known = {"catalog_version", "catalog_id", "assets", "characters", "metadata"}
        raw_assets, raw_characters = data.get("assets", []), data.get("characters", [])
        if not isinstance(raw_assets, (list, tuple)) or not isinstance(raw_characters, (list, tuple)):
            raise VisualAssetValidationError("catalog assets and characters must be arrays")
        return cls(data.get("catalog_id"),
                   tuple(VisualAsset.from_dict(item) for item in raw_assets),
                   tuple(CharacterDefinition.from_dict(item) for item in raw_characters),
                   version, data.get("metadata", {}), _unknown(data, known))
