"""Deterministic pixel-level scene transition compositing."""
from __future__ import annotations

from PIL import Image, ImageDraw

from app.universal.transitions import (
    TransitionSpec,
    TransitionValidationError,
    transition_boundary,
    transition_progress,
)


class TransitionCompositorError(ValueError):
    """Raised when transition frames cannot be composited safely."""


def composite_transition_frames(
    outgoing: Image.Image,
    incoming: Image.Image,
    spec: TransitionSpec,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    """Return one transition frame without mutating either input image.

    Both frames must have identical dimensions and modes. Callers that need
    canvas normalization must perform it explicitly before invoking this API.
    Wipe names describe the edge from which the incoming scene is revealed.
    """
    if not isinstance(outgoing, Image.Image) or not isinstance(incoming, Image.Image):
        raise TransitionCompositorError("outgoing and incoming must be Pillow images")
    if outgoing.size != incoming.size:
        raise TransitionCompositorError("transition frames must have identical dimensions")
    if outgoing.mode != incoming.mode:
        raise TransitionCompositorError("transition frames must have identical image modes")
    if outgoing.mode not in {"RGB", "RGBA"}:
        raise TransitionCompositorError("transition frames must use RGB or RGBA mode")
    if not isinstance(spec, TransitionSpec):
        raise TransitionCompositorError("spec must be a validated TransitionSpec")
    if spec.effect == "cut":
        raise TransitionCompositorError("cut transitions do not have overlap frames")

    try:
        progress = transition_progress(
            frame_index, frame_count, easing=spec.easing,
        )
    except TransitionValidationError as exc:
        raise TransitionCompositorError(str(exc)) from exc

    if spec.effect == "crossfade":
        return Image.blend(outgoing, incoming, progress)

    width, height = outgoing.size
    if spec.effect in {"wipe_left", "wipe_right", "wipe_up", "wipe_down"}:
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        if spec.effect in {"wipe_left", "wipe_right"}:
            boundary = transition_boundary(width, progress)
            if spec.effect == "wipe_left":
                if boundary:
                    draw.rectangle((0, 0, boundary - 1, height - 1), fill=255)
            else:
                start = width - boundary
                if boundary:
                    draw.rectangle((start, 0, width - 1, height - 1), fill=255)
        else:
            boundary = transition_boundary(height, progress)
            if spec.effect == "wipe_up":
                if boundary:
                    draw.rectangle((0, 0, width - 1, boundary - 1), fill=255)
            else:
                start = height - boundary
                if boundary:
                    draw.rectangle((0, start, width - 1, height - 1), fill=255)
        result = outgoing.copy()
        try:
            result.paste(incoming, (0, 0), mask)
        finally:
            mask.close()
        return result

    if spec.effect == "dip_to_color":
        color = Image.new(outgoing.mode, outgoing.size, (*spec.color_rgb, 255)
                          if outgoing.mode == "RGBA" else spec.color_rgb)
        try:
            if progress <= 0.5:
                return Image.blend(outgoing, color, progress * 2.0)
            return Image.blend(color, incoming, (progress - 0.5) * 2.0)
        finally:
            color.close()

    raise TransitionCompositorError(
        f"unsupported transition effect: {spec.effect!r}"
    )


__all__ = ["TransitionCompositorError", "composite_transition_frames"]
