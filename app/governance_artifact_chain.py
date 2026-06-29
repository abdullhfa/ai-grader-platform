"""
Governance Artifact Chain — full institutional governance provenance.

Links: drift → supersession → mitigation → stability → epoch → RFC → signed verdict

Auto layers support institutional judgement — they do not replace it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.canonical_stability_trajectory import (
    ACTIVE_FREEZE_EPOCH,
    FREEZE_EPOCHS,
    load_stability_history,
    detect_stability_transitions,
)
from app.grading_snapshot_governance import (
    TAXONOMY_DRIFT_MODE,
    parse_snapshot_governance,
)

CHAIN_VERSION = "governance_artifact_chain_v1"

NODE_TYPES = (
    "epoch",
    "drift_incident",
    "supersession",
    "mitigation",
    "stability_transition",
    "rfc_review",
    "signed_verdict",
)


def _node(
    node_id: str,
    node_type: str,
    label: str,
    *,
    timestamp: str = "",
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "timestamp": timestamp,
        "data": data or {},
    }


def _edge(source: str, target: str, relation: str, *, note_ar: str = "") -> Dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "note_ar": note_ar,
    }


def _collect_supersession_nodes(db: Any, assignment_id: Optional[int]) -> Tuple[List, List]:
    from app.models import Submission, SubmissionStatus

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    q = db.query(Submission).filter(Submission.status == SubmissionStatus.COMPLETED)
    if assignment_id is not None:
        q = q.filter(Submission.assignment_id == assignment_id)
    for sub in q.order_by(Submission.id.asc()).all():
        if not sub.grading_snapshot_json:
            continue
        try:
            snap = json.loads(str(sub.grading_snapshot_json))
        except Exception:
            continue
        gov = parse_snapshot_governance(snap)
        if gov.get("institutional_status") != "superseded":
            continue
        sup = gov.get("supersession") or {}
        nid = f"sup_{sub.id}"
        nodes.append(
            _node(
                nid,
                "supersession",
                f"supersession: {sub.student_name}",
                timestamp=str(snap.get("graded_at") or ""),
                data={
                    "submission_id": sub.id,
                    "batch_id": sub.batch_id,
                    "student_name": sub.student_name,
                    "supersession": sup,
                    "failure_mode": TAXONOMY_DRIFT_MODE,
                },
            )
        )
        canon_id = sup.get("canonical_submission_id")
        if canon_id:
            edges.append(
                _edge(
                    nid,
                    f"sup_canonical_{canon_id}",
                    "superseded_by_canonical_snapshot",
                    note_ar="bounded historical variance — non-authoritative",
                )
            )
            nodes.append(
                _node(
                    f"sup_canonical_{canon_id}",
                    "drift_incident",
                    f"canonical reference #{canon_id}",
                    data={"submission_id": canon_id, "role": "canonical_authority"},
                )
            )
        for inc in snap.get("governance_incidents") or []:
            if inc.get("failure_mode_id") == TAXONOMY_DRIFT_MODE:
                did = f"drift_{sub.id}"
                if not any(n["id"] == did for n in nodes):
                    nodes.append(
                        _node(
                            did,
                            "drift_incident",
                            f"GFM_CANONICAL_DRIFT: {sub.student_name}",
                            data=inc,
                        )
                    )
                edges.append(
                    _edge(did, nid, "triggered_supersession", note_ar=inc.get("reason_ar", ""))
                )
    return nodes, edges


def build_governance_artifact_chain(
    db: Any,
    *,
    epoch_id: str = ACTIVE_FREEZE_EPOCH,
    assignment_id: Optional[int] = None,
    anchor_artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Assemble provenance chain for an epoch (or anchor on one signed artifact).
    """
    from app.governance_epoch_mitigation_ledger import load_ledger_entries, seed_epoch_ledger_if_empty
    from app.governance_epoch_narrative import build_epoch_review_rfc_package
    from app.governance_epoch_workshop import load_epoch_workshop_reviews
    from app.institutional_artifact import list_artifacts, load_artifact, verify_artifact_integrity

    seed_epoch_ledger_if_empty(epoch_id)
    epoch_meta = FREEZE_EPOCHS.get(epoch_id, {})

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    epoch_node_id = f"epoch_{epoch_id}"
    nodes.append(
        _node(
            epoch_node_id,
            "epoch",
            f"{epoch_id} · {epoch_meta.get('freeze_id', '')}",
            timestamp=str(epoch_meta.get("since") or ""),
            data={
                "epoch_id": epoch_id,
                "freeze_id": epoch_meta.get("freeze_id"),
                "label_ar": epoch_meta.get("label_ar"),
                "status": epoch_meta.get("status"),
            },
        )
    )

    # ── Mitigation ledger ──
    for entry in load_ledger_entries(epoch_id=epoch_id):
        eid = entry.get("entry_id") or f"led_{len(nodes)}"
        nodes.append(
            _node(
                eid,
                "mitigation",
                f"{entry.get('issue')} → {entry.get('mitigation', '')[:40]}…",
                timestamp=entry.get("recorded_at", ""),
                data=entry,
            )
        )
        edges.append(
            _edge(
                epoch_node_id,
                eid,
                "epoch_contains_mitigation",
                note_ar=f"result: {entry.get('result_status')}",
            )
        )
        for ref in entry.get("artifact_refs") or []:
            edges.append(_edge(eid, ref, "mitigation_referenced_by_artifact"))

    # ── Supersession + drift from submissions ──
    sup_nodes, sup_edges = _collect_supersession_nodes(db, assignment_id)
    nodes.extend(sup_nodes)
    edges.extend(sup_edges)
    for n in sup_nodes:
        if n["type"] in ("supersession", "drift_incident"):
            edges.append(
                _edge(
                    epoch_node_id,
                    n["id"],
                    "epoch_observed_drift",
                    note_ar="identical evidence → divergent outcome",
                )
            )
    for led in load_ledger_entries(epoch_id=epoch_id):
        if "supersession" in str(led.get("issue", "")).lower():
            for n in sup_nodes:
                if n["type"] == "supersession":
                    edges.append(
                        _edge(
                            led.get("entry_id", ""),
                            n["id"],
                            "mitigation_addressed",
                            note_ar=led.get("result", ""),
                        )
                    )

    # ── Stability transitions ──
    history = load_stability_history(assignment_id=assignment_id, freeze_epoch=epoch_id)
    for i in range(1, len(history)):
        for ev in detect_stability_transitions(history[i - 1], history[i]):
            tid = f"trans_{i}_{ev.get('event', 'ev')}"
            nodes.append(
                _node(
                    tid,
                    "stability_transition",
                    ev.get("event", "transition"),
                    timestamp=history[i].get("recorded_at", ""),
                    data=ev,
                )
            )
            edges.append(
                _edge(epoch_node_id, tid, "stability_signal", note_ar=ev.get("meaning_ar", ""))
            )

    # ── RFC review snapshot (advisory — not signed) ──
    target_epoch = "epoch_2" if epoch_id == "epoch_1" else epoch_id
    try:
        rfc = build_epoch_review_rfc_package(
            db,
            target_epoch_id=target_epoch,
            current_epoch_id=epoch_id,
            assignment_id=assignment_id,
        )
        rfc_id = f"rfc_{epoch_id}_to_{target_epoch}"
        nodes.append(
            _node(
                rfc_id,
                "rfc_review",
                f"RFC review → {target_epoch}",
                timestamp=rfc.get("generated_at", ""),
                data={
                    "rfc_transition_ready": rfc.get("rfc_transition_ready"),
                    "rfc_summary_ar": rfc.get("rfc_summary_ar"),
                    "unresolved_gfms": rfc.get("unresolved_gfms"),
                    "advisory_only": True,
                },
            )
        )
        edges.append(
            _edge(
                epoch_node_id,
                rfc_id,
                "epoch_rfc_package",
                note_ar="auto-generated advisory — facilitator signs separately",
            )
        )
        for led in load_ledger_entries(epoch_id=epoch_id):
            edges.append(
                _edge(led.get("entry_id", ""), rfc_id, "mitigation_informs_rfc")
            )
    except Exception:
        pass

    # ── Signed institutional artifacts (verdict) ──
    rfc_node_id = next((n["id"] for n in nodes if n["type"] == "rfc_review"), None)

    if anchor_artifact_id:
        art = load_artifact(anchor_artifact_id)
        artifact_ids = [anchor_artifact_id] if art else []
    else:
        artifact_ids = [a.get("artifact_id") for a in list_artifacts(freeze_epoch_id=epoch_id) if a.get("artifact_id")]

    for aid in artifact_ids:
        full = load_artifact(aid)
        if not full:
            continue
        nodes.append(
            _node(
                aid,
                "signed_verdict",
                f"signed: {full.get('signatory', {}).get('name', aid)}",
                timestamp=full.get("signed_at", ""),
                data={
                    "artifact_kind": full.get("artifact_kind"),
                    "content_hash": full.get("content_hash"),
                    "signatory": full.get("signatory"),
                    "transition_verdict": (full.get("artifact_body") or {}).get(
                        "transition_verdict"
                    ),
                    "integrity": verify_artifact_integrity(full),
                },
            )
        )
        edges.append(
            _edge(
                epoch_node_id,
                aid,
                "epoch_signed_verdict",
                note_ar="signed institutional artifact — legitimacy anchor",
            )
        )
        if rfc_node_id:
            edges.append(
                _edge(
                    rfc_node_id,
                    aid,
                    "rfc_informed_by_verdict",
                    note_ar="workshop may accept/reject RFC readiness",
                )
            )
        for pref in full.get("provenance_refs") or []:
            edges.append(_edge(pref, aid, "provenance_reference"))
        body = full.get("artifact_body") or {}
        for qv in body.get("question_verdicts") or []:
            if qv.get("verdict") == "no":
                edges.append(
                    _edge(
                        aid,
                        epoch_node_id,
                        "verdict_blocks_transition",
                        note_ar=f"blocker: {qv.get('id')}",
                    )
                )

    # ── Workshop review logs (unsigned drafts) ──
    for wr in load_epoch_workshop_reviews(current_epoch_id=epoch_id):
        if wr.get("signed_institutional_artifact"):
            continue
        wid = f"workshop_draft_{wr.get('logged_at', len(nodes))}"
        nodes.append(
            _node(wid, "rfc_review", "workshop draft (unsigned)", timestamp=wr.get("logged_at", ""), data={})
        )

    # Timeline
    timeline = sorted(
        [n for n in nodes if n.get("timestamp")],
        key=lambda x: x.get("timestamp") or "",
    )

    # Provenance answers
    signed = [n for n in nodes if n["type"] == "signed_verdict"]
    drifts = [n for n in nodes if n["type"] in ("drift_incident", "supersession")]
    mitigations = [n for n in nodes if n["type"] == "mitigation"]

    who_approved = [
        {
            "name": (n.get("data") or {}).get("signatory", {}).get("name"),
            "role": (n.get("data") or {}).get("signatory", {}).get("role"),
            "signed_at": n.get("timestamp"),
            "artifact_id": n.get("id"),
            "verdict": (n.get("data") or {}).get("transition_verdict"),
        }
        for n in signed
    ]

    provenance_answers = {
        "why_freeze_may_evolve_ar": (
            "drift incidents + stability transitions + mitigation outcomes "
            "داخل epoch — RFC advisory يقرأها؛ facilitator يوقّع القرار."
        ),
        "who_approved": who_approved,
        "what_drift_existed": [
            {"id": n["id"], "label": n["label"], "type": n["type"]} for n in drifts
        ],
        "what_mitigation_preceded": [
            {
                "entry_id": n["id"],
                "issue": (n.get("data") or {}).get("issue"),
                "mitigation": (n.get("data") or {}).get("mitigation"),
                "result_status": (n.get("data") or {}).get("result_status"),
            }
            for n in mitigations
        ],
    }

    chain_sequence = [
        "drift_incident",
        "supersession",
        "mitigation",
        "stability_transition",
        "epoch",
        "rfc_review",
        "signed_verdict",
    ]

    return {
        "report_type": "governance_artifact_chain",
        "chain_version": CHAIN_VERSION,
        "epoch_id": epoch_id,
        "freeze_id": epoch_meta.get("freeze_id"),
        "assignment_id": assignment_id,
        "anchor_artifact_id": anchor_artifact_id,
        "purpose_ar": (
            "institutional governance provenance — "
            "artifact → supersession → epoch → RFC → mitigation → signed verdict"
        ),
        "design_principle_ar": (
            "auto signals · metrics · replay · stability layers "
            "**support** institutional judgement — ولا تستبدله."
        ),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "timeline": timeline,
        "chain_sequence": chain_sequence,
        "provenance_answers": provenance_answers,
        "institutional_legitimacy": {
            "automated": False,
            "auto_layers_support_judgement": True,
            "signed_artifact_required_for_transition": True,
            "note_ar": (
                "legitimacy = facilitator-signed artifact + mitigation lineage + "
                "bounded supersession — ليس metric threshold فقط."
            ),
        },
    }
