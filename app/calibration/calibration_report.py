"""
Build full large-scale calibration report (teacher vs system + shadow dashboards).

Read-only — does not modify thresholds or achieved logic.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.calibration.error_taxonomy import (
    DENSITY_REPORT_SCHEMA,
    TAXONOMY_VERSION,
    aggregate_fp_density_by_system,
    merge_taxonomy_counts,
    suggest_mismatch_tags,
)
from app.calibration.reliability_shadow_metrics import (
    SHADOW_METRICS_SCHEMA,
    build_shadow_metrics_block,
    extract_row_shadow_signals,
)
from app.calibration.taxonomy_helpers import criteria_match


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_gold_records(gold_path: Path) -> Tuple[Any, List[Dict[str, Any]]]:
    data = load_json(gold_path)
    if isinstance(data, dict) and "records" in data:
        return data, list(data["records"])
    if isinstance(data, list):
        return {"schema": "bare_list", "records": data}, data
    raise ValueError("gold file must contain {records: [...]} or be a bare list")


def index_system_by_submission(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict) and "submissions" in raw:
        return {str(k): v for k, v in raw["submissions"].items()}
    if isinstance(raw, list):
        out: Dict[str, Any] = {}
        for row in raw:
            sid = str(row.get("submission_id") or row.get("id") or "")
            if sid:
                out[sid] = row
        return out
    raise ValueError("system JSON must be {submissions:{...}} or list of rows with submission_id")


def system_achieved_for_criterion(snapshot: Dict[str, Any], gold_crit: str) -> Optional[bool]:
    for cr in snapshot.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        lvl = str(cr.get("criteria_level") or "")
        if criteria_match(lvl, gold_crit):
            return bool(cr.get("achieved"))
    return None


def compute_confusion(pairs: List[Tuple[bool, bool]]) -> Tuple[int, int, int, int]:
    tp = fp = fn = tn = 0
    for t, s in pairs:
        if t and s:
            tp += 1
        elif not t and s:
            fp += 1
        elif t and not s:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def cohens_kappa(pairs: List[Tuple[bool, bool]]) -> Optional[float]:
    """Cohen's Kappa for binary achieved agreement (teacher vs system)."""
    if not pairs:
        return None
    n = len(pairs)
    po = sum(1 for t, s in pairs if t == s) / n
    p_t_yes = sum(1 for t, _ in pairs if t) / n
    p_s_yes = sum(1 for _, s in pairs if s) / n
    pe = p_t_yes * p_s_yes + (1 - p_t_yes) * (1 - p_s_yes)
    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 4)


def pick_meta(cli_val: Optional[str], env_key: str) -> Optional[str]:
    v = (cli_val or "").strip()
    if v:
        return v
    ev = os.environ.get(env_key)
    return ev.strip() if ev else None


def build_reliability_run_metadata(
    *,
    gold_path: Path,
    systems_path: Path,
    gold_file_top: Any,
    run_id: Optional[str],
    rubric_version: Optional[str],
    extractor_version: Optional[str],
    freeze_window_id: Optional[str],
) -> Dict[str, Any]:
    gold_schema = None
    synthetic = None
    if isinstance(gold_file_top, dict):
        gold_schema = gold_file_top.get("schema")
        synthetic = gold_file_top.get("synthetic")

    return {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "run_id": run_id,
        "freeze_window_id": freeze_window_id,
        "rubric_version": rubric_version,
        "extractor_version": extractor_version,
        "inputs": {
            "gold_path": str(gold_path),
            "systems_path": str(systems_path),
        },
        "gold_dataset_schema": gold_schema,
        "gold_dataset_synthetic": synthetic,
        "report_schemas": {
            "false_positive_density": DENSITY_REPORT_SCHEMA,
            "taxonomy_suggestions": TAXONOMY_VERSION,
            "shadow_metrics": SHADOW_METRICS_SCHEMA,
        },
        "calibration_policy": {
            "shadow_drives_achieved": False,
            "analyze_false_positives_first": True,
            "threshold_changes_allowed_in_run": False,
        },
        "temporal_diff_hint": "Diff reliability_run + metrics + shadow_dashboard across run_id within same freeze_window.",
    }


def build_calibration_report(
    gold_path: Path,
    systems_path: Path,
    *,
    run_id: Optional[str] = None,
    rubric_version: Optional[str] = None,
    extractor_version: Optional[str] = None,
    freeze_window_id: Optional[str] = None,
) -> Dict[str, Any]:
    gold_top, gold_rows = load_gold_records(gold_path)
    sys_map = index_system_by_submission(load_json(systems_path))

    evaluated: List[Dict[str, Any]] = []
    shadow_rows: List[Dict[str, Any]] = []
    pairs: List[Tuple[bool, bool]] = []
    missing_system: List[str] = []
    missing_criterion: List[str] = []

    for row in gold_rows:
        sid = str(row.get("submission_id") or "")
        crit = str(row.get("criterion") or "")
        tr = row.get("teacher_result") or {}
        t_ach = bool(tr.get("achieved"))

        snap = sys_map.get(sid)
        if not snap:
            missing_system.append(f"{sid}/{crit}")
            continue
        s_ach = system_achieved_for_criterion(snap, crit)
        if s_ach is None:
            missing_criterion.append(f"{sid}/{crit}")
            continue

        pairs.append((t_ach, s_ach))
        tax = suggest_mismatch_tags(t_ach, s_ach, snap, crit)
        shadow = extract_row_shadow_signals(snap, crit)
        shadow_rows.append(shadow)

        shadow_gold_row = {
            **shadow,
            "submission_id": sid,
            "criterion": crit,
            "teacher_achieved": t_ach,
            "teacher_evidence_strength": row.get("teacher_evidence_strength"),
            "review_complexity": row.get("review_complexity"),
            "reviewer_taxonomy": row.get("reviewer_taxonomy"),
            "teacher_notes": row.get("teacher_notes"),
            "accepted_evidence": row.get("accepted_evidence"),
            "rejected_evidence": row.get("rejected_evidence"),
        }

        evaluated.append(
            {
                "submission_id": sid,
                "criterion": crit,
                "teacher_achieved": t_ach,
                "system_achieved": s_ach,
                "match": t_ach == s_ach,
                "teacher_confidence": tr.get("confidence"),
                "teacher_evidence_strength": row.get("teacher_evidence_strength"),
                "review_complexity": row.get("review_complexity"),
                "reviewer_taxonomy": row.get("reviewer_taxonomy"),
                "teacher_notes": row.get("teacher_notes"),
                "accepted_evidence": row.get("accepted_evidence"),
                "rejected_evidence": row.get("rejected_evidence"),
                "taxonomy_suggestion": tax,
                "shadow_signals": shadow,
            }
        )

    tp, fp, fn, tn = compute_confusion(pairs)
    denom_p = tp + fp
    denom_r = tp + fn
    precision = tp / denom_p if denom_p else 0.0
    recall = tp / denom_r if denom_r else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    kappa = cohens_kappa(pairs)
    accuracy = (tp + tn) / len(pairs) if pairs else None

    mismatch_tax_blocks = [r["taxonomy_suggestion"] for r in evaluated if r["taxonomy_suggestion"].get("suggested_tags")]
    fp_rows = [r for r in evaluated if (not r["teacher_achieved"]) and r["system_achieved"]]
    fn_rows = [r for r in evaluated if r["teacher_achieved"] and (not r["system_achieved"])]

    gold_for_shadow = [
        {
            **r,
            "rubric_shadow_sufficient": (r.get("shadow_signals") or {}).get(
                "rubric_shadow_sufficient"
            ),
        }
        for r in evaluated
    ]
    shadow_block = build_shadow_metrics_block(shadow_rows, gold_evaluated=gold_for_shadow)

    reviewer_taxonomy_counts: Dict[str, int] = {}
    from collections import Counter

    rtc: Counter = Counter()
    for r in evaluated:
        for t in r.get("reviewer_taxonomy") or []:
            rtc[str(t)] += 1
    reviewer_taxonomy_counts = dict(rtc.most_common(30))

    complexity_counts: Dict[str, int] = {}
    cc: Counter = Counter()
    for r in evaluated:
        rc = r.get("review_complexity")
        if rc:
            cc[str(rc)] += 1
    complexity_counts = dict(cc)

    return {
        "reliability_run": build_reliability_run_metadata(
            gold_path=gold_path,
            systems_path=systems_path,
            gold_file_top=gold_top,
            run_id=run_id,
            rubric_version=rubric_version,
            extractor_version=extractor_version,
            freeze_window_id=freeze_window_id,
        ),
        "cohort_summary": {
            "rows_gold": len(gold_rows),
            "pairs_compared": len(pairs),
            "missing_system_snapshot": len(missing_system),
            "missing_criterion_in_system": len(missing_criterion),
            "unique_submissions_gold": len({str(r.get("submission_id")) for r in gold_rows}),
            "unique_submissions_matched": len({r["submission_id"] for r in evaluated}),
        },
        "metrics": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "cohens_kappa": kappa,
            "precision_achieved_class": round(precision, 4),
            "recall_achieved_class": round(recall, 4),
            "f1_achieved_class": round(f1, 4),
            "false_positive_rate": round(fp / len(pairs), 4) if pairs else None,
            "false_negative_rate": round(fn / len(pairs), 4) if pairs else None,
        },
        "calibration_priority": {
            "analyze_false_positives_first": True,
            "rationale": "System awarding a criterion the teacher rejected is higher academic risk than withholding.",
        },
        "error_taxonomy_suggested_counts": merge_taxonomy_counts(mismatch_tax_blocks),
        "reviewer_taxonomy_confirmed_counts": reviewer_taxonomy_counts,
        "review_complexity_distribution": complexity_counts,
        "false_positive_density_report": aggregate_fp_density_by_system(fp_rows),
        "shadow_dashboard": shadow_block,
        "human_reviewer_agreement_notes": {
            "description": "Compare reviewer_taxonomy on FP/FN rows with taxonomy_suggestion; high divergence may indicate human inconsistency.",
            "rows_with_reviewer_taxonomy": sum(1 for r in evaluated if r.get("reviewer_taxonomy")),
        },
        "false_positive_rows": fp_rows,
        "false_negative_rows": fn_rows,
        "missing_system_snapshot": missing_system,
        "missing_criterion_in_system": missing_criterion,
        "per_row": evaluated,
    }
