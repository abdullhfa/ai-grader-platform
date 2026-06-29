"""AI Evidence Reasoning orchestrator — evidence graph → agents → arbitration."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from app.ai_reasoning.agents.academic_agent import run_academic_agent
from app.ai_reasoning.agents.gameplay_agent import run_gameplay_agent
from app.ai_reasoning.agents.integrity_agent import run_integrity_agent
from app.ai_reasoning.agents.reflection_agent import run_reflection_agent
from app.ai_reasoning.agents.runtime_agent import run_runtime_agent
from app.ai_reasoning.arbitration import arbitrate_opinions
from app.ai_reasoning.criterion_mapper import map_criteria_to_graphs
from app.ai_reasoning.evidence_graph import build_evidence_graphs
from app.ai_reasoning.hallucination_guard import guard_reasoning_text
from app.ai_reasoning.reasoning_session import ReasoningSession
from app.ai_reasoning.snapshots.snapshot_builder import build_reasoning_snapshot
from app.ai_reasoning.validators.evidence_validator import validate_evidence_graphs
from app.ai_reasoning.validators.timeline_validator import validate_timeline

logger = logging.getLogger("ai_grader.ai_reasoning")


def _enabled() -> bool:
    return os.environ.get("AI_GRADER_EVIDENCE_REASONING", "1").lower() in ("1", "true", "yes", "on")


def async_reasoning_enabled() -> bool:
    return os.environ.get("AI_GRADER_ASYNC_REASONING", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def queue_evidence_reasoning(
    *,
    submission_key: str,
    grading_result: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Enqueue reasoning on ``reasoning_jobs`` — non-blocking when Celery is enabled."""
    from app.tasks.celery_app import is_celery_enabled
    from app.tasks.dispatch import dispatch_async_only
    from app.tasks.worker_tasks import evidence_reasoning_task

    if not _enabled():
        return {"status": "disabled"}
    if not is_celery_enabled():
        return {"status": "celery_disabled", "mode": "sync_fallback_required"}
    job = dispatch_async_only(
        evidence_reasoning_task,
        submission_key,
        grading_result,
        artifact_inventory,
        grading_criteria,
    )
    return {"status": "queued", "task_id": getattr(job, "id", None), "queue": "reasoning_jobs"}


def run_evidence_reasoning(
    *,
    submission_key: str,
    grading_result: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
    gameplay_analysis: Optional[Dict[str, Any]] = None,
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if not _enabled():
        return {"status": "disabled"}

    inventory = artifact_inventory or grading_result.get("artifact_inventory") or {}
    gameplay = (
        gameplay_analysis
        or inventory.get("gameplay_analysis")
        or (inventory.get("runtime_observation_report") or {}).get("gameplay_analysis")
        or grading_result.get("gameplay_analysis")
    )

    obs = inventory.get("runtime_observation_report") or {}
    session_id = obs.get("runtime_session_id")

    graphs = build_evidence_graphs(
        gameplay_analysis=gameplay,
        artifact_inventory=inventory,
        grading_criteria=grading_criteria or grading_result.get("criteria_results"),
    )

    opinions = [
        run_gameplay_agent(gameplay, graphs),
        run_runtime_agent(inventory, gameplay),
        run_academic_agent(graphs, grading_criteria or grading_result.get("criteria_results")),
        run_integrity_agent(inventory, grading_result),
    ]
    opinions.append(run_reflection_agent(opinions))

    graph_conf = max((g.confidence for g in graphs), default=0.4)
    final = arbitrate_opinions(opinions, graph_confidence=graph_conf)

    # Hallucination guard on AI feedback text (not on raw video)
    feedback_blob = " ".join(
        str(grading_result.get(k) or "")
        for k in ("overall_feedback", "summary", "student_text")
    )
    for cr in grading_result.get("criteria_results") or []:
        if isinstance(cr, dict):
            feedback_blob += " " + str(cr.get("feedback") or cr.get("reasoning") or "")

    guard = guard_reasoning_text(feedback_blob, graphs)

    session = ReasoningSession(
        submission_key=submission_key,
        session_id=session_id,
        criterion_graphs=graphs,
        agent_opinions=opinions,
        final_decisions={"overall": final},
        hallucination_flags=guard.get("flags") or [],
    )

    if guard.get("reasoning_rejected"):
        final.reasoning_rejected = True
        if final.decision == "supported":
            final.decision = "manual_review"
            final.requires_manual_review = True
            final.arbitration_notes.append("hallucination_guard_triggered")

    payload = session.to_dict()
    payload["status"] = "completed"
    payload["criterion_mapping"] = map_criteria_to_graphs(
        graphs, grading_criteria or grading_result.get("criteria_results") or []
    )
    payload["validation"] = {
        "evidence_graphs": validate_evidence_graphs(graphs),
        "timeline": validate_timeline(gameplay),
    }
    payload["hallucination_guard"] = guard
    payload["final_decision"] = final.to_dict()

    snapshot = build_reasoning_snapshot(
        submission_key=submission_key,
        session_id=session_id,
        grading_result={**grading_result, "gameplay_analysis": gameplay},
        reasoning_session=payload,
        artifact_inventory=inventory,
    )
    payload["replay_snapshot"] = snapshot
    return payload


def attach_evidence_reasoning_to_grading_result(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
    submission_key: Optional[str] = None,
) -> Dict[str, Any]:
    key = submission_key or str(grading_result.get("student_name") or "unknown")
    try:
        reasoning = run_evidence_reasoning(
            submission_key=key,
            grading_result=grading_result,
            artifact_inventory=artifact_inventory,
            grading_criteria=grading_criteria,
        )
        grading_result["ai_evidence_reasoning"] = reasoning
        grading_result["evidence_reasoning_version"] = reasoning.get("pipeline_version")

        final = reasoning.get("final_decision") or {}
        if final.get("requires_manual_review"):
            grading_result.setdefault("grading_coverage_notice", {})
            if isinstance(grading_result["grading_coverage_notice"], dict):
                grading_result["grading_coverage_notice"]["manual_review_required"] = True
                grading_result["grading_coverage_notice"]["reason"] = "ai_evidence_reasoning_arbitration"

        if final.get("reasoning_rejected"):
            grading_result.setdefault("ai_reliability", {})
            if isinstance(grading_result["ai_reliability"], dict):
                grading_result["ai_reliability"]["hallucination_guard_rejected"] = True

    except Exception:
        logger.exception("Evidence reasoning failed (non-fatal)")
        grading_result["ai_evidence_reasoning"] = {"status": "error"}
    return grading_result
