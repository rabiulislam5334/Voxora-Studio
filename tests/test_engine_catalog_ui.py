from app.universal.engines import EngineCapabilities
from app.ui.engine_catalog_tab import format_capabilities


def test_catalog_capability_summary_is_complete_and_read_only():
    summary = format_capabilities(EngineCapabilities(
        scene_kinds=("image", "video"),
        style_tags=("documentary",),
        asset_kinds=("image",),
        output_formats=("mp4",),
        requires_gpu=False,
        supports_draft_render=True,
        max_concurrent_jobs=1,
        estimated_memory_mb=512,
    ))
    assert "Scene kinds: image, video" in summary
    assert "Style tags: documentary" in summary
    assert "Asset kinds: image" in summary
    assert "Output formats: mp4" in summary
    assert "GPU required: No" in summary
    assert "Draft render: Supported" in summary
    assert "Maximum concurrent jobs: 1" in summary
    assert "Estimated memory: 512 MB" in summary


def test_catalog_does_not_claim_undeclared_capabilities():
    summary = format_capabilities(EngineCapabilities())
    assert summary.count("Not declared") >= 5
    assert "GPU required: No" in summary
