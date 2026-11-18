from app.universal.asset_library import VisualAssetLibrary
from app.universal.visual_assets import (
    AssetProvenance, CharacterAppearance, CharacterDefinition, VisualAsset,
)
from app.ui.asset_library_tab import format_asset_inspection, format_character_inspection


def test_asset_inspection_includes_verified_metadata_and_provenance():
    asset = VisualAsset(
        asset_id="nebula-01", kind="background", location="assets/aa/image.png",
        content_sha256="a" * 64, media_type="image/png", width=1920, height=1080,
        tags=("space", "nebula"),
        provenance=AssetProvenance(source="user-upload", license="CC0", attribution="NASA"),
        metadata={"file_size_bytes": 4096},
    )
    result = format_asset_inspection(asset)
    assert "Dimensions: 1920 × 1080" in result
    assert "File size: 4,096 bytes" in result
    assert "SHA-256: " + "a" * 64 in result
    assert "Tags: space, nebula" in result
    assert "License declaration: CC0" in result


def test_character_inspection_exposes_stable_appearance_identity():
    character = CharacterDefinition(
        character_id="captain", display_name="Captain", description="A recurring character",
        appearance=CharacterAppearance(
            appearance_id="captain-v1", visual_description="Blue coat and silver hair",
            reference_asset_ids=("portrait-01",), style_tags=("2d", "watercolor"),
        ),
    )
    result = format_character_inspection(character)
    assert "Character ID: captain" in result
    assert "Appearance ID: captain-v1" in result
    assert character.appearance.appearance_fingerprint in result
    assert "Reference assets: portrait-01" in result
