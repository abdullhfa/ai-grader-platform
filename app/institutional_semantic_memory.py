"""
Institutional Semantic Memory — cross-epoch deliberative memory.

Historical epistemic awareness for workshop deliberation.
NOT: semantic governance scoring · normative authority · facilitator ranking.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.canonical_stability_trajectory import ACTIVE_FREEZE_EPOCH, FREEZE_EPOCHS

MEMORY_VERSION = "INSTITUTIONAL_SEMANTIC_MEMORY_v1"
MEMORY_DIR = Path("app/calibration/human_cohort_workshop")
MEMORY_FILE = "institutional_semantic_memory.jsonl"

CONSTITUTIONAL_CONSTRAINTS = [
    "memory never becomes normative authority",
    "no baseline ideal reviewer",
    "no semantic purity score",
    "no facilitator ranking",
    "no behavioural compliance metric",
    "cross-epoch deliberative memory only",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_dir() -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return MEMORY_DIR


def _read_entries() -> List[Dict[str, Any]]:
    path = _ensure_dir() / MEMORY_FILE
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _append_entry(entry: Dict[str, Any]) -> None:
    path = _ensure_dir() / MEMORY_FILE
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_semantic_memory_snapshot(
    *,
    batch_id: int,
    epistemic_synthesis: Dict[str, Any],
    freeze_epoch_id: str = ACTIVE_FREEZE_EPOCH,
    facilitator_note_ar: str = "",
    workshop_context_ar: str = "",
) -> Dict[str, Any]:
    """
    Append deliberative semantic memory snapshot — not normative scoring.
    """
    epoch = FREEZE_EPOCHS.get(freeze_epoch_id, {})
    leakage = epistemic_synthesis.get("leakage_lexicon_analysis") or {}
    patterns = leakage.get("patterns_by_type") or {}

    phrase_samples: List[Dict[str, Any]] = []
    for sub in leakage.get("per_submission") or []:
        for m in sub.get("advisory_matches") or []:
            phrase_samples.append({
                "submission_id": sub.get("submission_id"),
                "phrase": m.get("matched_phrase"),
                "leakage_type": m.get("leakage_type"),
            })
    for ex in epistemic_synthesis.get("linguistic_leakage_examples") or []:
        if ex.get("samples_ar"):
            phrase_samples.append({
                "submission_id": ex.get("submission_id"),
                "phrase": ex.get("samples_ar"),
                "leakage_type": "raw_sample",
            })

    behavioural_themes = list((epistemic_synthesis.get("behavioural_themes") or {}).keys())

    entry = {
        "memory_version": MEMORY_VERSION,
        "entry_id": f"ism_{uuid.uuid4().hex[:12]}",
        "recorded_at": _utc_now(),
        "batch_id": batch_id,
        "freeze_epoch_id": freeze_epoch_id,
        "freeze_id": epoch.get("freeze_id"),
        "not": "semantic governance scoring · normative authority",
        "purpose_ar": "historical epistemic awareness — cross-epoch deliberative memory",
        "constitutional_constraints": CONSTITUTIONAL_CONSTRAINTS,
        "observations_with_section_e": epistemic_synthesis.get("observations_with_section_e", 0),
        "total_observations": epistemic_synthesis.get("total_observations", 0),
        "leakage_types_observed": leakage.get("unique_leakage_types") or [],
        "leakage_type_counts": {
            k: len(v) for k, v in patterns.items()
        },
        "phrase_samples": phrase_samples,
        "behavioural_themes": behavioural_themes,
        "facilitator_interpretation_ar": epistemic_synthesis.get("facilitator_interpretation_ar") or [],
        "pattern_notes_ar": leakage.get("pattern_notes_ar") or [],
        "workshop_context_ar": workshop_context_ar,
        "facilitator_note_ar": facilitator_note_ar,
    }
    _append_entry(entry)
    return {"ok": True, "entry_id": entry["entry_id"], "entry": entry}


def build_semantic_memory_trajectory(
    *,
    freeze_epoch_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Cross-epoch semantic adaptation traces — for deliberation, not automation.
    """
    entries = _read_entries()
    if freeze_epoch_id:
        entries = [e for e in entries if e.get("freeze_epoch_id") == freeze_epoch_id]
    entries = entries[-limit:]

    phrase_recurrence: Dict[str, int] = {}
    leakage_recurrence: Dict[str, int] = {}
    theme_recurrence: Dict[str, int] = {}
    batches_recorded: List[int] = []

    for entry in entries:
        bid = entry.get("batch_id")
        if bid is not None:
            batches_recorded.append(int(bid))
        for ps in entry.get("phrase_samples") or []:
            phrase = str(ps.get("phrase") or "").strip()
            if phrase and len(phrase) < 200:
                phrase_recurrence[phrase] = phrase_recurrence.get(phrase, 0) + 1
        for lt, cnt in (entry.get("leakage_type_counts") or {}).items():
            leakage_recurrence[lt] = leakage_recurrence.get(lt, 0) + int(cnt or 0)
        for theme in entry.get("behavioural_themes") or []:
            theme_recurrence[str(theme)] = theme_recurrence.get(str(theme), 0) + 1

    top_phrases = sorted(phrase_recurrence.items(), key=lambda x: -x[1])[:15]
    top_leakage = sorted(leakage_recurrence.items(), key=lambda x: -x[1])

    deliberation_prompts: List[str] = []
    if top_leakage:
        dominant = top_leakage[0][0]
        deliberation_prompts.append(
            f"هل {dominant} يتكرر عبر workshops — mitigation أم semantic habit؟"
        )
    if top_phrases:
        deliberation_prompts.append(
            "هل العبارات المتكررة تتراجع بعد replay-first training؟"
        )
    if len(entries) >= 2:
        deliberation_prompts.append(
            "semantic governance evolution observable — ناقش patterns لا compliance."
        )
    if not entries:
        deliberation_prompts.append(
            "لا snapshots بعد — سجّل memory بعد batch workshop (Section E + lexicon)."
        )

    return {
        "report_type": "institutional_semantic_memory_trajectory",
        "memory_version": MEMORY_VERSION,
        "not": (
            "semantic purity score · facilitator ranking · "
            "behavioural compliance metric · normative baseline"
        ),
        "purpose_ar": "cross-epoch deliberative memory — institutional semantic adaptation traces",
        "constitutional_constraints": CONSTITUTIONAL_CONSTRAINTS,
        "freeze_epoch_id": freeze_epoch_id or "all",
        "snapshot_count": len(entries),
        "batches_recorded": sorted(set(batches_recorded)),
        "phrase_recurrence": [{"phrase": p, "occurrences": c} for p, c in top_phrases],
        "leakage_type_recurrence": [{"type": t, "occurrences": c} for t, c in top_leakage],
        "behavioural_theme_recurrence": [
            {"theme": t, "snapshots": c} for t, c in sorted(theme_recurrence.items(), key=lambda x: -x[1])
        ],
        "snapshots": entries,
        "deliberation_prompts_ar": deliberation_prompts,
        "explicitly_not_for": [
            "automatic institutional veto",
            "epoch transition gate",
            "reviewer ranking",
            "semantic compliance scoring",
        ],
    }
