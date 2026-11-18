"""Explicit capability bridge for scene-composition renderers.

The current FFmpeg segment adapter renders one blank/image/video source per
scene and does not implement layered composition rendering. This bridge
therefore reports it as unsupported rather than silently flattening or
dropping composition elements. Future adapters must opt in with a declared
CompositionRenderCapabilities value and a render_composition() method.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Protocol, Tuple

from app.universal.composition import SceneComposition
from app.universal.composition_workflow import (
    SceneCompositionPreview,
    preview_scene_composition,
)
from app.universal.engines import EngineDescriptor
from app.universal.models import Project if False else UniversalState
