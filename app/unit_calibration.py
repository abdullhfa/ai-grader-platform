"""
BTEC Unit Calibration Layer — load frozen unit specs (criteria, engines, gate rules).

First unit: Unit 9 (MOE) / Unit 8 (Pearson platform prefix) — Games.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.game_engine_signatures import detect_engine_from_text

_CALIBRATION_DIR = Path(__file__).resolve().parent / "calibration"
_GRADES_DIR = _CALIBRATION_DIR / "grades"
_GRADES_INDEX_PATH = _GRADES_DIR / "INDEX.json"
_LEGACY_UNIT9_PATH = _CALIBRATION_DIR / "unit9_games_spec.json"
_DEFAULT_SPEC_PATH = _GRADES_DIR / "grade_10" / "games" / "spec.json"

UNIT9_KEY = "unit_9_games"


def _load_grades_index() -> Dict[str, Any]:
    if not _GRADES_INDEX_PATH.is_file():
        return {"unit_specs": {}}
    with _GRADES_INDEX_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_spec_path(unit_key: str) -> Optional[Path]:
    key = (unit_key or "").strip().lower().replace(" ", "_")
    index = _load_grades_index()
    rel = (index.get("unit_specs") or {}).get(key)
    if rel:
        candidate = _GRADES_DIR / rel
        if candidate.is_file():
            return candidate
    if key in (UNIT9_KEY, "unit9", "unit_9", "unit8_games", "unit_8_games") and _DEFAULT_SPEC_PATH.is_file():
        return _DEFAULT_SPEC_PATH
    legacy = _CALIBRATION_DIR / f"{key}_spec.json"
    if legacy.is_file():
        return legacy
    if _LEGACY_UNIT9_PATH.is_file() and key in (UNIT9_KEY, "unit9", "unit_9", "unit8_games", "unit_8_games"):
        return _LEGACY_UNIT9_PATH
    return None


def list_grade_ids() -> List[str]:
    index = _load_grades_index()
    grades = index.get("grades")
    if isinstance(grades, list) and grades:
        return [str(g) for g in grades]
    if not _GRADES_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in _GRADES_DIR.iterdir()
        if p.is_dir() and p.name.startswith("grade_") and (p / "_grade.json").is_file()
    )


def load_grade_manifest(grade_id: str) -> Optional[Dict[str, Any]]:
    path = _GRADES_DIR / grade_id / "_grade.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=4)
def load_unit_spec(unit_key: str = UNIT9_KEY) -> Optional[Dict[str, Any]]:
    """Load a unit calibration spec by key (grades/grade_XX/{slug}/spec.json)."""
    path = _resolve_spec_path(unit_key)
    if not path:
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_unit9_spec() -> Dict[str, Any]:
    spec = load_unit_spec(UNIT9_KEY)
    if not spec:
        raise FileNotFoundError(f"Missing unit calibration spec for {UNIT9_KEY} under {_GRADES_DIR}")
    return spec


def list_criteria(spec: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = spec or get_unit9_spec()
    rows = data.get("criteria") or []
    return [r for r in rows if isinstance(r, dict)]


def criterion_by_code(code: str, spec: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    target = (code or "").strip().upper()
    for row in list_criteria(spec):
        if str(row.get("code") or "").upper() == target:
            return row
    return None


def moe_approved_engine_ids(spec: Optional[Dict[str, Any]] = None) -> frozenset[str]:
    data = spec or get_unit9_spec()
    block = data.get("moe_approved_engines") or {}
    return frozenset(
        str(e.get("id"))
        for e in block.get("engines") or []
        if isinstance(e, dict) and e.get("id")
    )


def assess_moe_engine_compliance(
    *,
    engine: Optional[str] = None,
    submission_paths: Optional[Sequence[str]] = None,
    spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Check detected engine against MOE Jordan approved list for Unit 9.

    Returns compliance status — does not block grading unless policy changes to ``reject``.
    """
    data = spec or get_unit9_spec()
    block = data.get("moe_approved_engines") or {}
    policy = str(block.get("policy") or "warn")
    approved = moe_approved_engine_ids(data)

    detected = (engine or "").strip().lower() or None
    if not detected and submission_paths:
        joined = " ".join(str(p) for p in submission_paths).lower()
        detected = detect_engine_from_text(joined)

    if not detected:
        return {
            "compliant": None,
            "engine": None,
            "policy": policy,
            "message_ar": "لم يُكتشف محرك لعبة — لا يمكن التحقق من توافق الوزارة.",
        }

    compliant = detected in approved
    if compliant:
        msg = f"المحرك {detected} ضمن القائمة المعتمدة من وزارة التربية للوحدة 9."
    else:
        msg = (
            f"المحرك {detected} غير مدرج في قائمة الوزارة المعتمدة "
            f"(Godot, Unity, Unreal, Scratch, GameMaker). "
            f"سياسة المنصة: {policy}."
        )
    return {
        "compliant": compliant,
        "engine": detected,
        "policy": policy,
        "approved_engines": sorted(approved),
        "message_ar": msg,
    }


def runtime_gated_codes(spec: Optional[Dict[str, Any]] = None) -> frozenset[str]:
    data = spec or get_unit9_spec()
    gate = data.get("runtime_gate") or {}
    return frozenset(str(x).upper() for x in gate.get("criteria_short") or [])


def assignment_brief_criteria(spec: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return [r for r in list_criteria(spec) if r.get("in_assignment_brief")]


def get_freeze_checklist(spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return freeze checklist from spec + derived ready-to-freeze flag."""
    data = spec or get_unit9_spec()
    cal = data.get("calibration") or {}
    checklist = dict(cal.get("freeze_checklist") or {})
    blockers = [
        k for k, v in checklist.items()
        if v is False or v == "partial"
    ]
    return {
        "status": data.get("status"),
        "frozen_at": data.get("frozen_at"),
        "calibration_status": cal.get("status"),
        "checklist": checklist,
        "blockers": blockers,
        "ready_to_freeze": data.get("status") != "frozen" and not blockers,
    }


def to_pearson_registry_entry(spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Shape for ``pearson_unit_spec_registry.UNIT_SPECS``."""
    data = spec or get_unit9_spec()
    unit = data.get("unit") or {}
    criteria_out: List[Dict[str, Any]] = []
    for row in list_criteria(data):
        criteria_out.append(
            {
                "code": row.get("code"),
                "level": row.get("band"),
                "platform_level": row.get("platform_level"),
                "aim": row.get("aim"),
                "title_ar": row.get("title_ar"),
                "evidence_types": row.get("evidence_types") or [],
                "requires_runtime": bool(row.get("requires_runtime")),
                "runtime_gate": bool(row.get("runtime_gate")),
                "in_assignment_brief": bool(row.get("in_assignment_brief")),
            }
        )
    return {
        "title": unit.get("title_en"),
        "title_ar": unit.get("title_ar"),
        "moe_number": unit.get("moe_number"),
        "pearson_number": unit.get("pearson_number"),
        "pearson_edition": "BTEC International Level 2 IT",
        "status": data.get("status"),
        "criteria": criteria_out,
    }
