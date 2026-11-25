"""Choose and validate the plan used by supplied-narration Auto Produce.

An external package is a proposal only. It must match the active normalized
spoken script, narration source and channel profile before the UI can request
explicit approval and pass it to the existing Director handoff.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.universal.external_visual_direction import (
    VisualDirectionImportError,
    import_visual_direction_package,
)
from app.universal.production_director import DirectorPlan, ProductionDirector
from app.universal.profiles.models import ChannelProfile
from app.universal.storyboard import NarrationSource


def create_auto_produce_plan(
    narration_source: NarrationSource,
    profile: ChannelProfile,
    *,
    visual_direction_path: Optional[str | Path] = None,
) -> DirectorPlan:
    """Return the internal plan or a validated external plan proposal.

    The fingerprint is bound to NarrationSource.text: the exact spoken text
    after the existing parser removes non-spoken markup and canonical sentence
    segmentation normalizes alignment whitespace. This is the same text sent
    to the measured narration aligner.
    """
    if not isinstance(narration_source, NarrationSource):
        raise TypeError("narration_source must be NarrationSource")
    if not isinstance(profile, ChannelProfile):
        raise TypeError("profile must be ChannelProfile")
    if visual_direction_path is None or (
        isinstance(visual_direction_path, str) and not visual_direction_path.strip()
    ):
        return ProductionDirector().create_plan(narration_source, profile)

    package_path = Path(visual_direction_path).expanduser()
    plan = import_visual_direction_package(
        package_path,
        script=narration_source.text,
        profile_id=profile.profile_id,
        narration_source=narration_source,
    )
    expected_style = profile.visual_defaults.style_family
    if plan.profile_style_family != expected_style:
        raise VisualDirectionImportError(
            "package profile_style_family does not match the active Channel Profile"
        )
    return plan
