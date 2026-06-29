"""
Criterion Authority Guardrails v1 — institutional hard gates (not advisory).

Blocks autonomous achievement escalation for execution-oriented criteria when
operational evidence is insufficient. Does NOT auto-fail — sets HUMAN_REVIEW_REQUIRED.

Companion: GOVERNANCE_FREEZE_v1 — presence ≠ authority.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

GUARDRAILS_ID = "CRITERION_AUTHORITY_GUARDRAILS_v1"

# Minimum institutional authority for autonomous Achieved by criterion class
CRITERION_AUTHORITY_FLOORS: Dict[str, Dict[str, Any]] = {
    "execution_runtime": {
        "min_runtime_level": 4,
        "label_ar": "تنفيذ/تشغيل",
        "requires_any_of": ["runtime_verified", "source_code", "runtime_telemetry"],
    },
    "operational_testing": {
        "min_runtime_level": 4,
        "label_ar": "اختبار تشغيلي",
        "requires_any_of": ["runtime_verified", "source_code", "runtime_telemetry", "corroborated_test_evidence"],
    },
    "documentation": {
        "min_runtime_level": 1,
        "label_ar": "توثيق",
        "requires_any_of": [],
    },
    "reflection": {
        "min_runtime_level": 1,
        "label_ar": "تأمل/تقييم نصي",
        "requires_any_of": [],
    },
}

# BTEC game / IT execution criteria — extend as packages are calibrated
_EXECUTION_LEVEL_CODES = frozenset({"C.P5", "C.P6", "C.P7"})
_TESTING_LEVEL_CODES = frozenset({"C.P6"})
_EXECUTION_LEVEL_RE = re.compile(r"^(?:[A-Z]+\.)?P(?:5|7)$", re.I)
_TESTING_LEVEL_RE = re.compile(r"^(?:[A-Z]+\.)?P6$", re.I)


def _short_level(criteria_level: str) -> str:
    lv = (criteria_level or "").strip()
    return lv.split(".")[-1].upper() if "." in lv else lv.upper()


def classify_criterion_guardrail_type(criteria_level: str) -> str:
    """Map criterion code to guardrail class."""
    full = (criteria_level or "").strip().upper()
    short = _short_level(full)
    if full in _EXECUTION_LEVEL_CODES or _EXECUTION_LEVEL_RE.match(short):
        return "execution_runtime"
    if full in _TESTING_LEVEL_CODES or _TESTING_LEVEL_RE.match(short):
        return "operational_testing"
    return "documentation"


def assess_evidence_authority_floor(
    artifact_inventory: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Current operational evidence ceiling from artifact inventory."""
    inv = artifact_inventory or {}
    rt = inv.get("runtime_evidence_level") or {}
    level = int(rt.get("level") or 0)
    exe = inv.get("executable_artifacts") or {}
    runtime_art = inv.get("runtime_artifacts") or {}

    runtime_verified = bool(
        exe.get("runtime_verified")
        or runtime_art.get("runtime_verified")
        or (inv.get("runtime_verification") or {}).get("status") == "verified"
        or (inv.get("runtime_observation_report") or {}).get("runtime_verified")
    )
    has_source = bool(inv.get("has_source_code_artifacts"))
    has_telemetry = bool(
        inv.get("runtime_telemetry")
        or inv.get("telemetry_graph")
        or inv.get("runtime_signal_graph")
    )
    has_exe = bool(inv.get("has_executable_artifacts"))
    corroborated_test = runtime_verified or (level >= 4 and has_telemetry)

    insufficient_for_execution_autonomy = (
        not runtime_verified
        and not has_source
        and not has_telemetry
        and level <= 2
    )

    return {
        "runtime_evidence_level": level,
        "runtime_verified": runtime_verified,
        "has_source_code": has_source,
        "has_executable_detected": has_exe,
        "has_runtime_telemetry": has_telemetry,
        "corroborated_test_evidence": corroborated_test,
        "insufficient_for_execution_autonomy": insufficient_for_execution_autonomy,
        "summary_ar": (
            f"L{level} — runtime_verified={runtime_verified}, "
            f"source={has_source}, telemetry={has_telemetry}, "
            f"exe_detected={has_exe} (not executed unless verified)"
        ),
    }


def _floor_satisfied(
    floor: Dict[str, Any],
    evidence: Dict[str, Any],
) -> bool:
    """True if evidence meets minimum for autonomous achievement."""
    min_level = int(floor.get("min_runtime_level") or 1)
    if evidence.get("runtime_verified"):
        return True
    if evidence.get("runtime_evidence_level", 0) >= min_level and evidence.get("has_runtime_telemetry"):
        return True
    requires = floor.get("requires_any_of") or []
    if not requires:
        return True
    checks = {
        "runtime_verified": evidence.get("runtime_verified"),
        "source_code": evidence.get("has_source_code"),
        "runtime_telemetry": evidence.get("has_runtime_telemetry"),
        "corroborated_test_evidence": evidence.get("corroborated_test_evidence"),
    }
    return any(checks.get(k) for k in requires if k in checks)


def _should_block_escalation(
    guardrail_type: str,
    evidence: Dict[str, Any],
) -> Tuple[bool, str]:
    if guardrail_type not in ("execution_runtime", "operational_testing"):
        return False, ""
    floor = CRITERION_AUTHORITY_FLOORS[guardrail_type]
    if _floor_satisfied(floor, evidence):
        return False, ""
    if not evidence.get("insufficient_for_execution_autonomy"):
        return False, ""
    return True, (
        f"لا يكفي L{evidence.get('runtime_evidence_level', 0)} + "
        f"{'exe مُرصد' if evidence.get('has_executable_detected') else 'بدون exe'} "
        f"لتصعيد {floor['label_ar']} إلى Achieved تلقائياً — "
        f"مراجعة بشرية مطلوبة (L4 runtime أو L5 human)."
    )


def apply_criterion_authority_guardrails(
    grading_result: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Validate grading output against authority floors.
    Blocks autonomous escalation — does not hard-fail to Not Achieved semantics.
    """
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    evidence = assess_evidence_authority_floor(inv)
    criteria = grading_result.get("criteria_results") or []
    blocked: List[Dict[str, Any]] = []
    original_grade = grading_result.get("grade_level")

    for cr in criteria:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        if not cr.get("achieved"):
            continue
        if cr.get("achievement_authority") == "RUNTIME_OBSERVATION_L4":
            continue
        gtype = classify_criterion_guardrail_type(level)
        block, reason_ar = _should_block_escalation(gtype, evidence)
        if not block:
            continue

        cr["ai_proposed_achieved"] = True
        cr["achieved"] = False
        cr["achievement_authority"] = "HUMAN_REVIEW_REQUIRED"
        cr["authority_guardrail"] = {
            "guardrails_id": GUARDRAILS_ID,
            "gate": "block_autonomous_escalation",
            "criterion_type": gtype,
            "reason_ar": reason_ar,
            "required_floor": CRITERION_AUTHORITY_FLOORS[gtype],
            "evidence_floor": evidence,
            "failure_mode_id": "GFM_AUTHORITY_INFLATION",
        }
        prefix = (
            "⏸ [مراجعة بشرية مطلوبة — لم يُمنح Achieved مؤسسياً] "
            "النظام منع التصعيد التلقائي: presence ≠ achievement. "
        )
        cr["feedback"] = prefix + reason_ar + "\n\n" + str(cr.get("feedback") or "")

        blocked.append({
            "criteria_level": level,
            "criterion_type": gtype,
            "ai_proposed_achieved": True,
            "achievement_authority": "HUMAN_REVIEW_REQUIRED",
            "reason_ar": reason_ar,
        })

    report: Dict[str, Any] = {
        "guardrails_id": GUARDRAILS_ID,
        "evidence_floor": evidence,
        "blocked_escalations": blocked,
        "blocked_count": len(blocked),
        "human_review_required": len(blocked) > 0,
        "summary_ar": (
            f"تم منع {len(blocked)} تصعيد(ات) Achieved تلقائية — مراجعة بشرية مطلوبة."
            if blocked
            else "لا تصعيد Achieved محظور — authority floor محترم."
        ),
    }

    if blocked:
        from app.btec_grade_resolution import determine_grade_level

        grading_result["criteria_results"] = criteria
        new_grade = determine_grade_level(criteria)
        grading_result["grade_level"] = new_grade
        total_score_sum = sum(
            int(cr.get("score") or 0) for cr in criteria if isinstance(cr, dict)
        )
        total_count = len(criteria) or 1
        percentage = int(total_score_sum / total_count)
        grading_result["percentage"] = percentage
        grading_result["total_score"] = percentage
        grading_result["max_score"] = grading_result.get("max_score") or 100

        note = (
            f"\n\n⏸ [Criterion Authority Guardrails] "
            f"تم منع تصعيد Achieved تلقائي لـ {len(blocked)} معيار(ات) تشغيل/اختبار "
            f"({', '.join(b['criteria_level'] for b in blocked)}) — "
            f"الدرجة المؤسسية: {original_grade} → {new_grade}. "
            f"مراجعة verifier مطلوبة قبل اعتبار المعيار متحققاً."
        )
        grading_result["overall_feedback"] = (grading_result.get("overall_feedback") or "") + note

        report["grade_adjusted"] = True
        report["original_grade_level"] = original_grade
        report["institutional_grade_level"] = new_grade
        report["export_policy"] = {
            "gate": "block_until_review",
            "allow_export": False,
            "message_ar": (
                "تصدير التقرير موقوف — معيار(ات) تشغيل/اختبار تتطلب مراجعة بشرية "
                "قبل اعتبار Achieved مؤسسياً."
            ),
            "source": GUARDRAILS_ID,
        }
    else:
        report["export_policy"] = {
            "gate": "allow",
            "allow_export": True,
            "source": GUARDRAILS_ID,
        }

    grading_result["criterion_authority_guardrails"] = report
    return report


def merge_export_policy_with_guardrails(
    governance_export: Optional[Dict[str, Any]],
    guardrails_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Resolve export gate: institutional guardrails win when explicit allow/block;
    otherwise worst gate vs governance drift.
    """
    g_exp = (guardrails_report or {}).get("export_policy") or {}
    g_gate = g_exp.get("gate") or "allow"
    if g_gate == "allow" and g_exp.get("allow_export"):
        return g_exp
    if g_gate == "block_until_review":
        return g_exp

    gov = governance_export or {}
    priority = {"allow": 0, "warn_and_review": 1, "block_until_review": 2, "none": 0, "advisory_warning": 1, "conditional_block": 2}
    gov_gate = gov.get("gate") or "allow"
    if priority.get(g_gate, 0) >= priority.get(gov_gate, 0):
        return g_exp if g_gate != "allow" else gov
    return gov
