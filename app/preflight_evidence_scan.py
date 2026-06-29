"""
Fast pre-grade evidence scan — paths / archive listing only (no AI, vision, or runtime).

Typical cost: sub-second to a few seconds even for large ZIPs (central directory read only).
"""
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.archive_extraction_utils import is_runtime_nested_archive
from app.game_engine_signatures import (
    ENGINE_PATH_MARKERS,
    detect_engine_from_text,
    has_runnable_game_project,
    is_runnable_game_path,
)
from app.pro_evidence_signals import (
    path_looks_like_peer_design_doc,
    path_looks_like_testing_doc,
)
from app.project_intelligence.submission_intake import path_matches_intake_ignore

PREFLIGHT_VERSION = "preflight_evidence_v4"

_GDD_PATH_RE = re.compile(
    r"gdd|game[\s_-]*design"
    r"|وثيق[ةه]\s*تصميم"
    r"|تصميم\s*(?:ال)?لعبة"  # «تصميم لعبة» أو «تصميم اللعبة» (أسماء عربية شائعة)
    r"|design[\s_-]*doc",
    re.IGNORECASE,
)
_TEST_PLAN_PATH_RE = re.compile(r"test[\s_-]*plan|خطة[\s_-]*اختبار", re.IGNORECASE)
_WORD_PDF_RE = re.compile(r"\.(docx?|pdf)$", re.IGNORECASE)
# .sb3/.sb2 = Scratch projects, runnable game builds (executable-equivalent).
_EXE_RE = re.compile(r"\.(exe|win|pck|apk|sb3|sb2)$", re.IGNORECASE)

# Engine markers come from the shared single-source registry so Scratch / GameMaker
# / etc. stay in sync with every other detection path.
_ENGINE_MARKERS: Dict[str, Tuple[str, ...]] = dict(ENGINE_PATH_MARKERS)


def _norm_path(p: str) -> str:
    return (p or "").replace("\\", "/").strip()


def _effective_paths(path_size_pairs: Sequence[Tuple[str, int]]) -> List[str]:
    out: List[str] = []
    for raw, _sz in path_size_pairs:
        rel = _norm_path(raw)
        if not rel or rel.endswith("/"):
            continue
        if path_matches_intake_ignore(rel):
            continue
        out.append(rel)
    return out


def _basename_lower(p: str) -> str:
    return PurePosixPath(_norm_path(p)).name.lower()


def _detect_engine(joined_lower: str) -> Optional[str]:
    return detect_engine_from_text(joined_lower)


def _compute_preflight_grade_hint(
    *,
    has_gdd: bool,
    has_project: bool,
    has_exe: bool,
    has_word_pdf: bool,
    advisory_missing: Sequence[str],
) -> str:
    """
    Advisory grade hint from filenames/structure only — never a final BTEC grade.

    Core deliverables (project + runnable build + documentation) outweigh missing
    *separate* test-plan / bug-log filenames; those sections may live inside Word.
    """
    core_ready = has_project and has_exe and has_word_pdf
    if core_ready and has_gdd:
        return "P+"
    if core_ready:
        return "P"
    if has_project and has_word_pdf:
        return "P?"
    if has_project or has_word_pdf or has_exe:
        return "?"
    _ = advisory_missing  # gaps already surface in checklist / warn_teacher
    return "U"


def _scan_path_list(paths: Sequence[str]) -> Dict[str, Any]:
    path_list = [_norm_path(p) for p in paths if _norm_path(p)]
    joined = "\n".join(path_list)
    joined_lower = joined.lower()

    has_gdd = bool(_GDD_PATH_RE.search(joined)) or any(
        _GDD_PATH_RE.search(_basename_lower(p)) for p in path_list
    ) or any(path_looks_like_peer_design_doc(p) for p in path_list)
    has_test_plan = bool(_TEST_PLAN_PATH_RE.search(joined)) or any(
        _TEST_PLAN_PATH_RE.search(_basename_lower(p)) for p in path_list
    )
    has_testing_doc = any(path_looks_like_testing_doc(p) for p in path_list)
    has_word_pdf = any(_WORD_PDF_RE.search(p) for p in path_list)
    # A Scratch .sb3 / GameMaker data.win is a runnable build even with no classic .exe.
    has_runnable_game = any(
        is_runnable_game_path(_basename_lower(p), PurePosixPath(_norm_path(p)).suffix.lower())
        for p in path_list
    )
    # Nested build archives inside RAR/ZIP (e.g. «(.exe)بعد التعديل.zip») — same heuristic
    # as full grading in archive_extraction_utils; preflight lists outer members only.
    has_nested_build = any(is_runtime_nested_archive(p) for p in path_list)
    has_exe = (
        any(_EXE_RE.search(p) for p in path_list)
        or has_runnable_game
        or has_nested_build
    )
    engine = _detect_engine(joined_lower)
    has_project = (
        engine is not None
        or has_runnable_game
        or has_runnable_game_project(joined_lower)
    )

    items = [
        ("gdd", "وثيقة تصميم اللعبة (GDD)", has_gdd),
        ("project", "مشروع اللعبة (محرك/ملفات مصدر)", has_project),
        ("test_plan", "خطة اختبار (Test Plan)", has_test_plan or has_testing_doc),
        ("word_pdf", "وثيقة Word/PDF", has_word_pdf),
        ("executable", "ملف تنفيذي / build", has_exe),
    ]

    checklist = [
        {
            "key": key,
            "label_ar": label,
            "present": present,
            "symbol": "✓" if present else "✗",
        }
        for key, label, present in items
    ]
    missing = [c["label_ar"] for c in checklist if not c["present"]]
    present_labels = [c["label_ar"] for c in checklist if c["present"]]

    # Filename-only gaps — advisory warnings, NOT automatic U (content may be inside Word).
    advisory_missing: List[str] = []
    if not has_test_plan and not has_testing_doc:
        advisory_missing.append("خطة اختبار (Test Plan) — قد تكون داخل Word")

    cp6_checks = [has_test_plan or has_testing_doc, has_exe or has_project, has_word_pdf]
    cp6_likely_pct = round(100 * sum(cp6_checks) / len(cp6_checks))

    expected = _compute_preflight_grade_hint(
        has_gdd=has_gdd,
        has_project=has_project,
        has_exe=has_exe,
        has_word_pdf=has_word_pdf,
        advisory_missing=advisory_missing,
    )

    warn_teacher = bool(advisory_missing) or expected in ("?", "P?", "U")
    summary_parts: List[str] = []
    if missing:
        summary_parts.append("لم يتم العثور على (أسماء ملفات): " + "، ".join(missing[:6]))
    if advisory_missing and expected not in ("U", "?"):
        summary_parts.append(
            "تنبيه: قد تكون داخل Word — "
            + "، ".join(advisory_missing[:3])
        )
    if present_labels:
        summary_parts.append("متوفر: " + "، ".join(present_labels[:6]))
    if engine:
        summary_parts.append(f"محرك مُكتشف: {engine}")
    if has_nested_build:
        summary_parts.append("build داخل أرشيف متداخل (من الاسم)")
    summary_parts.append(f"تغطية C.P6 (أسماء ملفات فقط): {cp6_likely_pct}%")
    summary_parts.append(f"تلميح تقدير أولي (ليس نهائياً): {expected}")
    if expected in ("P", "P+"):
        summary_parts.append("الأدلة الأساسية متوفرة — التصحيح الكامل يقرأ محتوى Word")

    return {
        "version": PREFLIGHT_VERSION,
        "scan_method": "path_names_only",
        "file_count": len(path_list),
        "engine_detected": engine,
        "items": checklist,
        "missing_ar": missing,
        "present_ar": present_labels,
        "advisory_missing_ar": advisory_missing,
        "critical_missing_ar": advisory_missing,  # legacy key — same advisory list
        "warn_teacher": warn_teacher,
        "cp6_path_coverage_pct": cp6_likely_pct,
        "expected_grade_hint": expected,
        "expected_grade_label_ar": f"تلميح تقدير أولي: {expected} (ليس حكماً نهائياً)",
        "summary_ar": " — ".join(summary_parts),
        "disclaimer_ar": (
            "فحص أولي سريع من أسماء الملفات والهيكل فقط — لا يستبدل التصحيح الكامل. "
            "خطة الاختبار وسجل الأخطاء قد يكونان داخل Word/PowerPoint ويُكتشفان عند التصحيح. "
            "التقدير المعروض تلميح إرشادي وليس درجة Pearson النهائية."
        ),
    }


def scan_path_size_pairs(path_size_pairs: Sequence[Tuple[str, int]]) -> Dict[str, Any]:
    paths = _effective_paths(path_size_pairs)
    return _scan_path_list(paths)


def scan_relative_paths(paths: Sequence[str]) -> Dict[str, Any]:
    pairs = [(_norm_path(p), 0) for p in paths if _norm_path(p)]
    return scan_path_size_pairs(pairs)


def list_zip_member_paths(archive_path: str) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = _norm_path(info.filename)
            if name:
                out.append((name, info.file_size or 0))
    return out


def list_archive_member_paths(archive_path: str) -> List[Tuple[str, int]]:
    path = archive_path
    ext = Path(path).suffix.lower()
    if ext == ".zip":
        if not zipfile.is_zipfile(path):
            raise ValueError("not_a_zip")
        return list_zip_member_paths(path)
    if ext == ".rar":
        from app.archive_extraction_utils import list_rar_members_fast

        members = list_rar_members_fast(path, timeout=120)
        return [(_norm_path(m), 0) for m in members]
    raise ValueError("unsupported_archive")


def scan_archive_file(archive_path: str) -> Dict[str, Any]:
    pairs = list_archive_member_paths(archive_path)
    result = scan_path_size_pairs(pairs)
    result["scan_method"] = "archive_listing"
    result["archive_name"] = Path(archive_path).name
    result["archive_members_listed"] = len(pairs)
    return result


async def scan_upload_archive(upload_file: Any) -> Dict[str, Any]:
    """Save upload to temp file, list members, scan, delete temp."""
    suffix = Path(getattr(upload_file, "filename", None) or "upload.zip").suffix or ".zip"
    fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="preflight_")
    os.close(fd)
    try:
        body = await upload_file.read()
        Path(tmp).write_bytes(body)
        try:
            await upload_file.seek(0)
        except Exception:
            pass
        return scan_archive_file(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
