"""Per-shot visual resolution for approved Production Director plans.

This coordinator reuses the existing VisualAssetLibrary and
VisualGenerationRuntime. It ranks verified, rights-described local assets first,
then optionally invokes one explicitly selected generation provider. It does
not fetch stock media, apply Project bindings, or render scenes.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.production_director import DirectorPlan, DirectorShot
from app.universal.profiles.models import ChannelProfile
from app.universal.storyboard import NarrationSource
from app.universal.visual_assets import VisualAsset, VisualAssetCatalog
from app.universal.visual_generation import VisualGenerationRequest
from app.universal.visual_generation_runtime import (
    VisualGenerationCancelled,
    VisualGenerationRuntime,
    VisualGenerationRuntimeError,
)

_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "into", "over",
    "under", "about", "what", "why", "how", "when", "where", "which",
    "visual", "image", "scene", "shot", "style", "family", "profile",
    "cinematic", "illustrative", "illustration", "show", "shows", "showing",
    "depict", "depicts", "depicting", "create", "make", "use", "using",
})


class ShotVisualAcquisitionError(ValueError):
    """Raised when an approved Director plan cannot be safely resolved."""


@dataclass(frozen=True)
class ShotVisualResolution:
    shot_id: str
    scene_id: str
    status: str
    asset_id: Optional[str] = None
    asset_path: Optional[str] = None
    source: Optional[str] = None
    match_score: int = 0
    provider_id: Optional[str] = None
    diagnostic: str = ""


@dataclass(frozen=True)
class DirectorVisualResolution:
    plan_id: str
    source_fingerprint: str
    profile_id: str
    shots: tuple[ShotVisualResolution, ...]

    @property
    def is_complete(self) -> bool:
        return bool(self.shots) and all(item.asset_id is not None for item in self.shots)


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]{3,}", value.casefold())
        if token not in _STOP_WORDS
    }


def _metadata_terms(asset: VisualAsset) -> set[str]:
    parts = list(asset.tags)
    for key in ("keywords", "subjects", "description", "subject", "prompt", "style_tags"):
        value = asset.metadata.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
            parts.extend(value)
    return set().union(*(_tokens(part) for part in parts)) if parts else set()


def _rights_eligible(asset: VisualAsset) -> bool:
    provenance = asset.provenance
    if provenance is None:
        return False
    source = provenance.source.casefold()
    if source in {"user-upload", "user_upload", "user-import", "user_import"} or source.startswith("generated:"):
        return True
    license_name = re.sub(r"[^a-z0-9]+", " ", (provenance.license or "").casefold()).strip()
    if license_name.startswith(("public domain", "cc0", "cc 0")):
        return True
    if license_name.startswith(("cc by ", "cc by sa ")):
        return not any(marker in license_name for marker in (" non commercial", " noncommercial", " nc ", " no derivatives", " nd "))
    return False


def _profile_eligible(asset: VisualAsset, profile_id: str) -> bool:
    profile_ids = asset.metadata.get("profile_ids")
    if profile_ids is None:
        return True
    if isinstance(profile_ids, str):
        profile_ids = (profile_ids,)
    return isinstance(profile_ids, (list, tuple)) and profile_id in profile_ids


def _shot_scene_map(plan: DirectorPlan) -> dict[str, str]:
    shot_ids = tuple(shot.shot_id for shot in plan.shots)
    if not shot_ids or len(set(shot_ids)) != len(shot_ids):
        raise ShotVisualAcquisitionError("Director plan must contain unique shots")
    scene_ids = tuple(scene.scene_id for scene in plan.scenes)
    if not scene_ids or len(set(scene_ids)) != len(scene_ids):
        raise ShotVisualAcquisitionError("Director plan must contain unique scenes")
    mapping: dict[str, str] = {}
    for scene in plan.scenes:
        for shot_id in scene.shot_ids:
            if shot_id in mapping:
                raise ShotVisualAcquisitionError("A Director shot is referenced by multiple scenes")
            mapping[shot_id] = scene.scene_id
    if set(mapping) != set(shot_ids):
        raise ShotVisualAcquisitionError("Director scenes must reference every shot exactly once")
    return mapping


def _rank_local_assets(
    shot: DirectorShot,
    narration_text: str,
    catalog: VisualAssetCatalog,
    library: VisualAssetLibrary,
    profile: ChannelProfile,
) -> tuple[Optional[tuple[VisualAsset, int]], tuple[str, ...]]:
    prompt_terms = _tokens(narration_text)
    intent = getattr(shot.intent, "value", str(shot.intent))
    profile_style_tags = set(profile.visual_defaults.style_tags)
    ranked: list[tuple[int, str, VisualAsset]] = []
    diagnostics: list[str] = []
    for asset in catalog.assets:
        if not _rights_eligible(asset) or not _profile_eligible(asset, profile.profile_id):
            continue
        try:
            if not library.verify_asset(asset):
                diagnostics.append(f"Asset {asset.asset_id} failed content verification.")
                continue
            library.resolve_asset_path(asset)
        except AssetImportError:
            diagnostics.append(f"Asset {asset.asset_id} is missing or unsafe.")
            continue
        asset_terms = _metadata_terms(asset)
        overlap = prompt_terms.intersection(asset_terms)
        intent_match = intent in asset.tags or asset.metadata.get("intent") == intent
        raw_style_tags = asset.metadata.get("style_tags", ())
        if isinstance(raw_style_tags, str):
            raw_style_tags = (raw_style_tags,)
        asset_style_tags = {tag for tag in raw_style_tags if isinstance(tag, str)} if isinstance(raw_style_tags, (list, tuple)) else set()
        style_match = bool(profile_style_tags.intersection(asset_style_tags))
        if not overlap and not intent_match:
            continue
        score = len(overlap) * 2 + (4 if intent_match else 0) + (1 if style_match else 0)
        ranked.append((score, asset.asset_id, asset))
    if not ranked:
        return None, tuple(diagnostics)
    ranked.sort(key=lambda item: (-item[0], item[1]))
    score, _, asset = ranked[0]
    return (asset, score), tuple(diagnostics)


def resolve_director_plan_visuals(
    plan: DirectorPlan,
    *,
    script: str,
    narration_source: NarrationSource,
    profile: ChannelProfile,
    asset_library: VisualAssetLibrary,
    approved: bool,
    generation_runtime: Optional[VisualGenerationRuntime] = None,
    provider_id: Optional[str] = None,
    width: int = 512,
    height: int = 512,
    allow_network: bool = False,
    allow_api_key: bool = False,
    progress=None,
) -> DirectorVisualResolution:
    """Resolve every approved Director shot to a verified asset or diagnostic.

    Existing local assets are preferred. Generation is attempted only when the
    caller supplies both an injected runtime and an exact provider ID; network
    and credential consent are forwarded explicitly and default to false.
    """
    if not isinstance(plan, DirectorPlan):
        raise ShotVisualAcquisitionError("plan must be a DirectorPlan")
    if approved is not True:
        raise ShotVisualAcquisitionError("explicit approval of the Director prompts is required")
    if not isinstance(script, str) or not script.strip():
        raise ShotVisualAcquisitionError("script must be non-empty")
    fingerprint = hashlib.sha256(script.encode("utf-8")).hexdigest()
    if plan.source_fingerprint != fingerprint:
        raise ShotVisualAcquisitionError("Director plan is stale: script fingerprint does not match")
    if not isinstance(narration_source, NarrationSource):
        raise ShotVisualAcquisitionError("narration_source must be the exact NarrationSource used by the Director")
    if narration_source.text != script or narration_source.source_fingerprint != fingerprint:
        raise ShotVisualAcquisitionError("NarrationSource does not match the supplied script")
    if narration_source.source_id != plan.source_id:
        raise ShotVisualAcquisitionError("NarrationSource does not match the Director source ID")
    if tuple(unit.unit_id for unit in narration_source.units) != tuple(
        unit_id for shot in plan.shots for unit_id in shot.narration_unit_ids
    ):
        raise ShotVisualAcquisitionError("Director shots must cover every narration unit exactly once and in order")
    if not isinstance(profile, ChannelProfile):
        raise ShotVisualAcquisitionError("profile must be a ChannelProfile")
    if plan.profile_id != profile.profile_id or plan.profile_style_family != profile.visual_defaults.style_family:
        raise ShotVisualAcquisitionError("Director plan does not match the active channel profile")
    if not isinstance(asset_library, VisualAssetLibrary):
        raise ShotVisualAcquisitionError("asset_library must be a VisualAssetLibrary")
    if generation_runtime is not None:
        if not isinstance(generation_runtime, VisualGenerationRuntime):
            raise ShotVisualAcquisitionError("generation_runtime must be a VisualGenerationRuntime")
        if generation_runtime.asset_library is not asset_library:
            raise ShotVisualAcquisitionError("generation runtime must use the same VisualAssetLibrary")
    if provider_id is not None and (not isinstance(provider_id, str) or not provider_id.strip()):
        raise ShotVisualAcquisitionError("provider_id must be a non-empty string or null")
    if provider_id is not None and generation_runtime is None:
        raise ShotVisualAcquisitionError("provider_id requires an injected generation_runtime")
    if progress is not None and not callable(progress):
        raise ShotVisualAcquisitionError("progress must be callable or null")
    for name, value in (("allow_network", allow_network), ("allow_api_key", allow_api_key)):
        if not isinstance(value, bool):
            raise ShotVisualAcquisitionError(f"{name} must be a boolean")

    scene_by_shot = _shot_scene_map(plan)
    catalog = asset_library.load_catalog()
    resolved: list[ShotVisualResolution] = []
    units_by_id = {unit.unit_id: unit for unit in narration_source.units}
    for shot in plan.shots:
        if not isinstance(shot.visual_prompt, str) or not shot.visual_prompt.strip():
            raise ShotVisualAcquisitionError(f"Director shot {shot.shot_id} has no approved visual prompt")
        scene_id = scene_by_shot[shot.shot_id]
        narration_text = " ".join(
            narration_source.text_for_unit(units_by_id[unit_id]).strip()
            for unit_id in shot.narration_unit_ids
        )
        match, match_diagnostics = _rank_local_assets(
            shot, narration_text, catalog, asset_library, profile
        )
        if match is not None:
            asset, score = match
            resolved.append(ShotVisualResolution(
                shot_id=shot.shot_id,
                scene_id=scene_id,
                status="selected",
                asset_id=asset.asset_id,
                asset_path=str(asset_library.resolve_asset_path(asset)),
                source=asset.provenance.source if asset.provenance else None,
                match_score=score,
                diagnostic=("Selected the highest-scoring content-verified local asset." + (" Model/media rights review remains required." if asset.provenance and asset.provenance.source.startswith("generated:") else "")),
            ))
            continue

        if generation_runtime is None or provider_id is None:
            detail = " ".join(match_diagnostics)
            resolved.append(ShotVisualResolution(
                shot_id=shot.shot_id,
                scene_id=scene_id,
                status="unresolved",
                diagnostic=("No suitable verified local asset and no generation provider was selected. "
                            "Use a profile-compatible procedural fallback or configure a provider. " + detail).strip(),
            ))
            continue

        request_id = "vxp105-" + uuid4().hex
        request = VisualGenerationRequest(
            request_id=request_id,
            scene_id=scene_id,
            prompt=shot.visual_prompt,
            width=width,
            height=height,
            output_format="png",
            image_count=1,
            style_tags=tuple(dict.fromkeys((shot.intent.value, shot.style_family) + tuple(profile.visual_defaults.style_tags))),
            metadata={
                "plan_id": plan.plan_id,
                "shot_id": shot.shot_id,
                "profile_id": profile.profile_id,
                "intent": shot.intent.value,
                "timing": shot.timing.to_dict(),
                "rights_review_required": True,
            },
        )
        try:
            generated = generation_runtime.generate(
                request,
                provider_id,
                allow_network=allow_network,
                allow_api_key=allow_api_key,
                progress=progress,
            )
        except VisualGenerationCancelled:
            raise
        except VisualGenerationRuntimeError as exc:
            resolved.append(ShotVisualResolution(
                shot_id=shot.shot_id,
                scene_id=scene_id,
                status="unresolved",
                provider_id=provider_id,
                diagnostic=f"Visual generation failed [{exc.code}]: {exc}",
            ))
            continue

        if len(generated.assets) != 1:
            raise ShotVisualAcquisitionError("generation runtime did not return exactly one image for the shot")
        asset = generated.assets[0]
        if asset.kind != "generated-image" or not asset.provenance or not asset.provenance.source.startswith("generated:"):
            raise ShotVisualAcquisitionError("generation runtime returned an asset without generated-image provenance")
        if not asset_library.verify_asset(asset):
            raise ShotVisualAcquisitionError("generated image failed content verification")
        resolved.append(ShotVisualResolution(
            shot_id=shot.shot_id,
            scene_id=scene_id,
            status="generated",
            asset_id=asset.asset_id,
            asset_path=str(asset_library.resolve_asset_path(asset)),
            source=asset.provenance.source,
            provider_id=provider_id,
            diagnostic="Generated and imported one still image; model/media rights review remains required.",
        ))

    return DirectorVisualResolution(
        plan_id=plan.plan_id,
        source_fingerprint=plan.source_fingerprint,
        profile_id=plan.profile_id,
        shots=tuple(resolved),
    )
