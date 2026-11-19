"""Local stable-diffusion.cpp CLI provider."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from app.universal.visual_generation import (
    VisualGenerationProviderCapabilities,
    VisualGenerationProviderDescriptor,
    VisualGenerationRequest,
)
from app.universal.visual_generation_runtime import (
    VisualGenerationCancelled,
    VisualGenerationRuntimeError,
)


class StableDiffusionCppProvider:
    """Generate one still image with an explicitly configured local CLI/model."""

    PROVIDER_ID = "stable-diffusion-cpp"
    MODEL_ID = "sd15"

    def __init__(
        self,
        executable_path: str | os.PathLike[str],
        model_path: str | os.PathLike[str],
        *,
        threads: int = 4,
        steps: int = 20,
        timeout_seconds: float = 1800,
    ) -> None:
        if isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 32:
            raise ValueError("threads must be an integer between 1 and 32")
        if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 100:
            raise ValueError("steps must be an integer between 1 and 100")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.executable_path = Path(executable_path).expanduser()
        self.model_path = Path(model_path).expanduser()
        self.threads = threads
        self.steps = steps
        self.timeout_seconds = float(timeout_seconds)
        self.descriptor = self._build_descriptor()

    def _build_descriptor(self) -> VisualGenerationProviderDescriptor:
        reasons = []
        if not self.executable_path.is_file():
            reasons.append(f"stable-diffusion.cpp executable not found: {self.executable_path}")
        if not self.model_path.is_file():
            reasons.append(f"local model file not found: {self.model_path}")
        return VisualGenerationProviderDescriptor(
            provider_id=self.PROVIDER_ID,
            display_name="Stable Diffusion.cpp (Local CPU)",
            version="1",
            capabilities=VisualGenerationProviderCapabilities(
                output_formats=("png", "jpeg"),
                max_width=512,
                max_height=512,
                max_images_per_request=1,
                supports_reference_images=False,
                supports_seed=True,
                requires_network=False,
                requires_api_key=False,
                estimated_memory_mb=4096,
            ),
            model_ids=(self.MODEL_ID,),
            available=not reasons,
            unavailable_reason="; ".join(reasons),
        )

    def generate(
        self,
        request: VisualGenerationRequest,
        output_dir: Path,
        cancel_event: threading.Event,
        progress: Callable[[int, int, str], None],
    ) -> Iterable[Path]:
        if not self.descriptor.available:
            raise VisualGenerationRuntimeError(
                "provider_unavailable", self.descriptor.unavailable_reason,
                request_id=request.request_id,
            )
        if request.model_id not in (None, self.MODEL_ID):
            raise VisualGenerationRuntimeError(
                "unsupported_model", f"Only model profile '{self.MODEL_ID}' is supported",
                request_id=request.request_id,
            )
        if request.width > 512 or request.height > 512:
            raise VisualGenerationRuntimeError(
                "hardware_limit", "The initial low-memory profile supports images up to 512x512",
                request_id=request.request_id,
            )

        executable = self.executable_path.resolve(strict=True)
        model = self.model_path.resolve(strict=True)
        extension = ".png" if request.output_format == "png" else ".jpg"
        output_path = output_dir / f"generated{extension}"
        log_path = output_dir / "stable-diffusion-cpp.log"
        command = [
            str(executable),
            "--model", str(model),
            "--prompt", request.prompt,
            "--negative-prompt", request.negative_prompt,
            "--width", str(request.width),
            "--height", str(request.height),
            "--steps", str(self.steps),
            "--threads", str(self.threads),
            "--backend", "cpu",
            "--output", str(output_path),
        ]
        if request.seed is not None:
            command.extend(["--seed", str(request.seed)])

        if cancel_event.is_set():
            raise VisualGenerationCancelled(request.request_id)
        progress(0, 1, "Starting local CPU image generation")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        started = time.monotonic()
        try:
            with log_path.open("wb") as log_stream:
                process = subprocess.Popen(
                    command,
                    cwd=str(output_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    creationflags=creationflags,
                )
                while process.poll() is None:
                    if cancel_event.wait(0.15):
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise VisualGenerationCancelled(request.request_id)
                    if time.monotonic() - started > self.timeout_seconds:
                        process.kill()
                        process.wait()
                        raise VisualGenerationRuntimeError(
                            "provider_timeout",
                            f"Local image generation exceeded {self.timeout_seconds:g} seconds",
                            request_id=request.request_id,
                        )
                return_code = process.returncode
        except VisualGenerationRuntimeError:
            raise
        except OSError as exc:
            raise VisualGenerationRuntimeError(
                "provider_launch_failed", f"Could not launch stable-diffusion.cpp: {exc}",
                request_id=request.request_id,
            ) from exc

        if return_code != 0:
            try:
                details = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            except OSError:
                details = "No provider log was available."
            raise VisualGenerationRuntimeError(
                "provider_process_failed",
                f"stable-diffusion.cpp exited with code {return_code}: {details.strip()}",
                request_id=request.request_id,
            )
        if cancel_event.is_set():
            raise VisualGenerationCancelled(request.request_id)
        if not output_path.is_file():
            raise VisualGenerationRuntimeError(
                "provider_output_missing",
                "stable-diffusion.cpp completed without creating the requested image",
                request_id=request.request_id,
            )
        progress(1, 1, "Local image generation finished")
        return (output_path,)
