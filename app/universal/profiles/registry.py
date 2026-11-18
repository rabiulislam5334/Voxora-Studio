"""Deterministic, data-driven registry of Voxora's built-in channel profiles.

The registry stores only serializable profile documents and returns a freshly
validated model on every read. Callers therefore cannot mutate shared registry
state through the mutable JSON metadata carried by the frozen domain models.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from app.universal.profiles.models import ChannelProfile, ProfileValidationError


_BUILTIN_PROFILE_DATA: tuple[dict[str, Any], ...] = (
    {
        "schema_version": 1,
        "profile_id": "quasivanta",
        "display_name": "Quasivanta",
        "description": "Space, astronomy, and evidence-led science storytelling.",
        "content_domains": ["space_science", "astronomy", "planetary_science", "astrophysics"],
        "audience": {"language": "en", "region": "international"},
        "narration_defaults": {"tone": "curious", "pacing": "documentary"},
        "visual_defaults": {
            "style_family": "cinematic_scientific_visualization",
            "style_tags": ["cinematic_3d", "scientific_diagrams", "space_environments", "planetary_motion", "infographics"],
            "mood": ["wonder", "scale", "discovery"],
            "composition_guidance": ["Prioritize scientific clarity and readable scale.", "Distinguish verified data from artistic visualization."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30},
        "preferred_engines": [],
        "rules": [
            {
                "rule_id": "label_artistic_visualizations",
                "category": "review",
                "severity": "warning",
                "scope": "scene_plan",
                "target": "scientific_visualization_accuracy",
                "operator": "manual_review",
                "message": "Review scientific visualizations and distinguish artistic interpretation from observed data.",
            }
        ],
        "presets": [],
        "metadata": {"profile_family": "science_documentary"},
    },
    {
        "schema_version": 1,
        "profile_id": "veltracis",
        "display_name": "Veltracis",
        "description": "Historical mysteries, ancient civilizations, archaeology, and unexplained events.",
        "content_domains": ["history", "archaeology", "ancient_civilizations", "historical_mystery", "exploration"],
        "audience": {"language": "en", "region": "international"},
        "narration_defaults": {"tone": "investigative", "pacing": "cinematic_documentary"},
        "visual_defaults": {
            "style_family": "documentary_collage_2_5d",
            "style_tags": ["documentary_collage", "sketch_illustration", "historical_maps", "artifacts", "timelines", "2_5d"],
            "mood": ["intrigue", "discovery", "historical_atmosphere"],
            "composition_guidance": ["Use maps and artifacts as visual evidence.", "Keep reconstructions visually distinct from documented records."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30},
        "preferred_engines": [],
        "rules": [
            {
                "rule_id": "review_historical_claims",
                "category": "review",
                "severity": "warning",
                "scope": "project",
                "target": "historical_claims_and_sources",
                "operator": "manual_review",
                "message": "Review historical claims, dates, and source quality before approval.",
            }
        ],
        "presets": [],
        "metadata": {"profile_family": "history_documentary"},
    },
    {
        "schema_version": 1,
        "profile_id": "sizzjin",
        "display_name": "Sizzjin",
        "description": "Original horror, psychological suspense, and atmospheric storytelling.",
        "content_domains": ["horror", "psychological_suspense", "fiction", "mystery"],
        "audience": {"language": "en", "region": "international"},
        "narration_defaults": {"tone": "suspenseful", "pacing": "controlled_revelation"},
        "visual_defaults": {
            "style_family": "cinematic_illustration_2_5d",
            "style_tags": ["silhouette", "paper_cutout", "atmospheric_2_5d", "cinematic_illustration", "shadow_composition"],
            "mood": ["dread", "uncertainty", "tension"],
            "composition_guidance": ["Build suspense through lighting, framing, and negative space.", "Prefer original visual concepts over horror clichés."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30},
        "preferred_engines": [],
        "rules": [],
        "presets": [],
        "metadata": {"profile_family": "fictional_storytelling"},
    },
    {
        "schema_version": 1,
        "profile_id": "drowsehaven",
        "display_name": "Drowsehaven",
        "description": "Long-form adult sleep stories, mythology, fantasy, and quiet literary journeys.",
        "content_domains": ["sleep_stories", "mythology", "fantasy", "public_domain_literature", "relaxation"],
        "audience": {"language": "en", "region": "international", "content_format": "long_form"},
        "narration_defaults": {"tone": "soothing", "pacing": "slow", "delivery": "gentle"},
        "visual_defaults": {
            "style_family": "watercolor_cinematic_illustration",
            "style_tags": ["watercolor", "cinematic_illustration", "2_5d", "ambient_environments", "slow_camera_movement"],
            "mood": ["peaceful", "dreamlike", "wonder"],
            "composition_guidance": ["Favor calm compositions and soft visual transitions.", "Avoid abrupt motion and visually aggressive contrast."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30, "audio_policy": "narration_and_single_ambient_music_bed"},
        "preferred_engines": [],
        "rules": [],
        "presets": [],
        "metadata": {"profile_family": "long_form_sleep_story"},
    },
    {
        "schema_version": 1,
        "profile_id": "rihvaya",
        "display_name": "Rihvaya",
        "description": "Islamic stories, Quran and authentic Hadith education, history, and civilization.",
        "content_domains": ["islamic_education", "quran", "authentic_hadith", "prophetic_history", "sahaba", "islamic_civilization", "quran_and_science"],
        "audience": {"language": "en", "region": "international"},
        "narration_defaults": {"tone": "respectful", "pacing": "documentary", "source_policy": "evidence_led"},
        "visual_defaults": {
            "style_family": "respectful_islamic_documentary",
            "style_tags": ["historical_maps", "manuscript_animation", "documentary_illustration", "2d_motion_graphics", "respectful_visual_storytelling"],
            "mood": ["reflective", "educational", "reverent"],
            "composition_guidance": ["Use respectful symbolic, environmental, and historical visuals.", "Do not depict Prophets or Sahaba as identifiable faces.", "Do not invent dialogue or present uncertain reports as established facts."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30},
        "preferred_engines": [],
        "rules": [
            {
                "rule_id": "verify_religious_sources",
                "category": "review",
                "severity": "warning",
                "scope": "project",
                "target": "quran_hadith_and_historical_sources",
                "operator": "manual_review",
                "message": "Verify Quran references, Hadith authenticity, and historical claims before approval.",
            },
            {
                "rule_id": "review_sensitive_depictions",
                "category": "review",
                "severity": "warning",
                "scope": "scene_plan",
                "target": "religious_visual_sensitivity",
                "operator": "manual_review",
                "message": "Review sensitive religious depictions and ensure visual choices follow the channel's respectful constraints.",
            },
        ],
        "presets": [
            {
                "preset_id": "islamic_documentary",
                "display_name": "Islamic Documentary",
                "description": "Evidence-led narration with source review, historical context, maps, manuscripts, and diagrams.",
                "visual_defaults": {
                    "style_family": "respectful_documentary_illustration",
                    "style_tags": ["historical_maps", "manuscripts", "diagrams", "cinematic_documentary"],
                    "mood": ["reverent", "informative", "reflective"],
                    "composition_guidance": ["Make evidence and historical context visually clear.", "Keep uncertain reconstructions distinct from verified source material."],
                },
                "narration_defaults": {"tone": "evidence_led", "pacing": "cinematic_documentary"},
                "rules": [
                    {
                        "rule_id": "documentary_source_review",
                        "category": "review",
                        "severity": "warning",
                        "scope": "project",
                        "target": "source_verification",
                        "operator": "manual_review",
                        "message": "Complete source verification before approving the documentary.",
                    }
                ],
            },
            {
                "preset_id": "islamic_2d_cartoon_storytelling",
                "display_name": "Islamic 2D Cartoon Storytelling",
                "description": "Narration-synchronized 2D scenes with consistent characters, actions, reactions, backgrounds, props, and camera continuity.",
                "visual_defaults": {
                    "style_family": "2d_cartoon_storytelling",
                    "style_tags": ["2d_cartoon", "consistent_recurring_characters", "narration_synced_actions", "background_continuity", "prop_continuity", "camera_continuity"],
                    "mood": ["educational", "warm", "engaging"],
                    "composition_guidance": ["Align visible actions and reactions with the narration.", "Maintain character, costume, prop, and background continuity.", "Apply respectful visual constraints to religious and historical subjects."],
                },
                "narration_defaults": {"tone": "clear_storytelling", "pacing": "scene_synchronized"},
                "rules": [
                    {
                        "rule_id": "cartoon_sensitive_visual_review",
                        "category": "review",
                        "severity": "warning",
                        "scope": "scene_plan",
                        "target": "character_and_scene_visuals",
                        "operator": "manual_review",
                        "message": "Review character and scene visuals for continuity and religious sensitivity before approval.",
                    }
                ],
            },
        ],
        "metadata": {"profile_family": "islamic_education", "supports_multiple_production_presets": True},
    },
    {
        "schema_version": 1,
        "profile_id": "mindniq",
        "display_name": "MindNiq",
        "description": "Accessible educational explainers about ideas, psychology, science, and technology.",
        "content_domains": ["education", "psychology", "science", "technology", "general_explainers"],
        "audience": {"language": "en", "region": "international"},
        "narration_defaults": {"tone": "clear", "pacing": "engaging_explainer"},
        "visual_defaults": {
            "style_family": "stickman_flat_vector",
            "style_tags": ["stickman", "flat_vector", "whiteboard", "motion_graphics", "simple_diagrams"],
            "mood": ["clear", "curious", "approachable"],
            "composition_guidance": ["Use simple visual metaphors to explain abstract concepts.", "Keep diagrams uncluttered and readable."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30},
        "preferred_engines": [],
        "rules": [],
        "presets": [],
        "metadata": {"profile_family": "educational_explainer"},
    },
    {
        "schema_version": 1,
        "profile_id": "inventions-discoveries",
        "display_name": "Inventions & Discoveries",
        "description": "The stories, engineering, people, and science behind inventions and discoveries.",
        "content_domains": ["inventions", "discoveries", "engineering", "technology", "innovation", "science_history"],
        "audience": {"language": "en", "region": "international"},
        "narration_defaults": {"tone": "curious", "pacing": "story_driven_explainer"},
        "visual_defaults": {
            "style_family": "technical_cinematic_explainer",
            "style_tags": ["technical_diagrams", "3d_visualization", "4d_concepts", "motion_graphics", "historical_reconstruction"],
            "mood": ["discovery", "innovation", "wonder"],
            "composition_guidance": ["Explain how an invention works before emphasizing spectacle.", "Use clearly labeled stages, components, and timelines where useful."],
        },
        "production_defaults": {"aspect_ratio": "16:9", "frame_rate": 30},
        "preferred_engines": [],
        "rules": [
            {
                "rule_id": "review_invention_timeline",
                "category": "review",
                "severity": "warning",
                "scope": "project",
                "target": "invention_dates_and_attribution",
                "operator": "manual_review",
                "message": "Review invention dates, attribution, and historical context before approval.",
            }
        ],
        "presets": [],
        "metadata": {"profile_family": "inventions_and_discoveries"},
    },
)


class BuiltinProfileRegistry:
    """Read-only registry that returns fresh validated profile instances."""

    def __init__(self, profile_documents: Sequence[Mapping[str, Any]]) -> None:
        documents: list[dict[str, Any]] = []
        profile_ids: set[str] = set()
        for document in profile_documents:
            snapshot = copy.deepcopy(dict(document))
            profile = ChannelProfile.from_dict(snapshot)
            if profile.read_only:
                raise ProfileValidationError("built-in profiles cannot use an unsupported schema version")
            if profile.profile_id in profile_ids:
                raise ProfileValidationError(f"duplicate built-in profile ID: {profile.profile_id}")
            profile_ids.add(profile.profile_id)
            documents.append(snapshot)
        self._documents = tuple(documents)
        self._profile_ids = tuple(ChannelProfile.from_dict(item).profile_id for item in self._documents)

    @property
    def profile_ids(self) -> tuple[str, ...]:
        """Stable profile IDs in registry order."""
        return self._profile_ids

    def list_profiles(self) -> tuple[ChannelProfile, ...]:
        """Return all profiles in deterministic registration order."""
        return tuple(ChannelProfile.from_dict(copy.deepcopy(item)) for item in self._documents)

    def get_profile(self, profile_id: str) -> ChannelProfile | None:
        """Return a fresh profile by stable ID, or None when it is unknown."""
        if not isinstance(profile_id, str):
            return None
        for document in self._documents:
            if document["profile_id"] == profile_id:
                return ChannelProfile.from_dict(copy.deepcopy(document))
        return None


BUILTIN_PROFILE_REGISTRY = BuiltinProfileRegistry(_BUILTIN_PROFILE_DATA)


def list_builtin_profiles() -> tuple[ChannelProfile, ...]:
    """List built-in channel profiles in stable registration order."""
    return BUILTIN_PROFILE_REGISTRY.list_profiles()


def get_builtin_profile(profile_id: str) -> ChannelProfile | None:
    """Look up a built-in channel profile by stable ID."""
    return BUILTIN_PROFILE_REGISTRY.get_profile(profile_id)
