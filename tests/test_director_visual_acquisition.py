from __future__ import annotations

import struct
from dataclasses import replace
from pathlib import Path

import pytest

from app.universal.asset_library import VisualAssetLibrary
from app.universal.director_visual_acquisition import (
    ShotVisualAcquisitionError,
    resolve_director_plan_visuals,
)
from app.universal.narration_segmentation import segment_narration
from app.universal.production_director import ProductionDirector
from app.universal.profiles.models import ChannelProfile
from app.universal.visual_assets import AssetProvenance
from app.universal.visual_generation import (
    VisualGenerationProviderCapabilities,
    VisualGenerationProviderDescriptor,
)
from app.universal.visual_generation_runtime import VisualGenerationRuntime


def _profile():
    return ChannelProfile.from_dict({
        "schema_version": 1,
        "profile_id": "quasivanta",
        "display_name": "Quasivanta",
        "visual_defaults": {
            "style_family": "cinematic_scientific_visualization",
            "style_tags": ["infographics"],
            "mood": ["curious"],
            "composition_guidance": ["Keep visual claims proportional to narration."],
        },
    })


def _plan():
    script = "Why does the planet move? Its orbit follows gravity."
    source = segment_narration(script, source_id="vxp105-test", total_duration_ms=8000)
    profile = _profile()
    return script, source, profile, ProductionDirector().create_plan(source, profile)


def _png_bytes(width=32, height=24):
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13) + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"test-image-payload"
    )


def _import_asset(library, tmp_path, *, asset_id, tags, provenance):
    source = tmp_path / f"{asset_id}.png"
    source.write_bytes(_png_bytes())
    return library.import_file(
        source, asset_id=asset_id, tags=tags, provenance=provenance
    )


class _FakeProvider:
    def __init__(self):
        self.descriptor = VisualGenerationProviderDescriptor(
            provider_id="fake-local",
            display_name="Fake Local",
            version="test",
            capabilities=VisualGenerationProviderCapabilities(
                output_formats=("png",),
                max_width=512,
                max_height=512,
                max_images_per_request=1,
                requires_network=False,
                requires_api_key=False,
            ),
            available=True,
            unavailable_reason="",
        )
        self.calls = []

    def generate(self, request, output_dir: Path, cancel_event, progress):
        self.calls.append(request)
        path = output_dir / "shot.png"
        path.write_bytes(_png_bytes(64, 64))
        progress(1, 1, "fixture generated")
        return (path,)


def test_selects_best_verified_local_asset_before_generation(tmp_path):
    script, narration_source, profile, plan = _plan()
    library = VisualAssetLibrary(tmp_path / "library")
    _import_asset(
        library, tmp_path, asset_id="unverified-match", tags=("gravity",),
        provenance=None,
    )
    _import_asset(
        library, tmp_path, asset_id="unknown-license", tags=("gravity",),
        provenance=AssetProvenance(source="commons", license="All rights reserved"),
    )
    _import_asset(
        library, tmp_path, asset_id="planet-question", tags=("planet", "question_reveal"),
        provenance=AssetProvenance(source="user-upload"),
    )
    selected = _import_asset(
        library, tmp_path, asset_id="gravity-diagram", tags=("gravity", "diagram"),
        provenance=AssetProvenance(source="user-upload"),
    )
    provider = _FakeProvider()
    runtime = VisualGenerationRuntime(library, [provider])

    result = resolve_director_plan_visuals(
        plan, script=script, narration_source=narration_source, profile=profile, asset_library=library,
        generation_runtime=runtime, provider_id="fake-local", approved=True,
    )

    diagram = next(item for item in result.shots if item.shot_id == plan.shots[1].shot_id)
    assert diagram.status == "selected"
    assert diagram.asset_id == selected.asset_id
    assert diagram.source == "user-upload"
    assert provider.calls == []


def test_generates_one_image_for_each_unmatched_shot_with_explicit_provider(tmp_path):
    script, narration_source, profile, plan = _plan()
    library = VisualAssetLibrary(tmp_path / "library")
    provider = _FakeProvider()
    runtime = VisualGenerationRuntime(library, [provider])
    events = []

    result = resolve_director_plan_visuals(
        plan, script=script, narration_source=narration_source, profile=profile, asset_library=library,
        generation_runtime=runtime, provider_id="fake-local", approved=True,
        progress=events.append,
    )

    assert len(result.shots) == len(plan.shots)
    assert all(item.status == "generated" for item in result.shots)
    assert all(item.asset_id and item.asset_path for item in result.shots)
    assert len(provider.calls) == len(plan.shots)
    assert all(call.metadata["rights_review_required"] is True for call in provider.calls)
    assert result.is_complete


def test_does_not_generate_or_claim_success_without_provider(tmp_path):
    script, narration_source, profile, plan = _plan()
    library = VisualAssetLibrary(tmp_path / "library")

    result = resolve_director_plan_visuals(
        plan, script=script, narration_source=narration_source, profile=profile, asset_library=library, approved=True,
    )

    assert not result.is_complete
    assert all(item.status == "unresolved" for item in result.shots)
    assert all("no generation provider" in item.diagnostic for item in result.shots)


def test_requires_explicit_approval_and_rejects_stale_script_or_profile(tmp_path):
    script, narration_source, profile, plan = _plan()
    library = VisualAssetLibrary(tmp_path / "library")
    with pytest.raises(ShotVisualAcquisitionError, match="explicit approval"):
        resolve_director_plan_visuals(
            plan, script=script, narration_source=narration_source, profile=profile, asset_library=library, approved=False,
        )
    with pytest.raises(ShotVisualAcquisitionError, match="stale"):
        resolve_director_plan_visuals(
            plan, script=script + " changed", narration_source=narration_source, profile=profile,
            asset_library=library, approved=True,
        )
    other_profile = ChannelProfile.from_dict({
        "schema_version": 1, "profile_id": "veltracis", "display_name": "Veltracis",
        "visual_defaults": {
            "style_family": "documentary_collage_2_5d",
            "style_tags": ["sketch"], "mood": ["mysterious"],
            "composition_guidance": ["Do not invent historical evidence."],
        },
    })
    with pytest.raises(ShotVisualAcquisitionError, match="active channel profile"):
        resolve_director_plan_visuals(
            plan, script=script, narration_source=narration_source, profile=other_profile,
            asset_library=library, approved=True,
        )


def test_rejects_scene_plan_that_does_not_reference_every_shot_once(tmp_path):
    script, narration_source, profile, plan = _plan()
    broken_scene = replace(plan.scenes[0], shot_ids=())
    broken_plan = replace(plan, scenes=(broken_scene,) + plan.scenes[1:])
    with pytest.raises(ShotVisualAcquisitionError, match="every shot exactly once"):
        resolve_director_plan_visuals(
            broken_plan, script=script, narration_source=narration_source, profile=profile,
            asset_library=VisualAssetLibrary(tmp_path / "library"), approved=True,
        )


def test_generation_runtime_must_share_the_same_asset_library(tmp_path):
    script, narration_source, profile, plan = _plan()
    library = VisualAssetLibrary(tmp_path / "library")
    other_library = VisualAssetLibrary(tmp_path / "other")
    runtime = VisualGenerationRuntime(other_library, [_FakeProvider()])
    with pytest.raises(ShotVisualAcquisitionError, match="same VisualAssetLibrary"):
        resolve_director_plan_visuals(
            plan, script=script, narration_source=narration_source, profile=profile, asset_library=library,
            generation_runtime=runtime, provider_id="fake-local", approved=True,
        )
