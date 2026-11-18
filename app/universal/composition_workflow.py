"""Scene composition binding, preview diagnostics, and explicit persistence.

All operations are deterministic and renderer-independent. Preview is read-only;
persistence is opt-in and stored additively in UniversalState.extra.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from app.models.project import Project
from app.models.scene import Scene
from app.universal.composition import SceneComposition
from app.universal.models import UniversalState


SCENE_COMPOSITIONS_KEY = "scene_compositions"
SCENE_COMPOSITION_STORAGE_VERSION = 1


class SceneCompositionWorkflowError(ValueError):
    """Raised when composition preview or explicit persistence is unsafe."""


@dataclass(frozen=True)
class CompositionDiagnostic:
    code: str
    severity: str
    message: str
    subject_id: Optional[str] = None
    related_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositionElementPreview:
    element_id: str
    asset_id: str
    layer_order: int
    fit_mode: str
    visible: bool
    opacity: float
    x_px: float
    y_px: float
    width_px: float
    height_px: float


@dataclass(frozen=True)
class SceneCompositionPreview:
    project_id: str
    scene_id: str
    composition_id: str
    composition_fingerprint: str
    target_fingerprint: str
    canvas_width: int
    canvas_height: int
    elements: Tuple[CompositionElementPreview, ...]
    diagnostics: Tuple[CompositionDiagnostic, ...]

    @property
    def is_valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


def _target_fingerprint(project: Project, scene_id: str) -> str:
    if not isinstance(project.settings, dict):
        raise SceneCompositionWorkflowError("project.settings must be an object")
    scene = project.get_scene(scene_id)
    if scene is None:
        raise SceneCompositionWorkflowError(f"unknown scene: {scene_id}")
    state = UniversalState.from_project_settings(project.settings)
    plan = state.scene_plans.get(scene_id) if not state.read_only else None
    payload = {
        "project_id": project.id,
        "scene": {
            "id": scene.id,
            "title": scene.title,
            "text": scene.text,
            "notes": scene.notes,
            "visual_prompt": scene.visual_prompt,
            "order": scene.order,
        },
        "universal": state.raw_payload if state.read_only else state.to_dict(),
        "scene_plan": plan.to_dict() if plan is not None else None,
    }
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SceneCompositionWorkflowError(
            f"project state cannot be fingerprinted safely: {exc}"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _intersects(left: CompositionElementPreview, right: CompositionElementPreview) -> bool:
    return (
        min(left.x_px + left.width_px, right.x_px + right.width_px)
        > max(left.x_px, right.x_px)
        and min(left.y_px + left.height_px, right.y_px + right.height_px)
        > max(left.y_px, right.y_px)
    )


def preview_scene_composition(
    project: Project,
    composition: SceneComposition,
) -> SceneCompositionPreview:
    """Resolve existing scene asset bindings and produce a read-only layout preview.

    Pixel geometry is derived from normalized coordinates. Rotation is retained
    in the source composition but overlap diagnostics use unrotated rectangles.
    No image bytes are opened and no renderer is invoked.
    """
    if not isinstance(project, Project):
        raise SceneCompositionWorkflowError("project must be a Project")
    if not isinstance(composition, SceneComposition):
        raise SceneCompositionWorkflowError("composition must be a SceneComposition")
    if not isinstance(project.settings, dict):
        raise SceneCompositionWorkflowError("project.settings must be an object")
    scene = project.get_scene(composition.scene_id)
    diagnostics = []
    if scene is None:
        diagnostics.append(CompositionDiagnostic(
            "SCENE_NOT_FOUND", "error",
            "The composition references a scene that does not exist.",
            composition.scene_id,
        ))
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        diagnostics.append(CompositionDiagnostic(
            "UNIVERSAL_STATE_READ_ONLY", "error",
            "Universal project data is malformed or from a future version; composition cannot be safely validated.",
        ))
        bound_asset_ids = set()
        plan = None
    else:
        plan = state.scene_plans.get(composition.scene_id)
        bound_asset_ids = {
            item.asset_id for item in plan.asset_refs
        } if plan is not None else set()
    if not composition.elements:
        diagnostics.append(CompositionDiagnostic(
            "EMPTY_COMPOSITION", "error",
            "A composition must contain at least one visual element.",
            composition.composition_id,
        ))
    elements = []
    for item in sorted(composition.elements, key=lambda value: (value.layer_order, value.element_id)):
        if item.asset_id not in bound_asset_ids:
            diagnostics.append(CompositionDiagnostic(
                "ELEMENT_ASSET_NOT_BOUND", "error",
                f"Asset '{item.asset_id}' is not bound to this scene.",
                item.element_id, (item.asset_id,),
            ))
        transform = item.transform
        elements.append(CompositionElementPreview(
            element_id=item.element_id,
            asset_id=item.asset_id,
            layer_order=item.layer_order,
            fit_mode=item.fit_mode,
            visible=item.visible,
            opacity=transform.opacity,
            x_px=transform.x * composition.canvas.width,
            y_px=transform.y * composition.canvas.height,
            width_px=transform.width * composition.canvas.width,
            height_px=transform.height * composition.canvas.height,
        ))
        if not item.visible:
            diagnostics.append(CompositionDiagnostic(
                "ELEMENT_HIDDEN", "info",
                "This element is hidden in the composition preview.", item.element_id,
            ))
        elif transform.opacity == 0:
            diagnostics.append(CompositionDiagnostic(
                "ELEMENT_FULLY_TRANSPARENT", "warning",
                "This visible element has zero opacity.", item.element_id,
            ))
    visible = [item for item in elements if item.visible and item.opacity > 0]
    for index, left in enumerate(visible):
        for right in visible[index + 1:]:
            if _intersects(left, right):
                diagnostics.append(CompositionDiagnostic(
                    "ELEMENT_OVERLAP", "warning",
                    "These elements overlap in their unrotated layout bounds; overlap may be intentional.",
                    left.element_id, (right.element_id,),
                ))
                if left.layer_order == right.layer_order:
                    diagnostics.append(CompositionDiagnostic(
                        "OVERLAP_SAME_LAYER_ORDER", "warning",
                        "Overlapping elements share the same layer order; set an explicit stacking order if needed.",
                        left.element_id, (right.element_id,),
                    ))
    return SceneCompositionPreview(
        project_id=project.id,
        scene_id=composition.scene_id,
        composition_id=composition.composition_id,
        composition_fingerprint=composition.fingerprint,
        target_fingerprint=_target_fingerprint(project, composition.scene_id)
        if scene is not None else "",
        canvas_width=composition.canvas.width,
        canvas_height=composition.canvas.height,
        elements=tuple(elements),
        diagnostics=tuple(diagnostics),
    )


def apply_scene_composition(
    project: Project,
    composition: SceneComposition,
    preview: SceneCompositionPreview,
    *,
    approved: bool = False,
) -> None:
    """Persist a reviewed composition under Universal settings after explicit approval.

    Existing project scenes, ScenePlans, asset bindings, and legacy project schema
    remain unchanged. The composition for this scene is replaced as one atomic
    settings update after stale-preview and forward-version checks.
    """
    if approved is not True:
        raise SceneCompositionWorkflowError(
            "explicit approval is required before persisting a scene composition"
        )
    if not isinstance(project, Project):
        raise SceneCompositionWorkflowError("project must be a Project")
    if not isinstance(composition, SceneComposition):
        raise SceneCompositionWorkflowError("composition must be a SceneComposition")
    if not isinstance(preview, SceneCompositionPreview):
        raise SceneCompositionWorkflowError("preview must be a SceneCompositionPreview")
    if not preview.is_valid:
        raise SceneCompositionWorkflowError("composition preview contains blocking diagnostics")
    if preview.project_id != project.id or preview.scene_id != composition.scene_id:
        raise SceneCompositionWorkflowError("preview belongs to a different project or scene")
    current = preview_scene_composition(project, composition)
    if (
        current.composition_id != preview.composition_id
        or current.composition_fingerprint != preview.composition_fingerprint
        or current.target_fingerprint != preview.target_fingerprint
        or current.elements != preview.elements
        or current.diagnostics != preview.diagnostics
    ):
        raise SceneCompositionWorkflowError(
            "composition preview is stale; rebuild and review it before applying"
        )
    if not current.is_valid:
        raise SceneCompositionWorkflowError("current composition preview is not valid")
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise SceneCompositionWorkflowError("Universal project data is read-only")
    stored = state.extra.get(SCENE_COMPOSITIONS_KEY, {})
    if not isinstance(stored, dict):
        raise SceneCompositionWorkflowError("stored scene_compositions data is malformed")
    existing = stored.get(composition.scene_id)
    if existing is not None:
        if not isinstance(existing, dict):
            raise SceneCompositionWorkflowError("stored scene composition entry is malformed")
        version = existing.get("storage_version", SCENE_COMPOSITION_STORAGE_VERSION)
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != SCENE_COMPOSITION_STORAGE_VERSION
        ):
            raise SceneCompositionWorkflowError("stored scene composition uses an unsupported storage version")
        existing_payload = existing.get("composition")
        if not isinstance(existing_payload, dict):
            raise SceneCompositionWorkflowError("stored scene composition payload is malformed")
        try:
            SceneComposition.from_dict(existing_payload)
        except (TypeError, ValueError) as exc:
            raise SceneCompositionWorkflowError(
                f"stored scene composition cannot be safely replaced: {exc}"
            ) from exc
    next_state = copy.deepcopy(state)
    next_stored = copy.deepcopy(stored)
    next_stored[composition.scene_id] = {
        "storage_version": SCENE_COMPOSITION_STORAGE_VERSION,
        "composition": composition.to_dict(),
        "composition_fingerprint": composition.fingerprint,
    }
    next_state.extra[SCENE_COMPOSITIONS_KEY] = next_stored
    next_settings = next_state.apply_to_project_settings(project.settings)
    project.settings = next_settings
    project.touch()
