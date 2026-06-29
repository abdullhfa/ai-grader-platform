"""
Epoch Mitigation Ledger — institutional mitigation lineage per freeze epoch.

Makes governance evolution historically explainable — not only measurable.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.canonical_stability_trajectory import ACTIVE_FREEZE_EPOCH, FREEZE_EPOCHS

LEDGER_ID = "EPOCH_MITIGATION_LEDGER_v1"
LEDGER_DIR = Path("app/calibration/human_cohort_workshop")
LEDGER_FILE = "epoch_mitigation_ledger.jsonl"

# Seed lineage for epoch_1 — known institutional responses (editable via API)
EPOCH_1_SEED_ENTRIES: List[Dict[str, str]] = [
    {
        "issue": "canonical drift",
        "failure_mode_id": "GFM_CANONICAL_DRIFT",
        "mitigation": "binary hash replay + grading_governance snapshot",
        "result": "drift mitigation deployed — trajectory monitoring active",
        "result_status": "in_progress",
    },
    {
        "issue": "institutional supersession gap",
        "failure_mode_id": "GFM_CANONICAL_DRIFT",
        "mitigation": "institutional supersession policy (bounded historical variance)",
        "result": "batch 28 superseded — canonical authority preserved",
        "result_status": "effective",
    },
    {
        "issue": "replay abandonment risk",
        "failure_mode_id": "GFM_TRUST_EROSION",
        "mitigation": "canonical stability metrics + replay trust proxy in observatory",
        "result": "replay reuse monitoring — pending cohort workshop",
        "result_status": "pending",
    },
    {
        "issue": "modality dominance",
        "failure_mode_id": "GFM_MODALITY_DOMINANCE",
        "mitigation": "downgrade visibility + governance pilot observatory workshop",
        "result": "L3 confusion tracking — pending observations",
        "result_status": "pending",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_dir() -> Path:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    return LEDGER_DIR


def _read_ledger() -> List[Dict[str, Any]]:
    path = LEDGER_DIR / LEDGER_FILE
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


def _append_entry(entry: Dict[str, Any]) -> Optional[str]:
    try:
        _ensure_dir()
        path = LEDGER_DIR / LEDGER_FILE
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return str(path)
    except OSError:
        return None


def seed_epoch_ledger_if_empty(epoch_id: str = ACTIVE_FREEZE_EPOCH) -> int:
    """Insert seed lineage rows once per epoch."""
    existing = [r for r in _read_ledger() if r.get("epoch_id") == epoch_id]
    if existing:
        return 0
    if epoch_id != "epoch_1":
        return 0

    freeze = FREEZE_EPOCHS.get(epoch_id, {})
    count = 0
    for seed in EPOCH_1_SEED_ENTRIES:
        append_ledger_entry(
            epoch_id=epoch_id,
            issue=seed["issue"],
            mitigation=seed["mitigation"],
            result=seed["result"],
            failure_mode_id=seed.get("failure_mode_id"),
            result_status=seed.get("result_status", "pending"),
            recorded_by="system_seed",
            result_evidence_ar="seed entry — epoch_1 institutional response lineage",
        )
        count += 1
    return count


def append_ledger_entry(
    *,
    epoch_id: str,
    issue: str,
    mitigation: str,
    result: str,
    failure_mode_id: Optional[str] = None,
    result_status: str = "pending",
    recorded_by: str = "",
    result_evidence_ar: str = "",
    lineage_refs: Optional[List[str]] = None,
    artifact_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    freeze = FREEZE_EPOCHS.get(epoch_id, {})
    entry = {
        "ledger_id": LEDGER_ID,
        "entry_id": f"led_{uuid.uuid4().hex[:12]}",
        "epoch_id": epoch_id,
        "freeze_id": freeze.get("freeze_id", ""),
        "issue": issue,
        "failure_mode_id": failure_mode_id,
        "mitigation": mitigation,
        "result": result,
        "result_status": result_status,
        "result_evidence_ar": result_evidence_ar,
        "recorded_at": _utc_now(),
        "recorded_by": recorded_by,
        "lineage_refs": list(lineage_refs or []),
        "artifact_refs": list(artifact_refs or []),
    }
    path = _append_entry(entry)
    if path:
        entry["log_path"] = path
    return entry


def load_ledger_entries(epoch_id: Optional[str] = None) -> List[Dict[str, Any]]:
    seed_epoch_ledger_if_empty(ACTIVE_FREEZE_EPOCH)
    rows = _read_ledger()
    if epoch_id:
        rows = [r for r in rows if r.get("epoch_id") == epoch_id]
    return rows


def _sync_from_mitigation_memory(epoch_id: str) -> List[Dict[str, Any]]:
    """Promote effective mitigation memory rows into ledger suggestions (not auto-append)."""
    try:
        from app.governance_mitigation_memory import analyze_mitigation_effectiveness

        mem = analyze_mitigation_effectiveness()
        suggestions: List[Dict[str, Any]] = []
        for row in mem.get("by_failure_mode") or []:
            if row.get("effectiveness_rate") is None:
                continue
            suggestions.append({
                "epoch_id": epoch_id,
                "issue": row.get("failure_mode_id", "unknown"),
                "mitigation": "governance_mitigation_memory response",
                "result": row.get("learning_ar", ""),
                "result_status": "effective" if (row.get("effectiveness_rate") or 0) >= 0.5 else "partial",
                "source": "mitigation_memory_sync",
                "suggested_not_committed": True,
            })
        return suggestions
    except Exception:
        return []


def build_mitigation_ledger_report(
    db: Any,
    *,
    epoch_id: str = ACTIVE_FREEZE_EPOCH,
    assignment_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Institutional mitigation lineage table + narrative."""
    seed_epoch_ledger_if_empty(epoch_id)
    entries = load_ledger_entries(epoch_id=epoch_id)

    table = [
        {
            "epoch": e.get("epoch_id"),
            "issue": e.get("issue"),
            "failure_mode_id": e.get("failure_mode_id"),
            "mitigation": e.get("mitigation"),
            "result": e.get("result"),
            "result_status": e.get("result_status"),
            "recorded_at": e.get("recorded_at"),
            "entry_id": e.get("entry_id"),
        }
        for e in entries
    ]

    by_status: Dict[str, int] = {}
    for e in entries:
        st = e.get("result_status") or "pending"
        by_status[st] = by_status.get(st, 0) + 1

    narrative_lines: List[str] = []
    for e in entries:
        narrative_lines.append(
            f"• [{e.get('epoch_id')}] {e.get('issue')} → {e.get('mitigation')} → {e.get('result')}"
        )

    try:
        from app.canonical_stability_trajectory import load_stability_history

        history = load_stability_history(assignment_id=assignment_id, freeze_epoch=epoch_id)
        if len(history) >= 2:
            m0 = history[0].get("metrics") or {}
            m1 = history[-1].get("metrics") or {}
            drift0 = m0.get("canonical_drift_rate")
            drift1 = m1.get("canonical_drift_rate")
            if drift0 is not None and drift1 is not None:
                narrative_lines.append(
                    f"• canonical_drift_rate trajectory: {drift0} → {drift1} (within {epoch_id})"
                )
    except Exception:
        pass

    return {
        "report_type": "epoch_mitigation_ledger",
        "ledger_id": LEDGER_ID,
        "epoch_id": epoch_id,
        "freeze_id": FREEZE_EPOCHS.get(epoch_id, {}).get("freeze_id"),
        "purpose_ar": (
            "institutional mitigation lineage — governance evolution historically explainable"
        ),
        "entry_count": len(entries),
        "result_status_counts": by_status,
        "table": table,
        "lineage_narrative_ar": narrative_lines,
        "mitigation_memory_suggestions": _sync_from_mitigation_memory(epoch_id),
        "explainability_note_ar": (
            "كل صف = Issue → Mitigation → Result — يربط transition events وworkshop verdicts "
            "بقرارات مؤسسية قابلة للتدقيق."
        ),
    }
