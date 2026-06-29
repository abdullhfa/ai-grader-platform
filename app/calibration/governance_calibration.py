"""
Governance Calibration Cycle — Disagreement Taxonomy Matrix.

Turns criterion mismatches into institutional learning artifacts.
Read-only on grades; never fabricates human labels.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WAVE_1 = [1]
WAVE_2 = [22, 15, 19, 14, 16]
WAVE_3 = [20, 21, 17, 18, 25]
PILOT_WAVE_IDS = WAVE_1 + WAVE_2 + WAVE_3

TAXONOMY_DECISIONS: Dict[str, str] = {
    "no_runtime_build": "submission policy",
    "replay_insufficient": "replay enhancement",
    "weak_evidence": "threshold tuning",
    "rubric_ambiguity": "rubric clarification",
    "ai_conservative": "threshold tuning",
    "ai_overclaiming": "governance tightening",
    "human_leniency": "moderation normalization",
    "human_harshness": "moderation normalization",
    "overall_grade_mismatch": "moderation review",
    "agreement": "no action",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_by_submission(runtime_dashboard: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for entry in runtime_dashboard.get("entries") or []:
        sid = str(entry.get("submission_id") or "")
        if sid:
            out[sid] = entry
    return out


def classify_criterion_mismatch(
    mismatch: Dict[str, Any],
    *,
    runtime_entry: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, str]:
    """Returns (taxonomy_type, governance_decision, rationale_ar)."""
    criterion = str(mismatch.get("criterion") or "")
    if criterion == "__overall_grade__":
        return (
            "overall_grade_mismatch",
            TAXONOMY_DECISIONS["overall_grade_mismatch"],
            "اختلاف overall grade — مراجعة moderation",
        )

    teacher = mismatch.get("teacher_achieved")
    system = mismatch.get("system_achieved")
    if teacher is None or system is None:
        return ("rubric_ambiguity", TAXONOMY_DECISIONS["rubric_ambiguity"], "بيانات ناقصة للمقارنة")

    tax = (runtime_entry or {}).get("taxonomy")
    replay_ok = bool(mismatch.get("replay_verified"))
    hall = str(mismatch.get("hallucination_risk") or "").lower()

    if tax in ("source_only", "missing_artifacts"):
        if teacher and not system:
            return (
                "no_runtime_build",
                TAXONOMY_DECISIONS["no_runtime_build"],
                "المعلم Achieved والنظام Not — لا build قابل للتشغيل",
            )
        if not teacher and system:
            return (
                "ai_overclaiming",
                TAXONOMY_DECISIONS["ai_overclaiming"],
                "النظام Achieved بدون runtime كافٍ",
            )

    if not replay_ok:
        return (
            "replay_insufficient",
            TAXONOMY_DECISIONS["replay_insufficient"],
            "replay غير verified — auditability ناقصة",
        )

    if hall in ("high", "medium"):
        return (
            "weak_evidence",
            TAXONOMY_DECISIONS["weak_evidence"],
            "evidence ضعيفة أو hallucination risk",
        )

    if teacher and not system:
        return (
            "ai_conservative",
            TAXONOMY_DECISIONS["ai_conservative"],
            "النظام متحفظ أكثر — threshold calibration",
        )
    if not teacher and system:
        return (
            "ai_overclaiming",
            TAXONOMY_DECISIONS["ai_overclaiming"],
            "النظام منح Achieved والمعلم رفض",
        )

    return (
        "rubric_ambiguity",
        TAXONOMY_DECISIONS["rubric_ambiguity"],
        "اختلاف بدون إشارة runtime/replay واضحة — rubric غامض",
    )


def _wave_progress(labels_doc: Dict[str, Any]) -> Dict[str, Any]:
    criteria_keys = ("P3", "P4", "P5", "P6", "P7", "M2", "M3", "D2", "D3")

    def progress_for(ids: List[int]) -> Dict[str, Any]:
        idset = set(ids)
        rows = [r for r in labels_doc.get("records") or [] if int(r.get("submission_id") or 0) in idset]
        complete = 0
        crit_filled = 0
        for rec in rows:
            crit = rec.get("criteria") or {}
            filled = sum(1 for k in criteria_keys if (crit.get(k) or {}).get("decision") is not None)
            if rec.get("overall_grade") is not None:
                filled += 1
            crit_filled += filled
            if filled == len(criteria_keys) + 1:
                complete += 1
        max_slots = len(rows) * (len(criteria_keys) + 1)
        return {
            "submission_ids": ids,
            "records": len(rows),
            "fully_complete": complete,
            "slots_filled": crit_filled,
            "slots_total": max_slots,
            "pct": round(crit_filled / max(max_slots, 1) * 100, 1),
            "ready_for_cycle": complete == len(ids) and len(ids) > 0,
        }

    w1 = progress_for(WAVE_1)
    w2 = progress_for(WAVE_2)
    w3 = progress_for(WAVE_3)
    pilot_complete = w1["fully_complete"] + w2["fully_complete"] + w3["fully_complete"]
    return {
        "wave_1_abdullah": w1,
        "wave_2_top5": w2,
        "wave_3_bottom5": w3,
        "pilot_cohort_size": len(PILOT_WAVE_IDS),
        "pilot_fully_complete": pilot_complete,
        "pilot_ready": pilot_complete == len(PILOT_WAVE_IDS),
    }


def build_governance_calibration_cycle(
    *,
    disagreement_report: Dict[str, Any],
    runtime_dashboard: Optional[Dict[str, Any]] = None,
    labels_doc: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    runtime_map = _runtime_by_submission(runtime_dashboard or {})
    classified: List[Dict[str, Any]] = []
    matrix_counts: Dict[str, int] = {}
    decision_counts: Dict[str, int] = {}

    for mismatch in disagreement_report.get("criterion_mismatches") or []:
        sid = str(mismatch.get("submission_id") or "")
        tax_type, decision, rationale = classify_criterion_mismatch(
            mismatch,
            runtime_entry=runtime_map.get(sid),
        )
        row = {
            **mismatch,
            "taxonomy_type": tax_type,
            "governance_decision": decision,
            "rationale_ar": rationale,
            "defensibility_question_ar": "هل replay/evidence تدعم قرار المعلم؟",
        }
        classified.append(row)
        matrix_counts[tax_type] = matrix_counts.get(tax_type, 0) + 1
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

    summary = disagreement_report.get("summary") or {}
    gold_rows = int(summary.get("gold_rows_used") or 0)
    wave_progress = _wave_progress(labels_doc or {})

    matrix_rows = [
        {
            "taxonomy_type": tax,
            "count": count,
            "governance_decision": TAXONOMY_DECISIONS.get(tax, "review"),
            "pct_of_mismatches": round(count / max(len(classified), 1) * 100, 1),
        }
        for tax, count in sorted(matrix_counts.items(), key=lambda x: -x[1])
    ]

    cycle_status = "pending_pilot_wave"
    if wave_progress.get("pilot_ready"):
        cycle_status = "ready_for_moderation_review" if gold_rows >= 50 else "partial_data"
    elif gold_rows > 0:
        cycle_status = "partial_data"

    return {
        "schema": "governance_calibration_cycle_v1",
        "generated_at": _utc_now(),
        "run_id": run_id,
        "cycle_status": cycle_status,
        "description_ar": "أول Governance Learning Artifact — taxonomy من disagreements حقيقية",
        "pilot_wave_progress": wave_progress,
        "calibration_metrics": {
            "gold_rows_used": gold_rows,
            "cohens_kappa": summary.get("cohens_kappa"),
            "agreement_rate": summary.get("agreement_rate"),
            "false_positives": summary.get("false_positives"),
            "false_negatives": summary.get("false_negatives"),
            "criterion_mismatch_count": summary.get("criterion_mismatch_count"),
            "note_ar": "Kappa مؤشر — taxonomy = القيمة المؤسسية",
        },
        "disagreement_taxonomy_matrix": matrix_rows,
        "governance_decision_summary": [
            {"decision": d, "count": c} for d, c in sorted(decision_counts.items(), key=lambda x: -x[1])
        ],
        "classified_mismatches": classified,
        "moderation_review_agenda_ar": [
            "أين وافق AI مع المعلم؟",
            "أين اختلف؟ وهل الاختلاف defensible؟",
            "هل replay كافية للدفاع؟",
            "هل runtime evidence غيّرت القرار؟",
            "قرارات: policy / rubric / threshold / moderation",
        ],
        "next_steps_ar": _next_steps(wave_progress, gold_rows),
    }


def _next_steps(wave_progress: Dict[str, Any], gold_rows: int) -> List[str]:
    steps: List[str] = []
    w1 = wave_progress.get("wave_1_abdullah") or {}
    if not w1.get("ready_for_cycle"):
        steps.append("إنهاء Abdullah (#1) 100% في /institutional/moderation")
    if (wave_progress.get("wave_2_top5") or {}).get("fully_complete", 0) < 5:
        steps.append("إنهاء Top 5 (#22, #15, #19, #14, #16)")
    if (wave_progress.get("wave_3_bottom5") or {}).get("fully_complete", 0) < 5:
        steps.append("إنهاء Bottom 5 (#20, #21, #17, #18, #25)")
    if gold_rows < 50:
        steps.append("تشغيل run_institutional_closure.py بعد الموجة")
    steps.append("اجتماع moderation review مع المعلّم والمشرف ومسؤول الجودة")
    if gold_rows >= 50:
        steps.append("Governance freeze sign-off عند Kappa مستقرة + disagreements مفهومة")
    return steps


def write_governance_calibration_artifacts(
    cycle: Dict[str, Any],
    out_dir: Path,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "GOVERNANCE_CALIBRATION_CYCLE_v1.json"
    json_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out_dir / "GOVERNANCE_CALIBRATION_CYCLE.md"
    md_path.write_text(_render_markdown(cycle), encoding="utf-8")

    return {"json": str(json_path), "markdown": str(md_path)}


def _render_markdown(cycle: Dict[str, Any]) -> str:
    metrics = cycle.get("calibration_metrics") or {}
    wave = cycle.get("pilot_wave_progress") or {}
    w1 = wave.get("wave_1_abdullah") or {}
    matrix = cycle.get("disagreement_taxonomy_matrix") or []

    lines = [
        "# Governance Calibration Cycle",
        "",
        f"Generated: {cycle.get('generated_at')}",
        f"Status: **{cycle.get('cycle_status')}**",
        "",
        "## Pilot wave progress",
        "",
        "| Wave | Complete | Progress |",
        "|------|----------|----------|",
        f"| Abdullah | {w1.get('fully_complete', 0)}/1 | {w1.get('pct', 0)}% |",
        f"| Top 5 | {(wave.get('wave_2_top5') or {}).get('fully_complete', 0)}/5 | {(wave.get('wave_2_top5') or {}).get('pct', 0)}% |",
        f"| Bottom 5 | {(wave.get('wave_3_bottom5') or {}).get('fully_complete', 0)}/5 | {(wave.get('wave_3_bottom5') or {}).get('pct', 0)}% |",
        "",
        "## Calibration metrics (secondary)",
        "",
        f"- Gold rows: {metrics.get('gold_rows_used')}",
        f"- Cohen's Kappa: {metrics.get('cohens_kappa')}",
        f"- Agreement: {metrics.get('agreement_rate')}",
        f"- False positives: {metrics.get('false_positives')}",
        f"- False negatives: {metrics.get('false_negatives')}",
        "",
        "## Disagreement Taxonomy Matrix (primary value)",
        "",
        "| Type | Count | Governance Decision |",
        "|------|-------|---------------------|",
    ]
    for row in matrix:
        lines.append(
            f"| {row.get('taxonomy_type')} | {row.get('count')} | {row.get('governance_decision')} |"
        )
    if not matrix:
        lines.append("| — | 0 | awaiting human labels wave |")

    lines.extend(["", "## Next steps", ""])
    for step in cycle.get("next_steps_ar") or []:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def build_governance_intelligence_review(cycle: Dict[str, Any]) -> Dict[str, Any]:
    """Meeting pack for PHASE 2 moderation review — no fabricated decisions."""
    wave = cycle.get("pilot_wave_progress") or {}
    matrix = cycle.get("disagreement_taxonomy_matrix") or []
    classified = cycle.get("classified_mismatches") or []

    taxonomy_discussion = []
    for row in matrix:
        tax = row.get("taxonomy_type")
        taxonomy_discussion.append(
            {
                "taxonomy_type": tax,
                "count": row.get("count"),
                "governance_decision_proposed": row.get("governance_decision"),
                "discussion_questions_ar": _taxonomy_questions(tax),
                "institutional_decision": None,
                "institutional_decision_notes_ar": None,
                "signed_off_by": None,
            }
        )

    abdullah_pending: List[Dict[str, Any]] = []
    labels_path_str = cycle.get("_labels_path")
    if labels_path_str:
        labels_doc = _load_json(Path(labels_path_str))
        for rec in labels_doc.get("records") or []:
            if int(rec.get("submission_id") or 0) != 1:
                continue
            for key in ("P3", "P4", "P5", "P6", "P7", "M2", "M3", "D2", "D3"):
                row = (rec.get("criteria") or {}).get(key) or {}
                if row.get("decision") is None:
                    abdullah_pending.append(
                        {
                            "criterion": key,
                            "ai_system_achieved": row.get("ai_system_achieved"),
                            "status": "PENDING_TEACHER",
                        }
                    )

    return {
        "schema": "governance_intelligence_review_v1",
        "generated_at": _utc_now(),
        "run_id": cycle.get("run_id"),
        "status": "ready_for_meeting" if wave.get("pilot_ready") else "awaiting_pilot_wave",
        "description_ar": "حزمة اجتماع moderation review — قرارات المؤسسة تُملأ في الاجتماع",
        "attendees_required": [
            {"role": "teacher", "name": None, "present": None},
            {"role": "supervisor", "name": None, "present": None},
            {"role": "quality_officer", "name": None, "present": None},
        ],
        "pilot_wave_checklist": {
            "abdullah_complete": (wave.get("wave_1_abdullah") or {}).get("ready_for_cycle"),
            "top5_complete": (wave.get("wave_2_top5") or {}).get("fully_complete") == 5,
            "bottom5_complete": (wave.get("wave_3_bottom5") or {}).get("fully_complete") == 5,
            "pilot_ready": wave.get("pilot_ready"),
            "pilot_fully_complete": wave.get("pilot_fully_complete"),
            "pilot_cohort_size": wave.get("pilot_cohort_size"),
        },
        "reference_governance_case": {
            "submission_id": 1,
            "label": "Abdullah — First Fully Traceable Governance Case",
            "pending_criteria": abdullah_pending,
            "authority_chain_ar": [
                "runtime → operational proof",
                "replay → evidence / auditability",
                "governance → policy",
                "AI → recommendation",
                "human moderator → final authority",
            ],
        },
        "calibration_metrics": cycle.get("calibration_metrics"),
        "taxonomy_review": taxonomy_discussion,
        "case_discussions": [
            {
                "submission_id": m.get("submission_id"),
                "criterion": m.get("criterion"),
                "taxonomy_type": m.get("taxonomy_type"),
                "teacher_vs_system": {
                    "teacher": m.get("teacher_achieved"),
                    "system": m.get("system_achieved"),
                },
                "replay_verified": m.get("replay_verified"),
                "runtime_status": m.get("runtime_status"),
                "defensibility_question_ar": m.get("defensibility_question_ar"),
                "rationale_ar": m.get("rationale_ar"),
                "meeting_verdict_ar": None,
            }
            for m in classified
        ],
        "governance_evolution_decisions": [
            {
                "area": "submission_policy",
                "trigger": "no_runtime_build",
                "decision_ar": None,
                "owner": None,
            },
            {
                "area": "moderation_consistency",
                "trigger": "overall_grade_mismatch",
                "decision_ar": None,
                "owner": None,
            },
            {
                "area": "rubric_clarification",
                "trigger": "rubric_ambiguity",
                "decision_ar": None,
                "owner": None,
            },
            {
                "area": "threshold_tuning",
                "trigger": "ai_conservative",
                "decision_ar": None,
                "owner": None,
            },
        ],
        "core_question_ar": "عند الاختلاف — هل القرار defensible؟",
    }


def _taxonomy_questions(tax_type: Optional[str]) -> List[str]:
    mapping: Dict[str, List[str]] = {
        "no_runtime_build": [
            "هل submission policy واضحة للطلاب؟",
            "هل conservative grading صحيح بدون build؟",
        ],
        "overall_grade_mismatch": [
            "هل المعلم استخدم contextual judgment؟",
            "هل replay تدعم overall grade؟",
        ],
        "replay_insufficient": [
            "ما evidence ناقصة في replay؟",
            "هل audit trail كافٍ للاعتراض؟",
        ],
        "weak_evidence": [
            "هل AI overclaiming رغم evidence ضعيفة؟",
            "هل threshold يحتاج تشديد؟",
        ],
        "rubric_ambiguity": [
            "أي wording في rubric يسبب الاختلاف؟",
            "هل refinement مطلوب قبل pilot launch؟",
        ],
        "ai_conservative": [
            "هل conservatism مبرر أم مبالغ؟",
            "هل runtime كان سيغيّر القرار؟",
        ],
        "ai_overclaiming": [
            "هل FP خطر أكاديمي هنا؟",
            "هل governance tightening مطلوب؟",
        ],
    }
    return mapping.get(tax_type or "", ["هل الاختلاف مفهوم ويمكن الدفاع عنه؟"])


def write_governance_intelligence_review(
    review: Dict[str, Any],
    out_dir: Path,
) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "GOVERNANCE_INTELLIGENCE_REVIEW_v1.json"
    json_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = out_dir / "GOVERNANCE_INTELLIGENCE_REVIEW.md"
    md_path.write_text(_render_intelligence_md(review), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _render_intelligence_md(review: Dict[str, Any]) -> str:
    checklist = review.get("pilot_wave_checklist") or {}
    lines = [
        "# Governance Intelligence Review",
        "",
        f"Status: **{review.get('status')}**",
        "",
        "## Pilot wave checklist",
        "",
        f"- Abdullah complete: {checklist.get('abdullah_complete')}",
        f"- Top 5 complete: {checklist.get('top5_complete')}",
        f"- Bottom 5 complete: {checklist.get('bottom5_complete')}",
        f"- Pilot ready ({checklist.get('pilot_fully_complete')}/{checklist.get('pilot_cohort_size')}): {checklist.get('pilot_ready')}",
        "",
        f"**Core question:** {review.get('core_question_ar')}",
        "",
        "## Taxonomy review",
        "",
    ]
    for row in review.get("taxonomy_review") or []:
        lines.append(f"### {row.get('taxonomy_type')} ({row.get('count')})")
        lines.append(f"Proposed: {row.get('governance_decision_proposed')}")
        for q in row.get("discussion_questions_ar") or []:
            lines.append(f"- {q}")
        lines.append("")
    lines.append("## Case discussions")
    lines.append("")
    for case in review.get("case_discussions") or []:
        lines.append(
            f"- #{case.get('submission_id')} {case.get('criterion')}: "
            f"{case.get('taxonomy_type')} — teacher={case.get('teacher_vs_system', {}).get('teacher')} "
            f"system={case.get('teacher_vs_system', {}).get('system')}"
        )
    lines.append("")
    return "\n".join(lines)


def build_from_closure_reports(
    reports_dir: Path,
    *,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    disagreement = _load_json(reports_dir / "phase_a_disagreement.json")
    runtime = _load_json(reports_dir / "runtime_coverage_dashboard.json")
    labels_path = Path(disagreement.get("inputs", {}).get("human_labels", ""))
    labels_doc = _load_json(labels_path) if labels_path.exists() else {}
    cycle = build_governance_calibration_cycle(
        disagreement_report=disagreement,
        runtime_dashboard=runtime,
        labels_doc=labels_doc,
        run_id=run_id or disagreement.get("run_id"),
    )
    cycle["_labels_path"] = str(labels_path) if labels_path.exists() else None
    write_governance_calibration_artifacts(cycle, reports_dir)

    review = build_governance_intelligence_review(cycle)
    intel_paths = write_governance_intelligence_review(review, reports_dir)
    cycle.pop("_labels_path", None)

    cycle["governance_intelligence_review"] = intel_paths
    return cycle
