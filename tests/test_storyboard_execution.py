from __future__ import annotations

from pathlib import Path

import pytest

from app.models.project import Project
from app.universal.adapters.workflows import (
    DocumentaryWorkflowAdapter,
    TwoDStorytellingAdapter,
)
from app.universal.engines import EngineCapabilities, EngineDescriptor
from app.universal.models import UniversalState
from app.universal.normalizer import NormalizedSegment
from app.universal.narration_segmentation import segment_narration
from app.universal.requests import RawEngineOutput
from app.universal.runtime import EngineRuntimeRegistry
from app.universal.storyboard_apply import (
    apply_storyboard_proposal,
    preview_storyboard_apply,
)
from app.universal.storyboard_builder import build_storyboard_proposal
from app.universal.storyboard_execution import (
    StoryboardExecutionApprovalError,
    StoryboardExecutionReadinessError,
    StoryboardWorkflowExecutionCoordinator,
)


def make_descriptor(*, family="2d", available=True):
    return EngineDescriptor(
        engine_id="selected-2d",
        display_name="Selected 2D Engine",
        version="test",
        capabilities=EngineCapabilities(
            scene_kinds=("image",),
            style_tags=("cinematic",),
            asset_kinds=(),
            output_formats=("mp4",),
            workflow_families=(family,),
        ),
        available=available,
        unavailable_reason="engine offline" if not available else "",
    )


class FakeEngine:
    def __init__(self, descriptor, tmp_path):
        self.descriptor = descriptor
        self.tmp_path = tmp_path
        self.calls = []

    def render(self, request, *, on_progress=None, cancel=None):
        self.calls.append((request, cancel))
        raw = self.tmp_path / f"{request.scene_id}.raw.mp4"
        raw.write_bytes(b"raw")
        if on_progress:
            on_progress(0.5)
        return RawEngineOutput(raw, {"engine": self.descriptor.engine_id})


class FakeNormalizer:
    def __init__(self):
        self.calls = []

    def normalize(self, source, destination, spec, *, on_progress=None, cancel=None):
        self.calls.append((source, destination, spec, cancel))
        if on_progress:
            on_progress(0.5)
        return NormalizedSegment(
            Path(destination), spec.duration_s, spec.width, spec.height, spec.fps
        )


def prepared_storyboard():
    source = segment_narration(
        "A door opens. A shadow moves across the hallway.",
        source_id="execution-source",
        total_duration_ms=5000,
    )
    proposal = build_storyboard_proposal(source)
    project = Project(name="Storyboard execution")
    preview = preview_storyboard_apply(project, proposal, source)
    apply_storyboard_proposal(project, proposal, source, preview, approved=True)
    return project, source, proposal, preview


def make_coordinator(tmp_path, *, family="2d"):
    descriptor = make_descriptor(family=family)
    engine = FakeEngine(descriptor, tmp_path)
    inner_runtime = EngineRuntimeRegistry()
    inner_runtime.register(descriptor, engine)
    adapter_type = (
        TwoDStorytellingAdapter if family == "2d" else DocumentaryWorkflowAdapter
    )
    adapter = adapter_type(inner_runtime, descriptor.engine_id)
    normalizer = FakeNormalizer()
    coordinator = StoryboardWorkflowExecutionCoordinator(normalizer=normalizer)
    return coordinator, descriptor, adapter, engine, normalizer


def execute_args(tmp_path, descriptor, adapter):
    return {
        "approved": True,
        "workflow_id": "2d_storytelling",
        "selected_engine_id": descriptor.engine_id,
        "engine_descriptor": descriptor,
        "workflow_adapter": adapter,
        "scene_kind": "image",
        "style_tags": ("cinematic",),
        "output_format": "mp4",
        "output_directory": tmp_path / "normalized",
        "width": 640,
        "height": 360,
        "fps": 24,
    }


def test_executes_applied_storyboard_sequentially_through_explicit_workflow_adapter(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)
    progress = []

    result = coordinator.execute(
        project, proposal, source, preview,
        **execute_args(tmp_path, descriptor, adapter),
        on_progress=progress.append,
    )

    assert result.completed_count == len(preview.scenes)
    assert result.scene_ids == tuple(item.scene_id for item in preview.scenes)
    assert len(engine.calls) == len(preview.scenes)
    assert len(normalizer.calls) == len(preview.scenes)
    assert all(call[0].scene_kind == "image" for call in engine.calls)
    assert all(call[0].output_format == "mp4" for call in engine.calls)
    assert all(call[0].style_tags == ("cinematic",) for call in engine.calls)
    assert progress == sorted(progress)
    assert progress[-1] == 1.0


def test_execution_requires_a_separate_explicit_approval(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)
    args = execute_args(tmp_path, descriptor, adapter)
    args["approved"] = False

    with pytest.raises(StoryboardExecutionApprovalError, match="explicit"):
        coordinator.execute(project, proposal, source, preview, **args)

    assert engine.calls == []
    assert normalizer.calls == []


def test_execution_requires_proposal_to_be_applied_to_project(tmp_path):
    source = segment_narration("A door opens.", source_id="not-applied")
    proposal = build_storyboard_proposal(source)
    project = Project()
    preview = preview_storyboard_apply(project, proposal, source)
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)

    with pytest.raises(StoryboardExecutionReadinessError, match="applied"):
        coordinator.execute(
            project, proposal, source, preview,
            **execute_args(tmp_path, descriptor, adapter),
        )
    assert engine.calls == []


def test_execution_rejects_engine_family_mismatch_without_rendering(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(
        tmp_path, family="documentary"
    )

    with pytest.raises(StoryboardExecutionReadinessError, match="family"):
        coordinator.execute(
            project, proposal, source, preview,
            **execute_args(tmp_path, descriptor, adapter),
        )
    assert engine.calls == []


def test_execution_requires_adapter_engine_to_match_explicit_selection(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)
    args = execute_args(tmp_path, descriptor, adapter)
    args["selected_engine_id"] = "some-other-engine"

    with pytest.raises(StoryboardExecutionReadinessError, match="different engine"):
        coordinator.execute(project, proposal, source, preview, **args)
    assert engine.calls == []


def test_execution_rejects_stale_or_modified_applied_scene(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    project.scenes[-1].visual_prompt = "changed after storyboard review"
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)

    with pytest.raises(StoryboardExecutionReadinessError, match="changed after review"):
        coordinator.execute(
            project, proposal, source, preview,
            **execute_args(tmp_path, descriptor, adapter),
        )
    assert engine.calls == []


def test_execution_rejects_tampered_preview_content(tmp_path):
    from dataclasses import replace

    project, source, proposal, preview = prepared_storyboard()
    changed_scene = replace(preview.scenes[0], visual_prompt="tampered")
    changed_preview = replace(
        preview, scenes=(changed_scene, *preview.scenes[1:])
    )
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)

    with pytest.raises(StoryboardExecutionReadinessError, match="preview scene content"):
        coordinator.execute(
            project, proposal, source, changed_preview,
            **execute_args(tmp_path, descriptor, adapter),
        )
    assert engine.calls == []


def test_execution_does_not_overwrite_existing_normalized_outputs(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)
    args = execute_args(tmp_path, descriptor, adapter)
    output_dir = Path(args["output_directory"])
    output_dir.mkdir()
    existing = output_dir / f"{preview.scenes[0].scene_id}.mp4"
    existing.write_bytes(b"keep")

    with pytest.raises(StoryboardExecutionReadinessError, match="overwrite"):
        coordinator.execute(project, proposal, source, preview, **args)
    assert existing.read_bytes() == b"keep"
    assert engine.calls == []


def test_execution_does_not_mutate_persisted_scene_plans(tmp_path):
    project, source, proposal, preview = prepared_storyboard()
    state_before = UniversalState.from_project_settings(project.settings)
    before = {
        key: value.to_dict() for key, value in state_before.scene_plans.items()
    }
    coordinator, descriptor, adapter, engine, normalizer = make_coordinator(tmp_path)

    coordinator.execute(
        project, proposal, source, preview,
        **execute_args(tmp_path, descriptor, adapter),
    )

    state_after = UniversalState.from_project_settings(project.settings)
    assert {key: value.to_dict() for key, value in state_after.scene_plans.items()} == before
