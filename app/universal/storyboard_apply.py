"""Reviewable storyboard preview and explicit, atomic Project application.

This module converts approved storyboard intent into existing Scene and
ScenePlan contracts. It does not generate visual assets or render anything.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from app.models.project import Project
from app.models.scene import Scene
from app.universal.models import ScenePlan, UniversalState
from app.universal.storyboard import (
    NarrationSource,
    ProposalReviewStatus,
    StoryboardProposal,
    StoryboardValidationError,
)
from app.universal.storyboard_diagnostics import (
    StoryboardDiagnostic,
    StoryboardDiagnosticSeverity,
    diagnose_storyboard,
)


@dataclass(frozen=True)
class StoryboardScenePreview:
    """One proposed Project Scene, shown without mutating the Project."""

    scene_id: str
    beat_id: str
    title: str
    narration_text: str
    visual_prompt: str
    notes: str
    start_ms: int
    end_ms: int
    timing_basis: str


@dataclass(frozen=True)
class StoryboardPreviewDiagnostic:
    code: str
    severity: str
    message: str
    subject_id: Optional[str] = None


@dataclass(frozen=True)
class StoryboardApplyPreview:
    """Immutable preview tied to the exact source and target Project snapshot."""

    proposal_id: str
    source_id: str
    source_fingerprint: str
    project_id: str
    target_fingerprint: str
    scenes: Tuple[StoryboardScenePreview, ...]
    diagnostics: Tuple[StoryboardPreviewDiagnostic, ...]

    @property
    def is_valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


def _target_fingerprint(project: Project) -> str:
    """Fingerprint the Project fields this additive apply operation depends on."""
    if not isinstance(project.settings, dict):
        raise StoryboardValidationError("project.settings must be an object")
    scene_data = []
    for scene in project.scenes:
        if not isinstance(scene, Scene):
            raise StoryboardValidationError("project.scenes must contain Scene values")
        scene_data.append({
            "id": scene.id,
            "title": scene.title,
            "text": scene.text,
            "notes": scene.notes,
            "visual_prompt": scene.visual_prompt,
            "order": scene.order,
        })
    payload = {
        "project_id": project.id,
        "scenes": scene_data,
        "universal": copy.deepcopy(project.settings.get("universal")),
    }
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StoryboardValidationError(
            f"project state cannot be fingerprinted safely: {exc}"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _scene_id(proposal_id: str, beat_id: str) -> str:
    digest = hashlib.sha256(f"{proposal_id}:{beat_id}".encode("utf-8")).hexdigest()
    return f"sb-{digest[:16]}"


def preview_storyboard_apply(
    project: Project,
    proposal: StoryboardProposal,
    source: NarrationSource,
) -> StoryboardApplyPreview:
    """Build a deterministic diff-like preview; this function is read-only."""
    if not isinstance(project, Project):
        raise StoryboardValidationError("project must be a Project")
    if not isinstance(proposal, StoryboardProposal):
        raise StoryboardValidationError("proposal must be a StoryboardProposal")
    if not isinstance(source, NarrationSource):
        raise StoryboardValidationError("source must be a NarrationSource")

    diagnostics = []
    if proposal.review_status is ProposalReviewStatus.APPROVED:
        diagnostics.append(StoryboardPreviewDiagnostic(
            "PROPOSAL_ALREADY_APPROVED", "info",
            "This proposal is already marked approved; review the preview before explicit apply.",
        ))
    try:
        proposal.validate_against(source)
    except StoryboardValidationError as exc:
        diagnostics.append(StoryboardPreviewDiagnostic(
            "SOURCE_MISMATCH", "error", str(exc), proposal.proposal_id
        ))

    for item in diagnose_storyboard(proposal, source):
        diagnostics.append(StoryboardPreviewDiagnostic(
            item.code, item.severity.value, item.message, item.subject_id
        ))

    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        diagnostics.append(StoryboardPreviewDiagnostic(
            "UNIVERSAL_STATE_READ_ONLY", "error",
            "Universal project data is malformed or from a future version; apply is blocked.",
        ))
    applied = state.extra.get("storyboard_applied_proposal_ids", [])
    if not isinstance(applied, list) or any(not isinstance(item, str) for item in applied):
        diagnostics.append(StoryboardPreviewDiagnostic(
            "APPLY_HISTORY_INVALID", "error",
            "Storyboard apply history is malformed; existing project data will not be changed.",
        ))
    elif proposal.proposal_id in applied:
        diagnostics.append(StoryboardPreviewDiagnostic(
            "PROPOSAL_ALREADY_APPLIED", "error",
            "This storyboard proposal has already been applied to this project.",
            proposal.proposal_id,
        ))

    existing_ids = {scene.id for scene in project.scenes if isinstance(scene, Scene)}
    previews = []
    for index, beat in enumerate(proposal.beats, start=1):
        scene_id = _scene_id(proposal.proposal_id, beat.beat_id)
        if scene_id in existing_ids:
            diagnostics.append(StoryboardPreviewDiagnostic(
                "SCENE_ID_COLLISION", "error",
                "A deterministic storyboard scene ID already exists in this project.",
                scene_id,
            ))
        narration_parts = []
        for unit_id in beat.narration_unit_ids:
            unit = next((item for item in source.units if item.unit_id == unit_id), None)
            if unit is None:
                diagnostics.append(StoryboardPreviewDiagnostic(
                    "UNKNOWN_NARRATION_UNIT", "error",
                    "A beat references a narration unit absent from the supplied source.",
                    unit_id,
                ))
                continue
            narration_parts.append(source.text_for_unit(unit))
        notes = []
        if beat.action_cues:
            notes.append("Action cues: " + "; ".join(beat.action_cues))
        if beat.continuity_reference_ids:
            notes.append("Continuity references: " + ", ".join(beat.continuity_reference_ids))
        previews.append(StoryboardScenePreview(
            scene_id=scene_id,
            beat_id=beat.beat_id,
            title=f"Scene {index}",
            narration_text="".join(narration_parts),
            visual_prompt=beat.visual_description,
            notes="\n".join(notes),
            start_ms=beat.timing.start_ms,
            end_ms=beat.timing.end_ms,
            timing_basis=beat.timing.basis.value,
        ))

    return StoryboardApplyPreview(
        proposal_id=proposal.proposal_id,
        source_id=proposal.source_id,
        source_fingerprint=proposal.source_fingerprint,
        project_id=project.id,
        target_fingerprint=_target_fingerprint(project),
        scenes=tuple(previews),
        diagnostics=tuple(diagnostics),
    )


def apply_storyboard_proposal(
    project: Project,
    proposal: StoryboardProposal,
    source: NarrationSource,
    preview: StoryboardApplyPreview,
    *,
    approved: bool = False,
) -> None:
    """Atomically append storyboard scenes after explicit human approval.

    The caller must pass approved=True after reviewing the preview. The source
    and target fingerprints are rechecked immediately before mutation. Existing
    scenes are preserved; the proposal is idempotent per Project.
    """
    if approved is not True:
        raise StoryboardValidationError(
            "explicit approval is required before applying a storyboard proposal"
        )
    if not isinstance(preview, StoryboardApplyPreview):
        raise StoryboardValidationError("preview must be a StoryboardApplyPreview")
    if not preview.is_valid:
        raise StoryboardValidationError("preview contains blocking diagnostics")

    current = preview_storyboard_apply(project, proposal, source)
    if (
        current.proposal_id != preview.proposal_id
        or current.source_fingerprint != preview.source_fingerprint
        or current.project_id != preview.project_id
        or current.target_fingerprint != preview.target_fingerprint
        or current.scenes != preview.scenes
    ):
        raise StoryboardValidationError(
            "storyboard preview is stale; rebuild and review the preview before applying"
        )
    if not current.is_valid:
        raise StoryboardValidationError("current storyboard preview contains blocking diagnostics")
    if proposal.review_status is not ProposalReviewStatus.NEEDS_REVIEW:
        raise StoryboardValidationError(
            "only a proposal awaiting review can be applied through this operation"
        )
    proposal.validate_against(source)

    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise StoryboardValidationError("Universal project data is read-only; apply was refused")
    history = state.extra.get("storyboard_applied_proposal_ids", [])
    if not isinstance(history, list) or any(not isinstance(item, str) for item in history):
        raise StoryboardValidationError("storyboard apply history is malformed")
    if proposal.proposal_id in history:
        raise StoryboardValidationError("this storyboard proposal has already been applied")

    next_scenes = copy.deepcopy(project.scenes)
    next_state = copy.deepcopy(state)
    for item, beat in zip(current.scenes, proposal.beats):
        scene = Scene(
            id=item.scene_id,
            title=item.title,
            text=item.narration_text,
            notes=item.notes,
            visual_prompt=item.visual_prompt,
            order=len(next_scenes),
        )
        next_scenes.append(scene)
        plan = ScenePlan(
            scene_id=item.scene_id,
            kind="storyboard",
            style_tags=["storyboard", "narration-linked"],
            requirements={
                "storyboard": {
                    "proposal_id": proposal.proposal_id,
                    "beat_id": beat.beat_id,
                    "narration_unit_ids": list(beat.narration_unit_ids),
                    "continuity_reference_ids": list(beat.continuity_reference_ids),
                    "timing": {
                        "start_ms": beat.timing.start_ms,
                        "end_ms": beat.timing.end_ms,
                        "basis": beat.timing.basis.value,
                    },
                }
            },
            notes=item.notes,
            plan_status="approved",
            script_hash=hashlib.sha256(item.narration_text.encode("utf-8")).hexdigest(),
        )
        next_state.scene_plans[item.scene_id] = plan

    next_state.extra["storyboard_applied_proposal_ids"] = [
        *history, proposal.proposal_id
    ]
    next_settings = next_state.apply_to_project_settings(project.settings)

    # Single mutation point after every validation and detached-copy operation.
    project.scenes = next_scenes
    project.settings = next_settings
    project.touch()
