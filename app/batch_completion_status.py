"""Backward-compatible batch completion scope derived from runtime facts."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


COMPLETED_STATIC_ONLY = "COMPLETED_STATIC_ONLY"
STATIC_ONLY_MARKER = "[completion_scope:COMPLETED_STATIC_ONLY]"
STATIC_ONLY_MESSAGE_AR = (
    "اكتمل التحليل الساكن فقط؛ لم يُنفّذ اختبار اللعبة لعدم توفر بيئة التشغيل المعزولة."
)


def runtime_status_from_result(result: Mapping[str, Any]) -> str:
    inventory = result.get("artifact_inventory") or {}
    observation = inventory.get("runtime_observation_report") or {}
    gm = observation.get("gamemaker_observation") or {}
    return str(
        observation.get("runtime_status")
        or gm.get("runtime_status")
        or (observation.get("signals") or {}).get("runtime_status")
        or ""
    ).upper()


def is_static_only_result(result: Mapping[str, Any]) -> bool:
    return bool(result.get("success")) and runtime_status_from_result(result) == "SKIPPED_UNSUPPORTED_ENVIRONMENT"


def completion_scope_for_results(results: Iterable[Mapping[str, Any]]) -> str:
    rows = list(results)
    successful = [row for row in rows if row.get("success")]
    if rows and not successful:
        return "FAILED"
    if successful and all(is_static_only_result(row) for row in successful):
        return COMPLETED_STATIC_ONLY
    return "COMPLETED"


def completion_scope_from_batch(status: str, failure_message: str | None) -> str:
    if str(status).lower() == "completed" and str(failure_message or "").startswith(STATIC_ONLY_MARKER):
        return COMPLETED_STATIC_ONLY
    return str(status).upper()


def display_status_ar(scope: str) -> str:
    if scope == COMPLETED_STATIC_ONLY:
        return "اكتمل التحليل الساكن فقط"
    if scope == "FAILED":
        return "فشل"
    if scope == "PROCESSING":
        return "جاري"
    if scope == "PENDING":
        return "بانتظار التنفيذ"
    return "مكتمل"


def static_only_message(failure_message: str | None) -> str:
    raw = str(failure_message or "")
    if raw.startswith(STATIC_ONLY_MARKER):
        return raw[len(STATIC_ONLY_MARKER):].strip() or STATIC_ONLY_MESSAGE_AR
    return ""
