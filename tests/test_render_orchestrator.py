from __future__ import annotations

import pytest

from app.universal.render_orchestrator import (
    RenderGraph,
    RenderGraphError,
    RenderStage,
    SequentialRenderOrchestrator,
)


def test_graph_executes_dependencies_in_stable_sequential_order():
    calls = []

    def stage(name, value):
        def execute(context, outputs, cancel, progress):
            calls.append(name)
            if progress:
                progress(0.5, f"{name} halfway")
            return value
        return execute

    graph = RenderGraph((
        RenderStage("render", stage("render", "mp4"), dependencies=("compose",)),
        RenderStage("inspect", stage("inspect", "valid"), dependencies=("render",)),
        RenderStage("prepare", stage("prepare", "plan")),
        RenderStage("compose", stage("compose", "film"), dependencies=("prepare",)),
    ))
    progress = []
    result = SequentialRenderOrchestrator().run(
        graph, {"project": "p"}, on_progress=lambda value, message: progress.append((value, message)),
    )

    assert result.stage_order == ("prepare", "compose", "render", "inspect")
    assert calls == list(result.stage_order)
    assert dict(result.outputs) == {
        "prepare": "plan", "compose": "film", "render": "mp4", "inspect": "valid",
    }
    assert all(left[0] <= right[0] for left, right in zip(progress, progress[1:]))
    assert progress[-1][0] == 1.0


def test_stage_receives_only_completed_read_only_outputs():
    seen = []

    def first(context, outputs, cancel, progress):
        return "ready"

    def second(context, outputs, cancel, progress):
        seen.append(dict(outputs))
        with pytest.raises(TypeError):
            outputs["mutate"] = True
        return "done"

    result = SequentialRenderOrchestrator().run(
        RenderGraph((
            RenderStage("first", first),
            RenderStage("second", second, dependencies=("first",)),
        )),
        None,
    )

    assert seen == [{"first": "ready"}]
    assert result.outputs["second"] == "done"


def test_graph_rejects_unknown_dependencies_duplicate_ids_and_cycles():
    noop = lambda *args: None

    with pytest.raises(RenderGraphError, match="unknown stage"):
        RenderGraph((RenderStage("a", noop, dependencies=("missing",)),))
    with pytest.raises(RenderGraphError, match="unique"):
        RenderGraph((RenderStage("a", noop), RenderStage("a", noop)))
    with pytest.raises(RenderGraphError, match="cycle"):
        RenderGraph((
            RenderStage("a", noop, dependencies=("b",)),
            RenderStage("b", noop, dependencies=("a",)),
        )).ordered_stages()


def test_failure_stops_later_stages_and_propagates_original_exception():
    calls = []
    failure = RuntimeError("renderer failed")

    def fail(context, outputs, cancel, progress):
        calls.append("fail")
        raise failure

    def later(context, outputs, cancel, progress):
        calls.append("later")

    with pytest.raises(RuntimeError) as caught:
        SequentialRenderOrchestrator().run(
            RenderGraph((
                RenderStage("fail", fail),
                RenderStage("later", later, dependencies=("fail",)),
            )),
            None,
        )

    assert caught.value is failure
    assert calls == ["fail"]


def test_cancellation_is_checked_between_stages():
    class Token:
        def __init__(self):
            self.calls = 0

        def raise_if_cancelled(self):
            self.calls += 1
            if self.calls >= 2:
                raise RuntimeError("cancelled")

    calls = []
    token = Token()

    with pytest.raises(RuntimeError, match="cancelled"):
        SequentialRenderOrchestrator().run(
            RenderGraph((
                RenderStage("first", lambda *args: calls.append("first")),
                RenderStage("second", lambda *args: calls.append("second"), dependencies=("first",)),
            )),
            None,
            cancel=token,
        )

    assert calls == ["first"]


def test_invalid_stage_weights_and_progress_observer_failures_are_safe():
    noop = lambda *args: "ok"
    with pytest.raises(RenderGraphError, match="positive finite"):
        RenderStage("bad", noop, weight=0)

    result = SequentialRenderOrchestrator().run(
        RenderGraph((RenderStage("ok", noop),)),
        None,
        on_progress=lambda *_: (_ for _ in ()).throw(RuntimeError("UI closed")),
    )
    assert result.outputs["ok"] == "ok"
