from __future__ import annotations

import struct

import pytest

from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.visual_assets import CharacterAppearance, CharacterDefinition


def _png(width=8, height=8):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
            + b"\x00\x00\x00\x00payload")


def _character(refs=()):
    return CharacterDefinition(
        character_id="hero", display_name="Hero", description="",
        appearance=CharacterAppearance(
            appearance_id="hero-v1", visual_description="Red jacket",
            reference_asset_ids=tuple(refs), style_tags=("2d",),
        ),
    )


def test_character_create_update_and_reload_round_trip(tmp_path):
    source = tmp_path / "ref.png"
    source.write_bytes(_png())
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source)
    first = _character((asset.asset_id,))
    library.save_character(first)
    updated = CharacterDefinition(
        character_id="hero", display_name="The Hero", description="Updated",
        appearance=CharacterAppearance(
            appearance_id="hero-v2", visual_description="Blue jacket",
            reference_asset_ids=(asset.asset_id,), style_tags=("2d", "cinematic"),
        ),
    )
    library.save_character(updated)
    loaded = VisualAssetLibrary(library.root).load_catalog()
    assert loaded.characters == (updated,)


def test_character_rejects_unknown_reference_asset_without_catalog_mutation(tmp_path):
    library = VisualAssetLibrary(tmp_path / "library")
    with pytest.raises(AssetImportError, match="unknown assets"):
        library.save_character(_character(("missing-image",)))
    assert library.load_catalog().characters == ()


def test_asset_metadata_update_persists_and_preserves_file(tmp_path):
    from dataclasses import replace
    from app.universal.visual_assets import AssetProvenance

    source = tmp_path / "image.png"
    source.write_bytes(_png())
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source)
    updated = replace(
        asset, kind="character-reference", tags=("hero",),
        provenance=AssetProvenance(source="manual", license="CC0"),
    )
    library.update_asset(updated)
    assert library.load_catalog().assets == (updated,)
    assert library.verify_asset(updated)
    assert library.resolve_asset_path(updated).is_file()


def test_asset_remove_is_blocked_while_character_references_it(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(_png())
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source)
    library.save_character(_character((asset.asset_id,)))
    with pytest.raises(AssetImportError, match="referenced by characters"):
        library.remove_asset(asset.asset_id)
    library.remove_character("hero")
    removed = library.remove_asset(asset.asset_id)
    assert removed == asset
    assert library.load_catalog().assets == ()
    assert (library.root / asset.location).is_file()


def test_remove_unknown_character_and_asset_raise_clear_errors(tmp_path):
    library = VisualAssetLibrary(tmp_path / "library")
    with pytest.raises(AssetImportError, match="Unknown character"):
        library.remove_character("missing")
    with pytest.raises(AssetImportError, match="Unknown asset"):
        library.remove_asset("missing")


def test_asset_file_identity_cannot_be_changed_through_metadata_api(tmp_path):
    from dataclasses import replace

    source = tmp_path / "image.png"
    source.write_bytes(_png())
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source)
    tampered = replace(asset, content_sha256="b" * 64)
    with pytest.raises(AssetImportError, match="identity.*immutable"):
        library.update_asset(tampered)
    assert library.load_catalog().assets == (asset,)
