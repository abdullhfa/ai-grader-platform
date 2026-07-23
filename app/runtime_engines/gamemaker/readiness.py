"""Structured, side-effect-free readiness diagnostics for GameMaker windows."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any, Optional

def _dimensions(frame: Any) -> Optional[tuple[int, int]]:
    if hasattr(frame, "size") and isinstance(frame.size, tuple):
        return (int(frame.size[0]), int(frame.size[1]))
    shape = getattr(frame, "shape", None)
    return (int(shape[1]), int(shape[0])) if shape is not None and len(shape) >= 2 else None


class ReadinessReason(str, Enum):
    HWND_INVALID = "HWND_INVALID"
    WINDOW_RECT_MISMATCH = "WINDOW_RECT_MISMATCH"
    CLIENT_RECT_EMPTY = "CLIENT_RECT_EMPTY"
    CAPTURE_FAILED = "CAPTURE_FAILED"
    CAPTURE_SIZE_MISMATCH = "CAPTURE_SIZE_MISMATCH"
    GEOMETRY_UNSTABLE = "GEOMETRY_UNSTABLE"
    CAPTURE_UNSTABLE = "CAPTURE_UNSTABLE"
    TIMEOUT_WAITING_FOR_STABILITY = "TIMEOUT_WAITING_FOR_STABILITY"
    WINDOW_READY = "WINDOW_READY"


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    reason_code: ReadinessReason
    failing_condition: Optional[str]
    elapsed_ms: float
    sample_count: int
    samples: list[dict[str, Any]] = field(default_factory=list)
    last_valid_sample: Optional[dict[str, Any]] = None


def evaluate_readiness(hwnd: int, expected_rect: tuple[int, int, int, int], adapter: Any, *, required_samples: int = 2) -> ReadinessResult:
    """Evaluate one or more already-captured samples without sending input."""
    started = monotonic()
    samples: list[dict[str, Any]] = []
    previous = None
    for _ in range(required_samples):
        if not adapter.is_window(hwnd):
            return ReadinessResult(False, ReadinessReason.HWND_INVALID, "IsWindow", (monotonic()-started)*1000, len(samples), samples)
        rect, client, frame = adapter.get_rect(hwnd), adapter.get_client_rect(hwnd), adapter.capture(hwnd)
        sample = {"window_rect": rect, "client_rect": client, "frame_size": _dimensions(frame)}
        samples.append(sample)
        if rect != expected_rect:
            return ReadinessResult(False, ReadinessReason.WINDOW_RECT_MISMATCH, "GetWindowRect", (monotonic()-started)*1000, len(samples), samples)
        if client is None or client[2] <= client[0] or client[3] <= client[1]:
            return ReadinessResult(False, ReadinessReason.CLIENT_RECT_EMPTY, "GetClientRect", (monotonic()-started)*1000, len(samples), samples)
        if frame is None:
            return ReadinessResult(False, ReadinessReason.CAPTURE_FAILED, "capture", (monotonic()-started)*1000, len(samples), samples)
        if _dimensions(frame) != (client[2]-client[0], client[3]-client[1]):
            return ReadinessResult(False, ReadinessReason.CAPTURE_SIZE_MISMATCH, "capture.size", (monotonic()-started)*1000, len(samples), samples)
        signature = (rect, frame.tobytes())
        if previous is not None and signature != previous:
            return ReadinessResult(False, ReadinessReason.GEOMETRY_UNSTABLE, "sample_signature", (monotonic()-started)*1000, len(samples), samples)
        previous = signature
    return ReadinessResult(True, ReadinessReason.WINDOW_READY, None, (monotonic()-started)*1000, len(samples), samples, samples[-1])
