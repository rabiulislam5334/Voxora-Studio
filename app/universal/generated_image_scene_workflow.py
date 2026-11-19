"""Reviewed handoff from generated images into Project scene plans.

Generated files first enter the VisualAssetLibrary. This module provides a
narrow, explicit next step: preview their use in a scene, then apply only
after approval. It never edits project state during preview.
"""
from __future__ import annotations

from typing import Iterable

from app.models.project import Project
from app.universal.scene_asset_bindings import (
    SceneAssetBinding,
    SceneBindingError,
    SceneBindingPreview,
    apply_scene_bindings,
    preview_scene_bindings,
)
from app.universal.visual_assets import VisualAssetCatalog


def preview_generated_image_binding(
    project: Project,
    catalog: VisualAssetCatalog,
    scene_id: str,
    asset_ids: Iterable[str],
    *,
    role: str = "visual",
) -> SceneBindingPreview:
    """Build a read-only binding preview for generated-image assets only."""
    if not isinstance(role, str) or not role.strip():
        raise SceneBindingError("role must be a non-empty string")
    if isinstance(asset_ids, (str, bytes)):
        raise SceneBindingError("asset_ids must be a sequence of asset IDs")
    try:
        selected_ids = tuple(asset_ids)
    except TypeError:
        raise SceneBindingError("asset_ids must be a sequence of asset IDs") from None
    if not selected_ids:
        raise SceneBindingError("select at least one generated image")
    if len(set(selected_ids)) != len(selected_ids):
        raise SceneBindingError("generated image selection must not contain duplicates")

    assets = {asset.asset_id: asset for asset in catalog.assets}
    bindings = []
    for asset_id in selected_ids:
        asset = assets.get(asset_id)
        if asset is None:
            raise SceneBindingError(f"generated image is not in the catalog: {asset_id}")
        provenance = asset.provenance
        if asset.kind != "generated-image" or provenance is None or not provenance.source.startswith("generated:"):
            raise SceneBindingError(f"asset is not a verified generated image: {asset_id}")
        bindings.append(SceneAssetBinding(asset_id=asset_id, role=role.strip()))

    return preview_scene_bindings(
        project, catalog, scene_id, asset_bindings=tuple(bindings)
    )


def apply_generated_image_binding(
    project: Project,
    catalog: VisualAssetCatalog,
    preview: SceneBindingPreview,
    *,
    approved: bool = False,
) -> None:
    """Apply a previously reviewed generated-image binding proposal."""
    if not isinstance(preview, SceneBindingPreview):
        raise SceneBindingError("a SceneBindingPreview is required")
    for binding in preview.asset_bindings:
        asset = next((item for item in catalog.assets if item.asset_id == binding.asset_id), None)
        provenance = asset.provenance if asset is not None else None
        if (asset is None or asset.kind != "generated-image" or provenance is None
                or not provenance.source.startswith("generated:")):
            raise SceneBindingError("preview contains an asset that is no longer a generated image")
    apply_scene_bindings(project, catalog, preview, approved=approved)
