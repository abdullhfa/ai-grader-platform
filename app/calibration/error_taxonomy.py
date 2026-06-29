"""
Suggested error taxonomy tags for calibration review (heuristic, not ground truth).

Human reviewers should confirm / relabel in gold `reviewer_taxonomy` after review.
FP (system achieved, teacher not) is prioritized — higher academic risk than FN.

`evidence_density` supports per-system calibration (same model confidence can mean
different things for collision_system vs inventory_system).
`evidence_diversity_score` (per system) is normalized entropy over evidence_type counts
(code_system vs pattern_hint, etc.) — high density with low diversity still flags weak sufficiency potential.

`aggregate_fp_density_by_system` adds percentiles (incl. p5/p95) and coarse histograms so
FP analysis is not reduced to a single average — tail / bimodal risk stays visible.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple

from app.calibration.taxonomy_helpers import criteria_match

TAXONOMY_VERSION = "0.3"

# Heuristic priors for suggested tags (0–1); not empirical until measured on gold.
_TAG_CONFIDENCE_PRIOR: Mapping[str, float] = {
    "fp_system_achieved_teacher_not": 0.99,
    "fp_no_persisted_evidence_items_llm_may_have_overclaimed": 0.86,
    "fp_pattern_only_collision_hint": 0.54,
    "fp_collision_weak_execution_suspected": 0.63,
    "fp_strong_collision_signal_teacher_rejected_borderline": 0.48,
    "fp_inventory_signal_present_teacher_rejected": 0.58,
    "fn_teacher_achieved_system_not": 0.99,
    "fn_no_collision_semantic_in_evidence_layer": 0.72,
    "fn_only_weak_collision_signals": 0.66,
}


def _evidence_type_diversity(by_evidence_type: Mapping[str, Any]) -> tuple[int, float]:
    """Normalized Shannon entropy over evidence_type counts (0 = single-type only, 1 = uniform mix)."""
    counts = [int(c) for c in by_evidence_type.values() if int(c) > 0]
    k = len(counts)
    if k <= 1:
        return k, 0.0
    total = float(sum(counts))
    h = 0.0
    for c in counts:
        p = c / total
        h -= p * math.log2(p)
    max_h = math.log2(k)
    return k, round(h / max_h, 4) if max_h > 0 else 0.0


DENSITY_REPORT_SCHEMA = "fp_density_v2"


def _percentile_linear(sorted_vals: List[float], p: float) -> float:
    """p in [0, 100]. Linear interpolation between ranks (R-type)."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = (n - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    w = idx - lo
    return sorted_vals[lo] * (1 - w) + sorted_vals[hi] * w


def _percentile_summary(xs: List[float]) -> Optional[Dict[str, float]]:
    if not xs:
        return None
    ys = sorted(xs)
    return {
        f"p{int(p)}": round(_percentile_linear(ys, float(p)), 4)
        for p in (5, 10, 25, 50, 75, 90, 95)
    }


def _histogram_int_bins(values: List[int], bin_specs: List[Tuple[int, Optional[int], str]]) -> List[Dict[str, Any]]:
    """
    bin_specs: (lo inclusive, hi exclusive or None for infinity) -> label
    """
    out_list: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for lo, hi, label in bin_specs:
        counts[label] = 0
    for v in values:
        placed = False
        for lo, hi, label in bin_specs:
            if hi is None:
                if v >= lo:
                    counts[label] += 1
                    placed = True
                    break
            elif lo <= v < hi:
                counts[label] += 1
                placed = True
                break
        if not placed:
            counts[bin_specs[-1][2]] += 1
    for lo, hi, label in bin_specs:
        out_list.append({"bin": label, "count": counts[label]})
    return out_list


def _histogram_float_bins(values: List[float], bin_specs: List[Tuple[float, float, str]]) -> List[Dict[str, Any]]:
    out_list: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {lab: 0 for _, _, lab in bin_specs}
    for v in values:
        placed = False
        for lo, hi, lab in bin_specs:
            if lo <= v < hi:
                counts[lab] += 1
                placed = True
                break
        if not placed and bin_specs:
            counts[bin_specs[-1][2]] += 1
    for _, _, lab in bin_specs:
        out_list.append({"bin": lab, "count": counts[lab]})
    return out_list


_COUNT_BINS: List[Tuple[int, Optional[int], str]] = [
    (0, 1, "0"),
    (1, 2, "1"),
    (2, 4, "2-3"),
    (4, 8, "4-7"),
    (8, 16, "8-15"),
    (16, None, "16+"),
]

_CONF_BINS: List[Tuple[float, float, str]] = [
    (0.0, 0.5, "[0.0,0.5)"),
    (0.5, 0.7, "[0.5,0.7)"),
    (0.7, 0.8, "[0.7,0.8)"),
    (0.8, 0.9, "[0.8,0.9)"),
    (0.9, 1.0001, "[0.9,1.0]"),
]

_DIV_BINS: List[Tuple[float, float, str]] = [
    (0.0, 0.25, "[0,0.25)"),
    (0.25, 0.5, "[0.25,0.5)"),
    (0.5, 0.75, "[0.5,0.75)"),
    (0.75, 1.0001, "[0.75,1.0]"),
]


def compute_evidence_density(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize how many evidence_layer rows and underlying signals exist per `system`.
    Uses extractor `evidence_count` and source list lengths where present.
    """
    items = _evidence_items(snapshot)
    by_system: Dict[str, MutableMapping[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        sk = str(it.get("system") or "_unscoped")
        row = by_system.setdefault(
            sk,
            {
                "item_row_count": 0,
                "by_evidence_type": {},
                "evidence_count_sum": 0,
                "sources_len_sum": 0,
                "confidences": [],
            },
        )
        row["item_row_count"] = int(row["item_row_count"]) + 1
        et = str(it.get("evidence_type") or "unknown")
        bet = row["by_evidence_type"]
        bet[et] = int(bet.get(et, 0)) + 1
        ec = it.get("evidence_count")
        if isinstance(ec, (int, float)):
            row["evidence_count_sum"] = int(row["evidence_count_sum"]) + int(ec)
        src = it.get("sources") or []
        if isinstance(src, list):
            row["sources_len_sum"] = int(row["sources_len_sum"]) + len(src)
        conf = it.get("confidence")
        if isinstance(conf, (int, float)):
            row["confidences"].append(float(conf))

    by_system_out: Dict[str, Any] = {}
    for key, row in by_system.items():
        confs: List[float] = list(row.pop("confidences") or [])
        bet = row.get("by_evidence_type") or {}
        kind_count, div_score = _evidence_type_diversity(bet)
        by_system_out[key] = {
            **row,
            "evidence_type_kind_count": kind_count,
            "evidence_diversity_score": div_score,
            "max_confidence": max(confs) if confs else None,
            "mean_confidence": round(sum(confs) / len(confs), 4) if confs else None,
        }

    return {
        "total_item_rows": len(items),
        "by_system": by_system_out,
    }


def aggregate_fp_density_by_system(fp_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Distribution of evidence density across false-positive rows, broken down by
    `system` keys in evidence_density.by_system (collision_system vs inventory_system, etc.).
    """
    total_fp = len(fp_rows)
    empty_evidence = 0
    accum: Dict[str, Dict[str, List[Any]]] = {}

    for r in fp_rows:
        dens = (r.get("taxonomy_suggestion") or {}).get("evidence_density") or {}
        if int(dens.get("total_item_rows") or 0) == 0:
            empty_evidence += 1
        by_sys = dens.get("by_system") or {}
        for sys_key, sys_stats in by_sys.items():
            if not isinstance(sys_stats, dict):
                continue
            bucket = accum.setdefault(
                sys_key,
                {
                    "item_row_counts": [],
                    "evidence_count_sums": [],
                    "sources_len_sums": [],
                    "max_confidences": [],
                    "mean_confidences": [],
                    "diversity_scores": [],
                },
            )
            bucket["item_row_counts"].append(int(sys_stats.get("item_row_count") or 0))
            bucket["evidence_count_sums"].append(int(sys_stats.get("evidence_count_sum") or 0))
            bucket["sources_len_sums"].append(int(sys_stats.get("sources_len_sum") or 0))
            mc = sys_stats.get("max_confidence")
            if isinstance(mc, (int, float)):
                bucket["max_confidences"].append(float(mc))
            mnc = sys_stats.get("mean_confidence")
            if isinstance(mnc, (int, float)):
                bucket["mean_confidences"].append(float(mnc))
            dv = sys_stats.get("evidence_diversity_score")
            if isinstance(dv, (int, float)):
                bucket["diversity_scores"].append(float(dv))

    def _mean(xs: List[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 4) if xs else None

    by_system_report: List[Dict[str, Any]] = []
    for sys_key in sorted(accum.keys()):
        b = accum[sys_key]
        n = len(b["item_row_counts"])
        ics = b["item_row_counts"]
        ecs = b["evidence_count_sums"]
        sls = b["sources_len_sums"]
        by_system_report.append(
            {
                "system": sys_key,
                "fp_rows_with_evidence_for_system": n,
                "false_positives_total_in_run": total_fp,
                "mean_item_row_count": _mean([float(x) for x in ics]),
                "mean_evidence_count_sum": _mean([float(x) for x in ecs]),
                "mean_sources_len_sum": _mean([float(x) for x in sls]),
                "mean_max_confidence": _mean(b["max_confidences"]),
                "mean_mean_confidence": _mean(b["mean_confidences"]),
                "mean_evidence_diversity_score": _mean(b["diversity_scores"]),
                "percentiles": {
                    "item_row_count": _percentile_summary([float(x) for x in ics]),
                    "evidence_count_sum": _percentile_summary([float(x) for x in ecs]),
                    "sources_len_sum": _percentile_summary([float(x) for x in sls]),
                    "max_confidence": _percentile_summary(b["max_confidences"]),
                    "mean_confidence": _percentile_summary(b["mean_confidences"]),
                    "evidence_diversity_score": _percentile_summary(b["diversity_scores"]),
                },
                "histograms": {
                    "item_row_count": _histogram_int_bins(list(ics), _COUNT_BINS),
                    "evidence_count_sum": _histogram_int_bins(list(ecs), _COUNT_BINS),
                    "max_confidence": _histogram_float_bins(b["max_confidences"], _CONF_BINS)
                    if b["max_confidences"]
                    else [],
                    "evidence_diversity_score": _histogram_float_bins(b["diversity_scores"], _DIV_BINS)
                    if b["diversity_scores"]
                    else [],
                },
            }
        )

    fp_empty_ratio = round(empty_evidence / total_fp, 4) if total_fp else None

    return {
        "schema": DENSITY_REPORT_SCHEMA,
        "false_positives_total": total_fp,
        "fp_rows_with_empty_evidence_layer": empty_evidence,
        "fp_empty_evidence_layer_ratio": fp_empty_ratio,
        "by_system": by_system_report,
        "interpretation_notes": [
            "Percentiles (incl. p5/p95) surface tail risk; means can hide bimodal or rare catastrophic FP.",
            "Histogram bins are coarse defaults; adjust as N grows.",
            "Correlate with gold review_complexity; narrow samples (one teacher, one difficulty band) bias calibration.",
        ],
    }


def _taxonomy_tag_confidence(tags: List[str], evidence_density: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    total_rows = int(evidence_density.get("total_item_rows") or 0)
    for t in tags:
        base = float(_TAG_CONFIDENCE_PRIOR.get(t, 0.5))
        if t == "fp_no_persisted_evidence_items_llm_may_have_overclaimed":
            base = 0.9 if total_rows == 0 else 0.35
        if t == "fp_pattern_only_collision_hint":
            base -= 0.03 if total_rows >= 4 else 0.0
        out[t] = round(min(1.0, max(0.0, base)), 2)
    return out


def _criterion_implies_collision_heuristic(gold_crit: str) -> bool:
    """Unity L3 exemplar: P3 is gameplay/collision-heavy; avoid mis-tagging M1 etc."""
    c = (gold_crit or "").strip().upper()
    return c == "P3" or c.endswith(".P3")


def _criterion_snapshot_row(snapshot: Dict[str, Any], gold_crit: str) -> Dict[str, Any]:
    for cr in snapshot.get("criteria_results") or []:
        if isinstance(cr, dict) and criteria_match(str(cr.get("criteria_level") or ""), gold_crit):
            return cr
    return {}


def _evidence_items(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    el = snapshot.get("evidence_layer") or {}
    return list(el.get("items") or [])


def suggest_mismatch_tags(
    teacher_achieved: bool,
    system_achieved: bool,
    snapshot: Dict[str, Any],
    gold_crit: str,
) -> Dict[str, Any]:
    """
    Return suggested taxonomy strings + evidence cues for one compared row.
    Empty tags if teacher/system agree.
    """
    evidence_density = compute_evidence_density(snapshot)
    if teacher_achieved == system_achieved:
        return {
            "taxonomy_version": TAXONOMY_VERSION,
            "suggested_tags": [],
            "kind": "match",
            "evidence_density": evidence_density,
            "taxonomy_tag_confidence": {},
        }

    items = _evidence_items(snapshot)
    cr = _criterion_snapshot_row(snapshot, gold_crit)

    tags: List[str] = []
    kind = "false_positive" if (not teacher_achieved and system_achieved) else "false_negative"

    def _find_system(name: str) -> List[Dict[str, Any]]:
        return [
            it
            for it in items
            if it.get("evidence_type") == "code_system" and it.get("system") == name
        ]

    collision_scoped = _criterion_implies_collision_heuristic(gold_crit)
    collision_items = _find_system("collision_system") if collision_scoped else []
    inv_items = _find_system("inventory_system") if collision_scoped else []

    if kind == "false_positive":
        tags.append("fp_system_achieved_teacher_not")
        if collision_scoped:
            if collision_items:
                ev = max(
                    (str(x.get("execution_evidence") or "unknown").lower() for x in collision_items),
                    key=lambda x: {"strong": 3, "medium": 2, "weak": 1, "unknown": 0}.get(x, 0),
                )
                if ev == "weak":
                    tags.append("fp_collision_weak_execution_suspected")
                elif ev in ("medium", "strong"):
                    tags.append("fp_strong_collision_signal_teacher_rejected_borderline")
            else:
                has_pattern_collision = any(
                    it.get("evidence_type") == "pattern_hint" and it.get("system") == "collision_system"
                    for it in items
                )
                if has_pattern_collision:
                    tags.append("fp_pattern_only_collision_hint")
            if inv_items:
                tags.append("fp_inventory_signal_present_teacher_rejected")
        # LLM may have over-achieved vs deterministic evidence
        if not items and system_achieved:
            tags.append("fp_no_persisted_evidence_items_llm_may_have_overclaimed")
    else:
        tags.append("fn_teacher_achieved_system_not")
        if collision_scoped:
            if not collision_items:
                tags.append("fn_no_collision_semantic_in_evidence_layer")
            elif all(str(x.get("execution_evidence")).lower() == "weak" for x in collision_items):
                tags.append("fn_only_weak_collision_signals")

    reason_preview = ""
    if isinstance(cr, dict):
        reason_preview = str(cr.get("reasoning") or "")[:280]

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "kind": kind,
        "suggested_tags": tags,
        "taxonomy_tag_confidence": _taxonomy_tag_confidence(tags, evidence_density),
        "evidence_density": evidence_density,
        "criterion": gold_crit,
        "system_reasoning_preview": reason_preview,
    }


def merge_taxonomy_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate tag counts from per-row suggestion dicts (key 'suggested_tags')."""
    from collections import Counter

    c: Counter = Counter()
    for r in rows:
        for t in r.get("suggested_tags") or []:
            c[t] += 1
    return dict(c.most_common())
