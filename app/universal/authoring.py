"""Pure, deterministic authoring proposals for Universal Scene Plans.

Proposal generation never mutates a Project, performs I/O, or selects an engine.
The caller must review a proposal before a later explicit apply operation.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Literal, Sequence

from app.core.timebase import seconds_to_ticks
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
        if self.split_strategy not in {
            "existing_scenes", "paragraphs", "explicit_marker", "manual"
        }:
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
    if selected.split_strategy == "existing_scenes":
        if existing_scenes is None:
            proposal.diagnostics.append(AuthoringDiagnostic(
                "missing_existing_scenes", "existing_scenes strategy requires existing_scenes input"
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
            # Preserve source IDs separately; existing scene proposals must retain identity.
        source_ids = [
            scene.id for scene in existing_scenes
            if isinstance(scene, Scene) and isinstance(scene.id, str) and scene.id.strip()
            and isinstance(scene.text, str) and scene.text.strip()
        ]
        if len(source_ids) != len(segments):
            # Duplicate or invalid source scenes were already diagnosed; avoid misaligning IDs.
            source_ids = []
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
    for index, (title, text, notes, visual_prompt) in enumerate(segments):
        scene_id = source_ids[index] if source_ids else uuid.uuid4().hex[:12]
        words = count_words(text)
        # Fractional seconds are converted exactly to the canonical integer tick clock.
        estimated_ticks = seconds_to_ticks(f"{words * 60}/{selected.words_per_minute}")
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
