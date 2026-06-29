"""
Evidence Map — domain layer between grading snapshots and teacher UI.

Do not read raw snapshot keys from templates; use ``build_evidence_map``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.btec_criteria_governance import _short_level
from app.runtime_evidence_gate import RUNTIME_GATED_SHORT, is_game_submission

# Required evidence types per criterion short code (Unit 8 games — typical)
_REQUIRED_BY_SHORT: Dict[str, List[str]] = {
    "P3": ["gdd_doc", "design_text"],
    "P4": ["visual_design", "flowchart"],
    "P5": ["source_or_project", "runtime_verified"],
    "P6": ["test_plan", "presentation", "runtime_or_playtest"],
    "P7": ["requirements_review"],
    "M2": ["peer_review", "design_revision"],
    "M3": ["testing_evidence", "refinement", "runtime_verified"],
    "D2": ["critical_evaluation"],
    "D3": ["development_log", "runtime_verified"],
}

_REQUIRED_LABELS_AR: Dict[str, str] = {
    "gdd_doc": "وثيقة تصميم (GDD)",
    "design_text": "شرح التصميم في النص",
    "visual_design": "تصاميم بصرية / storyboard",
    "flowchart": "مخطط انسيابي",
    "source_or_project": "ملف مشروع / كود مصدري (.sb3, .yyp, …)",
    "runtime_verified": "تشغيل موثّق (فيديو / playtest / Runtime PASS)",
    "test_plan": "خطة اختبار",
    "presentation": "عرض تقديمي / تواصل تقني",
    "runtime_or_playtest": "لعب فعلي أو فيديو gameplay",
    "requirements_review": "مراجعة المتطلبات",
    "peer_review": "ملاحظات المراجعين",
    "design_revision": "نسخة محسّنة من التصميم",
    "testing_evidence": "أدلة اختبار موثقة",
    "refinement": "تحسين بناءً على الاختبار",
    "critical_evaluation": "تقييم نقدي مبرر",
    "development_log": "سجل تطوير / انعكاس",
}


@dataclass
class CriterionEvidenceStatus:
    criterion_code: str
    criterion_level: str
    achieved_final: bool
    awardable: bool
    achieved_ai_suggestion: Optional[bool] = None
    gate_relevant: bool = False
    gate_applied: bool = False
    gate_satisfied: Optional[bool] = None
    required_evidence_types: List[str] = field(default_factory=list)
    required_evidence_labels_ar: List[str] = field(default_factory=list)
    available_evidence: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    downgrade_reason_ar: Optional[str] = None
    coverage_score: Optional[float] = None
    authority: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _coverage_index(snapshot: Dict[str, Any], inv: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = snapshot.get("evidence_coverage_by_criterion") or inv.get("evidence_coverage_by_criterion")
    if not rows:
        try:
            from app.evidence_coverage_score import compute_evidence_coverage_by_criterion

            levels = [
                str(r.get("criteria_level"))
                for r in snapshot.get("criteria_results") or []
                if isinstance(r, dict) and r.get("criteria_level")
            ]
            rows = compute_evidence_coverage_by_criterion(
                inv,
                student_text=str(snapshot.get("student_text") or "")[:50000],
                word_only_text=str(
                    snapshot.get("plagiarism_text") or snapshot.get("student_text") or ""
                )[:50000],
                submission_paths=snapshot.get("submission_paths") or [],
                criteria_levels=levels or None,
            )
        except Exception:
            rows = []
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        short = _short_level(str(row.get("criteria_level") or ""))
        if short:
            out[short] = row
    return out


def _downgrade_by_criterion(snapshot: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in snapshot.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        level = str(row.get("criteria_level") or "")
        if row.get("award_block_reason_ar"):
            out[level] = str(row["award_block_reason_ar"])
        elif row.get("governance_adjustment_ar"):
            out[level] = str(row["governance_adjustment_ar"])
    gate = snapshot.get("runtime_evidence_gate") or {}
    if gate.get("summary_ar"):
        for short in RUNTIME_GATED_SHORT:
            for row in snapshot.get("criteria_results") or []:
                if not isinstance(row, dict):
                    continue
                if _short_level(str(row.get("criteria_level") or "")) == short:
                    if row.get("runtime_gate_block"):
                        out.setdefault(str(row.get("criteria_level")), str(gate.get("summary_ar")))
    return out


def build_evidence_map(snapshot: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build per-criterion evidence status for teacher UI.

    Safe on old snapshots — recomputes coverage when missing.
    """
    if not snapshot or not isinstance(snapshot, dict):
        return []

    inv = snapshot.get("artifact_inventory") or {}
    paths = snapshot.get("submission_paths") or []
    game = is_game_submission(inv, submission_paths=list(paths))
    gate = snapshot.get("runtime_evidence_gate") or {}
    gate_satisfied = gate.get("satisfied") if "satisfied" in gate else None
    gate_applied_global = bool(gate.get("applied"))
    cov_idx = _coverage_index(snapshot, inv)
    downgrade_map = _downgrade_by_criterion(snapshot)

    diag: Dict[str, Any] = {}
    try:
        from app.academic_explainability import build_missing_evidence_diagnostics

        diag = build_missing_evidence_diagnostics(
            inv,
            project_profile=snapshot.get("project_profile"),
            grading_mode=snapshot.get("grading_mode"),
        )
    except Exception:
        diag = {}

    checklist = diag.get("checklist") or diag.get("items") or []
    global_missing: List[str] = []
    if isinstance(checklist, list):
        for item in checklist:
            if isinstance(item, dict) and not item.get("present"):
                label = item.get("label_ar") or item.get("id") or ""
                if label:
                    global_missing.append(str(label))

    results: List[Dict[str, Any]] = []
    for row in snapshot.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        level = str(row.get("criteria_level") or "")
        short = _short_level(level)
        if not short:
            continue

        cov = cov_idx.get(short) or {}
        required = list(_REQUIRED_BY_SHORT.get(short, ["documentary_evidence"]))
        required_labels = [_REQUIRED_LABELS_AR.get(k, k) for k in required]

        available = [str(x) for x in (cov.get("evidence_found_ar") or cov.get("evidence_found") or []) if x]
        missing = [str(x) for x in (cov.get("evidence_missing_ar") or cov.get("evidence_missing") or []) if x]
        if not missing and global_missing and short in RUNTIME_GATED_SHORT:
            missing = list(global_missing[:4])

        gate_rel = short in RUNTIME_GATED_SHORT and game
        gate_applied = gate_rel and (gate_applied_global or bool(row.get("runtime_gate_block")))
        row_gate_sat: Optional[bool]
        if not gate_rel:
            row_gate_sat = None
        elif row.get("runtime_gate_block"):
            row_gate_sat = False
        else:
            row_gate_sat = gate_satisfied

        ai_hint: Optional[bool] = row.get("deterministic_suggested_achieved")
        if ai_hint is None and row.get("runtime_gate_block") and not row.get("achieved"):
            ai_hint = True

        status = CriterionEvidenceStatus(
            criterion_code=short,
            criterion_level=level,
            achieved_final=bool(row.get("achieved")),
            awardable=bool(row.get("awardable", row.get("achieved"))),
            achieved_ai_suggestion=ai_hint if isinstance(ai_hint, bool) else None,
            gate_relevant=gate_rel,
            gate_applied=gate_applied,
            gate_satisfied=row_gate_sat,
            required_evidence_types=required,
            required_evidence_labels_ar=required_labels,
            available_evidence=available,
            missing_evidence=missing,
            downgrade_reason_ar=downgrade_map.get(level),
            coverage_score=float(cov["coverage_pct"]) if cov.get("coverage_pct") is not None else None,
            authority=str(row.get("achievement_authority") or "") or None,
        )
        results.append(status.to_dict())

    results.sort(key=lambda r: (r.get("criterion_code") or ""))
    return results


def build_evidence_map_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compact summary for batch list / filters."""
    gated_down = [
        r for r in rows
        if r.get("gate_relevant") and r.get("gate_applied") and r.get("gate_satisfied") is False
    ]
    high_cov_u = [
        r for r in rows
        if not r.get("achieved_final")
        and (r.get("coverage_score") or 0) >= 50
    ]
    return {
        "total_criteria": len(rows),
        "gate_downgrade_count": len(gated_down),
        "high_coverage_not_achieved_count": len(high_cov_u),
        "has_gate_issue": bool(gated_down),
    }
