"""Safe handoff of scene-bound generated images into visual compositions.

This helper never binds assets or persists project state. It only returns a new
composition proposal containing generated images that are already bound to the
target scene. The caller remains responsible for preview and explicit apply.
"""
from __future__ import annotations

from app.models.project import Project
from app.universal.composition import (
    CompositionElement,
    SceneComposition,
    VisualTransform,
)
from app.universal.models import UniversalState
from app.universal.visual_assets import VisualAssetCatalog


class GeneratedImageCompositionError(ValueError):
    """Raised when generated-image composition integration is unsafe."""


def append_bound_generated_images(
    project: Project,
    catalog: VisualAssetCatalog,
    composition: SceneComposition,
    *,
    max_assets: int = 12,
) -> SceneComposition:
    """Return a composition with a compact grid of newly eligible generated images.

    Only assets already bound to the composition's scene and carrying verified
    generated-image provenance are considered. Existing composition elements
    are preserved and never duplicated.
    """
    if not isinstance(project, Project):
        raise GeneratedImageCompositionError("project must be a Project")
    if not isinstance(catalog, VisualAssetCatalog):
        raise GeneratedImageCompositionError("catalog must be a VisualAssetCatalog")
    if not isinstance(composition, SceneComposition):
        raise GeneratedImageCompositionError("composition must be a SceneComposition")
    if isinstance(max_assets, bool) or not isinstance(max_assets, int) or not 1 <= max_assets <= 48:
        raise GeneratedImageCompositionError("max_assets must be an integer between 1 and 48")
    if project.get_scene(composition.scene_id) is None:
        raise GeneratedImageCompositionError("composition scene does not exist in the project")

    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise GeneratedImageCompositionError("Universal project state is read-only")
    plan = state.scene_plans.get(composition.scene_id)
    if plan is None:
        raise GeneratedImageCompositionError("bind generated images to this scene before composing")

    assets = {asset.asset_id: asset for asset in catalog.assets}
    existing_asset_ids = {element.asset_id for element in composition.elements}
    candidates = []
    for reference in plan.asset_refs:
        if reference.kind != "generated-image" or reference.asset_id in existing_asset_ids:
            continue
        asset = assets.get(reference.asset_id)
        provenance = asset.provenance if asset is not None else None
        if (
            asset is None
            or asset.kind != "generated-image"
            or provenance is None
            or not isinstance(provenance.source, str)
            or not provenance.source.startswith("generated:")
        ):
            raise GeneratedImageCompositionError(
                f"bound generated image is missing or has invalid provenance: {reference.asset_id}"
            )
        candidates.append(asset)

    if not candidates:
        raise GeneratedImageCompositionError(
            "no new verified generated images are bound to this scene"
        )
    if len(candidates) > max_assets:
        raise GeneratedImageCompositionError(
            f"{len(candidates)} generated images are available; add at most {max_assets} per layout"
        )

    columns = min(3, len(candidates))
    rows = (len(candidates) + columns - 1) // columns
    gap = 0.02
    cell_width = (1.0 - gap * (columns + 1)) / columns
    cell_height = (1.0 - gap * (rows + 1)) / rows
    elements = list(composition.elements)
    used_ids = {element.element_id for element in elements}
    next_layer = max((element.layer_order for element in elements), default=-1) + 1

    for index, asset in enumerate(candidates):
        row, column = divmod(index, columns)
        element_number = index + 1
        element_id = f"generated-{element_number:04d}"
        while element_id in used_ids:
            element_number += 1
            element_id = f"generated-{element_number:04d}"
        used_ids.add(element_id)
        elements.append(CompositionElement(
            element_id=element_id,
            asset_id=asset.asset_id,
            transform=VisualTransform(
                x=gap + column * (cell_width + gap),
                y=gap + row * (cell_height + gap),
                width=cell_width,
                height=cell_height,
            ),
            layer_order=next_layer + index,
            fit_mode="contain",
            label=f"Generated · {asset.asset_id}",
            metadata={"composition_source": "generated-image", "layout": "auto-grid"},
        ))

    return SceneComposition(
        composition_id=composition.composition_id,
        scene_id=composition.scene_id,
        canvas=composition.canvas,
        elements=tuple(elements),
        composition_version=composition.composition_version,
        metadata=composition.metadata,
        extra=composition.extra,
    )
