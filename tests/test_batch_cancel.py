"""Tests for batch grading cancel / stop flow."""
from app.batch_grade_worker import (
    finalize_cancelled_batch_if_stuck,
    is_batch_cancel_requested,
    request_batch_cancel,
)


def test_request_cancel_sets_flag_and_timestamp():
    batch_progress = {
        3: {
            "batch_id": 99,
            "finished": False,
            "total": 1,
            "completed": 0,
        }
    }
    result = request_batch_cancel(batch_progress, 3)
    assert result["ok"] is True
    assert is_batch_cancel_requested(batch_progress, 3)
    assert batch_progress[3]["cancel_requested_at"] > 0
    assert batch_progress[3]["current_phase"] == "cancelling"


def test_finalize_cancelled_if_stuck_closes_ui_loop():
    import time

    batch_progress = {
        5: {
            "batch_id": 12,
            "finished": False,
            "cancel_requested": True,
            "cancel_requested_at": time.time() - 120,
            "total": 1,
            "completed": 0,
        }
    }
    assert finalize_cancelled_batch_if_stuck(batch_progress, 5, max_wait_seconds=90) is True
    info = batch_progress[5]
    assert info["finished"] is True
    assert info["cancelled"] is True
    assert info["final_response"]["cancelled"] is True
