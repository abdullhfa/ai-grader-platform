"""
Runtime Replay Viewer — teacher-facing read-only session replay.

Shows screenshots, visual states, Player.log signals, and process restriction
from L4 runtime observation. Does not mutate grades or claim gameplay verification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_GUARDrail_AR = (
    "هذا العرض يعيد بناء أدلة runtime المُرصدة فقط — "
    "لا يثبت gameplay correctness ولا يمنح Achieved تلقائياً. "
    "المراجعة البشرية مطلوبة قبل أي قرار نهائي."
)

_VISUAL_STATE_LABELS = {
    "black_screen": "شاشة سوداء",
    "loading_screen": "شاشة تحميل",
    "main_menu_candidate": "قائمة رئيسية (محتمل)",
    "gameplay_candidate": "gameplay (محتمل)",
    "static_ui": "واجهة ثابتة",
    "unknown": "غير معروف",
}


def path_to_upload_url(path: str) -> str:
    """Convert a local uploads path to a web URL served by StaticFiles."""
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    if normalized.startswith("/uploads/"):
        return normalized
    if normalized.startswith("uploads/"):
        return "/" + normalized
    try:
        rel = Path(path).as_posix()
        idx = rel.find("uploads/")
        if idx >= 0:
            return "/" + rel[idx:]
    except (TypeError, ValueError):
        pass
    return ""


def _visual_state_label(state: str) -> str:
    return _VISUAL_STATE_LABELS.get(state or "unknown", state or "unknown")


def _enrich_screenshot(shot: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(shot)
    enriched["url"] = path_to_upload_url(str(shot.get("path") or ""))
    state = shot.get("visual_state") or "unknown"
    enriched["visual_state_label_ar"] = _visual_state_label(state)
    return enriched


def _build_executable_replay(analysis: Dict[str, Any]) -> Dict[str, Any]:
    unity = analysis.get("unity_observation") or {}
    visual = analysis.get("visual_observation") or {}
    restriction = analysis.get("process_restriction") or {}
    screenshots = [
        _enrich_screenshot(s)
        for s in (analysis.get("runtime_screenshots") or [])
        if isinstance(s, dict)
    ]
    return {
        "artifact": analysis.get("artifact") or analysis.get("path") or "unknown",
        "type": analysis.get("type"),
        "engine": analysis.get("engine"),
        "valid": analysis.get("valid"),
        "smoke_result": analysis.get("smoke_result"),
        "signals": analysis.get("signals") or {},
        "unity_observation": unity,
        "visual_observation": visual,
        "process_restriction": restriction,
        "screenshots": screenshots,
        "interaction_trace": analysis.get("interaction_trace") or {},
        "player_log": {
            "found": bool(unity.get("player_log_found")),
            "path": unity.get("selected_log_path", ""),
            "unity_version_hint": unity.get("unity_version_hint", ""),
            "error_count": unity.get("error_count", 0),
            "exception_count": unity.get("exception_count", 0),
            "crash_signal_count": unity.get("crash_signal_count", 0),
            "crash_signals": (unity.get("crash_signals") or [])[:8],
            "error_signals": (unity.get("error_signals") or [])[:12],
            "scene_load_signals": (unity.get("scene_load_signals") or [])[:8],
            "input_system_signals": (unity.get("input_system_signals") or [])[:8],
            "candidate_log_count": unity.get("candidate_log_count", 0),
        },
    }


def _collect_audit_fields(
    obs_report: Dict[str, Any],
    inv: Dict[str, Any],
) -> Dict[str, Any]:
    audit = {
        "observed_visual_elements": [],
        "unverified_gameplay": [],
        "human_validation_required": [],
        "visual_states_observed": [],
        "black_screen_possible": False,
        "freeze_possible": False,
        "visual_runtime_confidence": 0.0,
    }
    for summary in obs_report.get("visual_observation_summary") or []:
        if not isinstance(summary, dict):
            continue
        audit["observed_visual_elements"].extend(summary.get("observed_visual_elements") or [])
        audit["unverified_gameplay"].extend(summary.get("unverified_gameplay") or [])
        audit["human_validation_required"].extend(summary.get("human_validation_required") or [])
        audit["visual_states_observed"].extend(summary.get("visual_states_observed") or [])
        audit["black_screen_possible"] = audit["black_screen_possible"] or bool(
            summary.get("black_screen_possible")
        )
        audit["freeze_possible"] = audit["freeze_possible"] or bool(summary.get("freeze_possible"))
        conf = float(summary.get("visual_runtime_confidence") or 0.0)
        audit["visual_runtime_confidence"] = max(audit["visual_runtime_confidence"], conf)

    rt = inv.get("runtime_artifacts") or {}
    for summary in rt.get("visual_runtime_observation") or []:
        if not isinstance(summary, dict):
            continue
        audit["observed_visual_elements"].extend(summary.get("observed_visual_elements") or [])
        audit["unverified_gameplay"].extend(summary.get("unverified_gameplay") or [])
        audit["human_validation_required"].extend(summary.get("human_validation_required") or [])

    def _dedupe(items: List[Any]) -> List[Any]:
        seen: set = set()
        out: List[Any] = []
        for item in items:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    audit["observed_visual_elements"] = _dedupe(audit["observed_visual_elements"])
    audit["unverified_gameplay"] = _dedupe(audit["unverified_gameplay"])
    audit["human_validation_required"] = _dedupe(audit["human_validation_required"])
    audit["visual_states_observed"] = _dedupe(audit["visual_states_observed"])
    return audit


def _load_inventory_from_disk(
    *,
    student_name: str = "",
    batch_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    debug_dir = Path("uploads/debug")
    if not debug_dir.is_dir():
        return None
    safe = re.sub(r"[^\w\-]+", "_", student_name or "")[:80]
    if not safe:
        return None
    suffix = f"_batch{batch_id}" if batch_id else ""
    candidate = debug_dir / f"{safe}{suffix}_artifact_inventory.json"
    if not candidate.is_file():
        for path in sorted(debug_dir.glob(f"{safe}*_artifact_inventory.json"), reverse=True):
            candidate = path
            break
        else:
            return None
    try:
        with open(candidate, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def build_runtime_replay(
    grading_snapshot: Optional[Dict[str, Any]] = None,
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    student_name: str = "",
    batch_id: Optional[int] = None,
    submission_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build read-only runtime replay payload for teacher review UI.
    """
    snap = grading_snapshot or {}
    inv = artifact_inventory or snap.get("artifact_inventory") or {}
    if not inv and student_name:
        inv = _load_inventory_from_disk(student_name=student_name, batch_id=batch_id) or {}

    obs_report = inv.get("runtime_observation_report") or {}
    analyses = obs_report.get("artifact_analyses") or []

    executables = [_build_executable_replay(a) for a in analyses if isinstance(a, dict)]
    all_screenshots: List[Dict[str, Any]] = []
    for exe in executables:
        all_screenshots.extend(exe.get("screenshots") or [])

    for shot in obs_report.get("runtime_screenshots") or []:
        if isinstance(shot, dict) and shot.get("status") == "captured":
            enriched = _enrich_screenshot(shot)
            if enriched.get("url") and enriched not in all_screenshots:
                all_screenshots.append(enriched)

    all_screenshots.sort(
        key=lambda s: (
            s.get("runtime_session_id") or "",
            float(s.get("timestamp_sec") or s.get("elapsed_seconds") or 0),
        )
    )

    restriction = inv.get("runtime_process_restriction") or {}
    if not restriction:
        for exe in executables:
            if exe.get("process_restriction"):
                restriction = exe["process_restriction"]
                break

    audit = _collect_audit_fields(obs_report, inv)
    interaction_traces = [
        exe.get("interaction_trace")
        for exe in executables
        if isinstance(exe.get("interaction_trace"), dict) and exe.get("interaction_trace")
    ]
    if not interaction_traces:
        interaction_traces = [
            t for t in (obs_report.get("interaction_trace_summary") or [])
            if isinstance(t, dict)
        ]
    screenshot_count = sum(1 for s in all_screenshots if s.get("status") == "captured")
    has_runtime = bool(
        executables
        or screenshot_count
        or obs_report.get("status") == "completed"
        or inv.get("runtime_artifacts", {}).get("runtime_screenshot_count")
    )

    return {
        "mode": "runtime_replay_viewer",
        "available": has_runtime,
        "submission_id": submission_id,
        "runtime_session_id": obs_report.get("runtime_session_id"),
        "runtime_evidence_level": obs_report.get("runtime_evidence_level"),
        "runtime_observed": obs_report.get("runtime_observed"),
        "runtime_verified": obs_report.get("runtime_verified"),
        "observation_status": obs_report.get("status"),
        "observation_summary_ar": obs_report.get("observation_summary_ar"),
        "human_authority_required": obs_report.get(
            "human_authority_required", True
        ),
        "guardrail_note_ar": _GUARDrail_AR,
        "executables": executables,
        "visual_timeline": all_screenshots,
        "runtime_screenshot_count": screenshot_count,
        "process_restriction": restriction,
        "audit": audit,
        "interaction_trace_summary": interaction_traces,
        "automated_interaction_observed": any(
            t.get("interaction_traces_detected") for t in interaction_traces
        ),
        "unity_observation_summary": obs_report.get("unity_observation_summary") or [],
        "language_note_ar": obs_report.get("language_note_ar"),
        "manual_playtest_pass": inv.get("manual_playtest_pass") or obs_report.get("manual_playtest_pass"),
        "runtime_criterion_support": inv.get("runtime_criterion_support")
        or snap.get("runtime_criterion_support"),
        "runtime_adjudication_db_sync": snap.get("runtime_adjudication_db_sync")
        or inv.get("runtime_adjudication_db_sync"),
    }
