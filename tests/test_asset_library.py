from __future__ import annotations

import hashlib
import struct
from dataclasses import replace

import pytest

from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.visual_assets import AssetProvenance


def png_bytes(width: int = 32, height: int = 24) -> bytes:
    # The importer validates the bounded PNG signature/IHDR header; it does not
    # decode image pixels. The remaining bytes make a deterministic test fixture.
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"test-image-payload"
    )


def test_import_copies_image_and_persists_verified_catalog(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")

    asset = library.import_file(
        source,
        kind="background",
        tags=("space", "nebula"),
        provenance=AssetProvenance(source="user-upload", license="user-declared"),
    )

    assert asset.content_sha256 == hashlib.sha256(png_bytes()).hexdigest()
    assert asset.media_type == "image/png"
    assert (asset.width, asset.height) == (32, 24)
    assert asset.location.startswith("assets/")
    assert library.verify_asset(asset) is True
    assert (library.root / asset.location).read_bytes() == png_bytes()

    loaded = VisualAssetLibrary(library.root).load_catalog()
    assert loaded.catalog_id == "voxora-visual-library"
    assert loaded.assets == (asset,)


def test_reimporting_identical_content_is_idempotent(tmp_path):
    source = tmp_path / "one.png"
    source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")

    first = library.import_file(source)
    second = library.import_file(source)

    assert first == second
    assert len(library.load_catalog().assets) == 1


def test_content_addressed_asset_id_is_stable_across_source_names(tmp_path):
    first_source = tmp_path / "first.png"
    second_source = tmp_path / "second.png"
    first_source.write_bytes(png_bytes())
    second_source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")

    first = library.import_file(first_source)
    second = library.import_file(second_source)

    assert first.asset_id == second.asset_id
    assert first.location == second.location
    assert len(library.load_catalog().assets) == 1


def test_custom_asset_id_collision_with_different_content_fails(tmp_path):
    one = tmp_path / "one.png"
    two = tmp_path / "two.png"
    one.write_bytes(png_bytes())
    two.write_bytes(png_bytes(10, 10))
    library = VisualAssetLibrary(tmp_path / "library")
    library.import_file(one, asset_id="custom-image")

    with pytest.raises(AssetImportError, match="already identifies different content"):
        library.import_file(two, asset_id="custom-image")

    assert len(library.load_catalog().assets) == 1


@pytest.mark.parametrize(
    "filename,payload",
    [
        ("bad.png", b"not an image"),
        ("wrong.jpg", png_bytes()),
        ("empty.png", b""),
        ("active.svg", b"<svg></svg>"),
    ],
)
def test_unsupported_malformed_or_mismatched_files_are_rejected(tmp_path, filename, payload):
    source = tmp_path / filename
    source.write_bytes(payload)
    library = VisualAssetLibrary(tmp_path / "library")

    with pytest.raises(AssetImportError):
        library.import_file(source)

    assert library.load_catalog().assets == ()
    assert not library.catalog_path.exists()


def test_file_size_and_pixel_limits_are_enforced(tmp_path):
    source = tmp_path / "large.png"
    source.write_bytes(png_bytes(100, 100))
    too_small_file_limit = VisualAssetLibrary(tmp_path / "file-limit", max_file_bytes=20)
    too_small_pixel_limit = VisualAssetLibrary(tmp_path / "pixel-limit", max_pixels=100)

    with pytest.raises(AssetImportError, match="maximum file size"):
        too_small_file_limit.import_file(source)
    with pytest.raises(AssetImportError, match="pixel limit"):
        too_small_pixel_limit.import_file(source)


def test_invalid_tags_and_asset_ids_do_not_change_catalog(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")

    with pytest.raises(AssetImportError, match="tags"):
        library.import_file(source, tags="not-a-sequence")
    with pytest.raises(AssetImportError):
        library.import_file(source, asset_id="../outside")

    assert library.load_catalog().assets == ()


def test_verify_detects_modified_content_and_missing_file(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source)
    stored = library.root / asset.location

    stored.write_bytes(b"modified")
    assert library.verify_asset(asset) is False
    stored.unlink()
    with pytest.raises(AssetImportError, match="missing"):
        library.verify_asset(asset)


def test_verify_rejects_path_traversal(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")
    asset = library.import_file(source)

    with pytest.raises(AssetImportError, match="safe relative path"):
        library.verify_asset(replace(asset, location="../../outside.png"))


def test_catalog_symlink_is_rejected_when_supported(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(png_bytes())
    library = VisualAssetLibrary(tmp_path / "library")
    library.import_file(source)
    external = tmp_path / "external.json"
    external.write_text('{"catalog_version": 1, "catalog_id": "external"}', encoding="utf-8")
    library.catalog_path.unlink()
    try:
        library.catalog_path.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available on this platform")

    with pytest.raises(AssetImportError, match="symbolic link"):
        library.load_catalog()
