"""
Academic Event Replay — immutable append-only event log + timeline reconstruction.

Event-sourced academic replay: revisions, governance, adjudications, authority transitions.
Each event links to snapshot_hash / event_hash chain for forensic audit.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ACADEMIC_EVENT_SCHEMA = "1.1"
REPLAY_MODE = "academic_timeline_replay"

_EVENT_TYPES = frozenset(
    {
        "initial_grading",
        "runtime_gated",
        "criterion_decision",
        "explainability_revision",
        "evidence_lineage_attached",
        "human_playtest_completed",
        "runtime_adjudication_applied",
        "authority_transition",
        "governance_state",
    }
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:16]}"


def _hash_event_body(body: Dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(body).encode("utf-8")).hexdigest()


def create_academic_event(
    event_type: str,
    authority: str,
    *,
    event_seq: Optional[int] = None,
    timestamp: Optional[str] = None,
    snapshot_hash: Optional[str] = None,
    previous_event_hash: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    synthetic: bool = False,
    title_ar: str = "",
    detail_ar: str = "",
) -> Dict[str, Any]:
    """Build one immutable academic event (hash computed before event_hash field)."""
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"unknown event_type: {event_type}")

    body: Dict[str, Any] = {
        "event_id": _event_id(),
        "event_type": event_type,
        "authority": authority,
        "timestamp": timestamp or _utc_now_iso(),
        "snapshot_hash": snapshot_hash,
        "previous_event_hash": previous_event_hash,
        "payload": payload or {},
        "synthetic": synthetic,
        "title_ar": title_ar,
        "detail_ar": detail_ar,
    }
    if event_seq is not None:
        body["event_seq"] = event_seq
    body["event_hash"] = _hash_event_body(body)
    return body


def _next_event_seq(log: Dict[str, Any], events: List[Dict[str, Any]]) -> int:
    stored = log.get("next_event_seq")
    if isinstance(stored, int) and stored > 0:
        return stored
    if events:
        last_seq = max(int(e.get("event_seq") or 0) for e in events)
        return last_seq + 1
    return 1


def _finalize_event(
    raw: Dict[str, Any],
    *,
    event_seq: int,
    previous_event_hash: Optional[str],
) -> Dict[str, Any]:
    ev = dict(raw)
    ev["event_seq"] = event_seq
    ev["previous_event_hash"] = previous_event_hash
    body = {k: v for k, v in ev.items() if k != "event_hash"}
    ev["event_hash"] = _hash_event_body(body)
    return ev


def get_academic_event_log(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    log = (snapshot or {}).get("academic_event_log") or {}
    if not isinstance(log, dict):
        return {"schema": ACADEMIC_EVENT_SCHEMA, "events": []}
    events = log.get("events")
    if not isinstance(events, list):
        events = []
    return {
        "schema": log.get("schema") or ACADEMIC_EVENT_SCHEMA,
        "events": events,
        "chain_head_hash": log.get("chain_head_hash"),
        "event_count": len(events),
        "next_event_seq": log.get("next_event_seq"),
    }


def append_academic_event(
    snapshot: Dict[str, Any],
    event: Dict[str, Any],
    *,
    allow_synthetic_overwrite: bool = False,
) -> Dict[str, Any]:
    """Append-only event log on snapshot — returns the appended event."""
    log = get_academic_event_log(snapshot)
    events: List[Dict[str, Any]] = list(log.get("events") or [])

    if events and not event.get("previous_event_hash"):
        event["previous_event_hash"] = events[-1].get("event_hash")
    elif not events:
        event["previous_event_hash"] = None

    if event.get("event_seq") is None:
        event["event_seq"] = _next_event_seq(log, events)

    event = _finalize_event(
        event,
        event_seq=int(event["event_seq"]),
        previous_event_hash=event.get("previous_event_hash"),
    )

    if not allow_synthetic_overwrite:
        for existing in events:
            if existing.get("event_hash") == event.get("event_hash"):
                return existing

    events.append(copy.deepcopy(event))
    next_seq = int(event["event_seq"]) + 1
    snapshot["academic_event_log"] = {
        "schema": ACADEMIC_EVENT_SCHEMA,
        "events": events,
        "chain_head_hash": event.get("event_hash"),
        "event_count": len(events),
        "next_event_seq": next_seq,
        "updated_at": _utc_now_iso(),
    }
    return event


def _snapshot_anchor_hash(snapshot: Dict[str, Any]) -> Optional[str]:
    rev = snapshot.get("explainability_revision") or {}
    if rev.get("snapshot_hash"):
        return str(rev["snapshot_hash"])
    layer = snapshot.get("explainability_layer") or {}
    lineage = layer.get("evidence_lineage") or snapshot.get("evidence_lineage") or {}
    if lineage.get("lineage_hash"):
        return str(lineage["lineage_hash"])
    if snapshot.get("grading_hash"):
        return str(snapshot["grading_hash"])
    return None


def _criterion_summary(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for cr in snapshot.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        short = level.split(".")[-1].upper() if "." in level else level.upper()
        if short not in ("P5", "P6"):
            continue
        achieved = bool(cr.get("achieved"))
        rows.append(
            {
                "criteria_level": level,
                "status": "ACHIEVED" if achieved else "NOT_ACHIEVED",
                "achievement_authority": cr.get("achievement_authority"),
            }
        )
    lineage = (
        (snapshot.get("explainability_layer") or {}).get("evidence_lineage")
        or snapshot.get("evidence_lineage")
        or {}
    )
    for key in ("C.P5", "C.P6"):
        crit = (lineage.get("criteria") or {}).get(key) or {}
        if crit and not any(r.get("criteria_level", "").endswith(key.split(".")[-1]) for r in rows):
            rows.append(
                {
                    "criteria_level": crit.get("criteria_level") or key,
                    "status": crit.get("status"),
                    "achievement_authority": crit.get("decision_authority"),
                }
            )
        elif crit:
            for r in rows:
                if key.split(".")[-1] in str(r.get("criteria_level", "")).upper():
                    r["status"] = crit.get("status") or r["status"]
                    r["achievement_authority"] = crit.get("decision_authority") or r.get(
                        "achievement_authority"
                    )
    return rows


def reconstruct_events_from_snapshot(
    snapshot: Dict[str, Any],
    *,
    graded_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Rebuild timeline from persisted snapshot fields when event log is empty or partial.
    Events marked synthetic=True — for replay only until persisted via seed/append.
    """
    if not isinstance(snapshot, dict):
        return []

    events: List[Dict[str, Any]] = []
    prev_hash: Optional[str] = None
    seq = 0
    base_ts = graded_at or _utc_now_iso()
    anchor = _snapshot_anchor_hash(snapshot)
    inv = snapshot.get("artifact_inventory") or {}

    def _add(
        event_type: str,
        authority: str,
        *,
        ts: Optional[str] = None,
        snap_hash: Optional[str] = None,
        payload: Optional[Dict] = None,
        title_ar: str = "",
        detail_ar: str = "",
    ) -> None:
        nonlocal prev_hash, seq
        seq += 1
        ev = create_academic_event(
            event_type,
            authority,
            event_seq=seq,
            timestamp=ts or base_ts,
            snapshot_hash=snap_hash or anchor,
            previous_event_hash=prev_hash,
            payload=payload or {},
            synthetic=True,
            title_ar=title_ar,
            detail_ar=detail_ar,
        )
        events.append(ev)
        prev_hash = ev["event_hash"]

    grade = snapshot.get("grade_level", "—")
    crit_rows = []
    for cr in snapshot.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        crit_rows.append(
            {
                "criteria_level": cr.get("criteria_level"),
                "achieved": cr.get("achieved"),
                "score": cr.get("score"),
                "achievement_authority": cr.get("achievement_authority"),
            }
        )
    def _norm_criterion_key_local(level: str) -> str:
        lv = (level or "").strip().upper()
        return lv.split(".")[-1] if "." in lv else lv

    summary_by_key = {
        _norm_criterion_key_local(str(s.get("criteria_level") or "")): s
        for s in _criterion_summary(snapshot)
    }

    for row in crit_rows:
        sk = _norm_criterion_key_local(str(row.get("criteria_level") or ""))
        if sk in summary_by_key:
            sm = summary_by_key[sk]
            row["status"] = sm.get("status")
    _add(
        "initial_grading",
        "AI_GRADING",
        payload={
            "grade_level": grade,
            "total_score": snapshot.get("total_score"),
            "max_score": snapshot.get("max_score"),
            "percentage": snapshot.get("percentage"),
            "criteria_count": len(crit_rows),
            "criteria_results": crit_rows,
        },
        title_ar="تصحيح أولي",
        detail_ar=f"الدرجة الأولية: {grade} — قرار AI grading مع criteria_results.",
    )

    obs = inv.get("runtime_observation_report") or {}
    if obs.get("status") == "gated":
        _add(
            "runtime_gated",
            "SYSTEM_GOVERNED",
            payload={
                "reason": obs.get("reason") or "GOVERNANCE_FREEZE_v1_active",
                "status": "gated",
            },
            title_ar="Runtime مقفول — حوكمة",
            detail_ar=obs.get("gate_ar")
            or "L4 sandbox معطّل — GOVERNANCE_FREEZE_v1 — Manual Playtest مطلوب.",
        )
    elif obs.get("status") == "completed":
        _add(
            "governance_state",
            "RUNTIME_OBSERVATION_L4",
            payload={"status": "completed", "runtime_verified": obs.get("runtime_verified")},
            title_ar="ملاحظة runtime L4",
            detail_ar="تمت ملاحظة runtime — استشارية فقط، لا Achieved تلقائي.",
        )

    lineage = (
        (snapshot.get("explainability_layer") or {}).get("evidence_lineage")
        or snapshot.get("evidence_lineage")
        or inv.get("evidence_lineage")
        or {}
    )
    if lineage.get("lineage_hash"):
        _add(
            "evidence_lineage_attached",
            "SYSTEM",
            snap_hash=str(lineage["lineage_hash"]),
            payload={
                "lineage_hash": lineage["lineage_hash"],
                "criteria": list((lineage.get("criteria") or {}).keys()),
            },
            title_ar="Evidence Lineage — DAG",
            detail_ar="بنية causality: evidence → governance → decision (C.P5/C.P6).",
        )

    history = snapshot.get("explainability_revision_history") or []
    rev_current = snapshot.get("explainability_revision") or {}
    rev_rows = list(history) if history else ([rev_current] if rev_current else [])
    for rev in rev_rows:
        if not isinstance(rev, dict) or not rev.get("version"):
            continue
        _add(
            "explainability_revision",
            str(rev.get("generated_by") or "system"),
            ts=rev.get("generated_at") or base_ts,
            snap_hash=str(rev.get("snapshot_hash") or anchor or ""),
            payload={
                "version": rev.get("version"),
                "explainability_schema": rev.get("explainability_schema"),
                "policy_version": rev.get("policy_version"),
                "trigger": rev.get("trigger"),
                "non_destructive": rev.get("non_destructive"),
            },
            title_ar=f"Explainability {rev.get('version')} — additive",
            detail_ar=rev.get("disclaimer_ar")
            or "طبقة شفافية — لم يُغيّر قرار أكاديمي.",
        )

    l5 = snapshot.get("l5_human_playtest") or inv.get("l5_human_playtest") or {}
    if l5.get("pass") or l5.get("status") == "completed":
        _add(
            "human_playtest_completed",
            "HUMAN_PLAYTEST_L5",
            ts=l5.get("finalized_at") or l5.get("recorded_at") or base_ts,
            payload={
                "pass": l5.get("pass"),
                "pass_id": l5.get("pass_id"),
                "verified": l5.get("verified"),
            },
            title_ar="Manual Playtest L5 — مكتمل",
            detail_ar="تحقق بشري — سلطة L5 متاحة لـ runtime adjudication.",
        )

    adj = snapshot.get("runtime_adjudication") or {}
    db_sync = snapshot.get("runtime_adjudication_db_sync") or {}
    changes = adj.get("changes") or db_sync.get("row_changes") or []
    if changes:
        _add(
            "runtime_adjudication_applied",
            "RUNTIME_ADJUDICATION",
            payload={"changes": changes},
            title_ar="Runtime adjudication — C.P5/C.P6",
            detail_ar=f"تطبيق {len(changes)} تغيير(ات) على معايير التشغيل.",
        )
        for ch in changes:
            before = ch.get("achieved_before")
            after = ch.get("achieved_after")
            if before is None or after is None or before == after:
                continue
            rich = dict(ch)
            rich["authority_from"] = "SYSTEM_GOVERNED"
            rich["authority_to"] = str(ch.get("achievement_authority") or "HUMAN_PLAYTEST_L5")
            _add(
                "authority_transition",
                rich["authority_to"],
                payload=rich,
                title_ar=f"{ch.get('criteria_level')}: {before} → {after}",
                detail_ar="انتقال سلطة — بعد playtest/adjudication.",
            )

    return events


def seed_academic_event_log(
    snapshot: Dict[str, Any],
    *,
    graded_at: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Persist initial event log on snapshot at grade time (append-only seed)."""
    log = get_academic_event_log(snapshot)
    if log.get("events") and not force:
        return snapshot

    raw_events = reconstruct_events_from_snapshot(snapshot, graded_at=graded_at)
    events: List[Dict[str, Any]] = []
    prev_hash: Optional[str] = None
    for seq, raw in enumerate(raw_events, start=1):
        ev = dict(raw)
        ev["synthetic"] = False
        ev = _finalize_event(ev, event_seq=seq, previous_event_hash=prev_hash)
        events.append(ev)
        prev_hash = ev["event_hash"]

    snapshot["academic_event_log"] = {
        "schema": ACADEMIC_EVENT_SCHEMA,
        "events": events,
        "chain_head_hash": events[-1]["event_hash"] if events else None,
        "event_count": len(events),
        "next_event_seq": len(events) + 1,
        "seeded_at": _utc_now_iso(),
    }
    return snapshot


def append_explainability_revision_event(
    snapshot: Dict[str, Any],
    revision: Dict[str, Any],
) -> Dict[str, Any]:
    ev = create_academic_event(
        "explainability_revision",
        str(revision.get("generated_by") or "system"),
        timestamp=revision.get("generated_at") or _utc_now_iso(),
        snapshot_hash=str(revision.get("snapshot_hash") or ""),
        payload={
            "version": revision.get("version"),
            "explainability_schema": revision.get("explainability_schema"),
            "policy_version": revision.get("policy_version"),
            "trigger": revision.get("trigger"),
            "non_destructive": revision.get("non_destructive"),
            "previous_snapshot_hash": revision.get("previous_snapshot_hash"),
        },
        synthetic=False,
        title_ar=f"Explainability {revision.get('version')} — backfill",
        detail_ar=revision.get("disclaimer_ar") or "",
    )
    append_academic_event(snapshot, ev)
    return snapshot


def append_playtest_finalize_events(
    snapshot: Dict[str, Any],
    *,
    playtest_result: Optional[Dict[str, Any]] = None,
    db_sync: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    l5 = snapshot.get("l5_human_playtest") or {}
    ev = create_academic_event(
        "human_playtest_completed",
        "HUMAN_PLAYTEST_L5",
        timestamp=l5.get("finalized_at") or _utc_now_iso(),
        snapshot_hash=_snapshot_anchor_hash(snapshot),
        payload={
            "pass": l5.get("pass"),
            "pass_id": l5.get("pass_id"),
            "playtest": playtest_result or {},
        },
        synthetic=False,
        title_ar="Manual Playtest L5 — finalized",
        detail_ar="اكتمال التحقق البشري — جاهز لـ runtime adjudication.",
    )
    append_academic_event(snapshot, ev)

    sync = db_sync or snapshot.get("runtime_adjudication_db_sync") or {}
    changes = sync.get("row_changes") or (snapshot.get("runtime_adjudication") or {}).get(
        "changes"
    ) or []
    if changes:
        adj_ev = create_academic_event(
            "runtime_adjudication_applied",
            "RUNTIME_ADJUDICATION",
            snapshot_hash=_snapshot_anchor_hash(snapshot),
            payload={"changes": changes, "db_sync": bool(sync.get("applied"))},
            synthetic=False,
            title_ar="Runtime adjudication applied",
            detail_ar=f"تحديث {len(changes)} معيار(اً) في قاعدة البيانات.",
        )
        append_academic_event(snapshot, adj_ev)
        for ch in changes:
            before = ch.get("achieved_before")
            after = ch.get("achieved_after")
            if before is None or after is None or before == after:
                continue
            rich = dict(ch)
            rich["authority_from"] = "SYSTEM_GOVERNED"
            rich["authority_to"] = str(ch.get("achievement_authority") or "HUMAN_PLAYTEST_L5")
            tr = create_academic_event(
                "authority_transition",
                rich["authority_to"],
                snapshot_hash=_snapshot_anchor_hash(snapshot),
                payload=rich,
                synthetic=False,
                title_ar=f"{ch.get('criteria_level')}: {before} → {after}",
                detail_ar="انتقال سلطة بعد L5 playtest.",
            )
            append_academic_event(snapshot, tr)
    return snapshot


def _group_events_by_date(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for ev in sorted(events, key=lambda e: str(e.get("timestamp") or "")):
        ts = str(ev.get("timestamp") or "")
        day = ts[:10] if len(ts) >= 10 else "unknown"
        buckets.setdefault(day, []).append(ev)
    return [{"date": d, "events": buckets[d]} for d in sorted(buckets.keys())]


def _norm_criterion_key_local(level: str) -> str:
    lv = (level or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def _criteria_signature_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, tuple]:
    sig: Dict[str, tuple] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = _norm_criterion_key_local(str(row.get("criteria_level") or ""))
        if not key:
            continue
        sig[key] = (
            bool(row.get("achieved")),
            row.get("score"),
            row.get("achievement_authority"),
        )
    return sig


def persisted_event_log_stale(snapshot: Dict[str, Any], persisted: List[Dict[str, Any]]) -> bool:
    """True when persisted log no longer matches snapshot academic decisions."""
    if not persisted:
        return False
    initial = next((e for e in persisted if e.get("event_type") == "initial_grading"), None)
    if not initial:
        return False
    payload = initial.get("payload") or {}
    event_sig = _criteria_signature_from_rows(payload.get("criteria_results") or [])
    snap_sig = _criteria_signature_from_rows(snapshot.get("criteria_results") or [])
    if event_sig != snap_sig:
        return True
    for field in ("grade_level", "total_score", "max_score", "percentage"):
        ev_val = payload.get(field)
        snap_val = snapshot.get(field)
        if ev_val is not None and snap_val is not None and ev_val != snap_val:
            return True
    return False


def build_academic_timeline_replay(
    grading_snapshot: Optional[Dict[str, Any]] = None,
    *,
    graded_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Event-Sourced Academic Replay — merged persisted log + synthetic reconstruction.
    Read-only; does not mutate grades.
    """
    snap = grading_snapshot or {}
    log = get_academic_event_log(snap)
    persisted = list(log.get("events") or [])

    if persisted and not persisted_event_log_stale(snap, persisted):
        events = persisted
        source = "persisted_event_log"
    elif persisted:
        events = reconstruct_events_from_snapshot(snap, graded_at=graded_at)
        source = "synthetic_reconstruction_stale_log"
    else:
        events = reconstruct_events_from_snapshot(snap, graded_at=graded_at)
        source = "synthetic_reconstruction"

    for i, ev in enumerate(events):
        if ev.get("event_seq") is None:
            ev["event_seq"] = i + 1

    by_date = _group_events_by_date(events)
    chain_intact = True
    for i, ev in enumerate(events):
        if i == 0:
            if ev.get("previous_event_hash") not in (None, ""):
                chain_intact = False
        else:
            if ev.get("previous_event_hash") != events[i - 1].get("event_hash"):
                chain_intact = False

    from app.academic_integrity_model import build_integrity_summary
    from app.authority_transition_replay import build_authority_transition_replay

    authority_replay = build_authority_transition_replay(snap, events=events)

    from app.deterministic_replay_engine import verify_deterministic_replay

    replay_verification = verify_deterministic_replay(events, snap)

    return {
        "schema": ACADEMIC_EVENT_SCHEMA,
        "mode": REPLAY_MODE,
        "source": source,
        "event_count": len(events),
        "chain_head_hash": log.get("chain_head_hash") or (events[-1]["event_hash"] if events else None),
        "next_event_seq": log.get("next_event_seq") or (len(events) + 1),
        "chain_integrity": chain_intact,
        "events": events,
        "timeline_by_date": by_date,
        "authority_transitions": authority_replay.get("transitions") or [],
        "integrity": build_integrity_summary(snap),
        "replay_verification": {
            k: v
            for k, v in replay_verification.items()
            if k != "replayed_state"
        },
        "snapshot_anchor_hash": _snapshot_anchor_hash(snap),
        "note_ar": (
            "Academic Timeline Replay — أحداث append-only مرتبطة بـ snapshot hash. "
            "لا تعدّل الدرجة."
        ),
    }
