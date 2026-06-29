"""Academic agent — BTEC criteria mapping over evidence graphs."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.ai_reasoning.criterion_mapper import map_criteria_to_graphs
from app.ai_reasoning.evidence_graph import CriterionEvidenceGraph
from app.ai_reasoning.reasoning_session import AgentOpinion


def run_academic_agent(
    graphs: List[CriterionEvidenceGraph],
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
) -> AgentOpinion:
    mapping = map_criteria_to_graphs(graphs, grading_criteria or [])
    satisfied = [m for m in mapping if m.get("evidence_sufficient")]
    weak = [m for m in mapping if not m.get("evidence_sufficient")]

    refs = [f"graph:{m['criterion']}" for m in satisfied[:6]]
    concerns = [f"weak_evidence:{m['criterion']}" for m in weak[:6]]

    if len(satisfied) >= max(1, len(mapping) // 2) and satisfied:
        return AgentOpinion(
            agent_id="academic_agent",
            verdict="support",
            confidence=round(sum(m.get("confidence", 0) for m in satisfied) / len(satisfied), 3),
            summary=f"BTEC evidence sufficient for {len(satisfied)}/{len(mapping)} mapped criteria hints.",
            evidence_refs=refs,
            concerns=concerns,
        )
    return AgentOpinion(
        agent_id="academic_agent",
        verdict="uncertain",
        confidence=0.42,
        summary="BTEC operational evidence incomplete for mapped criteria.",
        evidence_refs=refs,
        concerns=concerns or ["insufficient_btec_evidence"],
    )
