"""
Export a structured Human Review Workshop pack from a calibration report.

Selects diverse false_positive_rows (by submission archetype) for interpretability review.
Does NOT change thresholds or achieved logic.

Usage:
  python -m app.calibration.export_human_review_workshop \\
    --report app/calibration/reports/cal_reliability_stress_v2.json \\
    --out-dir app/calibration/workshop \\
    --max-rows 14
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_REVIEW_QUESTIONS = [
    {
        "id": "review_escalation_logical",
        "question_ar": "هل تصعيد المراجعة البشرية منطقي لهذه الحالة؟",
        "goal": "gate usefulness",
        "answer": None,
        "scale": ["yes", "partial", "no", "unclear"],
    },
    {
        "id": "reasoning_understandable",
        "question_ar": "هل reasoning النظام مفهوم لمراجع بشري؟",
        "goal": "interpretability",
        "answer": None,
        "scale": ["yes", "partial", "no", "unclear"],
    },
    {
        "id": "insufficiency_clear",
        "question_ar": "هل insufficiency / shadow flags واضحة أكاديمياً؟",
        "goal": "academic explainability",
        "answer": None,
        "scale": ["yes", "partial", "no", "unclear"],
    },
    {
        "id": "conflict_flags_useful",
        "question_ar": "هل conflict / corroboration flags مفيدة تشغيلياً؟",
        "goal": "operational clarity",
        "answer": None,
        "scale": ["yes", "partial", "no", "unclear"],
    },
    {
        "id": "severity_appropriate",
        "question_ar": "هل severity (low/medium/high/critical) مناسبة؟",
        "goal": "escalation calibration",
        "answer": None,
        "scale": ["yes", "partial", "no", "unclear"],
    },
    {
        "id": "noisy_triggers",
        "question_ar": "هل يوجد triggers أو reasons ضوضائية / مكررة؟",
        "goal": "gate tuning later",
        "answer": None,
        "notes": "",
    },
    {
        "id": "behavior_auditable",
        "question_ar": "هل السلوك قابل للتدقيق (مفهوم + قابل للتتبع) — وليس هل النظام «صح»؟",
        "goal": "institutional trust behavior",
        "answer": None,
        "scale": ["yes", "partial", "no", "unclear"],
    },
]


def _archetype_from_submission_id(sid: str) -> str:
    m = re.match(r"STRESS_\d+_(.+)$", sid or "")
    return m.group(1) if m else sid


def _compact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    sig = row.get("shadow_signals") or {}
    tax = row.get("taxonomy_suggestion") or {}
    return {
        "submission_id": row.get("submission_id"),
        "archetype": _archetype_from_submission_id(str(row.get("submission_id") or "")),
        "criterion": row.get("criterion"),
        "teacher_achieved": row.get("teacher_achieved"),
        "system_achieved": row.get("system_achieved"),
        "teacher_evidence_strength": row.get("teacher_evidence_strength"),
        "review_complexity": row.get("review_complexity"),
        "teacher_notes": row.get("teacher_notes"),
        "reviewer_taxonomy": row.get("reviewer_taxonomy"),
        "taxonomy_suggested_tags": (tax.get("suggested_tags") or []),
        "system_reasoning_preview": tax.get("system_reasoning_preview"),
        "evidence_item_count": sig.get("evidence_item_count"),
        "empty_evidence_layer": sig.get("empty_evidence_layer"),
        "rubric_shadow_sufficient": sig.get("rubric_shadow_sufficient"),
        "insufficiency_flags": sig.get("insufficiency_flags") or [],
        "human_review_required": sig.get("human_review_required"),
        "human_review_severity": sig.get("human_review_severity"),
        "human_review_reasons": sig.get("human_review_reasons") or [],
        "corroboration_conflict_count": sig.get("corroboration_conflict_count"),
        "cross_modal_diversity_score": sig.get("cross_modal_diversity_score"),
        "pattern_hint_only": sig.get("pattern_hint_only"),
        "video_only_windows": sig.get("video_only_windows"),
    }


def _select_diverse_fp_rows(
    fp_rows: List[Dict[str, Any]],
    *,
    max_rows: int,
) -> List[Dict[str, Any]]:
    by_arch: Dict[str, Dict[str, Any]] = {}
    for row in fp_rows:
        arch = _archetype_from_submission_id(str(row.get("submission_id") or ""))
        if arch not in by_arch:
            by_arch[arch] = row
    ordered = sorted(by_arch.values(), key=lambda r: _archetype_from_submission_id(str(r.get("submission_id"))))
    if len(ordered) >= max_rows:
        return ordered[:max_rows]
    seen = {str(r.get("submission_id")) for r in ordered}
    for row in fp_rows:
        sid = str(row.get("submission_id"))
        if sid in seen:
            continue
        ordered.append(row)
        seen.add(sid)
        if len(ordered) >= max_rows:
            break
    return ordered


def build_workshop_pack(
    report: Dict[str, Any],
    *,
    max_rows: int = 14,
    source_report_path: Optional[str] = None,
) -> Dict[str, Any]:
    fp_rows = list(report.get("false_positive_rows") or [])
    selected = _select_diverse_fp_rows(fp_rows, max_rows=max_rows)
    run = report.get("reliability_run") or {}

    cases = []
    for i, row in enumerate(selected, start=1):
        cases.append(
            {
                "workshop_row": i,
                "review_focus": "false_positive_interpretability",
                "context": _compact_row(row),
                "structured_review": [dict(q) for q in _REVIEW_QUESTIONS],
                "friction_notes": "",
                "operational_friction_tags": [],
            }
        )

    return {
        "schema": "reliability_human_review_workshop_v1",
        "workshop_title": "Structured Reliability Review — FP interpretability",
        "purpose": (
            "Assess whether system behavior is understandable and auditable — NOT whether achieved is academically correct."
        ),
        "source_report": source_report_path,
        "calibration_run_id": run.get("run_id"),
        "freeze_window_id": run.get("freeze_window_id"),
        "cohort_note": "Stress cohort (synthetic); FP rows are partially intentional for adversarial testing.",
        "reviewer_instructions": {
            "do_not_ask": "هل النظام صح؟",
            "do_ask": "هل behavior مفهوم وقابل للتدقيق؟",
            "after_workshop": "Pick 1–2 operational friction points only; then freeze → run → diff.",
        },
        "false_positives_available": len(fp_rows),
        "rows_selected": len(cases),
        "archetypes_covered": sorted({c["context"]["archetype"] for c in cases}),
        "cases": cases,
    }


def _markdown_instructions(pack: Dict[str, Any]) -> str:
    run_id = pack.get("calibration_run_id") or "?"
    arches = ", ".join(pack.get("archetypes_covered") or [])
    lines = [
        "# Structured Reliability Review Workshop",
        "",
        f"**Source:** `{pack.get('source_report')}`  ",
        f"**Run:** `{run_id}`  ",
        f"**Rows:** {pack.get('rows_selected')} diverse FP cases  ",
        f"**Archetypes:** {arches}",
        "",
        "## Purpose",
        "",
        "Evaluate **human-operational interpretability** — not grading accuracy.",
        "",
        "- Do **not** ask: «هل النظام صح؟»",
        "- **Do** ask: «هل behavior مفهوم وقابل للتدقيق؟»",
        "",
        "## Per row (fill `reliability_review_workshop_v1.json`)",
        "",
        "| Question ID | Goal | Scale / notes |",
        "| ----------- | ---- | ------------- |",
        "| `review_escalation_logical` | gate usefulness | yes / partial / no / unclear |",
        "| `reasoning_understandable` | interpretability | yes / partial / no / unclear |",
        "| `insufficiency_clear` | academic explainability | yes / partial / no / unclear |",
        "| `conflict_flags_useful` | operational clarity | yes / partial / no / unclear |",
        "| `severity_appropriate` | escalation calibration | yes / partial / no / unclear |",
        "| `noisy_triggers` | gate tuning later | free text in `notes` |",
        "| `behavior_auditable` | institutional trust | yes / partial / no / unclear |",
        "",
        "Also record: `friction_notes`, `operational_friction_tags` (e.g. `redundant_reason`, `severity_high_for_borderline`).",
        "",
        "## After workshop",
        "",
        "1. Summarize top **1–2** friction themes only.",
        "2. One scoped change per freeze window.",
        "3. `run_reliability_stress_cycle` → `calibration_diff` → observe.",
        "",
        "## Do not",
        "",
        "- Wire shadow → achieved.",
        "- Tune 5+ triggers at once.",
        "- Treat stress FP rate as production KPI.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Export human review workshop pack")
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("app/calibration/workshop"))
    ap.add_argument("--max-rows", type=int, default=14)
    ap.add_argument("--slug", type=str, default="reliability_review_workshop_v1")
    args = ap.parse_args()

    if not args.report.is_file():
        print(f"report not found: {args.report}", file=sys.stderr)
        return 1
    if args.max_rows < 1 or args.max_rows > 50:
        print("max-rows must be 1..50", file=sys.stderr)
        return 1

    report = json.loads(args.report.read_text(encoding="utf-8"))
    pack = build_workshop_pack(
        report,
        max_rows=args.max_rows,
        source_report_path=str(args.report).replace("\\", "/"),
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.slug}.json"
    md_path = args.out_dir / f"{args.slug}.md"
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown_instructions(pack), encoding="utf-8")

    print(f"Wrote {json_path} ({pack['rows_selected']} cases, {len(pack['archetypes_covered'])} archetypes)")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
