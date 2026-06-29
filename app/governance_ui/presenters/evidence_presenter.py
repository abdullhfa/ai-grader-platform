"""Evidence graph presenter — criterion → nodes → confidence."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _node_status(node: Dict[str, Any]) -> str:
    if node.get("contradicts"):
        return "contradicting"
    verified = node.get("verified", True)
    conf = float(node.get("confidence") or 0)
    if not verified or conf < 0.4:
        return "weak"
    if conf >= 0.75:
        return "supporting"
    return "partial"


def present_evidence_graph(
    bundle,
    browser: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    browser = browser or {}
    by_criterion = browser.get("by_criterion") or {}

    if not by_criterion:
        graphs = bundle.evidence
        if not graphs:
            graphs = (bundle.ai_reasoning or {}).get("criterion_graphs") or []
        if isinstance(graphs, list):
            for graph in graphs:
                if not isinstance(graph, dict):
                    continue
                cid = str(graph.get("criterion_id") or graph.get("criterion") or "unknown")
                nodes = []
                for node in graph.get("nodes") or graph.get("evidence_nodes") or []:
                    if isinstance(node, dict):
                        nodes.append({**node, "status": _node_status(node)})
                by_criterion[cid] = nodes

    criteria: List[Dict[str, Any]] = []
    total = 0
    for cid, nodes in by_criterion.items():
        enriched = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            status = n.get("status") or _node_status(n)
            enriched.append({
                "node_id": n.get("node_id") or n.get("id"),
                "claim": n.get("claim"),
                "source": n.get("source"),
                "confidence": n.get("confidence"),
                "confidence_pct": int(float(n.get("confidence") or 0) * 100),
                "status": status,
                "artifact_ref": n.get("artifact_ref"),
                "verified": n.get("verified", True),
            })
        total += len(enriched)
        avg_conf = (
            sum(float(x.get("confidence") or 0) for x in enriched) / len(enriched)
            if enriched
            else 0
        )
        criteria.append({
            "criterion_id": cid,
            "nodes": enriched,
            "node_count": len(enriched),
            "avg_confidence": round(avg_conf, 3),
        })

    return {
        "total_nodes": total,
        "criteria": criteria,
        "hallucination_flags": browser.get("hallucination_flags") or bundle.hallucination_flags,
        "contradictions": browser.get("contradictions") or bundle.contradictions,
    }
