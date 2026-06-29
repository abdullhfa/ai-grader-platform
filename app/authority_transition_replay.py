"""
Authority Transition Replay — semantic diff layer for authority escalations.

Answers: why authority changed, what changed (criteria, confidence), not just event labels.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.academic_event_replay import build_academic_timeline_replay

REPLAY_MODE = "authority_transition_replay"

_AUTHORITY_RANK = {
    "AI_GRADING": 10,
    "SYSTEM_GOVERNED": 20,
    "RUNTIME_INSUFFICIENT": 25,
    "HUMAN_REVIEW_REQUIRED": 30,
    "RUNTIME_OBSERVATION_L4": 40,
    "RUNTIME_ADJUDICATION": 45,
    "HUMAN_PLAYTEST_L5": 50,
}


def _authority_rank(auth: str) -> int:
    return _AUTHORITY_RANK.get((auth or "").strip().upper(), 0) or (
        35 if auth else 0
    )


def _status_label(achieved: Optional[bool], lineage_status: Optional[str] = None) -> str:
    if lineage_status:
        return str(lineage_status)
    if achieved is True:
        return "ACHIEVED"
    if achieved is False:
        return "NOT_ACHIEVED"
    return "UNKNOWN"


def _confidence_for_criterion(snapshot: Dict[str, Any], criteria_level: str) -> Optional[float]:
    lineage = (
        (snapshot.get("explainability_layer") or {}).get("evidence_lineage")
        or snapshot.get("evidence_lineage")
        or {}
    )
    crit_map = lineage.get("criteria") or {}
    key = "C.P5" if "P5" in criteria_level.upper() else "C.P6" if "P6" in criteria_level.upper() else ""
    if not key:
        return None
    entry = crit_map.get(key) or {}
    node_ids = (entry.get("lineage") or {}).get("evidence_nodes") or []
    shared = lineage.get("shared_nodes") or {}
    confs = [
        float((shared.get(nid) or {}).get("confidence") or 0)
        for nid in node_ids
        if (shared.get(nid) or {}).get("type") != "governance_gate"
    ]
    if not confs:
        return None
    return round(max(confs), 4)


def _infer_reasons(
    events_before: List[Dict[str, Any]],
    *,
    transition_event: Dict[str, Any],
) -> List[Dict[str, str]]:
    reasons: List[Dict[str, str]] = []
    lookback = events_before[-8:]

    for ev in lookback:
        et = ev.get("event_type")
        if et == "human_playtest_completed":
            reasons.append(
                {
                    "code": "manual_playtest_completed",
                    "label_ar": "اكتمل Manual Playtest L5",
                    "event_seq": str(ev.get("event_seq") or ""),
                }
            )
        elif et == "runtime_adjudication_applied":
            reasons.append(
                {
                    "code": "runtime_adjudication",
                    "label_ar": "تطبيق runtime adjudication على C.P5/C.P6",
                    "event_seq": str(ev.get("event_seq") or ""),
                }
            )
        elif et == "runtime_gated":
            reasons.append(
                {
                    "code": "governance_gate",
                    "label_ar": "Runtime مقفول — GOVERNANCE_FREEZE",
                    "event_seq": str(ev.get("event_seq") or ""),
                }
            )
        elif et == "evidence_lineage_attached":
            reasons.append(
                {
                    "code": "lineage_available",
                    "label_ar": "Evidence lineage DAG متاح للمراجعة",
                    "event_seq": str(ev.get("event_seq") or ""),
                }
            )

    payload = transition_event.get("payload") or {}
    if payload.get("achievement_authority"):
        reasons.append(
            {
                "code": "adjudication_authority",
                "label_ar": f"سلطة adjudication: {payload['achievement_authority']}",
                "event_seq": str(transition_event.get("event_seq") or ""),
            }
        )

    if not reasons:
        reasons.append(
            {
                "code": "event_chain_context",
                "label_ar": "سياق من سلسلة الأحداث السابقة",
                "event_seq": "",
            }
        )

    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for r in reasons:
        k = r["code"]
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _impact_from_payload(
    payload: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    level = str(payload.get("criteria_level") or "")
    before_a = payload.get("achieved_before")
    after_a = payload.get("achieved_after")

    before_status = _status_label(before_a if before_a is not None else False)
    after_status = _status_label(after_a if after_a is not None else True)

    conf = _confidence_for_criterion(snapshot, level)
    conf_before = conf
    conf_after = conf
    if before_a is False and after_a is True and conf is not None:
        conf_before = min(conf, 0.45)
        conf_after = max(conf, 0.93)
    elif before_a is True and after_a is False and conf is not None:
        conf_before = max(conf, 0.93)
        conf_after = min(conf, 0.45)

    return {
        "criteria_level": level,
        "status_before": before_status,
        "status_after": after_status,
        "achieved_before": before_a,
        "achieved_after": after_a,
        "confidence_before": conf_before,
        "confidence_after": conf_after,
        "confidence_delta": (
            round((conf_after or 0) - (conf_before or 0), 4)
            if conf_before is not None and conf_after is not None
            else None
        ),
    }


def _track_authority_state(events: List[Dict[str, Any]], up_to_index: int) -> str:
    state = "AI_GRADING"
    for ev in events[:up_to_index]:
        et = ev.get("event_type")
        auth = str(ev.get("authority") or "")
        if et == "initial_grading":
            state = "AI_GRADING"
        elif et == "runtime_gated":
            state = "SYSTEM_GOVERNED"
        elif et == "human_playtest_completed":
            state = "HUMAN_PLAYTEST_L5"
        elif et == "authority_transition" and auth:
            state = auth
        elif et == "criterion_decision" and auth:
            state = auth
    return state


def build_authority_transition_replay(
    grading_snapshot: Optional[Dict[str, Any]] = None,
    *,
    graded_at: Optional[str] = None,
    events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Decision delta semantics — authority transitions with reasons and impact.
    Read-only; does not mutate grades.
    """
    snap = grading_snapshot or {}
    if events is None:
        timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
        events = timeline.get("events") or []

    transitions: List[Dict[str, Any]] = []

    for i, ev in enumerate(events):
        if ev.get("event_type") != "authority_transition":
            continue

        payload = ev.get("payload") or {}
        from_auth = payload.get("authority_from") or _track_authority_state(events, i)
        to_auth = str(ev.get("authority") or payload.get("achievement_authority") or "UNKNOWN")
        impact = _impact_from_payload(payload, snap)
        reasons = _infer_reasons(events[:i], transition_event=ev)

        transitions.append(
            {
                "transition_id": f"atr_{ev.get('event_seq', i + 1)}",
                "event_id": ev.get("event_id"),
                "event_seq": ev.get("event_seq"),
                "event_hash": ev.get("event_hash"),
                "timestamp": ev.get("timestamp"),
                "synthetic": bool(ev.get("synthetic")),
                "from_authority": from_auth,
                "to_authority": to_auth,
                "escalation": _authority_rank(to_auth) > _authority_rank(from_auth),
                "reasons": reasons,
                "impact": impact,
                "title_ar": ev.get("title_ar")
                or f"{from_auth} → {to_auth}",
                "detail_ar": ev.get("detail_ar") or "",
            }
        )

    # Also surface implicit governance transitions (no explicit authority_transition event)
    for i, ev in enumerate(events):
        if ev.get("event_type") == "runtime_gated":
            transitions.append(
                {
                    "transition_id": f"atr_gov_{ev.get('event_seq', i + 1)}",
                    "event_id": ev.get("event_id"),
                    "event_seq": ev.get("event_seq"),
                    "event_hash": ev.get("event_hash"),
                    "timestamp": ev.get("timestamp"),
                    "synthetic": bool(ev.get("synthetic")),
                    "from_authority": "AI_GRADING",
                    "to_authority": "SYSTEM_GOVERNED",
                    "escalation": True,
                    "reasons": [
                        {
                            "code": "governance_freeze",
                            "label_ar": (ev.get("payload") or {}).get("reason")
                            or "GOVERNANCE_FREEZE_v1_active",
                            "event_seq": str(ev.get("event_seq") or ""),
                        }
                    ],
                    "impact": {
                        "criteria_level": "C.P5/C.P6",
                        "status_before": "PENDING",
                        "status_after": "HOLD",
                        "runtime_execution": "blocked",
                    },
                    "title_ar": "AI_GRADING → SYSTEM_GOVERNED",
                    "detail_ar": ev.get("detail_ar") or "Runtime gated — لا تشغيل L4.",
                }
            )

    transitions.sort(key=lambda t: (t.get("event_seq") or 0, str(t.get("timestamp") or "")))

    return {
        "schema": "1.0",
        "mode": REPLAY_MODE,
        "transition_count": len(transitions),
        "transitions": transitions,
        "note_ar": (
            "Authority Transition Replay — semantic diff: لماذا تغيّرت السلطة وماذا تأثر. "
            "لا يعدّل الدرجة."
        ),
    }
