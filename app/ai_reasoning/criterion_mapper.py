"""BTEC criteria ↔ evidence graph mapping."""
from __future__ import annotations

from typing import Any, Dict, List

from app.ai_reasoning.evidence_graph import CRITERION_EVIDENCE_REQUIREMENTS, CriterionEvidenceGraph


def map_criteria_to_graphs(
    graphs: List[CriterionEvidenceGraph],
    grading_criteria: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_criterion = {g.criterion: g for g in graphs}
    results: List[Dict[str, Any]] = []

    levels = []
    for cr in grading_criteria:
        if isinstance(cr, dict):
            lv = str(cr.get("criteria_level") or cr.get("level") or "")
            if lv:
                levels.append(lv)

    targets = set(by_criterion.keys()) | {lv.split(".")[-1] for lv in levels if lv}
    for criterion in sorted(targets):
        graph = by_criterion.get(criterion)
        req = CRITERION_EVIDENCE_REQUIREMENTS.get(criterion, {})
        required_any = req.get("required_any") or []

        supporting = graph.supporting_events if graph else []
        sufficient = bool(
            graph
            and (
                any(r in supporting for r in required_any)
                or (not required_any and graph.confidence >= 0.55)
            )
            and not graph.contradicting_events
        )

        results.append(
            {
                "criterion": criterion,
                "required_evidence": required_any,
                "supporting_events": supporting,
                "contradicting_events": graph.contradicting_events if graph else [],
                "confidence": graph.confidence if graph else 0.0,
                "evidence_sufficient": sufficient,
                "corroboration_strength": graph.corroboration_strength if graph else "weak",
            }
        )
    return results
