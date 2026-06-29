"""Replay bundle presenter — investigation interface view model."""
from __future__ import annotations

from typing import Any, Dict, List

from app.governance.replay_viewer import ReplayInspectionBundle
from app.governance_ui.presenters.evidence_presenter import present_evidence_graph
from app.governance_ui.presenters.timeline_presenter import present_timeline


def _section(title: str, key: str, payload: Any, *, available: bool) -> Dict[str, Any]:
    return {"title": title, "key": key, "available": available, "payload": payload}


def present_replay_investigation(
    review_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Build replay-first investigation model for templates."""
    bundle_dict = review_payload.get("replay_bundle") or {}
    bundle = ReplayInspectionBundle(
        submission_key=bundle_dict.get("submission_key", ""),
        session_id=bundle_dict.get("session_id", ""),
        snapshot_root=bundle_dict.get("snapshot_root", ""),
        deterministic_hash=bundle_dict.get("deterministic_hash"),
        runtime=bundle_dict.get("runtime") or {},
        timeline=bundle_dict.get("timeline") or {},
        evidence=bundle_dict.get("evidence"),
        ai_reasoning=bundle_dict.get("ai_reasoning") or {},
        grading_summary=bundle_dict.get("grading_summary") or {},
        screenshots=bundle_dict.get("screenshots") or [],
        contradictions=bundle_dict.get("contradictions") or [],
        confidence_scores=bundle_dict.get("confidence_scores") or {},
        hallucination_flags=bundle_dict.get("hallucination_flags") or [],
        bundle_complete=bool(bundle_dict.get("bundle_complete")),
        missing_sections=bundle_dict.get("missing_sections") or [],
    )

    timeline_vm = present_timeline(bundle)
    evidence_vm = present_evidence_graph(bundle, review_payload.get("evidence_browser"))
    final = (bundle.ai_reasoning or {}).get("final_decision") or {}

    sections: List[Dict[str, Any]] = [
        _section("Runtime", "runtime", bundle.runtime, available=bool(bundle.runtime)),
        _section("Timeline", "timeline", timeline_vm, available=timeline_vm.get("event_count", 0) > 0),
        _section("Evidence", "evidence", evidence_vm, available=evidence_vm.get("total_nodes", 0) > 0),
        _section(
            "Screenshots",
            "screenshots",
            {"items": _screenshot_items(bundle.screenshots)},
            available=bool(bundle.screenshots),
        ),
        _section("Reasoning", "reasoning", {
            "agent_opinions": (bundle.ai_reasoning or {}).get("agent_opinions") or [],
            "criterion_mapping": (bundle.ai_reasoning or {}).get("criterion_mapping") or {},
        }, available=bool(bundle.ai_reasoning)),
        _section("Integrity", "integrity", {
            "hallucination_flags": bundle.hallucination_flags,
            "contradictions": bundle.contradictions,
            "guard": (bundle.ai_reasoning or {}).get("hallucination_guard") or {},
        }, available=bool(bundle.hallucination_flags or bundle.contradictions)),
        _section("Final Arbitration", "final", final, available=bool(final)),
    ]

    return {
        "submission_key": bundle.submission_key,
        "session_id": bundle.session_id,
        "session_ref": f"{bundle.submission_key}/{bundle.session_id}",
        "deterministic_hash": bundle.deterministic_hash,
        "review_mode": "replay_first",
        "sections": sections,
        "runtime": bundle.runtime,
        "timeline": timeline_vm,
        "evidence": evidence_vm,
        "screenshots": _screenshot_items(bundle.screenshots),
        "reasoning": {
            "agent_opinions": (bundle.ai_reasoning or {}).get("agent_opinions") or [],
            "criterion_mapping": (bundle.ai_reasoning or {}).get("criterion_mapping") or {},
        },
        "integrity": {
            "hallucination_flags": bundle.hallucination_flags,
            "contradictions": bundle.contradictions,
            "guard": (bundle.ai_reasoning or {}).get("hallucination_guard") or {},
        },
        "final_decision": final,
        "grading_summary": bundle.grading_summary,
        "policy_evaluation": review_payload.get("policy_evaluation") or {},
        "review_session": review_payload.get("review_session") or {},
        "examiner_guidance": review_payload.get("examiner_guidance") or {},
        "bundle_complete": bundle.bundle_complete,
        "missing_sections": bundle.missing_sections,
    }


def _screenshot_items(paths: List[str]) -> List[Dict[str, str]]:
    items = []
    for idx, raw in enumerate(paths):
        name = raw.replace("\\", "/").split("/")[-1]
        url = raw.replace("\\", "/")
        if not url.startswith("/") and not url.startswith("http"):
            url = "/" + url.lstrip("/")
        items.append({"index": idx, "name": name, "url": url})
    return items
