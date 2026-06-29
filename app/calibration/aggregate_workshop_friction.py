"""
Aggregate filled Human Review Workshop responses — friction tags and answer distributions.

Usage (after reviewers fill reliability_review_workshop_v1.json):
  python -m app.calibration.aggregate_workshop_friction \\
    --workshop app/calibration/workshop/reliability_review_workshop_v1.json \\
    --out app/calibration/workshop/workshop_synthesis_v1.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

# On a ~14-row workshop: 1–2 mentions = anecdote; 4+ = actionable cluster (tune with cohort size)
_ACTIONABLE_TAG_MIN_COUNT = 4
_ACTIONABLE_TAG_MIN_SHARE = 0.35


def _answers_by_question(cases: List[Dict[str, Any]]) -> Dict[str, Counter]:
    out: Dict[str, Counter] = {}
    for case in cases:
        for q in case.get("structured_review") or []:
            qid = str(q.get("id") or "")
            ans = q.get("answer")
            if not qid:
                continue
            out.setdefault(qid, Counter())
            if ans is None or (isinstance(ans, str) and not ans.strip()):
                out[qid]["(unanswered)"] += 1
            else:
                out[qid][str(ans)] += 1
    return out


def aggregate(workshop: Dict[str, Any]) -> Dict[str, Any]:
    cases = list(workshop.get("cases") or [])
    friction_tags: Counter = Counter()
    archetype_by_tag: Dict[str, List[str]] = {}
    incomplete_rows: List[int] = []
    partial_or_no_auditable: List[Dict[str, Any]] = []

    for case in cases:
        row = int(case.get("workshop_row") or 0)
        ctx = case.get("context") or {}
        arch = ctx.get("archetype") or "unknown"
        tags = case.get("operational_friction_tags") or []
        if not tags:
            incomplete_rows.append(row)
        for t in tags:
            t = str(t).strip()
            if not t:
                continue
            friction_tags[t] += 1
            archetype_by_tag.setdefault(t, [])
            if arch not in archetype_by_tag[t]:
                archetype_by_tag[t].append(arch)

        answers = {str(q.get("id")): q.get("answer") for q in (case.get("structured_review") or [])}
        aud = answers.get("behavior_auditable")
        if aud in ("no", "partial", "unclear"):
            partial_or_no_auditable.append(
                {
                    "workshop_row": row,
                    "archetype": arch,
                    "behavior_auditable": aud,
                    "severity": ctx.get("human_review_severity"),
                    "reasons": ctx.get("human_review_reasons"),
                }
            )

    answer_dist = {
        qid: dict(cnt) for qid, cnt in _answers_by_question(cases).items()
    }

    top_friction = friction_tags.most_common(15)
    n_cases = max(1, len(cases))
    actionable_clusters: List[Dict[str, Any]] = []
    anecdote_only: List[Dict[str, Any]] = []
    for tag, count in top_friction:
        share = round(count / n_cases, 4)
        row = {
            "tag": tag,
            "count": count,
            "share_of_workshop_rows": share,
            "archetypes": archetype_by_tag.get(tag, []),
        }
        if count >= _ACTIONABLE_TAG_MIN_COUNT or share >= _ACTIONABLE_TAG_MIN_SHARE:
            actionable_clusters.append({**row, "verdict": "actionable_cluster"})
        else:
            anecdote_only.append({**row, "verdict": "anecdote_ignore_for_now"})

    suggested_run3_focus: List[str] = []
    if actionable_clusters:
        top = actionable_clusters[0]
        suggested_run3_focus.append(
            f"Pick ONE friction cluster for Run3: '{top['tag']}' "
            f"({top['count']}/{n_cases} rows, share={top['share_of_workshop_rows']}). "
            "Single-intent interpretability refinement only."
        )
    elif friction_tags:
        suggested_run3_focus.append(
            "No tag reached actionable frequency yet — complete more rows or do not open Run3."
        )
    if partial_or_no_auditable:
        suggested_run3_focus.append(
            f"{len(partial_or_no_auditable)} row(s) marked behavior_auditable as no/partial/unclear — review before Run3."
        )

    unanswered_total = sum(
        cnt.get("(unanswered)", 0) for cnt in answer_dist.values()
    )
    workshop_complete = len(cases) > 0 and not incomplete_rows and unanswered_total == 0
    governance_signal_valid = workshop_complete

    if not workshop_complete:
        operational_status = "workshop_incomplete"
        governance_decision = None
    elif len(actionable_clusters) == 0:
        operational_status = "hold_recommended"
        governance_decision = "HOLD"
    elif len(actionable_clusters) == 1:
        operational_status = "run3_candidate"
        governance_decision = "smallest_justified_Run3"
    else:
        operational_status = "multiple_clusters_review"
        governance_decision = "do_not_rush_change"

    return {
        "schema": "workshop_friction_synthesis_v1",
        "source_workshop": workshop.get("source_report"),
        "calibration_run_id": workshop.get("calibration_run_id"),
        "workshop_complete": workshop_complete,
        "governance_signal_valid": governance_signal_valid,
        "operational_status": operational_status,
        "governance_decision": governance_decision,
        "rows_in_workshop": len(cases),
        "rows_missing_friction_tags": incomplete_rows,
        "rows_unanswered_review_questions": unanswered_total,
        "friction_tag_counts": dict(friction_tags),
        "friction_tag_by_archetype": archetype_by_tag,
        "top_friction_tags": [{"tag": t, "count": c} for t, c in top_friction],
        "friction_frequency_policy": {
            "actionable_min_count": _ACTIONABLE_TAG_MIN_COUNT,
            "actionable_min_share": _ACTIONABLE_TAG_MIN_SHARE,
            "rule": "Prefer frequency over first complaint; ignore tags below threshold for Run3.",
        },
        "actionable_friction_clusters": actionable_clusters,
        "anecdote_friction_tags": anecdote_only,
        "answer_distributions": answer_dist,
        "not_fully_auditable_rows": partial_or_no_auditable,
        "suggested_run3_focus": suggested_run3_focus,
        "post_workshop_discipline": {
            "pick_friction_points": "1-2 maximum",
            "change_type": "interpretability refinement only (reasoning merge, severity calm, flag dedup)",
            "then": "freeze → run_reliability_stress_cycle → calibration_diff",
            "avoid": [
                "shadow_to_achieved",
                "major_architecture",
                "threshold_bundle_changes",
            ],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate workshop friction tags")
    ap.add_argument("--workshop", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.workshop.is_file():
        print(f"workshop not found: {args.workshop}", file=sys.stderr)
        return 1

    workshop = json.loads(args.workshop.read_text(encoding="utf-8"))
    synthesis = aggregate(workshop)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(synthesis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    status = synthesis.get("operational_status") or "unknown"
    print(f"operational_status={status} governance_signal_valid={synthesis.get('governance_signal_valid')}")

    if status == "workshop_incomplete":
        print("NOT HOLD / NOT Run3 — complete reliability_review_workshop_v1.json first.")
        missing = synthesis.get("rows_missing_friction_tags") or []
        if missing:
            print(f"Rows without tags: {missing}")
        return 0

    decision = synthesis.get("governance_decision")
    if decision:
        print(f"governance_decision={decision}")

    top = synthesis.get("top_friction_tags") or []
    if top:
        print("Top friction tags:")
        for row in top[:8]:
            print(f"  {row['tag']}: {row['count']}")
    elif not synthesis.get("actionable_friction_clusters"):
        print("No actionable clusters — HOLD is valid only because workshop is complete.")

    for note in synthesis.get("suggested_run3_focus") or []:
        print(f"→ {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
