"""
Evidence Lineage — structured criterion decision graph (DAG).

Links observed evidence → governance gates → criterion decisions.
Machine-readable; shared nodes allow cross-criterion reuse (C.P5/C.P6).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from app.runtime_criterion_mapping import EXECUTION_CRITERIA, _short_level

EVIDENCE_LINEAGE_SCHEMA = "1.0"
CONFIDENCE_MODEL = "EVIDENCE_CONFIDENCE_v1"

# Normalized confidence weights — advisory, not autonomous scoring.
CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "human_playtest": 0.95,
    "runtime_observation": 0.45,
    "testing_evidence": 0.40,
    "documentation": 0.35,
    "screenshot_only": 0.25,
    "partial_code_extraction": 0.18,
    "exe_detected_only": 0.15,
    "governance_gate": 0.0,
}

EXECUTION_CRITERION_KEYS = ("C.P5", "C.P6")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _lineage_hash(graph: Dict[str, Any]) -> str:
    payload = {k: v for k, v in graph.items() if k != "lineage_hash"}
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _criterion_key(criteria_level: str) -> Optional[str]:
    lv = (criteria_level or "").strip().upper()
    if lv in EXECUTION_CRITERIA:
        return lv
    short = _short_level(lv)
    if short == "P5":
        return "C.P5"
    if short == "P6":
        return "C.P6"
    return None


def _resolve_criterion_row(
    criteria_results: List[Dict[str, Any]], key: str
) -> Optional[Dict[str, Any]]:
    for cr in criteria_results:
        if not isinstance(cr, dict):
            continue
        if _criterion_key(str(cr.get("criteria_level") or "")) == key:
            return cr
    return None


def _criterion_status(
    cr: Optional[Dict[str, Any]],
    *,
    inventory: Dict[str, Any],
    runtime_support: Optional[Dict[str, Any]],
    key: str,
) -> str:
    if not cr:
        return "NOT_ACHIEVED"
    if cr.get("achieved"):
        return "ACHIEVED"

    auth = str(cr.get("achievement_authority") or "")
    sup = (runtime_support or {}).get(key) or {}
    support_level = sup.get("support_level", "insufficient")

    if auth in (
        "HUMAN_REVIEW_REQUIRED",
        "HUMAN_PLAYTEST_L5",
        "RUNTIME_OBSERVATION_L4",
        "RUNTIME_INSUFFICIENT",
    ):
        if support_level == "operational_support_partial":
            return "HOLD"
        if auth == "HUMAN_REVIEW_REQUIRED":
            return "HOLD"

    obs = inventory.get("runtime_observation_report") or {}
    exe = inventory.get("executable_artifacts") or {}
    has_exe = bool(exe.get("files"))
    l5 = inventory.get("l5_human_playtest") or {}

    if obs.get("status") == "gated" and has_exe and not l5.get("pass"):
        return "HOLD"
    if support_level == "operational_support_partial":
        return "HOLD"
    if auth == "HUMAN_REVIEW_REQUIRED":
        return "HOLD"
    return "NOT_ACHIEVED"


def _decision_authority(
    cr: Optional[Dict[str, Any]],
    *,
    inventory: Dict[str, Any],
) -> str:
    if cr and cr.get("achievement_authority"):
        return str(cr["achievement_authority"])

    obs = inventory.get("runtime_observation_report") or {}
    if obs.get("status") == "gated":
        return "SYSTEM_GOVERNED"
    gov = inventory.get("governance_intent") or {}
    if gov.get("automatic_achievement_allowed") is False:
        return "SYSTEM_GOVERNED"
    return "AI_GRADING"


def _build_shared_nodes(
    inventory: Dict[str, Any],
    *,
    runtime_support: Optional[Dict[str, Any]],
    governance_intent: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Shared DAG node pool — referenced by multiple criteria."""
    nodes: Dict[str, Dict[str, Any]] = {}
    gov = governance_intent or inventory.get("governance_intent") or {}
    obs = inventory.get("runtime_observation_report") or {}
    exe = inventory.get("executable_artifacts") or {}
    doc = inventory.get("documentation") or {}
    src = inventory.get("source_code") or {}
    testing = inventory.get("testing_evidence") or {}
    emb = inventory.get("embedded_screenshots") or {}
    rt = inventory.get("runtime_artifacts") or {}
    coverage = inventory.get("extraction_coverage") or {}
    l5 = inventory.get("l5_human_playtest") or {}

    has_exe = bool(exe.get("files") or rt.get("executables_detected"))
    has_word = any(
        f.get("ext", "").lower() in (".docx", ".doc", ".pdf", ".odt")
        for f in doc.get("files") or []
    )
    has_screenshots = (
        (emb.get("count") or 0) > 0
        or rt.get("screenshot_folder_detected")
        or (rt.get("runtime_screenshot_count") or 0) > 0
    )
    has_testing = testing.get("status") in ("partial", "detected", "documented", "analyzed")
    src_artifacts = inventory.get("source_code_artifacts") or {}
    has_src = (
        src.get("status") in ("detected", "analyzed")
        and bool(src.get("files"))
    ) or bool(src_artifacts.get("files"))
    weak_src = coverage.get("weak_analysis_risk", False)
    ratio = float(coverage.get("coverage_ratio") or 0.0)

    if has_exe:
        nodes["evidence:exe_detected"] = {
            "id": "evidence:exe_detected",
            "type": "executable_detected",
            "source": "artifact_inventory",
            "confidence": CONFIDENCE_WEIGHTS["exe_detected_only"],
            "present": True,
            "details": {
                "exe_count": len(exe.get("files") or []),
                "runtime_verified": bool(exe.get("runtime_verified")),
            },
            "label_ar": "ملف تنفيذي (build) مُرصد",
        }

    if has_word:
        nodes["evidence:documentation"] = {
            "id": "evidence:documentation",
            "type": "documentation",
            "source": "artifact_inventory",
            "confidence": CONFIDENCE_WEIGHTS["documentation"],
            "present": True,
            "details": {"document_count": len(doc.get("files") or [])},
            "label_ar": "توثيق Word/PDF",
        }
    else:
        nodes["evidence:documentation_missing"] = {
            "id": "evidence:documentation_missing",
            "type": "documentation",
            "source": "artifact_inventory",
            "confidence": 0.0,
            "present": False,
            "details": {},
            "label_ar": "توثيق Word/PDF مفقود",
        }

    if has_screenshots:
        nodes["evidence:screenshots"] = {
            "id": "evidence:screenshots",
            "type": "screenshot",
            "source": "artifact_inventory",
            "confidence": CONFIDENCE_WEIGHTS["screenshot_only"],
            "present": True,
            "details": {"embedded_count": emb.get("count") or 0},
            "label_ar": "لقطات شاشة",
        }
    else:
        nodes["evidence:screenshots_missing"] = {
            "id": "evidence:screenshots_missing",
            "type": "screenshot",
            "source": "artifact_inventory",
            "confidence": 0.0,
            "present": False,
            "details": {},
            "label_ar": "لقطات شاشة مفقودة",
        }

    if has_testing:
        nodes["evidence:testing"] = {
            "id": "evidence:testing",
            "type": "testing_evidence",
            "source": "artifact_inventory",
            "confidence": CONFIDENCE_WEIGHTS["testing_evidence"],
            "present": True,
            "details": {"status": testing.get("status")},
            "label_ar": "أدلة اختبار",
        }
    else:
        nodes["evidence:testing_missing"] = {
            "id": "evidence:testing_missing",
            "type": "testing_evidence",
            "source": "artifact_inventory",
            "confidence": 0.0,
            "present": False,
            "details": {},
            "label_ar": "أدلة اختبار مفقودة",
        }

    if has_src:
        conf = (
            CONFIDENCE_WEIGHTS["partial_code_extraction"]
            if weak_src
            else min(0.55, CONFIDENCE_WEIGHTS["partial_code_extraction"] * 3)
        )
        nodes["evidence:code_extraction"] = {
            "id": "evidence:code_extraction",
            "type": "source_code",
            "source": "artifact_inventory",
            "confidence": round(conf, 4),
            "present": True,
            "details": {
                "ingested_files": len(src.get("files") or []),
                "coverage_ratio": ratio,
                "weak_analysis_risk": weak_src,
            },
            "label_ar": (
                f"استخراج كود جزئي ({ratio * 100:.1f}%)"
                if weak_src
                else "كود مصدري مُستخرج"
            ),
        }
    else:
        nodes["evidence:code_missing"] = {
            "id": "evidence:code_missing",
            "type": "source_code",
            "source": "artifact_inventory",
            "confidence": 0.0,
            "present": False,
            "details": {},
            "label_ar": "لا كود مُستخرج",
        }

    obs_status = obs.get("status") or "unavailable"
    if obs_status == "completed":
        nodes["evidence:runtime_observation"] = {
            "id": "evidence:runtime_observation",
            "type": "runtime_observation",
            "source": "unity_runtime",
            "confidence": CONFIDENCE_WEIGHTS["runtime_observation"],
            "present": True,
            "details": {
                "status": obs_status,
                "runtime_verified": bool(obs.get("runtime_verified")),
                "player_log_found": bool(obs.get("player_log_found")),
            },
            "label_ar": "ملاحظة runtime L4 (استشارية)",
        }
    elif has_exe:
        nodes["evidence:runtime_not_verified"] = {
            "id": "evidence:runtime_not_verified",
            "type": "runtime_observation",
            "source": "unity_runtime",
            "confidence": CONFIDENCE_WEIGHTS["exe_detected_only"],
            "present": False,
            "details": {
                "exe_detected": True,
                "player_log_found": bool(obs.get("player_log_found")),
                "observation_status": obs_status,
            },
            "label_ar": "build مُرصد — gameplay غير مُتحقَّق",
        }

    if l5.get("pass"):
        nodes["evidence:human_playtest"] = {
            "id": "evidence:human_playtest",
            "type": "human_playtest",
            "source": "l5_manual_playtest",
            "confidence": CONFIDENCE_WEIGHTS["human_playtest"],
            "present": True,
            "details": {
                "pass": True,
                "recorded_at": l5.get("recorded_at"),
            },
            "label_ar": "Manual Playtest L5 — موثّق",
        }

    if obs_status == "gated":
        policy = gov.get("reason") or obs.get("reason") or "GOVERNANCE_FREEZE_v1"
        nodes["governance:runtime_gate"] = {
            "id": "governance:runtime_gate",
            "type": "governance_gate",
            "policy": policy,
            "effect": "runtime_execution_blocked",
            "confidence": CONFIDENCE_WEIGHTS["governance_gate"],
            "label_ar": gov.get("reason_ar")
            or obs.get("gate_ar")
            or "L4 sandbox مقفول — GOVERNANCE_FREEZE_v1",
        }

    if gov.get("automatic_achievement_allowed") is False and "governance:runtime_gate" not in nodes:
        nodes["governance:achievement_blocked"] = {
            "id": "governance:achievement_blocked",
            "type": "governance_gate",
            "policy": gov.get("reason") or "governance_policy",
            "effect": "automatic_achievement_blocked",
            "confidence": CONFIDENCE_WEIGHTS["governance_gate"],
            "label_ar": gov.get("academic_implication_ar") or "لا ترقية تلقائية للإنجاز",
        }

    sup = runtime_support or inventory.get("runtime_criterion_support") or {}
    if sup.get("smoke_only"):
        nodes["governance:smoke_only"] = {
            "id": "governance:smoke_only",
            "type": "governance_gate",
            "policy": "RUNTIME_CRITERION_MAPPING_v1",
            "effect": "smoke_only_insufficient_for_achievement",
            "confidence": CONFIDENCE_WEIGHTS["governance_gate"],
            "label_ar": "smoke/launch فقط — لا يكفي لـ Achieved",
        }

    return nodes


def _criterion_node_refs(key: str, shared: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str], List[str]]:
    """Which shared nodes feed each execution criterion."""
    evidence: List[str] = []

    cp5_evidence = (
        "evidence:exe_detected",
        "evidence:runtime_observation",
        "evidence:runtime_not_verified",
        "evidence:human_playtest",
        "evidence:screenshots",
        "evidence:screenshots_missing",
        "evidence:code_extraction",
        "evidence:code_missing",
        "evidence:documentation",
        "evidence:documentation_missing",
    )
    for nid in cp5_evidence:
        if nid in shared:
            evidence.append(nid)

    if key == "C.P6":
        for nid in ("evidence:testing", "evidence:testing_missing"):
            if nid in shared:
                evidence.append(nid)

    governance: List[str] = []
    for nid in (
        "governance:runtime_gate",
        "governance:achievement_blocked",
        "governance:smoke_only",
    ):
        if nid in shared:
            governance.append(nid)

    decision: List[str] = [f"decision:{key.lower()}"]

    def _dedupe(items: List[str]) -> List[str]:
        seen: Set[str] = set()
        out: List[str] = []
        for i in items:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return out

    return _dedupe(evidence), _dedupe(governance), decision


def _aggregate_confidence(node_ids: List[str], shared: Dict[str, Dict[str, Any]]) -> float:
    confs = [
        float((shared.get(nid) or {}).get("confidence") or 0.0)
        for nid in node_ids
        if (shared.get(nid) or {}).get("type") != "governance_gate"
    ]
    if not confs:
        return 0.0
    return round(max(confs), 4)


def _decision_node(
    key: str,
    *,
    status: str,
    cr: Optional[Dict[str, Any]],
    evidence_ids: List[str],
    governance_ids: List[str],
    shared: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    reasons: List[str] = []
    if status == "ACHIEVED":
        reasons.append("verified_evidence_sufficient")
    elif status == "HOLD":
        if "governance:runtime_gate" in governance_ids:
            reasons.append("governance_gate_active")
        if not any(shared.get(i, {}).get("present") for i in evidence_ids if "playtest" in i):
            reasons.append("insufficient_verified_evidence")
        if "governance:smoke_only" in governance_ids:
            reasons.append("smoke_only_hold")
        if not reasons:
            reasons.append("human_review_required")
    else:
        reasons.append("insufficient_verified_evidence")

    return {
        "id": f"decision:{key.lower()}",
        "type": "criterion_decision",
        "result": status,
        "reason": reasons[0],
        "reasons": reasons,
        "achieved": bool(cr.get("achieved")) if cr else False,
        "score": cr.get("score") if cr else 0,
        "aggregate_evidence_confidence": _aggregate_confidence(evidence_ids, shared),
        "label_ar": {
            "ACHIEVED": "محقق — أدلة كافية",
            "HOLD": "HOLD — أدلة غير كافية أو محكومة",
            "NOT_ACHIEVED": "غير محقق — أدلة غير كافية",
        }.get(status, status),
    }


def build_evidence_lineage(
    *,
    criteria_results: Optional[List[Dict[str, Any]]] = None,
    inventory: Optional[Dict[str, Any]] = None,
    runtime_support: Optional[Dict[str, Any]] = None,
    governance_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build criterion-centric evidence DAG for C.P5/C.P6."""
    inv = inventory or {}
    criteria = criteria_results or []
    shared = _build_shared_nodes(
        inv,
        runtime_support=runtime_support,
        governance_intent=governance_intent,
    )

    criteria_out: Dict[str, Any] = {}
    for key in EXECUTION_CRITERION_KEYS:
        cr = _resolve_criterion_row(criteria, key)
        status = _criterion_status(
            cr,
            inventory=inv,
            runtime_support=runtime_support,
            key=key,
        )
        evidence_ids, governance_ids, decision_ids = _criterion_node_refs(key, shared)
        decision = _decision_node(
            key,
            status=status,
            cr=cr,
            evidence_ids=evidence_ids,
            governance_ids=governance_ids,
            shared=shared,
        )
        shared[decision["id"]] = decision

        criteria_out[key] = {
            "criterion": key,
            "criteria_level": (cr or {}).get("criteria_level") or key,
            "status": status,
            "decision_authority": _decision_authority(cr, inventory=inv),
            "lineage": {
                "evidence_nodes": evidence_ids,
                "governance_nodes": governance_ids,
                "decision_nodes": decision_ids,
            },
        }

    graph: Dict[str, Any] = {
        "schema": EVIDENCE_LINEAGE_SCHEMA,
        "confidence_model": CONFIDENCE_MODEL,
        "confidence_weights": CONFIDENCE_WEIGHTS,
        "shared_nodes": shared,
        "criteria": criteria_out,
    }
    graph["lineage_hash"] = _lineage_hash(graph)
    return graph


def attach_evidence_lineage_to_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Populate evidence_lineage on grading snapshot (additive — no grade changes)."""
    if not isinstance(snapshot, dict):
        return snapshot

    inv = snapshot.get("artifact_inventory") or {}
    layer = snapshot.setdefault("explainability_layer", {})
    if not isinstance(layer, dict):
        layer = {}
        snapshot["explainability_layer"] = layer

    lineage = build_evidence_lineage(
        criteria_results=snapshot.get("criteria_results") or [],
        inventory=inv,
        runtime_support=snapshot.get("runtime_criterion_support")
        or inv.get("runtime_criterion_support"),
        governance_intent=layer.get("governance_intent") or inv.get("governance_intent"),
    )
    snapshot["evidence_lineage"] = lineage
    layer["evidence_lineage"] = lineage
    inv["evidence_lineage"] = lineage
    snapshot["artifact_inventory"] = inv
    return snapshot


def format_lineage_for_ui(criterion_entry: Dict[str, Any], shared: Dict[str, Any]) -> List[Dict[str, str]]:
    """Flat rows for template rendering — evidence → governance → decision."""
    rows: List[Dict[str, str]] = []
    lineage = criterion_entry.get("lineage") or {}

    for nid in lineage.get("evidence_nodes") or []:
        node = shared.get(nid) or {}
        rows.append({
            "kind": "evidence",
            "label": node.get("label_ar") or nid,
            "confidence": str(node.get("confidence", "")),
        })
    for nid in lineage.get("governance_nodes") or []:
        node = shared.get(nid) or {}
        rows.append({
            "kind": "governance",
            "label": node.get("label_ar") or nid,
            "confidence": "",
        })
    for nid in lineage.get("decision_nodes") or []:
        node = shared.get(nid) or {}
        rows.append({
            "kind": "decision",
            "label": node.get("label_ar") or nid,
            "confidence": str(node.get("aggregate_evidence_confidence", "")),
        })
    return rows
