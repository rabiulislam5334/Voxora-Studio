"""Local-first, deterministic Production Director planning core.

This is the first VXP-10.4 decision layer. It converts exact narration units
into reviewable scene/shot intent using transparent rules and channel-profile
policy. It does not claim LLM-level semantic understanding and never creates,
fetches, or renders media.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence, Tuple

from app.universal.profiles.models import ChannelProfile
from app.universal.storyboard import (
    NarrationSource,
    StoryboardValidationError,
    TimingInterval,
)
from app.universal.storyboard_builder import StoryboardBuilderConfig, build_storyboard_proposal


class DirectorIntent(str, Enum):
    QUESTION_REVEAL = "question_reveal"
    MAP = "map"
    DIAGRAM = "diagram"
    EVIDENCE = "evidence"
    TIMELINE = "timeline"
    CHARACTER_ACTION = "character_action"
    ENVIRONMENT = "environment"
    ILLUSTRATIVE = "illustrative"


class SceneRole(str, Enum):
    INTRO = "intro"
    BODY = "body"
    OUTRO = "outro"


@dataclass(frozen=True)
class ProductionDirectorConfig:
    """Bounded deterministic defaults; all estimates remain explicitly labelled."""

    max_shots_per_scene: int = 4
    default_shot_duration_ms: int = 5000

    def __post_init__(self) -> None:
        if (isinstance(self.max_shots_per_scene, bool)
                or not isinstance(self.max_shots_per_scene, int)
                or self.max_shots_per_scene < 1 or self.max_shots_per_scene > 12):
            raise StoryboardValidationError("max_shots_per_scene must be an integer from 1 to 12")
        if (isinstance(self.default_shot_duration_ms, bool)
                or not isinstance(self.default_shot_duration_ms, int)
                or self.default_shot_duration_ms <= 0):
            raise StoryboardValidationError("default_shot_duration_ms must be a positive integer")


@dataclass(frozen=True)
class DirectorShot:
    shot_id: str
    narration_unit_ids: Tuple[str, ...]
    timing: TimingInterval
    intent: DirectorIntent
    shot_type: str
    visual_prompt: str
    action_cues: Tuple[str, ...]
    style_family: str
    confidence: float
    rationale: Tuple[str, ...]
    tags: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "shot_id": self.shot_id,
            "narration_unit_ids": list(self.narration_unit_ids),
            "timing": self.timing.to_dict(),
            "intent": self.intent.value,
            "shot_type": self.shot_type,
            "visual_prompt": self.visual_prompt,
            "action_cues": list(self.action_cues),
            "style_family": self.style_family,
            "confidence": self.confidence,
            "rationale": list(self.rationale),
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class DirectorScene:
    scene_id: str
    title: str
    role: SceneRole
    purpose: str
    shot_ids: Tuple[str, ...]
    narration_unit_ids: Tuple[str, ...]
    timing: TimingInterval

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "role": self.role.value,
            "purpose": self.purpose,
            "shot_ids": list(self.shot_ids),
            "narration_unit_ids": list(self.narration_unit_ids),
            "timing": self.timing.to_dict(),
        }


@dataclass(frozen=True)
class DirectorPlan:
    plan_id: str
    source_id: str
    source_fingerprint: str
    profile_id: str
    profile_style_family: str
    scenes: Tuple[DirectorScene, ...]
    shots: Tuple[DirectorShot, ...]
    requires_review: bool = True
    limitations: Tuple[str, ...] = (
        "Rule-based semantic heuristics; not an LLM or human-level content understanding.",
        "Visual prompts are proposals only; no assets are acquired or generated.",
        "Estimated narration timing is not a substitute for measured audio alignment.",
        "Continuity, factual verification, and sensitive-content review remain required.",
    )

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "source_id": self.source_id,
            "source_fingerprint": self.source_fingerprint,
            "profile_id": self.profile_id,
            "profile_style_family": self.profile_style_family,
            "requires_review": self.requires_review,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "shots": [shot.to_dict() for shot in self.shots],
            "limitations": list(self.limitations),
        }


# Each rule is deliberately inspectable and conservative. A rule match is a
# planning hint, never a factual claim about the source narration.
_RULES = (
    (DirectorIntent.QUESTION_REVEAL, "question_reveal", ("why", "how", "what if", "mystery", "question", "revealed"), ("reveal", "hold", "push in")),
    (DirectorIntent.MAP, "map", ("map", "route", "border", "continent", "country", "city", "region", "island", "ocean", "river", "coast", "north", "south", "east", "west", "across"), ("map reveal", "route trace", "location highlight")),
    (DirectorIntent.DIAGRAM, "diagram", ("gravity", "orbit", "molecule", "cell", "dna", "energy", "force", "system", "process", "signal", "frequency", "temperature", "pressure", "wave", "percent", "data", "equation"), ("diagram build", "highlight relationship", "label key element")),
    (DirectorIntent.EVIDENCE, "evidence", ("document", "record", "letter", "photograph", "evidence", "report", "artifact", "manuscript", "logbook", "newspaper", "archive", "inscription", "source"), ("document reveal", "slow detail pan", "highlight evidence")),
    (DirectorIntent.TIMELINE, "timeline", ("century", "decade", "year", "before", "after", "later", "earlier", "in 18", "in 19", "in 20", "in 21", "timeline", "on this day"), ("timeline marker", "date emphasis", "chronological transition")),
    (DirectorIntent.CHARACTER_ACTION, "character_action", ("walked", "runs", "ran", "opened", "closed", "looked", "turned", "stood", "whispered", "entered", "left", "reached", "carried", "followed", "disappeared"), ("character action", "reaction pose", "motivated camera move")),
    (DirectorIntent.ENVIRONMENT, "environment", ("forest", "desert", "mountain", "ocean", "sky", "room", "street", "island", "planet", "cave", "village", "city", "storm", "shore", "valley"), ("establishing view", "atmospheric movement", "depth/parallax")),
)


def _matches(text: str, term: str) -> int:
    pattern = r"(?<!\\w)" + re.escape(term) + r"(?!\\w)"
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _classify(text: str, profile: ChannelProfile) -> tuple[DirectorIntent, str, float, tuple[str, ...], tuple[str, ...]]:
    normalized = text.casefold()
    scores = []
    for index, (intent, shot_type, terms, cues) in enumerate(_RULES):
        matched = tuple(term for term in terms if _matches(normalized, term))
        if matched:
            scores.append((len(matched), -index, intent, shot_type, matched, cues))
    if not scores:
        return (
            DirectorIntent.ILLUSTRATIVE,
            "illustrative_scene",
            0.25,
            ("No high-confidence intent keyword matched; use a neutral visual interpretation.",),
            ("slow camera drift", "emphasize the narration's central subject"),
        )
    score, _, intent, shot_type, matched, cues = max(scores, key=lambda item: (item[0], item[1]))
    confidence = min(0.92, 0.55 + 0.08 * (score - 1))
    rationale = tuple("matched keyword: " + term for term in matched)
    return intent, shot_type, confidence, rationale, cues


def _scene_family(intent: DirectorIntent) -> str:
    if intent in (DirectorIntent.MAP, DirectorIntent.EVIDENCE, DirectorIntent.TIMELINE):
        return "documentary"
    if intent in (DirectorIntent.DIAGRAM, DirectorIntent.QUESTION_REVEAL):
        return "explainer"
    if intent in (DirectorIntent.CHARACTER_ACTION, DirectorIntent.ENVIRONMENT):
        return "story"
    return "illustration"


def _short_title(text: str, limit: int = 8) -> str:
    words = text.strip().split()
    if not words:
        return "Visual sequence"
    title = " ".join(words[:limit]).strip(" \\t\\r\\n.,;:!?")
    return title + ("…" if len(words) > limit else "")


class ProductionDirector:
    """Build a deterministic, profile-aware scene/shot plan from exact narration."""

    def __init__(self, config: Optional[ProductionDirectorConfig] = None) -> None:
        self.config = config or ProductionDirectorConfig()
        if not isinstance(self.config, ProductionDirectorConfig):
            raise StoryboardValidationError("config must be ProductionDirectorConfig")

    def create_plan(self, source: NarrationSource, profile: ChannelProfile) -> DirectorPlan:
        if not isinstance(source, NarrationSource):
            raise StoryboardValidationError("source must be NarrationSource")
        if not isinstance(profile, ChannelProfile):
            raise StoryboardValidationError("profile must be ChannelProfile")
        if not source.text.strip() or not source.units:
            raise StoryboardValidationError("a non-empty script with narration units is required")

        timing_proposal = build_storyboard_proposal(
            source,
            config=StoryboardBuilderConfig(
                default_beat_duration_ms=self.config.default_shot_duration_ms
            ),
        )
        style_family = profile.visual_defaults.style_family
        style_tags = tuple(profile.visual_defaults.style_tags)
        guidance = tuple(profile.visual_defaults.composition_guidance)
        is_rihvaya = profile.profile_id == "rihvaya"
        policy_lines = list(guidance)
        if is_rihvaya:
            policy_lines.extend((
                "Never depict Prophets or Sahaba with identifiable facial features.",
                "Do not invent religious dialogue, events, or unsupported visual claims.",
            ))
        policy = " ".join(dict.fromkeys(policy_lines))
        shots = []
        unit_by_id = {unit.unit_id: unit for unit in source.units}
        for index, beat in enumerate(timing_proposal.beats, start=1):
            unit = unit_by_id[beat.narration_unit_ids[0]]
            narration_text = source.text_for_unit(unit).strip()
            intent, shot_type, confidence, rationale, cues = _classify(narration_text, profile)
            prompt_parts = [
                f"{shot_type.replace('_', ' ')} visual for: {narration_text}",
                f"Visual language: {style_family}.",
            ]
            if style_tags:
                prompt_parts.append("Style tags: " + ", ".join(style_tags) + ".")
            if policy:
                prompt_parts.append("Profile constraints: " + policy)
            shots.append(DirectorShot(
                shot_id=f"shot-{index:04d}",
                narration_unit_ids=(unit.unit_id,),
                timing=beat.timing,
                intent=intent,
                shot_type=shot_type,
                visual_prompt=" ".join(prompt_parts),
                action_cues=tuple(cues),
                style_family=style_family,
                confidence=confidence,
                rationale=rationale,
                tags=tuple(dict.fromkeys((intent.value, _scene_family(intent)) + style_tags)),
            ))

        # Group adjacent shots by narrative family, paragraph boundary, and a
        # bounded shot count. The source text and timing are never rewritten.
        groups: list[list[DirectorShot]] = []
        for shot in shots:
            unit = unit_by_id[shot.narration_unit_ids[0]]
            unit_text = source.text_for_unit(unit)
            paragraph_start = bool(groups and re.search(r"\\n[ \\t]*\\n", unit_text))
            if (not groups or len(groups[-1]) >= self.config.max_shots_per_scene
                    or _scene_family(groups[-1][-1].intent) != _scene_family(shot.intent)
                    or paragraph_start):
                groups.append([])
            groups[-1].append(shot)

        scenes = []
        for index, group in enumerate(groups, start=1):
            first_unit = unit_by_id[group[0].narration_unit_ids[0]]
            scene_text = source.text_for_unit(first_unit).strip()
            if len(groups) >= 3:
                role = SceneRole.INTRO if index == 1 else SceneRole.OUTRO if index == len(groups) else SceneRole.BODY
            else:
                role = SceneRole.BODY
            family = _scene_family(group[0].intent)
            purpose = {
                "documentary": "Present locations, chronology, or source evidence clearly.",
                "explainer": "Make the central question or explanatory relationship visually understandable.",
                "story": "Stage an environment or character action that supports the narration.",
                "illustration": "Provide a restrained visual interpretation of the narration.",
            }[family]
            start_ms = min(shot.timing.start_ms for shot in group)
            end_ms = max(shot.timing.end_ms for shot in group)
            basis = (
                group[0].timing.basis
                if all(shot.timing.basis == group[0].timing.basis for shot in group)
                else group[0].timing.basis
            )
            scenes.append(DirectorScene(
                scene_id=f"scene-{index:04d}",
                title=_short_title(scene_text),
                role=role,
                purpose=purpose,
                shot_ids=tuple(shot.shot_id for shot in group),
                narration_unit_ids=tuple(
                    unit_id for shot in group for unit_id in shot.narration_unit_ids
                ),
                timing=TimingInterval(start_ms, end_ms, basis),
            ))

        identity = {
            "source_id": source.source_id,
            "source_fingerprint": source.source_fingerprint,
            "profile_id": profile.profile_id,
            "config": {
                "max_shots_per_scene": self.config.max_shots_per_scene,
                "default_shot_duration_ms": self.config.default_shot_duration_ms,
            },
            "scenes": [scene.to_dict() for scene in scenes],
            "shots": [shot.to_dict() for shot in shots],
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return DirectorPlan(
            plan_id=f"director-{digest[:24]}",
            source_id=source.source_id,
            source_fingerprint=source.source_fingerprint,
            profile_id=profile.profile_id,
            profile_style_family=style_family,
            scenes=tuple(scenes),
            shots=tuple(shots),
        )
