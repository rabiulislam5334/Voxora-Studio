"""Bridge project scene visual plans into the existing production FFmpeg path.

The bridge is deliberately narrow: it validates the Universal ScenePlan and
creates an immutable EngineRenderRequest, while preserving SegmentSpec as the
renderer's source of timing and legacy Studio settings.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from app.universal.models import AssetRef, EngineChoice, ScenePlan
from app.universal.normalizer import SegmentOutputSpec
from app.universal.requests import EngineRenderRequest
from app.video.render import SegmentSpec


class ProductionPlanError(ValueError):
    """Raised when a Universal visual plan cannot describe the current scene."""


def build_production_render_request(
    scene_id: str,
    spec: SegmentSpec,
    destination: Path,
    plan: Optional[ScenePlan] = None,
) -> Tuple[ScenePlan, EngineRenderRequest]:
    """Build a strict FFmpeg request from a scene's current render spec.

    Projects without a Universal plan receive an ephemeral legacy-compatible
    plan. Existing plans are never mutated and must reference exactly the media
    currently selected in Studio settings. The caller still resolves the
    selected engine against the registry before execution.
    """
    if not isinstance(scene_id, str) or not scene_id.strip():
        raise ProductionPlanError("scene_id must be a non-empty string")
    if not isinstance(spec, SegmentSpec):
        raise TypeError("spec must be a SegmentSpec")
    if not isinstance(destination, (str, Path)) or not str(destination).strip():
        raise ProductionPlanError("destination must be a non-empty path")

    expected_assets = ()
    if spec.kind in ("image", "video"):
        if not isinstance(spec.media, str) or not spec.media.strip():
            raise ProductionPlanError(f"{spec.kind} scene requires a media path")
        expected_assets = (
            AssetRef(
                asset_id=f"{scene_id}:primary-visual",
                kind=spec.kind,
                path=spec.media,
            ),
        )
    elif spec.kind != "blank":
        raise ProductionPlanError(f"unsupported production scene kind: {spec.kind!r}")

    if plan is None:
        plan = ScenePlan(
            scene_id=scene_id,
            kind=spec.kind,
            requirements={
                "output_format": "mp4",
                "asset_kinds": [asset.kind for asset in expected_assets],
            },
            engine_choice=EngineChoice(engine_id="ffmpeg", chosen_by="legacy-production"),
            asset_refs=list(expected_assets),
        )
    elif not isinstance(plan, ScenePlan):
        raise TypeError("plan must be a ScenePlan or None")

    if plan.scene_id != scene_id:
        raise ProductionPlanError(
            f"visual plan scene_id '{plan.scene_id}' does not match scene '{scene_id}'"
        )
    if plan.kind != spec.kind:
        raise ProductionPlanError(
            f"visual plan kind '{plan.kind}' does not match configured media kind '{spec.kind}'"
        )
    if len(plan.asset_refs) != len(expected_assets):
        raise ProductionPlanError(
            f"{spec.kind} production currently requires exactly {len(expected_assets)} "
            f"asset reference(s); got {len(plan.asset_refs)}"
        )
    for actual, expected in zip(plan.asset_refs, expected_assets):
        if actual.kind != expected.kind:
            raise ProductionPlanError(
                f"asset '{actual.asset_id}' kind '{actual.kind}' does not match '{expected.kind}'"
            )
        if not actual.path:
            raise ProductionPlanError(f"asset '{actual.asset_id}' is missing its path")
        if Path(actual.path).resolve() != Path(expected.path).resolve():
            raise ProductionPlanError(
                f"asset '{actual.asset_id}' path does not match the scene's configured media"
            )

    output_format = plan.requirements.get("output_format")
    if output_format != "mp4":
        raise ProductionPlanError(
            "production visual plans must explicitly request requirements.output_format='mp4'"
        )

    output_spec = SegmentOutputSpec(
        duration_s=spec.length_s,
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
    )
    request = EngineRenderRequest(
        scene_id=scene_id,
        scene_kind=plan.kind,
        output_format=output_format,
        output_spec=output_spec,
        destination=Path(destination),
        style_tags=tuple(plan.style_tags),
        asset_refs=tuple(plan.asset_refs),
        engine_params={
            "motion": spec.motion,
            "fit": spec.fit,
            "length_ticks": spec.length_ticks,
            "frame_count": spec.frame_count,
        },
    )
    return plan, request
