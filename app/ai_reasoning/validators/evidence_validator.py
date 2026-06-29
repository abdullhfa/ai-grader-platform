"""Validate evidence graph completeness."""
from __future__ import annotations

from typing import Any, Dict, List

from app.ai_reasoning.evidence_graph import CriterionEvidenceGraph


def validate_evidence_graphs(graphs: List[CriterionEvidenceGraph]) -> Dict[str, Any]:
    issues: List[str] = []
    if not graphs:
        issues.append("no_criterion_graphs")
    for graph in graphs:
        if not graph.evidence_nodes:
            issues.append(f"empty_nodes:{graph.criterion}")
        if graph.confidence < 0.35:
            issues.append(f"low_confidence:{graph.criterion}")
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "graph_count": len(graphs),
    }
