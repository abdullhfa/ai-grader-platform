"""
Single source of truth for the institutional BTEC grade across UI, Word, PDF, and API.

Always prefer ``resolve_official_grade`` instead of reading ``grade_level``,
``summary.grade_level``, or Gemini output directly.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_grader.official_grade")


@dataclass
class OfficialGradeResult:
  """Institutional BTEC grade after governance + Runtime Evidence Gate."""

  grade: str  # U/P/M/D
  grade_label: str  # e.g. "BTEC U"
  source: str  # pipeline | institutional_resolution | grade_level | legacy_db
  gate_applied: bool = False
  gate_satisfied: Optional[bool] = None
  downgrades: List[Dict[str, Any]] = field(default_factory=list)
  snapshot_version: Optional[str] = None
  is_stale: bool = False
  grade_display_metrics: Dict[str, Any] = field(default_factory=dict)
  reapply_change_count: int = 0

  def to_dict(self) -> Dict[str, Any]:
    return asdict(self)


def _short_btec_token(raw: Any) -> str:
  text = str(raw or "U").strip().upper()
  if not text:
    return "U"
  head = text.split()[0]
  if head in ("D", "M", "P", "U"):
    return head
  if head.startswith("DISTINCTION"):
    return "D"
  if head.startswith("MERIT"):
    return "M"
  if head.startswith("PASS"):
    return "P"
  if head and head[0] in "DMPU":
    return head[0]
  return "U"


def _collect_downgrades(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
  out: List[Dict[str, Any]] = []
  seen: set[str] = set()

  gate = snapshot.get("runtime_evidence_gate") or {}
  for change in gate.get("changes") or []:
    key = f"gate:{change}"
    if key in seen:
      continue
    seen.add(key)
    out.append(
      {
        "criterion": str(change).split(":")[0],
        "layer": "runtime_evidence_gate",
        "reason_ar": gate.get("summary_ar") or "",
      }
    )

  for row in snapshot.get("criteria_results") or []:
    if not isinstance(row, dict):
      continue
    level = str(row.get("criteria_level") or "")
    if row.get("runtime_gate_block"):
      key = f"row:{level}:gate"
      if key not in seen:
        seen.add(key)
        out.append(
          {
            "criterion": level,
            "layer": "runtime_gate_block",
            "reason_ar": row.get("award_block_reason_ar")
            or row.get("governance_adjustment_ar")
            or "",
          }
        )
    gov = str(row.get("governance_adjustment_ar") or "").strip()
    if gov and not row.get("achieved"):
      key = f"row:{level}:gov"
      if key not in seen:
        seen.add(key)
        out.append(
          {
            "criterion": level,
            "layer": "btec_governance",
            "reason_ar": gov,
          }
        )

  gov_report = snapshot.get("btec_criteria_governance") or {}
  for change in gov_report.get("changes") or []:
    if not isinstance(change, dict):
      continue
    level = str(change.get("criteria_level") or "")
    key = f"gov:{level}:{change.get('action')}"
    if key in seen:
      continue
    seen.add(key)
    out.append(
      {
        "criterion": level,
        "layer": "btec_criteria_governance",
        "action": change.get("action"),
        "reason_ar": change.get("reason_ar") or "",
      }
    )
  return out


def _reapply_pipeline(snapshot: Dict[str, Any]) -> int:
  """Idempotent finalize in-memory. Returns change_count."""
  if not isinstance(snapshot.get("criteria_results"), list) or not snapshot["criteria_results"]:
    return 0
  try:
    from app.criteria_result_finalizer import finalize_grading_criteria_results

    fin = finalize_grading_criteria_results(
      snapshot,
      artifact_inventory=snapshot.get("artifact_inventory"),
    )
    return int(fin.get("change_count") or 0)
  except Exception as exc:
    logger.warning("official_grade pipeline reapply failed: %s", exc)
    return 0


def resolve_official_grade(
  snapshot: Optional[Dict[str, Any]],
  *,
  reapply_pipeline: bool = True,
  legacy_grade_level: Optional[str] = None,
) -> OfficialGradeResult:
  """
  Resolve the institutional BTEC grade from a grading snapshot.

  When ``reapply_pipeline`` is True (default), ``finalize_grading_criteria_results``
  is run in-memory so old snapshots without ``runtime_evidence_gate`` still get
  the terminal seal before the grade is read.

  Never reads Gemini output directly — only post-pipeline fields.
  """
  if not snapshot or not isinstance(snapshot, dict):
    grade = _short_btec_token(legacy_grade_level)
    return OfficialGradeResult(
      grade=grade,
      grade_label=f"BTEC {grade}",
      source="legacy_db",
      is_stale=True,
    )

  change_count = 0
  if reapply_pipeline:
    change_count = _reapply_pipeline(snapshot)

  working = snapshot
  fin_meta = working.get("criteria_finalizer") or {}
  snapshot_version = fin_meta.get("version") if isinstance(fin_meta, dict) else None

  gate = working.get("runtime_evidence_gate") or {}
  gate_applied = bool(gate.get("applied"))
  gate_satisfied: Optional[bool]
  if gate.get("reason") == "not_a_game_submission":
    gate_satisfied = None
  elif "satisfied" in gate:
    gate_satisfied = bool(gate.get("satisfied"))
  else:
    gate_satisfied = None

  from app.evidence_registry import build_grade_display_metrics

  gdm = build_grade_display_metrics(working)
  grade = _short_btec_token(gdm.get("final_btec_grade"))

  source = "pipeline"
  is_stale = False
  if not working.get("criteria_results"):
    inst = working.get("institutional_resolution") or {}
    if inst.get("btec_grade"):
      grade = _short_btec_token(inst.get("btec_grade"))
      source = "institutional_resolution"
      is_stale = True
    elif working.get("grade_level"):
      grade = _short_btec_token(working.get("grade_level"))
      source = "grade_level"
      is_stale = True

  downgrades = _collect_downgrades(working)

  return OfficialGradeResult(
    grade=grade,
    grade_label=f"BTEC {grade}",
    source=source,
    gate_applied=gate_applied,
    gate_satisfied=gate_satisfied,
    downgrades=downgrades,
    snapshot_version=snapshot_version,
    is_stale=is_stale,
    grade_display_metrics=gdm,
    reapply_change_count=change_count,
  )


def prepare_official_snapshot(
  snapshot: Dict[str, Any],
  *,
  reapply_pipeline: bool = True,
) -> tuple[Dict[str, Any], OfficialGradeResult]:
  """Deep-copy snapshot, reapply pipeline, return (working_copy, official_grade)."""
  working = copy.deepcopy(snapshot)
  official = resolve_official_grade(working, reapply_pipeline=reapply_pipeline)
  return working, official


def official_grade_short(result: OfficialGradeResult) -> str:
  """Convenience for templates expecting a single letter."""
  return result.grade
