"""
Submission intake reliability — deterministic packaging / noise diagnostics.

Not used for achieved grades; operational + audit layer only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Lowercase path segments treated as auto-ignore hints (align with batch extract filters).
INTAKE_IGNORE_DIR_NAMES: frozenset[str] = frozenset(
    {
        "bin",
        "obj",
        "debug",
        "release",
        ".vs",
        ".git",
        ".idea",
        "__pycache__",
        "node_modules",
        "__macosx",
        ".ds_store",
        "packages",
        "testresults",
        "library",  # Unity / Godot
        ".godot",
        "temp",
        "tmp",
        "build",
        "_build",
        "builds",
        "logs",
        "cachedata",
        ".gradle",
        "deriveddata",
    }
)

ZIP_PREFERRED_NOTICE_AR = (
    "يُفضّل تسليم المشروع كملف ZIP واحد مع استبعاد مجلدات Library وTemp وobj وbuild "
    "وnode_modules لتقليل الضجيج وتحسين سرعة الرفع واستقرار استخراج الأدلة الآلي."
)


def get_ingestion_limits() -> Dict[str, int]:
    """Hard caps for multipart intake (operational guardrails)."""

    def _i(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    return {
        "max_multipart_files": max(1000, _i("INGESTION_MAX_MULTIPART_FILES", 24_000)),
        "max_upload_bytes_total": max(
            64 * 1024 * 1024,
            _i("INGESTION_MAX_UPLOAD_BYTES_TOTAL", 4 * 1024 * 1024 * 1024),
        ),
    }


def get_intake_ratio_thresholds() -> Dict[str, float]:
    """Soft thresholds for noise / artifact diagnostics."""

    def _f(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except ValueError:
            return default

    return {
        "excessive_ignore_ratio": min(0.95, max(0.1, _f("INGESTION_EXCESSIVE_IGNORE_RATIO", 0.45))),
        "high_file_count_warning": max(1000, int(_f("INGESTION_HIGH_FILE_COUNT_WARNING", 8000))),
    }


def _norm_rel(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def path_matches_intake_ignore(rel_posix: str) -> bool:
    parts = [p.lower() for p in Path(_norm_rel(rel_posix)).parts if p not in (".", "")]
    return any(p in INTAKE_IGNORE_DIR_NAMES for p in parts)


def _per_path_noise_flags(rel_posix: str) -> List[Dict[str, str]]:
    parts = [p.lower() for p in Path(_norm_rel(rel_posix)).parts]
    flags: List[Dict[str, str]] = []
    if "library" in parts:
        flags.append({"flag": "unity_library_folder_uploaded"})
    if "temp" in parts or "tmp" in parts:
        flags.append({"flag": "engine_temp_or_tmp_uploaded"})
    if "node_modules" in parts:
        flags.append({"flag": "node_modules_folder_uploaded"})
    if ".git" in parts:
        flags.append({"flag": "git_folder_uploaded"})
    if "obj" in parts:
        flags.append({"flag": "dotnet_obj_folder_uploaded"})
    if "build" in parts or "builds" in parts:
        flags.append({"flag": "build_artifact_path_uploaded"})
    return flags


def _merge_flag_dicts(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        f = row.get("flag")
        if not f or f in seen:
            continue
        seen.add(f)
        out.append({"flag": f})
    return sorted(out, key=lambda x: x["flag"])


def analyze_path_intake_pairs(
    path_size_pairs: Sequence[Tuple[str, int]],
) -> Dict[str, Any]:
    """
    Core intake analysis from (relative_or_absolute_path, size_bytes) pairs.
    """
    thresholds = get_intake_ratio_thresholds()
    total_files = 0
    ignored_files = 0
    effective_files = 0
    total_bytes = 0
    ignored_bytes = 0
    ignore_hits: Dict[str, int] = {}
    all_flags: List[Dict[str, str]] = []

    for rel_raw, sz in path_size_pairs:
        rel = _norm_rel(rel_raw)
        if not rel:
            continue
        total_files += 1
        total_bytes += max(0, sz)
        all_flags.extend(_per_path_noise_flags(rel))
        ignored = path_matches_intake_ignore(rel)
        if ignored:
            ignored_files += 1
            ignored_bytes += max(0, sz)
            for p in [x.lower() for x in Path(rel).parts]:
                if p in INTAKE_IGNORE_DIR_NAMES:
                    ignore_hits[p] = ignore_hits.get(p, 0) + 1
        else:
            effective_files += 1

    ratio = (ignored_files / total_files) if total_files else 0.0
    noise = _merge_flag_dicts(all_flags)
    if ratio >= thresholds["excessive_ignore_ratio"] and total_files >= 5:
        noise.append({"flag": "excessive_runtime_artifacts"})
    if total_files >= thresholds["high_file_count_warning"]:
        noise.append({"flag": "high_multipart_file_count"})
    noise = _merge_flag_dicts(noise)

    diagnostics: Dict[str, Any] = {
        "total_files_uploaded": total_files,
        "total_bytes_uploaded": total_bytes,
        "ignored_files": ignored_files,
        "ignored_bytes_estimate": ignored_bytes,
        "effective_analysis_files": effective_files,
        "ignored_path_segment_hits": dict(sorted(ignore_hits.items(), key=lambda x: -x[1])[:20]),
        "ignore_ratio": round(ratio, 4),
        "packaging_recommendation_ar": ZIP_PREFERRED_NOTICE_AR,
        "auto_ignore_segments": sorted(INTAKE_IGNORE_DIR_NAMES),
    }

    return {
        "submission_noise_flags": noise,
        "upload_diagnostics": diagnostics,
    }


async def _multipart_part_size(uf: Any) -> int:
    """File size for intake limits without loading entire bodies into RAM."""
    sz = getattr(uf, "size", None)
    if sz is not None:
        try:
            return max(0, int(sz))
        except (TypeError, ValueError):
            pass
    spool = getattr(uf, "file", None)
    if spool is not None:
        try:
            pos = spool.tell()
            spool.seek(0, 2)
            n = int(spool.tell())
            spool.seek(pos)
            return max(0, n)
        except Exception:
            pass
    body = await uf.read()
    try:
        await uf.seek(0)
    except Exception:
        try:
            uf.file.seek(0)  # type: ignore[union-attr]
        except Exception:
            pass
    return len(body)


async def analyze_multipart_upload_manifest(files: Sequence[Any]) -> Dict[str, Any]:
    """
    Build intake summary from multipart metadata (sizes from headers/spool, not full reads).
    `files` items must be Starlette/FastAPI UploadFile-like (read/seek).
    """
    pairs: List[Tuple[str, int]] = []
    for uf in files:
        name = getattr(uf, "filename", None) or "unknown"
        pairs.append((_norm_rel(name), await _multipart_part_size(uf)))

    core = analyze_path_intake_pairs(pairs)
    core["upload_diagnostics"]["multipart_parts"] = len(pairs)
    return core


def build_submission_intake_profile(
    submission_disk_paths: Sequence[str],
    intake_relative_paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Per-submission intake block for project profile / evidence (after files are on disk).
    Prefer browser/archive-relative paths when available (preserves Library/ etc.).
    """
    if intake_relative_paths:
        pairs = [(_norm_rel(p), 0) for p in intake_relative_paths if _norm_rel(p)]
        rel_block = analyze_path_intake_pairs(pairs)
        disk_pairs: List[Tuple[str, int]] = []
        for raw in submission_disk_paths:
            if not raw or not raw.strip():
                continue
            try:
                p = Path(raw)
                st = p.stat() if p.is_file() else None
                sz = st.st_size if st else 0
            except OSError:
                sz = 0
            disk_pairs.append((_norm_rel(raw), sz))
        disk_block = analyze_path_intake_pairs(disk_pairs)
        merged_diag = dict(rel_block["upload_diagnostics"])
        merged_diag["relative_path_files"] = rel_block["upload_diagnostics"].get("total_files_uploaded")
        merged_diag["total_bytes_uploaded"] = disk_block["upload_diagnostics"].get("total_bytes_uploaded", 0)
        merged_diag["on_disk_files"] = disk_block["upload_diagnostics"].get("total_files_uploaded")
        merged_diag["on_disk_bytes"] = disk_block["upload_diagnostics"].get("total_bytes_uploaded")
        flags = _merge_flag_dicts(
            list(rel_block["submission_noise_flags"]) + list(disk_block["submission_noise_flags"])
        )
        return {
            "version": 1,
            "source": "relative_paths_plus_disk",
            "submission_noise_flags": flags,
            "upload_diagnostics": merged_diag,
        }

    disk_pairs: List[Tuple[str, int]] = []
    for raw in submission_disk_paths:
        if not raw or not raw.strip():
            continue
        try:
            p = Path(raw)
            if not p.is_file():
                continue
            disk_pairs.append((_norm_rel(str(p.resolve())), p.stat().st_size))
        except OSError:
            continue
    core = analyze_path_intake_pairs(disk_pairs)
    core["version"] = 1
    core["source"] = "disk_paths_only"
    return core


def intake_rejection_message(
    reason: str,
    *,
    limit: Optional[int] = None,
    actual: Optional[int] = None,
) -> str:
    if reason == "too_many_multipart_parts":
        return (
            "تم رفض الرفع: عدد أجزاء الطلب يتجاوز الحد التشغيلي المسموح. "
            f"الحد: {limit}، الوارد: {actual}. "
            "يُفضّل رفع ZIP واحد لكل طالب أو تقليل الملفات (استبعاد Library/Temp)."
        )
    if reason == "upload_too_large":
        return (
            "تم رفض الرفع: إجمالي حجم الملفات يتجاوز الحد المسموح للتشغيل الآمن. "
            f"الحد (بايت): {limit}، الوارد: {actual}. "
            "جرّب أرشفة أنظف أو رفع على دفعات."
        )
    return "تم رفض الرفع لأسباب تشغيلية."

