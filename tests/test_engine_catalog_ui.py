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


from app.universal.adapters.raster import RasterCompositionAdapter
from app.universal.providers.stable_diffusion_cpp import StableDiffusionCppProvider
from app.ui.engine_catalog_tab import EngineCatalogTab, format_composition_capabilities, format_provider_capabilities


def test_composition_catalog_summary_is_explicitly_still_png_only():
    summary = format_composition_capabilities(RasterCompositionAdapter())
    assert "Output formats: png" in summary
    assert "Output type: Still image" in summary
    assert "Video output: Not supported" in summary
    assert "GPU required: No" in summary


def test_visual_provider_catalog_summary_exposes_local_provider_limits():
    descriptor = StableDiffusionCppProvider("", "").descriptor
    summary = format_provider_capabilities(descriptor)
    assert "Model profiles: sd15" in summary
    assert "Maximum dimensions: 512 × 512" in summary
    assert "Network required: No" in summary
    assert "API key required: No" in summary


def test_catalog_categories_keep_engine_renderer_and_provider_contracts_separate():
    assert set(EngineCatalogTab.CATEGORY_INFO) == {"category:segments", "category:compositions", "category:providers"}
    assert "still" in EngineCatalogTab.CATEGORY_INFO["category:compositions"][1].lower()
