"""Submission contract layer — validity policy for institutional assessment."""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.runtime_engines.registry import resolve_engine
from app.runtime_engines.godot.export_runner import find_godot_executable, find_godot_project_root
from app.runtime_engines.gamemaker.project_probe import probe_gamemaker_layout
from app.runtime_engines.unity.detector import detect_unity_layout


VALIDITY_SCHEMA = "submission_validity_v1"


def assess_submission_validity(
    root: Path,
    *,
    paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Classify submission structure and validity — does NOT reject pipeline."""
    root = root.resolve()
    issues: List[str] = []
    warnings: List[str] = []
    decisions: List[Dict[str, str]] = []

    engine_cls = resolve_engine(root)
    engine_id = engine_cls.engine_id if engine_cls else None

    has_build = _has_runnable_build(root, engine_id)
    has_source = _has_source_project(root, engine_id)
    has_docs = _has_documentation(root, paths)
    zip_status = _check_zip_integrity(root, paths)

    if zip_status.get("corrupted"):
        issues.append("corrupted_zip")
        decisions.append({"condition": "corrupted_zip", "decision": "rejected", "grading": "blocked_pending_review"})

    if not engine_id:
        warnings.append("unsupported_or_unknown_engine")
        decisions.append({"condition": "unsupported_engine", "decision": "manual_review", "grading": "examiner_heavy"})

    if has_source and not has_build:
        warnings.append("missing_build")
        decisions.append({"condition": "missing_build", "decision": "partial_grading", "grading": "static_inference"})

    if has_build and not has_source:
        warnings.append("missing_source")
        decisions.append({"condition": "missing_source", "decision": "reduced_evidence", "grading": "runtime_verified"})

    if not has_docs:
        warnings.append("missing_documentation")
        decisions.append({"condition": "missing_docs", "decision": "governance_warning", "grading": "continue_with_flag"})

    build_count = _count_builds(root, engine_id)
    if build_count > 1:
        warnings.append("multiple_builds")
        decisions.append({"condition": "multiple_builds", "decision": "primary_build_only", "grading": "continue"})

    validity = "valid"
    if issues:
        validity = "invalid"
    elif warnings:
        validity = "partial"

    return {
        "schema": VALIDITY_SCHEMA,
        "validity": validity,
        "engine_id": engine_id,
        "has_runnable_build": has_build,
        "has_source_project": has_source,
        "has_documentation": has_docs,
        "build_count": build_count,
        "zip_status": zip_status,
        "issues": issues,
        "warnings": warnings,
        "decisions": decisions,
        "policy_note_ar": (
            "التحقق من صحة التسليم لا يوقف pipeline — يوجّه مستوى الثقة ومراجعة examiner."
        ),
    }


def _has_runnable_build(root: Path, engine_id: Optional[str]) -> bool:
    if engine_id == "unity":
        layout = detect_unity_layout(root)
        return layout.has_build_executable
    if engine_id == "godot":
        project = find_godot_project_root(root) or root
        return bool(find_godot_executable(project))
    if engine_id == "gamemaker":
        layout = probe_gamemaker_layout(root)
        return bool(layout.executable or layout.html_entry)
    if engine_id == "web":
        return bool(list(root.rglob("index.html"))[:1])
    if engine_id == "legacy_exe":
        return any(root.rglob("*.exe"))
    return False


def _has_source_project(root: Path, engine_id: Optional[str]) -> bool:
    if engine_id == "unity":
        return detect_unity_layout(root).has_source_project
    if engine_id == "godot":
        return find_godot_project_root(root) is not None
    if engine_id == "gamemaker":
        layout = probe_gamemaker_layout(root)
        return bool(layout.yyp_path or layout.yyz_path or layout.gml_files)
    if engine_id == "web":
        return bool(list(root.rglob("*.html"))[:1])
    return False


def _has_documentation(root: Path, paths: Optional[Sequence[str]]) -> bool:
    doc_ext = {".pdf", ".docx", ".doc", ".odt", ".rtf"}
    search_roots = [root]
    if paths:
        search_roots.extend(Path(p).parent if Path(p).is_file() else Path(p) for p in paths)
    for base in search_roots:
        if not base.is_dir():
            continue
        for fp in base.rglob("*"):
            if fp.is_file() and fp.suffix.lower() in doc_ext:
                return True
    return False


def _count_builds(root: Path, engine_id: Optional[str]) -> int:
    if engine_id == "unity":
        count = 0
        for fp in root.rglob("*.exe"):
            if (fp.parent / f"{fp.stem}_Data").is_dir():
                count += 1
        return count
    if engine_id == "gamemaker":
        layout = probe_gamemaker_layout(root)
        n = int(bool(layout.executable)) + int(bool(layout.html_entry))
        return max(n, 1 if n else 0)
    if engine_id == "godot":
        project = find_godot_project_root(root) or root
        exes = list(project.rglob("*.exe"))
        return len(exes)
    return 0


def _check_zip_integrity(root: Path, paths: Optional[Sequence[str]]) -> Dict[str, Any]:
    candidates: List[Path] = []
    if root.suffix.lower() == ".zip":
        candidates.append(root)
    if paths:
        for raw in paths:
            p = Path(raw)
            if p.suffix.lower() == ".zip" and p.is_file():
                candidates.append(p)
    for zp in candidates:
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                bad = zf.testzip()
                if bad:
                    return {"checked": True, "corrupted": True, "file": str(zp), "bad_entry": bad}
        except (zipfile.BadZipFile, OSError) as exc:
            return {"checked": True, "corrupted": True, "file": str(zp), "error": str(exc)}
    return {"checked": bool(candidates), "corrupted": False}
