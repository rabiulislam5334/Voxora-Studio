"""Local, content-addressed visual asset storage and safe raster import.

The library copies supported local raster images into a managed directory,
records verified metadata in a JSON catalog, and never performs network,
provider, AI, or rendering work.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import threading
from pathlib import Path
from typing import Optional

from app.universal.visual_assets import (
    AssetProvenance,
    VisualAsset,
    VisualAssetCatalog,
    VisualAssetValidationError,
)


class AssetImportError(ValueError):
    """Raised when a local asset cannot be safely imported or verified."""


_SUPPORTED = {
    ".png": ("image/png", "png"),
    ".jpg": ("image/jpeg", "jpeg"),
    ".jpeg": ("image/jpeg", "jpeg"),
    ".gif": ("image/gif", "gif"),
    ".bmp": ("image/bmp", "bmp"),
}
_MAX_HEADER_BYTES = 1024 * 1024
_DEFAULT_MAX_FILE_BYTES = 100 * 1024 * 1024
_DEFAULT_MAX_PIXELS = 100_000_000


def _dimensions(header: bytes) -> tuple[str, int, int]:
    """Return (media_type, width, height) from a supported raster header."""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(header) < 24 or header[12:16] != b"IHDR":
            raise AssetImportError("PNG header is incomplete or invalid")
        width, height = struct.unpack(">II", header[16:24])
        return "image/png", width, height

    if header.startswith((b"GIF87a", b"GIF89a")):
        if len(header) < 10:
            raise AssetImportError("GIF header is incomplete")
        width, height = struct.unpack("<HH", header[6:10])
        return "image/gif", width, height

    if header.startswith(b"BM"):
        if len(header) < 26:
            raise AssetImportError("BMP header is incomplete")
        dib_size = struct.unpack("<I", header[14:18])[0]
        if dib_size == 12:
            width, height = struct.unpack("<HH", header[18:22])
        elif dib_size >= 40 and len(header) >= 26:
            width, signed_height = struct.unpack("<ii", header[18:26])
            height = abs(signed_height)
        else:
            raise AssetImportError("Unsupported BMP DIB header")
        return "image/bmp", width, height

    if header.startswith(b"\xff\xd8"):
        offset = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while offset + 4 <= len(header):
            if header[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(header) and header[offset] == 0xFF:
                offset += 1
            if offset >= len(header):
                break
            marker = header[offset]
            offset += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
                continue
            if offset + 2 > len(header):
                break
            segment_length = struct.unpack(">H", header[offset:offset + 2])[0]
            if segment_length < 2:
                raise AssetImportError("Invalid JPEG segment length")
            if marker in sof_markers:
                if segment_length < 7 or offset + 7 > len(header):
                    raise AssetImportError("JPEG frame header is incomplete")
                height, width = struct.unpack(">HH", header[offset + 3:offset + 7])
                return "image/jpeg", width, height
            offset += segment_length
        raise AssetImportError("JPEG dimensions were not found in the first MiB")

    raise AssetImportError("Unsupported or unrecognized image format (PNG, JPEG, GIF, BMP only)")


def _safe_relative_location(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or not candidate.parts or any(part in ("..", "") for part in candidate.parts):
        raise AssetImportError("Asset location must be a safe relative path")
    return candidate


class VisualAssetLibrary:
    """Thread-safe, local-only image importer backed by a JSON asset catalog."""

    def __init__(
        self,
        root: os.PathLike[str] | str,
        *,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
        max_pixels: int = _DEFAULT_MAX_PIXELS,
    ) -> None:
        if isinstance(max_file_bytes, bool) or not isinstance(max_file_bytes, int) or max_file_bytes <= 0:
            raise AssetImportError("max_file_bytes must be a positive integer")
        if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or max_pixels <= 0:
            raise AssetImportError("max_pixels must be a positive integer")
        self.root = Path(root).expanduser().resolve()
        self.max_file_bytes = max_file_bytes
        self.max_pixels = max_pixels
        self.catalog_path = self.root / "catalog.json"
        self._lock = threading.RLock()

    def load_catalog(self) -> VisualAssetCatalog:
        if self.catalog_path.is_symlink():
            raise AssetImportError("Catalog path must not be a symbolic link")
        if not self.catalog_path.exists():
            return VisualAssetCatalog(catalog_id="voxora-visual-library")
        try:
            with self.catalog_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            return VisualAssetCatalog.from_dict(payload)
        except (OSError, json.JSONDecodeError, VisualAssetValidationError) as exc:
            raise AssetImportError(f"Cannot read visual asset catalog: {exc}") from exc

    def import_file(
        self,
        source_path: os.PathLike[str] | str,
        *,
        kind: str = "image",
        asset_id: Optional[str] = None,
        tags: tuple[str, ...] = (),
        provenance: Optional[AssetProvenance] = None,
    ) -> VisualAsset:
        """Copy one supported local image, verify it, and atomically update catalog."""
        source = Path(source_path).expanduser()
        if source.is_symlink():
            raise AssetImportError("Symbolic-link source files are not accepted")
        try:
            source = source.resolve(strict=True)
            if not source.is_file():
                raise AssetImportError("Source must be a regular file")
            if source.suffix.lower() not in _SUPPORTED:
                raise AssetImportError("File extension is not a supported raster image")
            if not isinstance(kind, str) or not kind.strip():
                raise AssetImportError("kind must be a non-empty string")
            if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
                raise AssetImportError("asset_id must be a non-empty string or null")
            if provenance is not None and not isinstance(provenance, AssetProvenance):
                raise AssetImportError("provenance must be AssetProvenance or null")
            if isinstance(tags, (str, bytes)):
                raise AssetImportError("tags must be a sequence of strings")
            try:
                tags = tuple(tags)
            except TypeError:
                raise AssetImportError("tags must be a sequence of strings") from None
        except OSError as exc:
            raise AssetImportError(f"Cannot access source file: {exc}") from exc

        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            staging_path: Optional[Path] = None
            stored_path: Optional[Path] = None
            created_asset = False
            try:
                digest = hashlib.sha256()
                byte_count = 0
                fd, temp_name = tempfile.mkstemp(prefix=".voxora-import-", dir=str(self.root))
                staging_path = Path(temp_name)
                with os.fdopen(fd, "wb") as output, source.open("rb") as input_stream:
                    while True:
                        chunk = input_stream.read(1024 * 1024)
                        if not chunk:
                            break
                        byte_count += len(chunk)
                        if byte_count > self.max_file_bytes:
                            raise AssetImportError("Image exceeds configured maximum file size")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

                if byte_count == 0:
                    raise AssetImportError("Cannot import an empty file")
                with staging_path.open("rb") as stream:
                    header = stream.read(_MAX_HEADER_BYTES)
                media_type, width, height = _dimensions(header)
                expected_media_type = _SUPPORTED[source.suffix.lower()][0]
                if media_type != expected_media_type:
                    raise AssetImportError("File extension does not match detected image content")
                if width <= 0 or height <= 0 or width * height > self.max_pixels:
                    raise AssetImportError("Image dimensions are invalid or exceed configured pixel limit")

                content_hash = digest.hexdigest()
                extension = ".jpg" if media_type == "image/jpeg" else source.suffix.lower()
                relative = Path("assets") / content_hash[:2] / f"{content_hash}{extension}"
                stored_path = self.root / relative
                stored_path.parent.mkdir(parents=True, exist_ok=True)
                for directory in (self.root / "assets", stored_path.parent):
                    if directory.is_symlink():
                        raise AssetImportError("Refusing to write through a symbolic-link directory")
                try:
                    stored_path.parent.resolve().relative_to(self.root)
                except ValueError:
                    raise AssetImportError("Asset destination escapes the library root") from None
                if stored_path.is_symlink():
                    raise AssetImportError("Refusing to write through a symbolic link")
                if stored_path.exists():
                    if self._hash_file(stored_path) != content_hash:
                        raise AssetImportError("Content-addressed destination exists with different content")
                else:
                    try:
                        os.link(staging_path, stored_path)
                        created_asset = True
                    except FileExistsError:
                        if self._hash_file(stored_path) != content_hash:
                            raise AssetImportError("Concurrent import created a conflicting destination")
                    except OSError:
                        if stored_path.exists():
                            if self._hash_file(stored_path) != content_hash:
                                raise AssetImportError("Content-addressed destination conflict")
                        else:
                            os.replace(staging_path, stored_path)
                            created_asset = True

                relative_location = relative.as_posix()
                catalog = self.load_catalog()
                resolved_id = asset_id or f"asset-{content_hash[:24]}"
                existing = next((item for item in catalog.assets if item.asset_id == resolved_id), None)
                if existing is not None:
                    if existing.content_sha256 != content_hash:
                        raise AssetImportError(f"Asset ID '{resolved_id}' already identifies different content")
                    if created_asset and stored_path.exists():
                        stored_path.unlink()
                        created_asset = False
                    return existing

                asset = VisualAsset(
                    asset_id=resolved_id,
                    kind=kind.strip(),
                    location=relative_location,
                    content_sha256=content_hash,
                    media_type=media_type,
                    width=width,
                    height=height,
                    tags=tuple(tags),
                    provenance=provenance,
                    metadata={"file_size_bytes": byte_count},
                )
                updated = VisualAssetCatalog(
                    catalog_id=catalog.catalog_id,
                    assets=catalog.assets + (asset,),
                    characters=catalog.characters,
                    catalog_version=catalog.catalog_version,
                    metadata=catalog.metadata,
                    extra=catalog.extra,
                )
                self._write_catalog(updated)
                return asset
            except (VisualAssetValidationError, TypeError) as exc:
                if created_asset and stored_path is not None and stored_path.exists():
                    stored_path.unlink()
                raise AssetImportError(str(exc)) from exc
            except Exception:
                if created_asset and stored_path is not None and stored_path.exists():
                    stored_path.unlink()
                raise
            finally:
                if staging_path is not None and staging_path.exists():
                    staging_path.unlink()

    def verify_asset(self, asset: VisualAsset) -> bool:
        """Verify that a catalog asset resolves inside this library and matches its hash."""
        if not isinstance(asset, VisualAsset):
            raise AssetImportError("asset must be a VisualAsset")
        relative = _safe_relative_location(asset.location)
        unresolved_target = self.root / relative
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise AssetImportError("Asset location traverses a symbolic link")
        target = unresolved_target.resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            raise AssetImportError("Asset location escapes the library root") from None
        if not target.is_file():
            raise AssetImportError("Asset file is missing or is not a regular file")
        if asset.content_sha256 is None:
            raise AssetImportError("Asset has no verified SHA-256 identity")
        return self._hash_file(target) == asset.content_sha256


    def resolve_asset_path(self, asset: VisualAsset) -> Path:
        """Resolve an asset path without following symlinks or leaving the library."""
        if not isinstance(asset, VisualAsset):
            raise AssetImportError("asset must be a VisualAsset")
        relative = _safe_relative_location(asset.location)
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise AssetImportError("Asset location traverses a symbolic link")
        target = current.resolve()
        try:
            target.relative_to(self.root)
        except ValueError:
            raise AssetImportError("Asset location escapes the library root") from None
        if not target.is_file():
            raise AssetImportError("Asset file is missing or is not a regular file")
        return target

    def update_asset(self, asset: VisualAsset) -> VisualAsset:
        """Replace editable catalog metadata for an existing asset; file bytes stay untouched."""
        if not isinstance(asset, VisualAsset):
            raise AssetImportError("asset must be a VisualAsset")
        with self._lock:
            catalog = self.load_catalog()
            if not any(item.asset_id == asset.asset_id for item in catalog.assets):
                raise AssetImportError(f"Unknown asset ID: {asset.asset_id}")
            updated = VisualAssetCatalog(
                catalog_id=catalog.catalog_id,
                assets=tuple(asset if item.asset_id == asset.asset_id else item for item in catalog.assets),
                characters=catalog.characters,
                catalog_version=catalog.catalog_version,
                metadata=catalog.metadata,
                extra=catalog.extra,
            )
            self._write_catalog(updated)
            return asset

    def remove_asset(self, asset_id: str) -> VisualAsset:
        """Remove an asset from the catalog, retaining its content-addressed file on disk."""
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise AssetImportError("asset_id must be a non-empty string")
        with self._lock:
            catalog = self.load_catalog()
            asset = next((item for item in catalog.assets if item.asset_id == asset_id), None)
            if asset is None:
                raise AssetImportError(f"Unknown asset ID: {asset_id}")
            references = [
                character.character_id for character in catalog.characters
                if asset_id in character.appearance.reference_asset_ids
            ]
            if references:
                raise AssetImportError(
                    "Asset is referenced by characters: " + ", ".join(sorted(references))
                )
            updated = VisualAssetCatalog(
                catalog_id=catalog.catalog_id,
                assets=tuple(item for item in catalog.assets if item.asset_id != asset_id),
                characters=catalog.characters,
                catalog_version=catalog.catalog_version,
                metadata=catalog.metadata,
                extra=catalog.extra,
            )
            self._write_catalog(updated)
            return asset

    def save_character(self, character) :
        """Insert or replace a character while validating all reference asset IDs."""
        from app.universal.visual_assets import CharacterDefinition

        if not isinstance(character, CharacterDefinition):
            raise AssetImportError("character must be a CharacterDefinition")
        with self._lock:
            catalog = self.load_catalog()
            existing = any(item.character_id == character.character_id for item in catalog.characters)
            characters = (
                tuple(character if item.character_id == character.character_id else item
                      for item in catalog.characters)
                if existing else catalog.characters + (character,)
            )
            try:
                updated = VisualAssetCatalog(
                    catalog_id=catalog.catalog_id,
                    assets=catalog.assets,
                    characters=characters,
                    catalog_version=catalog.catalog_version,
                    metadata=catalog.metadata,
                    extra=catalog.extra,
                )
            except VisualAssetValidationError as exc:
                raise AssetImportError(str(exc)) from exc
            self._write_catalog(updated)
            return character

    def remove_character(self, character_id: str):
        """Remove a character definition without changing any scene/project references."""
        if not isinstance(character_id, str) or not character_id.strip():
            raise AssetImportError("character_id must be a non-empty string")
        with self._lock:
            catalog = self.load_catalog()
            character = next(
                (item for item in catalog.characters if item.character_id == character_id), None
            )
            if character is None:
                raise AssetImportError(f"Unknown character ID: {character_id}")
            updated = VisualAssetCatalog(
                catalog_id=catalog.catalog_id,
                assets=catalog.assets,
                characters=tuple(
                    item for item in catalog.characters if item.character_id != character_id
                ),
                catalog_version=catalog.catalog_version,
                metadata=catalog.metadata,
                extra=catalog.extra,
            )
            self._write_catalog(updated)
            return character

    def _write_catalog(self, catalog: VisualAssetCatalog) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(catalog.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=".voxora-catalog-", dir=str(self.root))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.catalog_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
