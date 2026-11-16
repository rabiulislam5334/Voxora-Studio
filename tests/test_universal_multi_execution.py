from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.core.exceptions import GenerationCancelled
from app.universal.execution import SceneExecutionContext, SceneExecutionResult
from app.universal.models import ScenePlan
from app.universal.multi_execution import (
    MultiSceneExecutionCoordinator,
    MultiSceneExecutionError,
    MultiSceneExecutionRequest,
    MultiSceneExecutionResult,
)
from app.universal.normalizer import NormalizedSegment, SegmentOutputSpec
from app.universal.requests import RawEngineOutput
from app.workers.cancel import CancelToken


def plan(scene_id):
    return ScenePlan(scene_id=scene_id)


def context(tmp_path, name):
    return SceneExecutionContext(
        SegmentOutputSpec(2.0, 640, 360, 24),
        tmp_path / f"{name}.mp4",
    )


class FakeSceneCoordinator:
    def __init__(self, *, fail_at=None, cancel_at=None):
        self.calls = []
        self.fail_at = fail_at
        self.cancel_at = cancel_at

    def execute(self, scene_plan, scene_context, *, on_progress=None, cancel=None):
        index = len(self.calls)
        self.calls.append((scene_plan.scene_id, scene_context, cancel))
        if self.cancel_at == index:
            raise GenerationCancelled("cancelled")
        if on_progress:
            on_progress(0.0)
            on_progress(0.4)
            on_progress(1.0)
        if self.fail_at == index:
            raise RuntimeError("scene failed")
        raw = RawEngineOutput(Path(f"{scene_plan.scene_id}.raw"))
        normalized = NormalizedSegment(
            scene_context.destination, 2.0, 640, 360, 24
        )
        return SceneExecutionResult(
            scene_plan.scene_id, "fake", None, raw, normalized
        )


@pytest.fixture
def batch(tmp_path):
    plans = (plan("scene-c"), plan("scene-a"), plan("scene-b"))
    contexts = {item.scene_id: context(tmp_path, item.scene_id) for item in plans}
    return MultiSceneExecutionRequest(plans, contexts)


def test_executes_sequentially_in_caller_order_and_matches_contexts(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)
    result = coordinator.execute(batch)

    assert isinstance(result, MultiSceneExecutionResult)
    assert [call[0] for call in single.calls] == ["scene-c", "scene-a", "scene-b"]
    assert [call[1] for call in single.calls] == [
        batch.contexts["scene-c"], batch.contexts["scene-a"], batch.contexts["scene-b"]
    ]
    assert result.scene_ids == ("scene-c", "scene-a", "scene-b")
    assert result.completed_count == 3


def test_constructor_requires_single_scene_coordinator():
    with pytest.raises(TypeError):
        MultiSceneExecutionCoordinator(object())


@pytest.mark.parametrize("plans,contexts,error", [
    ((), {}, ValueError),
    ((plan("same"), plan("same")), {"same": object()}, ValueError),
    ((plan("one"),), {}, ValueError),
    ((plan("one"),), {"one": object()}, TypeError),
    ((plan("one"),), {"one": None, "extra": None}, TypeError),
    ((plan("one"),), {"one": None, "extra": None}, TypeError),
])
def test_request_validates_entire_batch(plans, contexts, error):
    with pytest.raises(error):
        MultiSceneExecutionRequest(plans, contexts)


def test_request_rejects_unexpected_context_key(tmp_path):
    with pytest.raises(ValueError, match="unexpected contexts"):
        MultiSceneExecutionRequest(
            (plan("one"),),
            {"one": context(tmp_path, "one"), "extra": context(tmp_path, "extra")},
        )


def test_request_rejects_non_scene_plan(tmp_path):
    with pytest.raises(TypeError):
        MultiSceneExecutionRequest(
            (object(),), {"object": context(tmp_path, "object")}
        )


def test_request_freezes_context_mapping(batch):
    with pytest.raises(TypeError):
        batch.contexts["new"] = batch.contexts["scene-c"]


def test_progress_is_monotonic_and_final_one_only_after_all_succeed(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)
    progress = []
    coordinator.execute(batch, on_progress=progress.append)

    assert progress == sorted(progress)
    assert all(0.0 <= value <= 1.0 for value in progress)
    assert progress[-1] == 1.0
    assert max(progress[:-1]) < 1.0


def test_observer_exceptions_do_not_interrupt_batch(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)

    def broken(_):
        raise RuntimeError("observer closed")

    result = coordinator.execute(batch, on_progress=broken)
    assert result.completed_count == 3
    assert len(single.calls) == 3


def test_invalid_progress_values_are_ignored(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)

    def noisy(scene_plan, scene_context, *, on_progress=None, cancel=None):
        if on_progress:
            for value in (float("nan"), float("inf"), "bad", True):
                on_progress(value)
        raw = RawEngineOutput(Path("raw"))
        normalized = NormalizedSegment(scene_context.destination, 2, 640, 360, 24)
        return SceneExecutionResult(scene_plan.scene_id, "fake", None, raw, normalized)

    single.execute = noisy
    seen = []
    coordinator.execute(batch, on_progress=seen.append)
    assert seen == [pytest.approx(1 / 3), pytest.approx(2 / 3), 1.0]


def test_cancellation_before_first_scene_starts_nothing(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)
    token = CancelToken()
    token.cancel()

    with pytest.raises(GenerationCancelled):
        coordinator.execute(batch, cancel=token)
    assert single.calls == []


def test_same_cancel_token_is_forwarded_to_each_scene(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)
    token = CancelToken()

    coordinator.execute(batch, cancel=token)
    assert all(call[2] is token for call in single.calls)


def test_cancellation_during_scene_propagates_without_starting_later_scenes(batch):
    single = FakeSceneCoordinator(cancel_at=1)
    coordinator = MultiSceneExecutionCoordinator(single)

    with pytest.raises(GenerationCancelled):
        coordinator.execute(batch)
    assert [call[0] for call in single.calls] == ["scene-c", "scene-a"]


def test_failure_is_fail_fast_and_exposes_only_completed_results(batch):
    single = FakeSceneCoordinator(fail_at=1)
    coordinator = MultiSceneExecutionCoordinator(single)

    with pytest.raises(MultiSceneExecutionError) as caught:
        coordinator.execute(batch)

    error = caught.value
    assert error.failed_scene_id == "scene-a"
    assert error.failed_scene_index == 1
    assert [item.scene_id for item in error.completed_results] == ["scene-c"]
    assert isinstance(error.__cause__, RuntimeError)
    assert [call[0] for call in single.calls] == ["scene-c", "scene-a"]


def test_progress_callback_must_be_callable(batch):
    single = FakeSceneCoordinator()
    coordinator = MultiSceneExecutionCoordinator(single)
    with pytest.raises(TypeError):
        coordinator.execute(batch, on_progress="no")
    assert single.calls == []
