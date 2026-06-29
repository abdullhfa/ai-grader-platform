"""Submission normalization — engine/build/source/evidence classification."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from app.runtime_engines.registry import resolve_engine
from app.submission.validity_policy import assess_submission_validity


NORMALIZE_SCHEMA = "submission_normalization_v1"


def normalize_submission(
    root: Path,
    *,
    paths: Optional[Sequence[str]] = None,
    submission_key: str = "",
) -> Dict[str, Any]:
    """Unified submission envelope for pipeline routing."""
    validity = assess_submission_validity(root, paths=paths)
    engine_cls = resolve_engine(root)
    engine_id = engine_cls.engine_id if engine_cls else None

    submission_mode = _classify_mode(validity)
    evidence_class = _classify_evidence(validity, submission_mode)

    return {
        "schema": NORMALIZE_SCHEMA,
        "submission_key": submission_key,
        "root": str(root),
        "engine_id": engine_id,
        "submission_mode": submission_mode,
        "evidence_class": evidence_class,
        "has_runnable_build": validity.get("has_runnable_build"),
        "has_source_project": validity.get("has_source_project"),
        "has_documentation": validity.get("has_documentation"),
        "validity": validity,
        "routing": _routing_hint(engine_id, submission_mode, validity),
    }


def _classify_mode(validity: Dict[str, Any]) -> str:
    if validity.get("issues"):
        return "invalid_or_corrupted"
    if validity.get("has_runnable_build") and validity.get("has_source_project"):
        return "build_and_source"
    if validity.get("has_runnable_build"):
        return "build_only"
    if validity.get("has_source_project"):
        return "source_only"
    return "unknown"


def _classify_evidence(validity: Dict[str, Any], mode: str) -> str:
    if mode == "build_and_source":
        return "full_evidence"
    if mode == "build_only":
        return "runtime_primary"
    if mode == "source_only":
        return "static_primary"
    if "missing_documentation" in (validity.get("warnings") or []):
        return "runtime_without_docs"
    return "minimal"


def _routing_hint(engine_id: Optional[str], mode: str, validity: Dict[str, Any]) -> Dict[str, str]:
    if validity.get("issues"):
        return {"runtime": "skip", "grading": "examiner_heavy", "tier_hint": "D"}
    if mode == "build_and_source":
        return {"runtime": "full", "grading": "standard", "tier_hint": "A"}
    if mode == "build_only":
        return {"runtime": "full", "grading": "reduced_source", "tier_hint": "B"}
    if mode == "source_only":
        return {"runtime": "static", "grading": "partial", "tier_hint": "C"}
    if not engine_id:
        return {"runtime": "skip", "grading": "manual_review", "tier_hint": "D"}
    return {"runtime": "attempt", "grading": "standard", "tier_hint": "C"}
