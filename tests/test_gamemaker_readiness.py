from PIL import Image

from app.runtime_engines.gamemaker.readiness import ReadinessReason, evaluate_readiness


class Adapter:
    def __init__(self, frames, *, rect=(1, 2, 21, 12), client=(1, 2, 21, 12), exists=True):
        self.frames = list(frames)
        self.rect, self.client, self.exists = rect, client, exists

    def is_window(self, hwnd): return self.exists
    def get_rect(self, hwnd): return self.rect
    def get_client_rect(self, hwnd): return self.client
    def capture(self, hwnd): return self.frames.pop(0) if self.frames else None


def test_ready_after_matching_samples():
    frame = Image.new("RGB", (20, 10), "black")
    result = evaluate_readiness(1, (1, 2, 21, 12), Adapter([frame, frame.copy()]))
    assert result.ready and result.reason_code is ReadinessReason.WINDOW_READY
    assert result.sample_count == 2


def test_capture_failure_has_precise_reason():
    result = evaluate_readiness(1, (1, 2, 21, 12), Adapter([]))
    assert not result.ready and result.reason_code is ReadinessReason.CAPTURE_FAILED


def test_rect_mismatch_has_precise_reason():
    result = evaluate_readiness(1, (0, 0, 1, 1), Adapter([Image.new("RGB", (20, 10))]))
    assert not result.ready and result.reason_code is ReadinessReason.WINDOW_RECT_MISMATCH


def test_capture_size_mismatch_has_precise_reason():
    result = evaluate_readiness(1, (1, 2, 21, 12), Adapter([Image.new("RGB", (10, 10))]))
    assert not result.ready and result.reason_code is ReadinessReason.CAPTURE_SIZE_MISMATCH
