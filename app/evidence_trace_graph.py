"""
Evidence Trace Graph — artifact → hint → corroboration → authority → claim boundary.

Debugging, governance review, and verifier audit trail.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid


def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build_evidence_trace_graph(
    inventory: Dict[str, Any],
    *,
    temporal_consistency: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_index: Dict[str, str] = {}

    def add_node(nid: str, ntype: str, label: str, meta: Optional[Dict] = None) -> str:
        nodes.append({
            "id": nid,
            "type": ntype,
            "label": label,
            "meta": meta or {},
        })
        node_index[nid] = ntype
        return nid

    def link(src: str, dst: str, relation: str) -> None:
        edges.append({"from": src, "to": dst, "relation": relation})

    # ── Artifacts ──
    for doc in (inventory.get("documentation") or {}).get("files") or []:
        nid = add_node(_nid("art"), "artifact", f"doc:{doc.get('name')}", {"kind": "documentation"})
        node_index[f"doc:{doc.get('name')}"] = nid

    rt = inventory.get("runtime_artifacts") or {}
    for exe in rt.get("executable_files") or []:
        nid = add_node(_nid("art"), "artifact", f"exe:{exe.get('name')}", {"kind": "executable"})
        node_index[f"exe:{exe.get('name')}"] = nid

    gvi = inventory.get("gameplay_video_inference") or {}
    for vname in gvi.get("video_sources") or []:
        nid = add_node(_nid("art"), "artifact", f"video:{vname}", {"kind": "gameplay_video"})
        node_index[f"video:{vname}"] = nid

    for src in (inventory.get("source_code") or {}).get("files") or []:
        nid = add_node(_nid("art"), "artifact", f"code:{src.get('name')}", {"kind": "source_code"})
        node_index[f"code:{src.get('name')}"] = nid

    emb_count = (inventory.get("embedded_screenshots") or {}).get("count") or 0
    if emb_count:
        emb_nid = add_node(_nid("art"), "artifact", f"embedded_images:{emb_count}", {"kind": "embedded_screenshots"})

    # ── Hints (screenshot intel + video) ──
    hint_nodes: List[str] = []
    for item in (inventory.get("screenshot_intelligence") or {}).get("items") or []:
        evs = item.get("possible_evidence") or ["visual_hint"]
        label = f"shot_hint:{evs[0]}"
        hn = add_node(_nid("hint"), "hint", label, {
            "source": item.get("source"),
            "confidence": item.get("confidence"),
            "mode": "advisory",
        })
        hint_nodes.append(hn)
        if emb_count:
            link(emb_nid, hn, "yields")

    for hint in (gvi.get("video_analysis") or {}).get("runtime_hints") or []:
        ht = hint.get("hint_type") or "video_hint"
        hn = add_node(_nid("hint"), "hint", f"video_hint:{ht}", {
            "detail": hint.get("detail"),
            "confidence": hint.get("confidence"),
            "hint_authority": hint.get("hint_authority"),
        })
        hint_nodes.append(hn)
        for vname in (gvi.get("video_sources") or [])[:1]:
            vk = f"video:{vname}"
            if vk in node_index:
                # find artifact node id
                for n in nodes:
                    if n.get("label") == vk:
                        link(n["id"], hn, "yields")
                        break

        for corr in hint.get("corroborated_by") or []:
            ck = None
            for prefix in ("code:", "exe:"):
                if isinstance(corr, str) and not corr.startswith("screenshot"):
                    ck = f"{prefix}{corr}"
                    break
            for n in nodes:
                if corr in str(n.get("label", "")) or (ck and n.get("label") == ck):
                    cn = add_node(_nid("corr"), "corroboration", f"corroborates:{corr}", {})
                    link(hn, cn, "corroborated_by")
                    link(cn, n["id"], "supports")
                    break

    # ── Authority nodes ──
    rt_level = inventory.get("runtime_evidence_level") or {}
    auth_nid = add_node(_nid("auth"), "authority", f"runtime_L{rt_level.get('level', 0)}", {
        "label_ar": rt_level.get("label_ar"),
        "authority": rt_level.get("authority"),
    })
    ta = gvi.get("temporal_evidence_authority") or {}
    if ta.get("temporal_authority_level") is not None:
        temp_nid = add_node(_nid("auth"), "authority", f"temporal_L{ta.get('temporal_authority_level')}", {
            "label_ar": ta.get("label_ar"),
            "max_claim_authority": ta.get("max_claim_authority"),
        })
        for hn in hint_nodes:
            link(hn, temp_nid, "bounded_by")

    for hn in hint_nodes:
        link(hn, auth_nid, "bounded_by")

    mapping = inventory.get("authority_mapping") or {}
    claim_nid = add_node(_nid("claim"), "claim_boundary", "allowed_claims", {
        "allowed_en": mapping.get("aggregate_allowed_claims_en"),
        "forbidden_en": mapping.get("aggregate_forbidden_claims_en"),
    })
    link(auth_nid, claim_nid, "permits")

    # ── Contradiction nodes ──
    tc = temporal_consistency or inventory.get("temporal_consistency") or {}
    for sig in tc.get("temporal_consistency_signals") or []:
        cn = add_node(_nid("contra"), "contradiction", sig.get("code", "contradiction"), {
            "severity": sig.get("severity"),
            "message_ar": sig.get("message_ar"),
        })
        if ta.get("temporal_authority_level") is not None:
            for n in nodes:
                if n.get("type") == "authority" and str(n.get("label", "")).startswith("temporal"):
                    link(cn, n["id"], "downgrades")
                    break
        link(cn, claim_nid, "constrains")

    cross = inventory.get("cross_artifact_consistency") or {}
    for amb in cross.get("ambiguities") or []:
        cn = add_node(_nid("contra"), "contradiction", amb.get("code", "cross_ambiguity"), {
            "severity": amb.get("severity"),
        })
        link(cn, claim_nid, "constrains")

    return {
        "version": 1,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "trace_summary_ar": (
            f"{len([n for n in nodes if n['type']=='artifact'])} artifact(s) → "
            f"{len([n for n in nodes if n['type']=='hint'])} hint(s) → "
            f"authority → claim boundary"
        ),
    }


def format_trace_graph_summary(graph: Dict[str, Any]) -> str:
    if not graph.get("nodes"):
        return ""
    lines = [
        "═══════════════════════════════════════════════════════════",
        "[Evidence Trace Graph | artifact → hint → authority → claim]",
        "═══════════════════════════════════════════════════════════",
        f"• {graph.get('trace_summary_ar', '')}",
        f"• nodes={graph.get('node_count')} edges={graph.get('edge_count')}",
    ]
    contradictions = [n for n in graph.get("nodes") or [] if n.get("type") == "contradiction"]
    if contradictions:
        lines.append(f"• contradictions in graph: {len(contradictions)}")
    lines.append("═══════════════════════════════════════════════════════════\n")
    return "\n".join(lines)
