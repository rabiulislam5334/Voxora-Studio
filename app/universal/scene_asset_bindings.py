"""Explicit, reviewable bindings between Project scenes and library assets/characters."""
from __future__ import annotations
import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple
from app.models.project import Project
from app.universal.models import AssetRef, ScenePlan, UniversalState
from app.universal.visual_assets import VisualAssetCatalog

class SceneBindingError(ValueError):
    """Raised when a scene binding proposal is invalid or stale."""

@dataclass(frozen=True)
class SceneAssetBinding:
    asset_id: str
    role: str = "visual"
    def __post_init__(self):
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise SceneBindingError("asset_id must be a non-empty string")
        if not isinstance(self.role, str) or not self.role.strip():
            raise SceneBindingError("asset role must be a non-empty string")

@dataclass(frozen=True)
class SceneCharacterBinding:
    character_id: str
    appearance_id: str
    appearance_fingerprint: str
    reference_asset_ids: Tuple[str, ...]
    style_tags: Tuple[str, ...]

@dataclass(frozen=True)
class SceneBindingDiagnostic:
    code: str
    severity: str
    message: str
    subject_id: Optional[str] = None

@dataclass(frozen=True)
class SceneBindingPreview:
    project_id: str
    scene_id: str
    target_fingerprint: str
    asset_bindings: Tuple[SceneAssetBinding, ...]
    character_bindings: Tuple[SceneCharacterBinding, ...]
    diagnostics: Tuple[SceneBindingDiagnostic, ...]
    @property
    def is_valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

def _fingerprint(project: Project, scene_id: str) -> str:
    scene = project.get_scene(scene_id)
    if scene is None:
        raise SceneBindingError(f"unknown scene: {scene_id}")
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise SceneBindingError("Universal project state is read-only")
    plan = state.scene_plans.get(scene_id)
    payload = {
        "project_id": project.id,
        "scene": {"id": scene.id, "title": scene.title, "text": scene.text,
                  "notes": scene.notes, "visual_prompt": scene.visual_prompt, "order": scene.order},
        "plan": plan.to_dict() if plan else None,
        "universal_extra": state.extra,
    }
    try:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SceneBindingError(f"scene state cannot be fingerprinted: {exc}") from exc
    return hashlib.sha256(raw).hexdigest()

def preview_scene_bindings(project: Project, catalog: VisualAssetCatalog, scene_id: str,
                           *, asset_bindings: Tuple[SceneAssetBinding, ...] = (),
                           character_ids: Tuple[str, ...] = ()) -> SceneBindingPreview:
    """Build a deterministic read-only proposal; no Project/catalog mutation."""
    if not isinstance(project, Project) or not isinstance(catalog, VisualAssetCatalog):
        raise SceneBindingError("project and catalog must be valid domain objects")
    if project.get_scene(scene_id) is None:
        raise SceneBindingError(f"unknown scene: {scene_id}")
    if isinstance(asset_bindings, (str, bytes)) or isinstance(character_ids, (str, bytes)):
        raise SceneBindingError("bindings and character_ids must be sequences")
    assets, requested = tuple(asset_bindings), tuple(character_ids)
    if not all(isinstance(item, SceneAssetBinding) for item in assets):
        raise SceneBindingError("asset_bindings must contain SceneAssetBinding values")
    if len({item.asset_id for item in assets}) != len(assets):
        raise SceneBindingError("asset bindings must not contain duplicate asset IDs")
    if any(not isinstance(item, str) or not item.strip() for item in requested) or len(set(requested)) != len(requested):
        raise SceneBindingError("character_ids must be unique non-empty strings")
    diagnostics = []
    asset_map = {item.asset_id: item for item in catalog.assets}
    character_map = {item.character_id: item for item in catalog.characters}
    for binding in assets:
        if binding.asset_id not in asset_map:
            diagnostics.append(SceneBindingDiagnostic("ASSET_NOT_IN_CATALOG", "error",
                f"Asset '{binding.asset_id}' is not present in the supplied catalog.", binding.asset_id))
    chars = []
    for character_id in requested:
        character = character_map.get(character_id)
        if character is None:
            diagnostics.append(SceneBindingDiagnostic("CHARACTER_NOT_IN_CATALOG", "error",
                f"Character '{character_id}' is not present in the supplied catalog.", character_id))
        else:
            appearance = character.appearance
            chars.append(SceneCharacterBinding(character_id, appearance.appearance_id,
                appearance.appearance_fingerprint, appearance.reference_asset_ids, appearance.style_tags))
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        diagnostics.append(SceneBindingDiagnostic("UNIVERSAL_STATE_READ_ONLY", "error",
            "Universal project data is malformed or from a future version."))
    else:
        plan = state.scene_plans.get(scene_id)
        existing_assets = {item.asset_id for item in plan.asset_refs} if plan else set()
        existing_chars = set()
        if plan:
            raw = plan.requirements.get("character_bindings", [])
            if not isinstance(raw, list):
                diagnostics.append(SceneBindingDiagnostic("CHARACTER_BINDINGS_INVALID", "error",
                    "Existing character_bindings must be a list."))
            else:
                existing_chars = {item.get("character_id") for item in raw if isinstance(item, dict)}
        for binding in assets:
            if binding.asset_id in existing_assets:
                diagnostics.append(SceneBindingDiagnostic("ASSET_ALREADY_BOUND", "error",
                    "This asset is already bound to the scene.", binding.asset_id))
        for binding in chars:
            if binding.character_id in existing_chars:
                diagnostics.append(SceneBindingDiagnostic("CHARACTER_ALREADY_BOUND", "error",
                    "This character is already bound to the scene.", binding.character_id))
    return SceneBindingPreview(project.id, scene_id, _fingerprint(project, scene_id),
                               assets, tuple(chars), tuple(diagnostics))

def apply_scene_bindings(project: Project, catalog: VisualAssetCatalog,
                         preview: SceneBindingPreview, *, approved: bool = False) -> None:
    """Atomically append reviewed bindings to the existing ScenePlan."""
    if approved is not True:
        raise SceneBindingError("explicit approval is required before applying scene bindings")
    if not isinstance(preview, SceneBindingPreview) or not preview.is_valid:
        raise SceneBindingError("a valid SceneBindingPreview is required")
    if preview.project_id != project.id:
        raise SceneBindingError("preview belongs to a different Project")
    current = preview_scene_bindings(project, catalog, preview.scene_id,
        asset_bindings=preview.asset_bindings,
        character_ids=tuple(item.character_id for item in preview.character_bindings))
    if (not current.is_valid or current.target_fingerprint != preview.target_fingerprint
            or current.asset_bindings != preview.asset_bindings
            or current.character_bindings != preview.character_bindings):
        raise SceneBindingError("scene binding preview is stale; rebuild and review it")
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise SceneBindingError("Universal project state is read-only")
    next_state = copy.deepcopy(state)
    plan = next_state.scene_plans.get(preview.scene_id)
    if plan is None:
        plan = ScenePlan(scene_id=preview.scene_id)
        next_state.scene_plans[preview.scene_id] = plan
    asset_map = {item.asset_id: item for item in catalog.assets}
    for binding in preview.asset_bindings:
        asset = asset_map[binding.asset_id]
        plan.asset_refs.append(AssetRef(asset_id=asset.asset_id, kind=asset.kind,
            path=asset.location, identity=asset.content_sha256,
            license=asset.provenance.license if asset.provenance else None,
            metadata={"role": binding.role, "location": asset.location,
                      "media_type": asset.media_type, "width": asset.width, "height": asset.height}))
    raw_chars = plan.requirements.get("character_bindings", [])
    if not isinstance(raw_chars, list):
        raise SceneBindingError("existing character_bindings must be a list")
    plan.requirements["character_bindings"] = [*copy.deepcopy(raw_chars), *[{
        "character_id": item.character_id, "appearance_id": item.appearance_id,
        "appearance_fingerprint": item.appearance_fingerprint,
        "reference_asset_ids": list(item.reference_asset_ids), "style_tags": list(item.style_tags),
    } for item in preview.character_bindings]]
    project.settings = next_state.apply_to_project_settings(project.settings)
    project.touch()
