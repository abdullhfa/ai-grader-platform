from pathlib import Path

from app.batch_completion_status import (
    COMPLETED_STATIC_ONLY,
    STATIC_ONLY_MARKER,
    STATIC_ONLY_MESSAGE_AR,
    completion_scope_for_results,
    completion_scope_from_batch,
    display_status_ar,
    static_only_message,
)


def _result(runtime_status: str, *, success: bool = True):
    return {
        "success": success,
        "artifact_inventory": {
            "runtime_observation_report": {"runtime_status": runtime_status}
        },
        "grade_level": "U",
    }


def test_skipped_runtime_maps_to_static_only_without_changing_grade():
    result = _result("SKIPPED_UNSUPPORTED_ENVIRONMENT")
    assert completion_scope_for_results([result]) == COMPLETED_STATIC_ONLY
    assert result["grade_level"] == "U"
    assert display_status_ar(COMPLETED_STATIC_ONLY) == "اكتمل التحليل الساكن فقط"


def test_verified_runtime_remains_completed():
    assert completion_scope_for_results([_result("PASS")]) == "COMPLETED"


def test_static_failure_is_not_static_only():
    assert completion_scope_for_results([_result("SKIPPED_UNSUPPORTED_ENVIRONMENT", success=False)]) == "FAILED"


def test_legacy_completed_batch_remains_readable():
    assert completion_scope_from_batch("completed", None) == "COMPLETED"


def test_persisted_static_only_marker_is_exposed_to_ui():
    stored = f"{STATIC_ONLY_MARKER} {STATIC_ONLY_MESSAGE_AR}"
    assert completion_scope_from_batch("completed", stored) == COMPLETED_STATIC_ONLY
    assert static_only_message(stored) == STATIC_ONLY_MESSAGE_AR


def test_template_contains_static_only_runtime_message():
    template = Path("app/templates/batch_results.html").read_text(encoding="utf-8")
    assert "COMPLETED_STATIC_ONLY" in template
    assert "غير منفّذ — البيئة غير متاحة" in template
