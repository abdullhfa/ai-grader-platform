"""V1 / V2 runtime comparison with source and build provenance.

Each version is run as its OWN session and keeps its own record (result, blockers,
provenance).  Nothing is merged: V2 never replaces V1, evidence of two different
builds is never combined, and a blocked run stays blocked.

The comparison carries no criterion verdict.  ``improvement_observed`` is ``None``
whenever either side was not really run (PAUSED / gated / skipped), so a blocked
V1 or V2 can never read as "not achieved".
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.runtime_provenance import detect_mismatches

SCHEMA = "runtime_version_comparison_v1"

RAN = "RAN"
PAUSED = "PAUSED"
NOT_RUN = "NOT_RUN"

CMP_COMPARABLE = "COMPARABLE"
CMP_BLOCKED = "BLOCKED"
CMP_PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
CMP_IDENTICAL_BUILD = "IDENTICAL_BUILD"

_RAN_STATUSES = {"completed", "partial", "failed", "crashed", "timeout"}
_L4_ORDER = {"L3": 3, "L4_partial": 4, "L4_full": 5}


def comparison_enabled() -> bool:
    return os.environ.get("AI_GRADER_VERSION_RUNTIME_COMPARE", "1").strip().lower() not in ("0", "off", "false")


def _find_gv(obj: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
    if depth > 7:
        return None
    if isinstance(obj, dict):
        gv = obj.get("gameplay_verification")
        if isinstance(gv, dict) and gv.get("l4_level"):
            return gv
        for v in obj.values():
            hit = _find_gv(v, depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj[:12]:
            hit = _find_gv(v, depth + 1)
            if hit:
                return hit
    return None


def _run_state(result: Dict[str, Any]) -> str:
    status = str(result.get("status") or "").lower()
    if status == "paused" or result.get("blockers"):
        return PAUSED
    return RAN if status in _RAN_STATUSES else NOT_RUN


def build_version_record(
    label: str,
    result: Dict[str, Any],
    *,
    group_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """One version's separate, self-describing record."""
    prov = dict(result.get("provenance") or {})
    prov["version_label"] = label
    if prov.get("source_provenance") is not None and prov.get("build_provenance") is not None:
        # Re-judge the mismatch against THIS version's own folder.
        prov["mismatches"] = detect_mismatches(
            prov["source_provenance"], prov["build_provenance"], group_root=group_root
        )
    state = _run_state(result)
    gv = _find_gv(result.get("signals") or {}) if state == RAN else None
    return {
        "version": label,
        "run_state": state,
        "status": result.get("status"),
        "blockers": list(result.get("blockers") or []),
        "provenance": prov,
        "l4": {
            "level": (gv or {}).get("l4_level"),
            "gameplay_entered": (gv or {}).get("gameplay_entered"),
            "mechanics_verified_count": (gv or {}).get("mechanics_verified_count"),
            "player_movement_verified": (gv or {}).get("player_movement_verified"),
        }
        if gv
        else None,
    }


def _build_hash(record: Dict[str, Any]) -> Optional[str]:
    exe = ((record.get("provenance") or {}).get("build_provenance") or {}).get("executable") or {}
    return exe.get("sha256")


def compare_version_records(v1: Dict[str, Any], v2: Dict[str, Any]) -> Dict[str, Any]:
    """Pure: compare two version records.  Never merges evidence, never gives a verdict."""
    mismatches: List[Dict[str, str]] = []
    for rec in (v1, v2):
        for m in (rec.get("provenance") or {}).get("mismatches") or []:
            mismatches.append({"version": rec["version"], **m})

    blockers: List[Dict[str, Any]] = []
    for rec in (v1, v2):
        for b in rec.get("blockers") or []:
            blockers.append({"version": rec["version"], **b})

    h1, h2 = _build_hash(v1), _build_hash(v2)
    identical = bool(h1 and h2 and h1 == h2)

    if v1["run_state"] != RAN or v2["run_state"] != RAN:
        status = CMP_BLOCKED
    elif mismatches:
        status = CMP_PROVENANCE_MISMATCH
    elif identical:
        status = CMP_IDENTICAL_BUILD
    else:
        status = CMP_COMPARABLE

    differences: Optional[Dict[str, Any]] = None
    improvement: Optional[bool] = None
    if status in (CMP_COMPARABLE, CMP_PROVENANCE_MISMATCH) and v1.get("l4") and v2.get("l4"):
        l1, l2 = v1["l4"], v2["l4"]
        m1 = int(l1.get("mechanics_verified_count") or 0)
        m2 = int(l2.get("mechanics_verified_count") or 0)
        differences = {
            "l4_level": {"v1": l1.get("level"), "v2": l2.get("level")},
            "mechanics_verified_count": {"v1": m1, "v2": m2, "delta": m2 - m1},
            "gameplay_entered": {"v1": l1.get("gameplay_entered"), "v2": l2.get("gameplay_entered")},
        }
        # A provenance mismatch keeps the numbers visible but they prove nothing.
        if status == CMP_COMPARABLE:
            improvement = (
                _L4_ORDER.get(str(l2.get("level")), 0) > _L4_ORDER.get(str(l1.get("level")), 0)
                or m2 > m1
            )

    return {
        "schema": SCHEMA,
        "status": status,
        "v1": v1,
        "v2": v2,
        "provenance_mismatches": mismatches,
        "blocked_by": blockers,
        "identical_build": identical,
        # Evidence of different builds is never combined.
        "evidence_merge_allowed": identical,
        "differences": differences,
        "improvement_observed": improvement,
        "improvement_verifiable": status == CMP_COMPARABLE,
    }


def run_version_runtime_comparison(
    root: Path,
    submission_key: str,
    *,
    grading_mode: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    runner: Optional[Callable[..., Dict[str, Any]]] = None,
    groups: Optional[Dict[str, Any]] = None,
    **session_flags: Any,
) -> Optional[Dict[str, Any]]:
    """Run V1 and V2 as separate sessions and compare them (None if no V1/V2 pair)."""
    if groups is None:
        from app.version_code_diff import discover_version_groups

        groups = discover_version_groups(Path(root))
    if not groups or groups.get("status") != "ok":
        return None
    if runner is None:
        from app.runtime.orchestrator import run_runtime_session as runner

    records: Dict[str, Dict[str, Any]] = {}
    for label in ("V1", "V2"):
        group = groups[label.lower()]
        group_root = Path(group["group_root"])
        try:
            result = runner(
                f"{submission_key}__{label}",
                group_root,
                timeout_seconds=timeout_seconds,
                grading_mode=grading_mode,
                **session_flags,
            )
        except Exception as exc:  # a crashed runner is a platform fault, not a verdict
            result = {
                "status": "paused",
                "blockers": [{
                    "code": "version_run_error",
                    "kind": "ENV_FAULT",
                    "detail": f"{type(exc).__name__}: {str(exc)[:160]}",
                    "resolvable_by": "retry",
                }],
            }
        records[label] = build_version_record(label, result, group_root=group_root)
    return compare_version_records(records["V1"], records["V2"])
