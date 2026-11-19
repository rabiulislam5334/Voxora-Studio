# Phase 3.5.6.4 — Local Image Generation Desktop Workflow

## Included

- Adds an **Image Generation** page to the desktop sidebar.
- Lets the user explicitly select a local `sd-cli.exe` executable and model file.
- Persists only executable/model paths, CPU thread count, and sampling steps in the machine-local `userdata/visual_generation.json` file.
- Provides prompt, negative prompt, width, height, and optional seed inputs.
- Runs generation through the existing `AsyncBridge` so inference does not block the Tkinter UI.
- Displays runtime progress, supports cancellation, and imports verified output through the existing content-addressed Visual Asset Library.
- Provides a direct navigation action to inspect generated images in **Visual Assets**.

## Safety and hardware boundaries

- The current provider is local-only: no network permission, API key, automatic model download, or cloud fallback.
- The UI defaults to one 512×512 PNG, CPU backend, four threads, and 20 steps. The provider rejects dimensions above 512×512.
- Users must obtain the executable and model separately and comply with the model's license.
- Generated images are imported into the existing local asset catalog; this phase does not bind them to a scene or create a Composition automatically.
- The settings file contains local filesystem paths. It is not embedded in `.voxora` project files and should not be committed.
- Actual model inference, speed, and memory consumption remain for the planned end-of-Phase-3 PC acceptance test.

## Manual verification

1. Open **Image Generation** from the sidebar.
2. Browse to a compatible local `sd-cli.exe` and SD 1.x model file.
3. Save Setup, then use Check Setup. The provider should report Ready only when both files exist.
4. Enter a prompt and keep the initial 512×512 dimensions.
5. Generate, observe progress, and test Cancel with a real local model.
6. Open Visual Assets and verify the generated image and `generated:stable-diffusion-cpp` provenance.
7. Restart Voxora and confirm the local runtime paths and CPU settings are restored.

CI tests validate settings persistence and integration imports; they do not run a heavyweight model.
