"""Gameplay agent — reasons over gameplay_analysis only."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.ai_reasoning.evidence_graph import CriterionEvidenceGraph
from app.ai_reasoning.reasoning_session import AgentOpinion


def run_gameplay_agent(
    gameplay_analysis: Optional[Dict[str, Any]],
    graphs: List[CriterionEvidenceGraph],
) -> AgentOpinion:
    gameplay = gameplay_analysis or {}
    detections = gameplay.get("detections") or []
    refs: List[str] = []
    concerns: List[str] = []

    motion = next((d for d in detections if d.get("detector") == "motion_detector"), None)
    freeze = next((d for d in detections if d.get("detector") == "freeze_detector"), None)
    win = next((d for d in detections if d.get("detector") == "win_detector"), None)

    if motion and motion.get("label") == "movement_detected":
        refs.append("det:motion_detector:movement_detected")
    if freeze and freeze.get("label") == "freeze_detected":
        concerns.append("freeze_detected_in_gameplay")
        refs.append("det:freeze_detector:freeze_detected")
    if win and win.get("label") == "win_detected":
        refs.append("det:win_detector:win_detected")

    graph_conf = graphs[0].confidence if graphs else 0.4
    if motion and not (freeze and freeze.get("label") == "freeze_detected"):
        return AgentOpinion(
            agent_id="gameplay_agent",
            verdict="support",
            confidence=min(0.92, graph_conf + 0.1),
            summary="Gameplay motion/progression signals present in temporal analysis.",
            evidence_refs=refs,
            concerns=concerns,
        )
    if freeze and freeze.get("label") == "freeze_detected":
        return AgentOpinion(
            agent_id="gameplay_agent",
            verdict="oppose",
            confidence=0.78,
            summary="Freeze detected — gameplay loop may be broken or static.",
            evidence_refs=refs,
            concerns=concerns,
        )
    return AgentOpinion(
        agent_id="gameplay_agent",
        verdict="uncertain",
        confidence=0.45,
        summary="Insufficient gameplay motion evidence.",
        evidence_refs=refs,
        concerns=concerns or ["no_clear_motion"],
    )
