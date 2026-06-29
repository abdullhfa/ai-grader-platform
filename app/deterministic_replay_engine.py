"""
Deterministic Replay Engine — pure event reducer for academic state.

replay(events) -> academic_state

No DB lookups, no mutable snapshot reads during fold — events are source of truth.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Optional

REPLAY_ENGINE_VERSION = "1.0"
GOVERNANCE_CONTRACT = "2.1"
REDUCER_VERSION = "1.0"

# Replay epochs — first-class governance labels (schema / policy boundaries).
EPOCH_INITIAL = "INITIAL"
EPOCH_POST_INITIAL_GRADING = "POST_INITIAL_GRADING"
EPOCH_RUNTIME_GATED = "RUNTIME_GATED"
EPOCH_POST_EXPLAINABILITY = "POST_EXPLAINABILITY"
EPOCH_POST_PLAYTEST_L5 = "POST_PLAYTEST_L5"
EPOCH_POST_ADJUDICATION = "POST_ADJUDICATION"

EPOCH_METADATA: Dict[str, Dict[str, str]] = {
    EPOCH_INITIAL: {
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
    },
    EPOCH_POST_INITIAL_GRADING: {
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
    },
    EPOCH_RUNTIME_GATED: {
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
    },
    EPOCH_POST_EXPLAINABILITY: {
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
    },
    EPOCH_POST_PLAYTEST_L5: {
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
    },
    EPOCH_POST_ADJUDICATION: {
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
    },
}


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _norm_criterion_key(criteria_level: str) -> str:
    lv = (criteria_level or "").strip().upper()
    if not lv:
        return ""
    return lv.split(".")[-1] if "." in lv else lv


def initial_replay_state() -> Dict[str, Any]:
    return {
        "replay_engine_version": REPLAY_ENGINE_VERSION,
        "replay_epoch": EPOCH_INITIAL,
        "grade_level": None,
        "total_score": None,
        "max_score": None,
        "percentage": None,
        "criteria": {},
        "governance": {
            "active_authority": "AI_GRADING",
            "runtime_status": "unknown",
            "runtime_gated": False,
            "policy": None,
        },
        "explainability_revisions": [],
        "lineage_attachments": [],
        "adjudication_history": [],
        "authority_history": [],
        "playtest": {},
        "lineage_hash": None,
        "events_applied": 0,
        "last_event_seq": 0,
        "last_event_hash": None,
    }


def _set_epoch(state: Dict[str, Any], epoch: str) -> None:
    state["replay_epoch"] = epoch
    meta = EPOCH_METADATA.get(epoch) or {}
    state["epoch_metadata"] = {
        "epoch": epoch,
        "governance_contract": meta.get("governance_contract", GOVERNANCE_CONTRACT),
        "reducer_version": meta.get("reducer_version", REDUCER_VERSION),
    }


def _apply_initial_grading(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    state["grade_level"] = payload.get("grade_level")
    state["total_score"] = payload.get("total_score")
    state["max_score"] = payload.get("max_score")
    state["percentage"] = payload.get("percentage")
    state["governance"]["active_authority"] = event.get("authority") or "AI_GRADING"
    for cr in payload.get("criteria_results") or []:
        if isinstance(cr, dict):
            _apply_criterion_decision(
                state,
                {
                    "payload": {
                        "criteria_level": cr.get("criteria_level"),
                        "achieved": cr.get("achieved"),
                        "score": cr.get("score"),
                        "status": "ACHIEVED" if cr.get("achieved") else "NOT_ACHIEVED",
                        "achievement_authority": cr.get("achievement_authority"),
                    },
                    "authority": "AI_GRADING",
                },
            )
    _set_epoch(state, EPOCH_POST_INITIAL_GRADING)


def _apply_runtime_gated(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    gov = state["governance"]
    gov["runtime_gated"] = True
    gov["runtime_status"] = "gated"
    gov["policy"] = payload.get("reason") or "GOVERNANCE_FREEZE_v1_active"
    gov["active_authority"] = "SYSTEM_GOVERNED"
    _set_epoch(state, EPOCH_RUNTIME_GATED)


def _apply_governance_state(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    gov = state["governance"]
    gov["runtime_status"] = payload.get("status") or gov.get("runtime_status")
    auth = event.get("authority")
    if auth:
        gov["active_authority"] = auth


def _apply_criterion_decision(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    key = _norm_criterion_key(str(payload.get("criteria_level") or ""))
    if not key:
        return
    achieved = payload.get("status") == "ACHIEVED"
    if "achieved" in payload:
        achieved = bool(payload.get("achieved"))
    state["criteria"][key] = {
        "criteria_level": payload.get("criteria_level") or key,
        "status": payload.get("status") or ("ACHIEVED" if achieved else "NOT_ACHIEVED"),
        "achieved": achieved,
        "score": payload.get("score"),
        "achievement_authority": payload.get("achievement_authority")
        if "achievement_authority" in payload
        else event.get("authority"),
    }


def _apply_explainability_revision(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    state["explainability_revisions"].append(
        {
            "version": payload.get("version"),
            "explainability_schema": payload.get("explainability_schema"),
            "policy_version": payload.get("policy_version"),
            "trigger": payload.get("trigger"),
            "non_destructive": payload.get("non_destructive"),
            "snapshot_hash": event.get("snapshot_hash"),
            "event_seq": event.get("event_seq"),
        }
    )
    if state["replay_epoch"] not in (EPOCH_POST_PLAYTEST_L5, EPOCH_POST_ADJUDICATION):
        _set_epoch(state, EPOCH_POST_EXPLAINABILITY)


def _apply_evidence_lineage(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    attachment = {
        "lineage_hash": payload.get("lineage_hash") or event.get("snapshot_hash"),
        "criteria": payload.get("criteria") or [],
        "event_seq": event.get("event_seq"),
    }
    state["lineage_attachments"].append(attachment)
    if attachment.get("lineage_hash"):
        state["lineage_hash"] = attachment["lineage_hash"]


def _apply_human_playtest(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    state["playtest"] = {
        "pass": payload.get("pass"),
        "pass_id": payload.get("pass_id"),
        "verified": payload.get("verified"),
        "completed": True,
    }
    state["governance"]["active_authority"] = "HUMAN_PLAYTEST_L5"
    _set_epoch(state, EPOCH_POST_PLAYTEST_L5)


def _apply_runtime_adjudication(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    entry = {
        "changes": payload.get("changes") or [],
        "db_sync": payload.get("db_sync"),
        "event_seq": event.get("event_seq"),
    }
    state["adjudication_history"].append(entry)
    _set_epoch(state, EPOCH_POST_ADJUDICATION)


def _apply_authority_transition(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    payload = event.get("payload") or {}
    key = _norm_criterion_key(str(payload.get("criteria_level") or ""))
    from_auth = payload.get("authority_from") or state["governance"].get("active_authority")
    to_auth = payload.get("authority_to") or event.get("authority") or payload.get(
        "achievement_authority"
    )
    transition = {
        "from_authority": from_auth,
        "to_authority": to_auth,
        "criteria_level": payload.get("criteria_level"),
        "achieved_before": payload.get("achieved_before"),
        "achieved_after": payload.get("achieved_after"),
        "event_seq": event.get("event_seq"),
    }
    state["authority_history"].append(transition)
    if to_auth:
        state["governance"]["active_authority"] = str(to_auth)
    if key:
        after = payload.get("achieved_after")
        state["criteria"][key] = {
            "criteria_level": payload.get("criteria_level") or key,
            "status": "ACHIEVED" if after else "NOT_ACHIEVED",
            "achieved": bool(after),
            "achievement_authority": to_auth,
        }


_EVENT_REDUCERS = {
    "initial_grading": _apply_initial_grading,
    "runtime_gated": _apply_runtime_gated,
    "governance_state": _apply_governance_state,
    "criterion_decision": _apply_criterion_decision,
    "explainability_revision": _apply_explainability_revision,
    "evidence_lineage_attached": _apply_evidence_lineage,
    "human_playtest_completed": _apply_human_playtest,
    "runtime_adjudication_applied": _apply_runtime_adjudication,
    "authority_transition": _apply_authority_transition,
}


def apply_event(state: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    """Pure reducer — returns new state (copy-on-write)."""
    if not isinstance(event, dict):
        return state

    new_state = copy.deepcopy(state)
    et = str(event.get("event_type") or "")
    reducer = _EVENT_REDUCERS.get(et)
    if reducer:
        reducer(new_state, event)

    new_state["events_applied"] = int(new_state.get("events_applied") or 0) + 1
    if event.get("event_seq") is not None:
        new_state["last_event_seq"] = int(event["event_seq"])
    new_state["last_event_hash"] = event.get("event_hash")
    return new_state


def replay_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fold events in deterministic order (event_seq, then timestamp)."""
    ordered = sorted(
        [e for e in events if isinstance(e, dict)],
        key=lambda e: (
            int(e.get("event_seq") or 0),
            str(e.get("timestamp") or ""),
        ),
    )
    state = initial_replay_state()
    for ev in ordered:
        state = apply_event(state, ev)
    return state


def _criteria_results_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _key, crit in sorted((state.get("criteria") or {}).items()):
        if not isinstance(crit, dict):
            continue
        rows.append(
            {
                "criteria_level": crit.get("criteria_level"),
                "achieved": crit.get("achieved"),
                "score": crit.get("score") if crit.get("score") is not None else (100 if crit.get("achieved") else 0),
                "achievement_authority": crit.get("achievement_authority"),
            }
        )
    return rows


def compute_replayed_protected_digest(state: Dict[str, Any]) -> str:
    """Fingerprint of replayed academic decision fields — mirrors protected_digest."""
    from app.explainability_migration import compute_academic_decision_digest

    return compute_academic_decision_digest(
        grade_level=state.get("grade_level"),
        total_score=state.get("total_score"),
        max_score=state.get("max_score"),
        percentage=state.get("percentage"),
        criteria_results=_criteria_results_from_state(state),
        decision_provenance=state.get("decision_provenance"),
        evidence_fingerprint=state.get("evidence_fingerprint"),
    )


def compute_replayed_state_hash(state: Dict[str, Any]) -> str:
    """Canonical hash of replayed governance + decision state."""
    canonical = {
        "replay_epoch": state.get("replay_epoch"),
        "grade_level": state.get("grade_level"),
        "criteria": state.get("criteria"),
        "governance": state.get("governance"),
        "lineage_hash": state.get("lineage_hash"),
        "explainability_revision_count": len(state.get("explainability_revisions") or []),
        "adjudication_count": len(state.get("adjudication_history") or []),
        "protected_digest": compute_replayed_protected_digest(state),
    }
    return hashlib.sha256(_stable_json(canonical).encode("utf-8")).hexdigest()


def _persisted_snapshot_hash(snapshot: Dict[str, Any]) -> Optional[str]:
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


def _semantic_verification(
    state: Dict[str, Any],
    snap: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare replayed semantics vs persisted snapshot (not hash-only)."""
    inv = snap.get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    layer = snap.get("explainability_layer") or {}
    persisted_lineage = (
        layer.get("evidence_lineage") or snap.get("evidence_lineage") or inv.get("evidence_lineage") or {}
    )
    persisted_lineage_hash = persisted_lineage.get("lineage_hash")
    replayed_lineage_hash = state.get("lineage_hash")
    lineage_match = (
        persisted_lineage_hash == replayed_lineage_hash
        if persisted_lineage_hash
        else replayed_lineage_hash is None
    )

    gov = state.get("governance") or {}
    runtime_gated_persisted = obs.get("status") == "gated"
    governance_match = gov.get("runtime_gated") == runtime_gated_persisted
    if obs.get("status") == "completed":
        governance_match = gov.get("runtime_status") == "completed"

    persisted_auth: Dict[str, Any] = {}
    for cr in snap.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        key = _norm_criterion_key(str(cr.get("criteria_level") or ""))
        if key:
            persisted_auth[key] = cr.get("achievement_authority")

    authority_match = True
    for key, crit in (state.get("criteria") or {}).items():
        if key not in persisted_auth:
            continue
        pa = persisted_auth.get(key)
        ra = crit.get("achievement_authority")
        if pa is not None and ra is not None and pa != ra:
            authority_match = False
            break
        if pa is None and ra not in (None, "AI_GRADING"):
            authority_match = False
            break

    semantic_replay_verified = lineage_match and governance_match and authority_match

    return {
        "semantic_replay_verified": semantic_replay_verified,
        "authority_match": authority_match,
        "lineage_match": lineage_match,
        "governance_match": governance_match,
        "epoch_metadata": state.get("epoch_metadata"),
    }


def verify_deterministic_replay(
    events: List[Dict[str, Any]],
    persisted_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Replay events and verify against persisted snapshot anchors.
    Pure — snapshot only used for comparison, not during fold.
    """
    state = replay_events(events)
    reconstructed_state_hash = compute_replayed_state_hash(state)
    reconstructed_protected_digest = compute_replayed_protected_digest(state)

    snap = persisted_snapshot or {}
    persisted_snapshot_hash = _persisted_snapshot_hash(snap)
    persisted_protected_digest: Optional[str] = None
    protected_match = False
    snapshot_hash_match = False

    if snap:
        try:
            from app.explainability_migration import academic_decision_digest_from_snapshot

            persisted_protected_digest = academic_decision_digest_from_snapshot(snap)
            protected_match = persisted_protected_digest == reconstructed_protected_digest
        except Exception:
            try:
                from app.explainability_migration import _protected_digest

                persisted_protected_digest = _protected_digest(snap)
                protected_match = persisted_protected_digest == reconstructed_protected_digest
            except Exception:
                pass

        if persisted_snapshot_hash and state.get("lineage_hash"):
            snapshot_hash_match = persisted_snapshot_hash == state.get("lineage_hash")
        elif persisted_snapshot_hash:
            rev = snap.get("explainability_revision") or {}
            snapshot_hash_match = persisted_snapshot_hash == rev.get("snapshot_hash")

    replay_verified = protected_match or (
        bool(events) and not snap
    )
    semantic = _semantic_verification(state, snap) if snap else {
        "semantic_replay_verified": bool(events),
        "authority_match": True,
        "lineage_match": True,
        "governance_match": True,
        "epoch_metadata": state.get("epoch_metadata"),
    }

    return {
        "replay_engine_version": REPLAY_ENGINE_VERSION,
        "governance_contract": GOVERNANCE_CONTRACT,
        "reducer_version": REDUCER_VERSION,
        "replay_verified": replay_verified,
        "semantic_replay_verified": semantic.get("semantic_replay_verified"),
        "authority_match": semantic.get("authority_match"),
        "lineage_match": semantic.get("lineage_match"),
        "governance_match": semantic.get("governance_match"),
        "epoch_metadata": semantic.get("epoch_metadata"),
        "reconstructed_state_hash": reconstructed_state_hash,
        "reconstructed_protected_digest": reconstructed_protected_digest,
        "persisted_snapshot_hash": persisted_snapshot_hash,
        "persisted_protected_digest": persisted_protected_digest,
        "protected_digest_match": protected_match,
        "snapshot_hash_match": snapshot_hash_match,
        "match": protected_match,
        "replay_epoch": state.get("replay_epoch"),
        "events_replayed": len(events),
        "state_summary": {
            "grade_level": state.get("grade_level"),
            "replay_epoch": state.get("replay_epoch"),
            "criteria_keys": sorted((state.get("criteria") or {}).keys()),
            "governance": state.get("governance"),
            "explainability_revisions": len(state.get("explainability_revisions") or []),
            "lineage_attachments": len(state.get("lineage_attachments") or []),
            "adjudication_history": len(state.get("adjudication_history") or []),
            "playtest_completed": bool((state.get("playtest") or {}).get("completed")),
        },
        "replayed_state": state,
    }


def build_deterministic_replay(
    grading_snapshot: Optional[Dict[str, Any]] = None,
    *,
    events: Optional[List[Dict[str, Any]]] = None,
    graded_at: Optional[str] = None,
    include_full_state: bool = False,
) -> Dict[str, Any]:
    """Entry point — events from log or synthetic reconstruction, then verify."""
    from app.academic_event_replay import build_academic_timeline_replay

    snap = grading_snapshot or {}
    if events is None:
        timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
        events = timeline.get("events") or []

    verification = verify_deterministic_replay(events, snap)
    out: Dict[str, Any] = {
        "mode": "deterministic_replay_engine",
        "verification": {
            k: v
            for k, v in verification.items()
            if k != "replayed_state" or include_full_state
        },
        "note_ar": (
            "Deterministic Replay — academic_state = fold(events). "
            "لا DB lookups أثناء replay."
        ),
    }
    if include_full_state:
        out["replayed_state"] = verification.get("replayed_state")
    return out
