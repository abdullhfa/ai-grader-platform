"""
Disagreement report — criterion/replay/runtime/evidence mismatches.

Builds on calibration_report + optional runtime cohort report.
Read-only — does not modify grades.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.calibration.calibration_report import build_calibration_report
from app.calibration.human_labels_io import export_gold_from_human_labels, load_human_labels
from app.calibration.taxonomy_helpers import criteria_match


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _system_achieved(snapshot: Dict[str, Any], criterion: str) -> Optional[bool]:
    for cr in snapshot.get("criteria_results") or []:
        if isinstance(cr, dict) and criteria_match(str(cr.get("criteria_level") or ""), criterion):
            return bool(cr.get("achieved"))
    return None


def _runtime_signals(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    inv = snapshot.get("artifact_inventory") or {}
    ror = inv.get("runtime_observation_report") or {}
    return {
        "runtime_status": ror.get("status"),
        "runtime_verified": ror.get("runtime_verified"),
        "human_playtest_verified": ror.get("human_playtest_verified"),
        "executable_count": (inv.get("executable_artifacts") or {}).get("count"),
        "runtime_evidence_level": (inv.get("runtime_evidence_level") or {}).get("level")
        if isinstance(inv.get("runtime_evidence_level"), dict)
        else inv.get("runtime_evidence_level"),
    }


def _replay_signals(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    from app.academic_event_replay import build_academic_timeline_replay
    from app.deterministic_replay_engine import verify_deterministic_replay

    timeline = build_academic_timeline_replay(snapshot)
    verification = verify_deterministic_replay(timeline.get("events") or [], snapshot)
    return {
        "timeline_source": timeline.get("source"),
        "replay_verified": verification.get("replay_verified"),
        "protected_digest_match": verification.get("protected_digest_match"),
        "semantic_replay_verified": verification.get("semantic_replay_verified"),
        "grade_level_replayed": (verification.get("state_summary") or {}).get("grade_level"),
    }


def _evidence_signals(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    gate = snapshot.get("evidence_completeness_gate") or {}
    rel = snapshot.get("ai_reliability") or {}
    return {
        "has_gaps": gate.get("has_gaps"),
        "missing_artifacts": gate.get("missing_artifacts") or [],
        "hallucination_risk": rel.get("hallucination_risk"),
        "ai_confidence": rel.get("confidence_score"),
    }


def build_disagreement_report(
    *,
    human_labels_path: Path,
    systems_path: Path,
    cohort_report_path: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    gold_export = export_gold_from_human_labels(
        human_labels_path,
        human_labels_path.with_suffix(".gold_export.json"),
    )
    gold_path = human_labels_path.with_suffix(".gold_export.json")

    calibration = build_calibration_report(gold_path, systems_path, run_id=run_id)

    with open(systems_path, encoding="utf-8") as f:
        systems_raw = json.load(f)
    sys_map = systems_raw.get("submissions") or {}

    labels_doc = load_human_labels(human_labels_path)
    criterion_mismatches: List[Dict[str, Any]] = []
    replay_mismatches: List[Dict[str, Any]] = []
    runtime_mismatches: List[Dict[str, Any]] = []
    evidence_flags: List[Dict[str, Any]] = []

    for rec in labels_doc.get("records") or []:
        sid = str(rec.get("submission_id") or "")
        snap = sys_map.get(sid)
        if not snap:
            continue

        replay = _replay_signals(snap)
        if not replay.get("replay_verified"):
            replay_mismatches.append({"submission_id": sid, **replay})

        runtime = _runtime_signals(snap)
        if runtime.get("executable_count") and runtime.get("runtime_status") not in (
            "completed",
            "partial",
        ):
            runtime_mismatches.append({"submission_id": sid, **runtime})

        evidence = _evidence_signals(snap)
        if evidence.get("has_gaps") or evidence.get("hallucination_risk") in ("high", "medium"):
            evidence_flags.append({"submission_id": sid, **evidence})

        criteria = rec.get("criteria") or {}
        if isinstance(criteria, dict):
            for crit_key, crit_row in criteria.items():
                if not isinstance(crit_row, dict):
                    continue
                decision = crit_row.get("decision")
                if decision is None:
                    continue
                teacher = str(decision).lower() in ("achieved", "pass", "yes", "true")
                system = _system_achieved(snap, str(crit_key))
                if system is None:
                    continue
                if teacher != system:
                    criterion_mismatches.append(
                        {
                            "submission_id": sid,
                            "criterion": crit_key,
                            "teacher_achieved": teacher,
                            "system_achieved": system,
                            "teacher_confidence": crit_row.get("confidence"),
                            "notes": crit_row.get("notes"),
                            "replay_verified": replay.get("replay_verified"),
                            "runtime_status": runtime.get("runtime_status"),
                            "hallucination_risk": evidence.get("hallucination_risk"),
                        }
                    )

        overall_teacher = rec.get("overall_grade")
        overall_system = snap.get("grade_level")
        if overall_teacher and overall_system and str(overall_teacher).upper() != str(overall_system).upper():
            criterion_mismatches.append(
                {
                    "submission_id": sid,
                    "criterion": "__overall_grade__",
                    "teacher_achieved": overall_teacher,
                    "system_achieved": overall_system,
                    "mismatch_type": "overall_grade_level",
                }
            )

    metrics = calibration.get("metrics") or {}
    tp, fp, fn, tn = (
        metrics.get("true_positives", 0),
        metrics.get("false_positives", 0),
        metrics.get("false_negatives", 0),
        metrics.get("true_negatives", 0),
    )
    evaluated = tp + fp + fn + tn
    agreement = (tp + tn) / evaluated if evaluated else None

    report: Dict[str, Any] = {
        "report_type": "disagreement_report_v1",
        "generated_at": _utc_now(),
        "run_id": run_id,
        "inputs": {
            "human_labels": str(human_labels_path),
            "systems": str(systems_path),
            "cohort_report": str(cohort_report_path) if cohort_report_path else None,
        },
        "summary": {
            "agreement_rate": agreement,
            "cohens_kappa": metrics.get("cohens_kappa"),
            "weighted_rubric_accuracy": metrics.get("accuracy"),
            "false_positives": fp,
            "false_negatives": fn,
            "ai_overclaim_rate": metrics.get("false_positive_rate"),
            "criterion_mismatch_count": len(criterion_mismatches),
            "replay_mismatch_count": len(replay_mismatches),
            "runtime_mismatch_count": len(runtime_mismatches),
            "evidence_flag_count": len(evidence_flags),
            "gold_rows_used": gold_export.get("record_count", 0),
        },
        "calibration": calibration,
        "criterion_mismatches": criterion_mismatches,
        "replay_mismatches": replay_mismatches,
        "runtime_mismatches": runtime_mismatches,
        "evidence_flags": evidence_flags,
        "confidence_mismatches": [
            m
            for m in criterion_mismatches
            if m.get("teacher_confidence") is not None and m.get("teacher_confidence", 1) < 0.7
        ],
    }

    if cohort_report_path and cohort_report_path.exists():
        try:
            cohort = json.loads(cohort_report_path.read_text(encoding="utf-8"))
            report["cohort_summary"] = cohort.get("summary")
        except (OSError, json.JSONDecodeError):
            pass

    return report
