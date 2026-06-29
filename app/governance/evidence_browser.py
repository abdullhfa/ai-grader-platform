"""Evidence graph browser — structured evidence for examiner review."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.governance.replay_viewer import ReplayInspectionBundle


def browse_evidence(bundle: ReplayInspectionBundle) -> Dict[str, Any]:
    """Return evidence nodes grouped by criterion — replay-first, not LLM summary."""
    graphs = bundle.evidence
    if not graphs:
        graphs = (bundle.ai_reasoning or {}).get("criterion_graphs") or []

    nodes: List[Dict[str, Any]] = []
    by_criterion: Dict[str, List[Dict[str, Any]]] = {}

    if isinstance(graphs, list):
        for graph in graphs:
            if not isinstance(graph, dict):
                continue
            cid = str(graph.get("criterion_id") or graph.get("criterion") or "unknown")
            for node in graph.get("nodes") or graph.get("evidence_nodes") or []:
                if not isinstance(node, dict):
                    continue
                entry = {
                    "criterion_id": cid,
                    "node_id": node.get("node_id") or node.get("id"),
                    "source": node.get("source"),
                    "claim": node.get("claim"),
                    "confidence": node.get("confidence"),
                    "verified": node.get("verified", True),
                    "artifact_ref": node.get("artifact_ref"),
                }
                nodes.append(entry)
                by_criterion.setdefault(cid, []).append(entry)

    return {
        "total_nodes": len(nodes),
        "by_criterion": by_criterion,
        "nodes": nodes,
        "screenshot_refs": bundle.screenshots,
        "hallucination_flags": bundle.hallucination_flags,
        "contradictions": bundle.contradictions,
    }
