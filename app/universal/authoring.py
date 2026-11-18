"""Pure, deterministic authoring proposals for Universal Scene Plans.

Proposal generation never mutates a Project, performs I/O, or selects an engine.
The caller must review a proposal before a later explicit apply operation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from fractions import Fraction
from dataclasses import dataclass, field
from typing import Literal, Sequence

from app.core.timebase import seconds_to_ticks
from app.models.project import Project
from app.models.scene import Scene
from app.text.wordcount import DEFAULT_WORDS_PER_MINUTE, count_words
from app.universal.models import ScenePlan

SplitStrategy = Literal["existing_scenes", "paragraphs", "explicit_marker", "manual"]


@dataclass(frozen=True)
class SceneAuthoringOptions:
    """Explicit, deterministic controls for turning text into scene drafts."""

    split_strategy: SplitStrategy = "paragraphs"
    explicit_marker: str | None = None
    words_per_minute: int = DEFAULT_WORDS_PER_MINUTE

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if self.split_strategy not in (
            "existing_scenes", "paragraphs", "explicit_marker", "manual"
        ):
            errors.append("split_strategy must be existing_scenes, paragraphs, explicit_marker, or manual")
        if self.split_strategy == "explicit_marker":
            if not isinstance(self.explicit_marker, str) or not self.explicit_marker:
                errors.append("explicit_marker strategy requires a non-empty marker")
        elif self.explicit_marker is not None and not isinstance(self.explicit_marker, str):
            errors.append("explicit_marker must be a string or null")
        if (
            isinstance(self.words_per_minute, bool)
            or not isinstance(self.words_per_minute, int)
            or self.words_per_minute <= 0
        ):
            errors.append("words_per_minute must be a positive integer")
        return tuple(errors)


@dataclass(frozen=True)
class AuthoringDiagnostic:
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    segment_index: int | None = None


@dataclass
class SceneDraft:
    """Editable proposal data; estimated timing is never render-authoritative."""

    scene_id: str
    title: str
    text: str
    notes: str
    visual_prompt: str
    order: int
    word_count: int
    estimated_duration_ticks: int
    visual_plan: ScenePlan


@dataclass
class ScenePlanProposal:
    split_strategy: str
    words_per_minute: int
    proposal_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source_scene_ids: list[str] = field(default_factory=list)
    scenes: list[SceneDraft] = field(default_factory=list)
    diagnostics: list[AuthoringDiagnostic] = field(default_factory=list)
    source_fingerprint: str = ""

    @property
    def is_valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


_PARAGRAPH_SEPARATOR = re.compile(r"\n[ \t]*\n+")


def _fingerprint(strategy: str, wpm: int, segments: Sequence[tuple[str, str, str, str]]) -> str:
    payload = {
        "strategy": strategy,
        "words_per_minute": wpm,
        "segments": [
            {"title": title, "text": text, "notes": notes, "visual_prompt": prompt}
            for title, text, notes, prompt in segments
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _split_script(script: str, options: SceneAuthoringOptions) -> tuple[list[str], list[AuthoringDiagnostic]]:
    diagnostics: list[AuthoringDiagnostic] = []
    if not isinstance(script, str):
        return [], [AuthoringDiagnostic("invalid_script", "script must be a string")]
    if not script.strip():
        return [], [AuthoringDiagnostic("empty_script", "script contains no narration text")]

    if options.split_strategy == "manual":
        raw_segments = [script]
    elif options.split_strategy == "paragraphs":
        raw_segments = _PARAGRAPH_SEPARATOR.split(script.strip())
    elif options.split_strategy == "explicit_marker":
        marker = options.explicit_marker
        if not isinstance(marker, str) or not marker:
            return [], [AuthoringDiagnostic(
                "missing_marker", "explicit_marker strategy requires a non-empty marker"
            )]
        raw_segments = script.split(marker)
    else:
        return [], [AuthoringDiagnostic(
            "wrong_split_strategy", "existing_scenes strategy requires existing_scenes input"
        )]

    segments: list[str] = []
    for index, raw in enumerate(raw_segments, start=1):
        text = raw.strip()
        if not text:
            diagnostics.append(AuthoringDiagnostic(
                "empty_segment",
                f"Split segment {index} is empty and was omitted.",
                severity="warning",
                segment_index=index,
            ))
            continue
        segments.append(text)
    if not segments:
        diagnostics.append(AuthoringDiagnostic("no_scenes", "No non-empty scene segments were produced"))
    return segments, diagnostics


def build_scene_plan_proposal(
    script: str | None = None,
    *,
    existing_scenes: Sequence[Scene] | None = None,
    options: SceneAuthoringOptions | None = None,
) -> ScenePlanProposal:
    """Build a reviewable proposal without changing project or source scenes.

    Supported strategies:
    - paragraphs: split on blank lines;
    - explicit_marker: split on the exact user-supplied marker;
    - manual: treat the entire script as one scene;
    - existing_scenes: preserve the supplied Scene boundaries and IDs.
    """
    selected = options or SceneAuthoringOptions()
    proposal = ScenePlanProposal(
        split_strategy=selected.split_strategy,
        words_per_minute=selected.words_per_minute,
    )
    option_errors = selected.validate()
    if option_errors:
        proposal.diagnostics.extend(
            AuthoringDiagnostic("invalid_options", message) for message in option_errors
        )
        return proposal

    segments: list[tuple[str, str, str, str]] = []
    source_ids: list[str] = []
    if selected.split_strategy == "existing_scenes":
        if existing_scenes is None:
            proposal.diagnostics.append(AuthoringDiagnostic(
                "missing_existing_scenes", "existing_scenes strategy requires existing_scenes input"
            ))
            return proposal
        if not isinstance(existing_scenes, Sequence) or isinstance(existing_scenes, (str, bytes)):
            proposal.diagnostics.append(AuthoringDiagnostic(
                "invalid_existing_scenes", "existing_scenes must be a sequence of Scene objects"
            ))
            return proposal
        seen_ids: set[str] = set()
        for index, scene in enumerate(existing_scenes):
            if not isinstance(scene, Scene):
                proposal.diagnostics.append(AuthoringDiagnostic(
                    "invalid_existing_scene", f"Item {index + 1} is not a Scene."
                ))
                continue
            if not isinstance(scene.id, str) or not scene.id.strip():
                proposal.diagnostics.append(AuthoringDiagnostic(
                    "invalid_scene_id", f"Existing scene {index + 1} has an empty ID."
                ))
                continue
            if scene.id in seen_ids:
                proposal.diagnostics.append(AuthoringDiagnostic(
                    "duplicate_scene_id", f"Duplicate existing scene ID: {scene.id}"
                ))
                continue
            seen_ids.add(scene.id)
            if not isinstance(scene.text, str) or not scene.text.strip():
                proposal.diagnostics.append(AuthoringDiagnostic(
                    "empty_existing_scene", f"Existing scene {scene.id} has no narration text.",
                    segment_index=index + 1,
                ))
                continue
            segments.append((
                scene.title if isinstance(scene.title, str) and scene.title.strip() else f"Scene {len(segments) + 1}",
                scene.text.strip(),
                scene.notes if isinstance(scene.notes, str) else "",
                scene.visual_prompt if isinstance(scene.visual_prompt, str) else "",
            ))
            source_ids.append(scene.id)
        if any(item.severity == "error" for item in proposal.diagnostics):
            return proposal
        if not segments:
            proposal.diagnostics.append(AuthoringDiagnostic(
                "no_scenes", "No non-empty existing scenes were supplied"
            ))
            return proposal
    else:
        if script is None:
            proposal.diagnostics.append(AuthoringDiagnostic(
                "missing_script", "A script string is required for this split strategy"
            ))
            return proposal
        text_segments, split_diagnostics = _split_script(script, selected)
        proposal.diagnostics.extend(split_diagnostics)
        segments = [
            (f"Scene {index}", text, "", "")
            for index, text in enumerate(text_segments, start=1)
        ]
        source_ids = []

    proposal.source_fingerprint = _fingerprint(
        selected.split_strategy, selected.words_per_minute, segments
    )
    proposal.source_scene_ids = list(source_ids)
    for index, (title, text, notes, visual_prompt) in enumerate(segments):
        scene_id = source_ids[index] if source_ids else uuid.uuid4().hex[:12]
        words = count_words(text)
        # Fractional seconds are converted exactly to the canonical integer tick clock.
        estimated_ticks = seconds_to_ticks(Fraction(words * 60, selected.words_per_minute))
        script_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        visual_plan = ScenePlan(
            scene_id=scene_id,
            kind="unspecified",
            plan_status="proposed",
            script_hash=script_hash,
            notes=notes,
        )
        proposal.scenes.append(SceneDraft(
            scene_id=scene_id,
            title=title,
            text=text,
            notes=notes,
            visual_prompt=visual_prompt,
            order=index,
            word_count=words,
            estimated_duration_ticks=estimated_ticks,
            visual_plan=visual_plan,
        ))
    return proposal



def apply_scene_plan_proposal(project: Project, proposal: ScenePlanProposal) -> None:
    """Atomically apply a reviewed proposal to a Project in memory.

    New-scene strategies append scenes; existing-scenes mode updates and
    reorders only the scenes captured by the proposal. Universal plans are
    persisted additively under settings["universal"]. The caller owns any
    ProjectManager dirty-state notification and disk save.

    Raises ValueError before mutation when validation, stale-source checks,
    duplicate-apply protection, or Universal payload compatibility fails.
    """
    from app.universal.models import ScenePlan, UniversalState

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    if not isinstance(proposal, ScenePlanProposal):
        raise ValueError("proposal must be a ScenePlanProposal")
    if not proposal.is_valid:
        raise ValueError("Cannot apply an invalid scene proposal")
    if not isinstance(proposal.proposal_id, str) or not proposal.proposal_id.strip():
        raise ValueError("proposal_id must be a non-empty string")
    if not isinstance(proposal.source_fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", proposal.source_fingerprint
    ):
        raise ValueError("proposal source fingerprint is invalid")
    if proposal.split_strategy not in (
        "existing_scenes", "paragraphs", "explicit_marker", "manual"
    ):
        raise ValueError("proposal split strategy is unsupported")
    if not isinstance(proposal.scenes, list) or not proposal.scenes:
        raise ValueError("proposal must contain at least one scene")

    drafts = list(proposal.scenes)
    if any(not isinstance(draft, SceneDraft) for draft in drafts):
        raise ValueError("proposal contains an invalid scene draft")
    if any(
        not isinstance(draft.scene_id, str) or not draft.scene_id.strip()
        or not isinstance(draft.title, str)
        or not isinstance(draft.text, str) or not draft.text.strip()
        or not isinstance(draft.notes, str)
        or not isinstance(draft.visual_prompt, str)
        or isinstance(draft.order, bool) or not isinstance(draft.order, int)
        or isinstance(draft.word_count, bool) or not isinstance(draft.word_count, int)
        or draft.word_count < 0
        or isinstance(draft.estimated_duration_ticks, bool)
        or not isinstance(draft.estimated_duration_ticks, int)
        or draft.estimated_duration_ticks < 0
        for draft in drafts
    ):
        raise ValueError("proposal contains invalid scene draft fields")

    ids = [draft.scene_id for draft in drafts]
    if len(ids) != len(set(ids)):
        raise ValueError("proposal contains duplicate scene IDs")
    if sorted(draft.order for draft in drafts) != list(range(len(drafts))):
        raise ValueError("proposal scene order must be a unique contiguous range")

    # Validate and detach every visual plan before touching the target project.
    accepted_plans: dict[str, ScenePlan] = {}
    for draft in drafts:
        if not isinstance(draft.visual_plan, ScenePlan):
            raise ValueError(f"scene {draft.scene_id} has no valid ScenePlan")
        if draft.visual_plan.scene_id != draft.scene_id:
            raise ValueError(f"scene plan ID does not match scene {draft.scene_id}")
        try:
            plan = ScenePlan.from_dict(draft.visual_plan.to_dict())
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"scene {draft.scene_id} has an invalid ScenePlan: {exc}") from exc
        plan.plan_status = "approved"
        plan.script_hash = hashlib.sha256(draft.text.encode("utf-8")).hexdigest()
        accepted_plans[draft.scene_id] = plan

    settings = project.settings
    if not isinstance(settings, dict):
        raise ValueError("project settings must be an object")
    state = UniversalState.from_project_settings(settings)
    if state.read_only:
        raise ValueError(
            "Universal project data is read-only (future or malformed format); "
            "apply was refused to protect existing data"
        )

    applied_ids = state.extra.get("authoring_applied_proposal_ids", [])
    if not isinstance(applied_ids, list) or any(not isinstance(item, str) for item in applied_ids):
        raise ValueError("Universal authoring apply history is malformed")
    if proposal.proposal_id in applied_ids:
        raise ValueError("This scene proposal has already been applied")

    # Build a complete replacement off to the side. No target state is mutated
    # until all source, ID, and Universal-state checks have succeeded.
    next_scenes = copy.deepcopy(project.scenes)
    if not isinstance(next_scenes, list) or any(not isinstance(scene, Scene) for scene in next_scenes):
        raise ValueError("project contains an invalid scene collection")

    ordered_drafts = sorted(drafts, key=lambda draft: draft.order)
    current_ids = [scene.id for scene in next_scenes]
    if len(current_ids) != len(set(current_ids)):
        raise ValueError("project contains duplicate scene IDs")

    if proposal.split_strategy == "existing_scenes":
        if not proposal.source_scene_ids or len(proposal.source_scene_ids) != len(set(proposal.source_scene_ids)):
            raise ValueError("existing-scenes proposal has invalid source scene IDs")
        if current_ids != proposal.source_scene_ids:
            raise ValueError("project scenes changed after this proposal was created; rebuild the proposal")
        if any(not isinstance(scene.text, str) for scene in next_scenes):
            raise ValueError("project scene text changed to an invalid value")
        source_segments = [
            (
                scene.title if isinstance(scene.title, str) and scene.title.strip() else f"Scene {index + 1}",
                scene.text.strip(),
                scene.notes if isinstance(scene.notes, str) else "",
                scene.visual_prompt if isinstance(scene.visual_prompt, str) else "",
            )
            for index, scene in enumerate(next_scenes)
        ]
        current_fingerprint = _fingerprint(
            proposal.split_strategy, proposal.words_per_minute, source_segments
        )
        if current_fingerprint != proposal.source_fingerprint:
            raise ValueError("project scene content changed after this proposal was created")
        scene_by_id = {scene.id: scene for scene in next_scenes}
        updated_scenes: list[Scene] = []
        for draft in ordered_drafts:
            scene = scene_by_id.get(draft.scene_id)
            if scene is None:
                raise ValueError(f"proposal references missing project scene: {draft.scene_id}")
            scene.title = draft.title
            scene.text = draft.text
            scene.notes = draft.notes
            scene.visual_prompt = draft.visual_prompt
            scene.order = draft.order
            scene.touch()
            updated_scenes.append(scene)
        next_scenes = updated_scenes
    else:
        if proposal.source_scene_ids:
            raise ValueError("new-scene proposal unexpectedly contains source scene IDs")
        collisions = set(ids).intersection(current_ids)
        if collisions:
            raise ValueError(
                "proposal scene IDs already exist in the project: " + ", ".join(sorted(collisions))
            )
        for draft in ordered_drafts:
            next_scenes.append(Scene(
                id=draft.scene_id,
                title=draft.title,
                text=draft.text,
                notes=draft.notes,
                visual_prompt=draft.visual_prompt,
                order=len(next_scenes),
            ))

    next_state = copy.deepcopy(state)
    next_state.scene_plans.update(accepted_plans)
    next_state.prune_scenes(scene.id for scene in next_scenes)
    next_state.extra["authoring_applied_proposal_ids"] = [
        *applied_ids, proposal.proposal_id
    ]
    next_settings = next_state.apply_to_project_settings(settings)

    # Single commit point: all operations above work on detached copies.
    project.scenes = next_scenes
    project.settings = next_settings
    project.touch()
