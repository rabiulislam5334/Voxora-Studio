# Phase 3.5.6.3 — Local stable-diffusion.cpp provider

Voxora now has an optional adapter for the upstream stable-diffusion.cpp command-line runtime. This is an adapter, not a bundled AI model or executable.

## Implemented

- Explicit local executable and model paths; no automatic download or remote API.
- CPU backend, configurable CPU thread count and sampling steps.
- Prompt, negative prompt, dimensions, PNG/JPEG output and optional seed mapping.
- Process polling, cancellation, timeout, exit-code reporting and bounded log excerpts.
- Output is written into the runtime's per-request staging directory and imported through the existing Asset Library.
- No new Python package dependency; ordinary CI uses a mocked CLI process.

## Initial low-memory profile

The initial descriptor intentionally supports one image up to 512x512 at a time. It does not guarantee that every SD 1.5 checkpoint will fit in 8 GB RAM. Quantized GGUF checkpoints may reduce memory use when supported by the selected upstream build. Generation speed depends on CPU, model format and backend. The adapter uses CPU for predictable compatibility; GPU/Vulkan/CUDA selection is deferred until it can be tested against supported hardware.

## Manual setup

1. Download a Windows sd-cli executable from https://github.com/leejet/stable-diffusion.cpp/releases.
2. Obtain a compatible SD 1.x model checkpoint separately and review its license and usage terms. Voxora does not download model weights.
3. Configure the provider with the executable and checkpoint paths:

    from pathlib import Path
    from app.universal.asset_library import VisualAssetLibrary
    from app.universal.providers.stable_diffusion_cpp import StableDiffusionCppProvider
    from app.universal.visual_generation_runtime import VisualGenerationRuntime

    provider = StableDiffusionCppProvider(
        executable_path=Path(r"C:\AI\stable-diffusion.cpp\sd-cli.exe"),
        model_path=Path(r"C:\AI\models\sd15.safetensors"),
        threads=4,
        steps=20,
    )
    library = VisualAssetLibrary(Path.home() / "Voxora" / "VisualAssets")
    runtime = VisualGenerationRuntime(library, providers=[provider])

The provider reports unavailable until both configured files exist. The current phase exposes the provider through the runtime API; wiring model-path selection, generation controls and progress/cancel UI into the desktop app is a separate integration phase. Real inference must be benchmarked on the target PC before choosing a production default.
