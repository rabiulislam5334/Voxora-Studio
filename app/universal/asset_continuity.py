"""Read-only cross-scene asset reuse and character continuity analysis."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
from app.models.project import Project
from app.universal.models import UniversalState
from app.universal.visual_assets import VisualAssetCatalog

@dataclass(frozen=True)
class AssetContinuityDiagnostic:
    code: str
    severity: str
    message: str
    subject_id: Optional[str] = None
    scene_ids: Tuple[str, ...] = ()

@dataclass(frozen=True)
class AssetReuseGroup:
    identity: str
    asset_ids: Tuple[str, ...]
    scene_ids: Tuple[str, ...]

@dataclass(frozen=True)
class CharacterContinuityGroup:
    character_id: str
    scene_ids: Tuple[str, ...]
    appearance_fingerprints: Tuple[str, ...]

@dataclass(frozen=True)
class AssetContinuityReport:
    diagnostics: Tuple[AssetContinuityDiagnostic, ...]
    asset_reuse_groups: Tuple[AssetReuseGroup, ...]
    character_groups: Tuple[CharacterContinuityGroup, ...]

def analyze_asset_continuity(project: Project, catalog: VisualAssetCatalog) -> AssetContinuityReport:
    """Inspect current scene bindings against the library; never repairs or mutates."""
    if not isinstance(project, Project) or not isinstance(catalog, VisualAssetCatalog):
        raise ValueError("project and catalog must be valid domain objects")
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        return AssetContinuityReport((AssetContinuityDiagnostic(
            "UNIVERSAL_STATE_READ_ONLY", "error",
            "Universal project data is malformed or from a future version; continuity analysis was skipped.",
        ),), (), ())
    assets = {item.asset_id: item for item in catalog.assets}
    characters = {item.character_id: item for item in catalog.characters}
    scenes = {scene.id for scene in project.scenes}
    diagnostics, asset_scenes, character_scenes, content_scenes = [], {}, {}, {}
    for scene_id, plan in state.scene_plans.items():
        if scene_id not in scenes:
            diagnostics.append(AssetContinuityDiagnostic("PLAN_SCENE_MISSING", "warning",
                "A ScenePlan exists without a matching Project scene.", scene_id, (scene_id,)))
            continue
        for ref in plan.asset_refs:
            asset_scenes.setdefault(ref.asset_id, set()).add(scene_id)
            asset = assets.get(ref.asset_id)
            if asset is None:
                diagnostics.append(AssetContinuityDiagnostic("BOUND_ASSET_MISSING", "error",
                    f"Bound asset '{ref.asset_id}' is absent from the current catalog.", ref.asset_id, (scene_id,)))
                continue
            if ref.identity and asset.content_sha256 and ref.identity != asset.content_sha256:
                diagnostics.append(AssetContinuityDiagnostic("BOUND_ASSET_IDENTITY_CHANGED", "error",
                    "Catalog content identity differs from the identity captured by this scene.", ref.asset_id, (scene_id,)))
            if asset.content_sha256:
                content_scenes.setdefault(asset.content_sha256, {}).setdefault(asset.asset_id, set()).add(scene_id)
        raw = plan.requirements.get("character_bindings", [])
        if not isinstance(raw, list):
            diagnostics.append(AssetContinuityDiagnostic("CHARACTER_BINDINGS_INVALID", "error",
                "Scene character bindings are malformed.", scene_id, (scene_id,)))
            continue
        for item in raw:
            if not isinstance(item, dict):
                diagnostics.append(AssetContinuityDiagnostic("CHARACTER_BINDING_INVALID", "error",
                    "A character binding entry is not an object.", scene_id, (scene_id,)))
                continue
            cid, fingerprint = item.get("character_id"), item.get("appearance_fingerprint")
            if not isinstance(cid, str) or not isinstance(fingerprint, str):
                diagnostics.append(AssetContinuityDiagnostic("CHARACTER_BINDING_INVALID", "error",
                    "A character binding is missing its stable ID or appearance fingerprint.", str(cid), (scene_id,)))
                continue
            character_scenes.setdefault(cid, {}).setdefault(fingerprint, set()).add(scene_id)
            character = characters.get(cid)
            if character is None:
                diagnostics.append(AssetContinuityDiagnostic("BOUND_CHARACTER_MISSING", "error",
                    f"Bound character '{cid}' is absent from the current catalog.", cid, (scene_id,)))
            elif character.appearance.appearance_fingerprint != fingerprint:
                diagnostics.append(AssetContinuityDiagnostic("CHARACTER_APPEARANCE_CHANGED", "warning",
                    "Library appearance changed since this scene captured its binding; review before updating.",
                    cid, (scene_id,)))
            refs = item.get("reference_asset_ids", [])
            if not isinstance(refs, list):
                diagnostics.append(AssetContinuityDiagnostic("CHARACTER_BINDING_INVALID", "error",
                    "Character reference_asset_ids must be a list.", cid, (scene_id,)))
                continue
            for asset_id in refs:
                if not isinstance(asset_id, str) or asset_id not in assets:
                    diagnostics.append(AssetContinuityDiagnostic("CHARACTER_REFERENCE_ASSET_MISSING", "error",
                        f"Character '{cid}' references missing asset '{asset_id}'.", str(asset_id), (scene_id,)))
    reuse = []
    for aid, used in sorted(asset_scenes.items()):
        if len(used) > 1:
            reuse.append(AssetReuseGroup(aid, (aid,), tuple(sorted(used))))
    for digest, by_asset in sorted(content_scenes.items()):
        if len(by_asset) > 1:
            reuse.append(AssetReuseGroup(digest, tuple(sorted(by_asset)),
                tuple(sorted(set().union(*by_asset.values())))))
    groups = []
    for cid, by_fp in sorted(character_scenes.items()):
        used = tuple(sorted(set().union(*by_fp.values())))
        fingerprints = tuple(sorted(by_fp))
        groups.append(CharacterContinuityGroup(cid, used, fingerprints))
        if len(fingerprints) > 1:
            diagnostics.append(AssetContinuityDiagnostic("CHARACTER_APPEARANCE_INCONSISTENT", "warning",
                "The same character is bound with multiple appearance fingerprints across scenes.", cid, used))
    diagnostics.sort(key=lambda item: (item.code, item.subject_id or "", item.scene_ids))
    return AssetContinuityReport(tuple(diagnostics), tuple(reuse), tuple(groups))
