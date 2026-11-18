from __future__ import annotations

import copy
import hashlib

import pytest

from app.universal.visual_assets import (
    AssetProvenance,
    CharacterAppearance,
    CharacterDefinition,
    VisualAsset,
    VisualAssetCatalog,
    VisualAssetValidationError,
)


def sample_catalog():
    portrait = VisualAsset(
        asset_id="asset-portrait",
        kind="character_reference",
        location="assets/characters/aria/portrait.png",
        content_sha256=hashlib.sha256(b"portrait").hexdigest(),
        media_type="image/png",
        width=512,
        height=512,
        tags=("portrait", "character"),
        provenance=AssetProvenance(
            source="user_import",
            license="user_owned",
            attribution="Created by project owner",
        ),
    )
    character = CharacterDefinition(
        character_id="aria",
        display_name="Aria",
        description="A recurring explorer character.",
        appearance=CharacterAppearance(
            appearance_id="aria-v1",
            visual_description="Short dark hair, round glasses, teal jacket.",
            reference_asset_ids=("asset-portrait",),
            style_tags=("2d", "flat_vector"),
            attributes={"hair": "dark", "jacket": "teal", "glasses": True},
        ),
    )
    return VisualAssetCatalog(
        catalog_id="project-visuals",
        assets=(portrait,),
        characters=(character,),
        metadata={"purpose": "storytelling"},
    )


def test_catalog_round_trips_assets_characters_and_provenance():
    catalog = sample_catalog()
    restored = VisualAssetCatalog.from_dict(catalog.to_dict())
    assert restored.to_dict() == catalog.to_dict()
    assert restored.characters[0].appearance.reference_asset_ids == ("asset-portrait",)
    assert restored.assets[0].provenance.license == "user_owned"


def test_character_appearance_fingerprint_is_stable_and_content_sensitive():
    appearance = sample_catalog().characters[0].appearance
    assert len(appearance.appearance_fingerprint) == 64
    assert appearance.appearance_fingerprint == CharacterAppearance.from_dict(
        appearance.to_dict()
    ).appearance_fingerprint
    changed = CharacterAppearance(
        "aria-v1", "Different outfit", ("asset-portrait",), ("2d", "flat_vector"),
        {"hair": "dark", "jacket": "red", "glasses": True},
    )
    assert changed.appearance_fingerprint != appearance.appearance_fingerprint


def test_catalog_rejects_duplicate_asset_and_character_ids():
    catalog = sample_catalog()
    with pytest.raises(VisualAssetValidationError, match="asset IDs must be unique"):
        VisualAssetCatalog("duplicate-assets", (catalog.assets[0], catalog.assets[0]))
    with pytest.raises(VisualAssetValidationError, match="character IDs must be unique"):
        VisualAssetCatalog(
            "duplicate-characters", (), (catalog.characters[0], catalog.characters[0])
        )


def test_character_references_must_resolve_to_catalog_assets():
    character = CharacterDefinition(
        "aria", "Aria", "", CharacterAppearance(
            "aria-v1", "Dark hair and teal jacket.", ("missing-asset",)
        )
    )
    with pytest.raises(VisualAssetValidationError, match="unknown assets"):
        VisualAssetCatalog("broken", (), (character,))


def test_visual_asset_validates_hash_dimensions_and_tags():
    with pytest.raises(VisualAssetValidationError, match="SHA-256"):
        VisualAsset("bad-hash", "background", "bg.png", content_sha256="not-a-hash")
    with pytest.raises(VisualAssetValidationError, match="width"):
        VisualAsset("bad-size", "background", "bg.png", width=0)
    with pytest.raises(VisualAssetValidationError, match="must not contain duplicates"):
        VisualAsset("bad-tags", "background", "bg.png", tags=("night", "night"))


def test_metadata_rejects_non_json_values_and_non_finite_numbers():
    with pytest.raises(VisualAssetValidationError, match="JSON-compatible"):
        VisualAsset("bad-meta", "prop", "key.png", metadata={"callback": lambda: None})
    with pytest.raises(VisualAssetValidationError, match="NaN or infinity"):
        CharacterAppearance("v1", "A stable look.", attributes={"scale": float("nan")})


def test_unknown_fields_are_preserved_without_mutating_input():
    raw = sample_catalog().to_dict()
    raw["future_catalog_field"] = {"nested": [1, 2, 3]}
    raw["assets"][0]["future_asset_field"] = "preserve-me"
    original = copy.deepcopy(raw)
    restored = VisualAssetCatalog.from_dict(raw)
    assert raw == original
    output = restored.to_dict()
    assert output["future_catalog_field"] == {"nested": [1, 2, 3]}
    assert output["assets"][0]["future_asset_field"] == "preserve-me"


def test_catalog_rejects_unknown_future_version():
    raw = sample_catalog().to_dict()
    raw["catalog_version"] = 999
    with pytest.raises(VisualAssetValidationError, match="future"):
        VisualAssetCatalog.from_dict(raw)


def test_character_appearance_fingerprint_detects_tampering():
    raw = sample_catalog().characters[0].appearance.to_dict()
    raw["visual_description"] = "Changed after fingerprinting"
    with pytest.raises(VisualAssetValidationError, match="fingerprint"):
        CharacterAppearance.from_dict(raw)
