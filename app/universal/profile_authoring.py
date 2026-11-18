"""Explicit channel-profile integration for Universal scene authoring.

This adapter is opt-in: ordinary authoring remains unchanged unless a caller
supplies a ChannelProfile. Profile defaults enrich proposed ScenePlans only;
rule evaluation is diagnostic-only and applying remains an explicit action.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Sequence

from app.universal.authoring import (
    SceneAuthoringOptions,
    ScenePlanProposal,
    apply_scene_plan_proposal,
    build_scene_plan_proposal,
)
from app.universal.profiles.evaluator import ProfileDiagnostic, evaluate_profile_rules
from app.universal.profiles.models import ChannelProfile, VisualDefaults
from app.universal.models import ScenePlan


@dataclass(frozen=True)
class ProfiledScenePlanProposal:
    """A regular authoring proposal plus profile context and review diagnostics."""

    proposal: ScenePlanProposal
    profile_id: str | None = None
    selected_preset_id: str | None = None
    diagnostics: tuple[ProfileDiagnostic, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Errors from either authoring or profile rules prevent explicit apply."""
        return self.proposal.is_valid and not any(
            item.severity == "error" for item in self.diagnostics
        )


def _merge_visual_defaults(
    profile_defaults: VisualDefaults,
    preset_defaults: VisualDefaults | None,
) -> VisualDefaults:
    """Apply preset values over profile defaults without discarding inherited tags."""
    if preset_defaults is None:
        return profile_defaults
    return VisualDefaults(
        style_family=(
            preset_defaults.style_family
            if preset_defaults.style_family != "unspecified"
            else profile_defaults.style_family
        ),
        style_tags=tuple(dict.fromkeys((*profile_defaults.style_tags, *preset_defaults.style_tags))),
        mood=tuple(dict.fromkeys((*profile_defaults.mood, *preset_defaults.mood))),
        composition_guidance=tuple(dict.fromkeys(
            (*profile_defaults.composition_guidance, *preset_defaults.composition_guidance)
        )),
    )


def build_profiled_scene_plan_proposal(
    script: str | None = None,
    *,
    profile: ChannelProfile | None = None,
    selected_preset_id: str | None = None,
    project_context: Any = None,
    completed_reviews: Sequence[str] = (),
    existing_scenes=None,
    options: SceneAuthoringOptions | None = None,
) -> ProfiledScenePlanProposal:
    """Build an ordinary proposal, optionally enriched by an explicitly supplied profile.

    No profile is inferred from the project. When supplied, its visual defaults
    are copied into proposed ScenePlans and its profile/preset rules are
    evaluated against the supplied project context, scene drafts, and plans.
    Existing narration, notes, visual prompts, engine choices, and assets are
    not rewritten. Review completion is input-only and is never persisted here.
    """
    proposal = build_scene_plan_proposal(
        script,
        existing_scenes=existing_scenes,
        options=options,
    )
    if profile is None:
        diagnostics: tuple[ProfileDiagnostic, ...] = ()
        if selected_preset_id is not None:
            diagnostics = (ProfileDiagnostic(
                "PROFILE_REQUIRED", "error",
                "A channel profile must be explicitly supplied when selecting a production preset.",
                source="preset",
            ),)
        return ProfiledScenePlanProposal(
            proposal=proposal,
            selected_preset_id=selected_preset_id,
            diagnostics=diagnostics,
        )
    if not isinstance(profile, ChannelProfile):
        raise TypeError("profile must be a ChannelProfile")

    preset = None
    if selected_preset_id is not None:
        preset = next(
            (item for item in profile.presets if item.preset_id == selected_preset_id),
            None,
        )

    # An unknown preset must not silently fall back to profile-only defaults.
    if not profile.read_only and (selected_preset_id is None or preset is not None):
        visual_defaults = _merge_visual_defaults(
            profile.visual_defaults,
            preset.visual_defaults if preset is not None else None,
        )
        for draft in proposal.scenes:
            plan = draft.visual_plan
            plan.style_tags = list(dict.fromkeys((*plan.style_tags, *visual_defaults.style_tags)))
            requirements = copy.deepcopy(plan.requirements)
            requirements["profile_visual_defaults"] = {
                "style_family": visual_defaults.style_family,
                "mood": list(visual_defaults.mood),
                "composition_guidance": list(visual_defaults.composition_guidance),
            }
            plan.requirements = requirements

    diagnostics = evaluate_profile_rules(
        profile,
        project=project_context,
        scenes=proposal.scenes,
        scene_plans=[draft.visual_plan for draft in proposal.scenes],
        selected_preset_id=selected_preset_id,
        completed_reviews=completed_reviews,
    )
    return ProfiledScenePlanProposal(
        proposal=proposal,
        profile_id=profile.profile_id,
        selected_preset_id=selected_preset_id,
        diagnostics=diagnostics,
    )


def apply_profiled_scene_plan_proposal(project, profiled_proposal: ProfiledScenePlanProposal) -> None:
    """Apply only after authoring validation and blocking profile diagnostics pass."""
    if not isinstance(profiled_proposal, ProfiledScenePlanProposal):
        raise ValueError("profiled_proposal must be a ProfiledScenePlanProposal")
    if not profiled_proposal.is_valid:
        blocking = [
            item.code for item in profiled_proposal.diagnostics
            if item.severity == "error"
        ]
        if blocking:
            raise ValueError(
                "Profile diagnostics must be resolved before apply: " + ", ".join(blocking)
            )
        raise ValueError("Cannot apply an invalid scene proposal")
    apply_scene_plan_proposal(project, profiled_proposal.proposal)
