"""
Archive extraction path utilities — Windows long-path safe (WinError 206).
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Tuple

# Leave headroom below MAX_PATH (260) for Windows APIs
_WIN_SAFE_MAX = 240


def win_long_path(path: str | Path) -> str:
    """Enable extended-length paths on Windows when needed."""
    p = str(path)
    if sys.platform != "win32":
        return p
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + os.path.abspath(p)


def makedirs_safe(path: Path) -> None:
    os.makedirs(win_long_path(path), exist_ok=True)


def collapse_redundant_archive_path(rel: str) -> str:
    """
    Collapse duplicated nested folder sequences inside archives.
    e.g. A/B/C/A/B/C/file -> A/B/C/file
    """
    parts = [p for p in PurePosixPath(rel.replace("\\", "/")).parts if p and p not in (".", "..")]
    if len(parts) < 4:
        return "/".join(parts)
    changed = True
    while changed and len(parts) >= 4:
        changed = False
        for i in range(1, len(parts) // 2 + 1):
            if len(parts) >= 2 * i and parts[:i] == parts[i : 2 * i]:
                parts = parts[:i] + parts[2 * i :]
                changed = True
                break
    return "/".join(parts)


def _sanitize_segment(seg: str, *, max_len: int = 80) -> str:
    seg = (seg or "file").strip().strip(".")
    seg = re.sub(r'[<>:"|?*\x00-\x1f]', "_", seg)
    if len(seg) > max_len:
        digest = hashlib.sha1(seg.encode("utf-8", errors="replace")).hexdigest()[:10]
        seg = seg[: max_len - 11] + "_" + digest
    return seg or "file"


def safe_archive_out_path(
    extract_dir: Path,
    decoded_path: str,
    *,
    max_total_len: int = _WIN_SAFE_MAX,
) -> Tuple[Path, str]:
    """
    Map archive relative path → disk path within extract_dir.
    Returns (absolute_out_path, normalized_relative_key).
    """
    rel = collapse_redundant_archive_path(decoded_path)
    rel = rel.replace("\\", "/").lstrip("/")
    parts = [_sanitize_segment(p) for p in PurePosixPath(rel).parts if p]
    if not parts:
        parts = ["file"]
    filename = parts[-1]
    parent_parts = parts[:-1]

    base = extract_dir.resolve()
    candidate = base.joinpath(*parent_parts, filename) if parent_parts else base / filename

    def _len_ok(p: Path) -> bool:
        return len(str(p)) <= max_total_len

    if _len_ok(candidate):
        makedirs_safe(candidate.parent)
        return candidate, rel

    # Flatten: extract_dir/_flat/{hash}_{basename}
    digest = hashlib.sha1(rel.encode("utf-8", errors="replace")).hexdigest()[:16]
    flat_name = f"{digest}_{_sanitize_segment(filename, max_len=120)}"
    flat = base / "_flat" / flat_name
    makedirs_safe(flat.parent)
    return flat, rel


def write_bytes_safe(path: Path, data: bytes) -> None:
    makedirs_safe(path.parent)
    with open(win_long_path(path), "wb") as f:
        f.write(data)


class RarToolUnavailableError(RuntimeError):
    """No `unrar`-compatible tool is installed to read/extract a RAR archive.

    Raised instead of silently treating the archive as empty (which previously caused
    valid RAR submissions to be graded ``U`` on servers without unrar installed).
    """


def find_unrar_tool() -> str | None:
    """Locate an `unrar`-compatible binary (supports the `lb` bare-list syntax).

    Windows: known WinRAR install paths. Linux/macOS (production): search PATH for
    `unrar` / `unrar-free`. Without this, RAR listing returns nothing on Linux.
    """
    import shutil

    if sys.platform == "win32":
        for unrar_path in (
            r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
            r"C:\Program Files\WinRAR\Rar.exe",
        ):
            if os.path.isfile(unrar_path):
                return unrar_path
    # PATH lookup covers Linux/macOS and any custom-installed Windows binary.
    for candidate in ("unrar", "unrar-free", "rar"):
        found = shutil.which(candidate)
        if found:
            return found
    # Explicit override for non-standard install locations.
    override = os.getenv("AI_GRADER_UNRAR_PATH", "").strip()
    if override and os.path.isfile(override):
        return override
    return None


def _apply_rarfile_unrar_tool() -> None:
    """Point rarfile at WinRAR UnRAR.exe when available (Windows)."""
    import rarfile  # type: ignore[import-untyped]

    tool = find_unrar_tool()
    if tool:
        setattr(rarfile, "UNRAR_TOOL", tool)


def _unrar_pipe_bytes(archive_path: str, member_name: str) -> bytes:
    """Stream one RAR member to memory — never touches nested paths on disk."""
    import subprocess

    tool = find_unrar_tool()
    if not tool:
        raise RuntimeError("UnRAR tool not found for long-path fallback")
    proc = subprocess.run(
        [tool, "p", "-inul", "-y", archive_path, member_name],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(err.strip() or f"unrar failed rc={proc.returncode}")
    return proc.stdout


_GENERIC_WRAPPER_NAMES = frozenset({
    "new folder",
    "newfolder",
    "new_folder",
    "folder",
    "مجلد جديد",
    "مجلد",
    "extract",
    "extracted",
    "archive",
    "rar",
    "zip",
    "submission",
    "submissions",
    "students",
    "student",
    "files",
    "file",
    "root",
    "__macosx",
    "temp",
    "tmp",
    "download",
    "downloads",
    "full",
})

_PROJECT_CATEGORY_HINTS = (
    "وثائق",
    "وثيقة",
    "تصميم",
    "العبة",
    "اللعبة",
    "فيديو",
    "صور",
    "استبيان",
    "مشروع",
    "تسليم",
    "game",
    "docs",
    "doc",
    "design",
    "video",
    "screenshot",
    "questionnaire",
    "godot",
    "unity",
    "exe",
    "console",
    "build",
    "release",
    "windows",
    "android",
    "ios",
    "linux",
    "mac",
    "presentation",
    "عرض",
)

_BUILD_ARTIFACT_FOLDER_NAMES = frozenset({
    "monobleedingedge",
    "d3d12",
    "burstdebuginformation",
    "plugins",
    "streamingassets",
})


def is_generic_wrapper_folder(name: str) -> bool:
    """True for «New folder»-style containers — not student-named folders."""
    n = (name or "").strip().lower()
    if not n:
        return False
    if n in _GENERIC_WRAPPER_NAMES:
        return True
    if re.match(r"^new folder\s*\(\d+\)$", n, re.I):
        return True
    if re.match(r"^new folder\s*\d*$", n, re.I):
        return True
    if re.match(r"^folder\s*\d*$", n, re.I):
        return True
    return False


def looks_like_project_category_folder(name: str) -> bool:
    """Artifact category folder inside one student bundle (وثائق، العبة، …)."""
    n = (name or "").strip().lower()
    if not n or n.startswith("."):
        return False
    return any(h in n for h in _PROJECT_CATEGORY_HINTS)


def looks_like_build_artifact_folder(name: str) -> bool:
    """Unity/Godot build sibling folders — not separate students."""
    n = (name or "").strip().lower()
    if not n:
        return False
    if n.endswith("_data"):
        return True
    if n in _BUILD_ARTIFACT_FOLDER_NAMES:
        return True
    if re.match(r"^.+_burst\.generated$", n):
        return True
    return False


def looks_like_submission_part_folder(name: str) -> bool:
    """Category or build artifact folder — part of one student bundle."""
    return (
        looks_like_project_category_folder(name)
        or looks_like_build_artifact_folder(name)
        or (name or "").startswith("_student_bundle")
    )


def looks_like_student_identity_folder(name: str) -> bool:
    """Student folder with institutional id, e.g. «… TF(77644) …»."""
    return bool(re.search(r"TF\s*\(\d+\)", name or "", re.I))


def looks_like_multi_student_bundle(seconds: set[str] | list[str]) -> bool:
    """True when one folder wraps several sibling student roots (not category subfolders)."""
    names = list(seconds)
    if len(names) < 2:
        return False
    non_category = [s for s in names if not looks_like_project_category_folder(s)]
    return len(non_category) >= 2


def merge_single_student_category_bundle(
    extracted_files: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    When unwrap left multiple sibling category folders (وثائق، العبة، …)
    from ONE student submission, merge under a virtual root for grading.
    """
    if not extracted_files:
        return extracted_files

    tops: set[str] = set()
    has_root_file = False
    for arc_path, _ in extracted_files:
        parts = Path(arc_path.replace("\\", "/")).parts
        if len(parts) == 1:
            has_root_file = True
        elif len(parts) >= 2:
            tops.add(parts[0])

    if len(tops) < 2:
        return extracted_files

    category_tops = [t for t in tops if looks_like_project_category_folder(t)]
    # One student project: several category folders ± loose exe/doc files at root.
    if len(category_tops) >= 2:
        return [(f"_student_bundle/{arc_path}", disk) for arc_path, disk in extracted_files]

    if has_root_file or not all(looks_like_project_category_folder(t) for t in tops):
        return extracted_files

    return [(f"_student_bundle/{arc_path}", disk) for arc_path, disk in extracted_files]


_DOC_EXTENSIONS = (".docx", ".pdf", ".doc", ".pptx")

# Files that must never become the primary graded submission (Unity/Mono system junk).
_PRIMARY_SKIP_BASENAMES = frozenset(
    {
        "browscap.ini",
        "globalconfig",
        "config",
        "machine.config",
        "settings.json",
        "default.env",
    }
)

_SYSTEM_EXE_MARKERS = (
    "unitycrashhandler",
    "unityplayer",
    "uninstall",
    "setup",
    "installer",
    "install",
    "driver",
    "audio-driver",
    "redist",
    "vc_redist",
    "dotnet",
    "bootstrap",
    "hotfix",
    "patch",
    "update",
    "launcher",
    "win64_",
    "win32_",
    "x64_setup",
    "x86_setup",
)

_RUNTIME_SKIP_PATH_SEGMENTS = frozenset(
    {
        "monobleedingedge",
        "embedruntime",
    }
)


def is_junk_primary_candidate(path: str) -> bool:
    """True for Mono/Unity config files that must not drive grading."""
    posix = path.replace("\\", "/")
    name = PurePosixPath(posix).name.lower()
    if name in _PRIMARY_SKIP_BASENAMES:
        return True
    parts = [p.lower() for p in PurePosixPath(posix).parts]
    if any(seg in _RUNTIME_SKIP_PATH_SEGMENTS for seg in parts):
        if name.endswith((".ini", ".cfg", ".config", ".xml", ".json")):
            return True
    return False


def is_system_executable(path: str) -> bool:
    name = PurePosixPath(path.replace("\\", "/")).name.lower()
    if not name.endswith(".exe"):
        return False
    if any(marker in name for marker in _SYSTEM_EXE_MARKERS):
        return True
    # Vendor driver bundles: many hyphen segments + WIN64/WIN32 token
    if re.search(r"win(64|32)", name) and name.count("-") >= 3:
        return True
    return False


def is_primary_game_executable(path: str) -> bool:
    """Student game/build .exe — not UnityCrashHandler, Godot editor, or installer tooling."""
    ps = path.lower()
    if not any(ps.endswith(ext) for ext in (".exe", ".pck", ".x86_64")):
        return False
    if is_system_executable(path) or is_junk_primary_candidate(path):
        return False
    try:
        from app.runtime_engines.godot.export_runner import is_godot_editor_executable

        if is_godot_editor_executable(Path(path)):
            return False
    except ImportError:
        pass
    return True


def _submission_file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _dedupe_code_scored(
    code_scored: list[tuple[tuple[int, int], str]],
) -> list[tuple[tuple[int, int], str]]:
    """Keep one path per source basename (Godot before/after folders duplicate .gd)."""
    by_name: dict[str, tuple[tuple[int, int], str]] = {}
    for score, path in code_scored:
        key = PurePosixPath(path.replace("\\", "/")).name.lower()
        prev = by_name.get(key)
        if prev is None or score < prev[0]:
            by_name[key] = (score, path)
    return sorted(by_name.values(), key=lambda x: x[0])


def _source_code_pick_score(path: str) -> tuple[int, int]:
    """Lower = better primary source file."""
    ps = path.lower().replace("\\", "/")
    parts = ps.split("/")
    rank = 5
    if ps.endswith(".cs"):
        rank = 1
        if "assets" in parts:
            rank = 0
        if any(p in parts for p in ("scripts", "script", "src", "source")):
            rank = -1
    elif ps.endswith((".py", ".java", ".cpp", ".c", ".js", ".gd", ".gml", ".lua")):
        rank = 2
    elif ps.endswith(".ini"):
        rank = 50
    if is_junk_primary_candidate(path):
        rank += 100
    return (rank, -_submission_file_size(path))


def pick_best_submission_file(
    file_list: list,
    *,
    doc_extensions: tuple[str, ...] | None = None,
) -> tuple | None:
    """
    From archive rows (student_name, path[, archive_rel]), pick the best primary file.
    Priority: documents → game .exe → project source code → other non-junk files.
    """
    if not file_list:
        return None

    try:
        from app.artifact_inventory import (  # type: ignore
            EXECUTABLE_ARTIFACT_EXTENSIONS,
            SOURCE_CODE_EXTENSIONS,
        )
    except ImportError:
        EXECUTABLE_ARTIFACT_EXTENSIONS = frozenset({".exe", ".pck"})
        SOURCE_CODE_EXTENSIONS = frozenset({".cs", ".py", ".java"})

    docs_ext = doc_extensions or _DOC_EXTENSIONS
    exe_ext = tuple(EXECUTABLE_ARTIFACT_EXTENSIONS)
    src_ext = tuple(SOURCE_CODE_EXTENSIONS)

    rows: list[tuple[str, str]] = []
    for row in file_list:
        path = str(row[1] if len(row) > 1 else row[0])
        name = str(row[0]) if len(row) > 1 else Path(path).stem
        rows.append((name, path))

    existing = [(sn, p) for sn, p in rows if os.path.isfile(p)] or rows

    docs = [
        (sn, p)
        for sn, p in existing
        if p.lower().endswith(docs_ext) and not is_junk_primary_candidate(p)
    ]
    if docs:
        return max(docs, key=lambda x: _submission_file_size(x[1]))

    exes = [
        (sn, p)
        for sn, p in existing
        if p.lower().endswith(exe_ext) and is_primary_game_executable(p)
    ]
    if exes:
        return max(exes, key=lambda x: _submission_file_size(x[1]))

    code = [
        (sn, p)
        for sn, p in existing
        if p.lower().endswith(src_ext) and not is_junk_primary_candidate(p)
    ]
    if code:
        return min(code, key=lambda x: _source_code_pick_score(x[1]))

    clean = [(sn, p) for sn, p in existing if not is_junk_primary_candidate(p)]
    if clean:
        return max(clean, key=lambda x: _submission_file_size(x[1]))

    return max(existing, key=lambda x: _submission_file_size(x[1]))


def _merge_archive_result_entries(
    result: list,
    *,
    student_name: str | None = None,
) -> list:
    """Combine multiple archive tuples into one student submission."""
    if not result:
        return result
    all_paths: list[str] = []
    all_arc: list[str] = []
    flat_rows: list[tuple] = []
    for entry in result:
        paths = list(entry[2]) if len(entry) > 2 else [str(entry[1])]
        arcs = list(entry[3]) if len(entry) > 3 else []
        all_paths.extend(str(p) for p in paths)
        all_arc.extend(str(a) for a in arcs)
        for p in paths:
            flat_rows.append((str(entry[0]), str(p)))
    picked = pick_best_submission_file(flat_rows)
    best_path = picked[1] if picked else str(result[0][1])
    if not student_name:
        try:
            from app.document_processor import extract_student_name_from_file

            student_name = extract_student_name_from_file(best_path) or str(result[0][0])
        except Exception:
            student_name = str(result[0][0])
    merged_paths = sorted(set(all_paths), key=lambda x: x.lower())
    merged_arc = sorted(set(all_arc), key=lambda x: x.lower())
    return [(student_name, best_path, merged_paths, merged_arc)]


def resolve_bundle_student_name(
    best_path: str,
    arc_paths: list[str],
    *,
    all_paths: list[str] | None = None,
) -> str:
    """Pick human name for a merged single-student archive bundle."""
    try:
        from app.document_processor import extract_student_name_from_file

        candidates: list[str] = []
        for path in [best_path, *(all_paths or [])]:
            if path and path not in candidates:
                candidates.append(path)

        def _rank(path: str) -> tuple[int, int]:
            lower = path.lower()
            is_doc = any(lower.endswith(ext) for ext in _DOC_EXTENSIONS)
            size = 0
            try:
                size = os.path.getsize(path)
            except OSError:
                pass
            return (0 if is_doc else 1, -size)

        for path in sorted(candidates, key=_rank)[:8]:
            if not any(path.lower().endswith(ext) for ext in _DOC_EXTENSIONS):
                continue
            doc = extract_student_name_from_file(path)
            if doc:
                return doc.strip()
    except Exception:
        pass
    tf_re = re.compile(r"TF\s*\(\d+\)", re.I)
    for arc in arc_paths:
        for part in Path(arc.replace("\\", "/")).parts:
            if tf_re.search(part):
                return part
    return ""


def merge_likely_single_student_bundle(
    result: list,
    *,
    top_level_folder_names: set[str] | list[str] | None = None,
    archive_name: str = "",
) -> list:
    """
    Merge sibling Unity/build folders (and optional root .exe) from ONE student
    into a single submission row.
    """
    if len(result) <= 1:
        return result

    names = [r[0].strip() for r in result if r[0].strip()]
    tops = {t.strip() for t in (top_level_folder_names or names) if t.strip()}
    tops.discard("__root__")

    identity_folders = [n for n in names if looks_like_student_identity_folder(n)]
    if len(identity_folders) >= 2:
        return result

    build_or_category_tops = sum(1 for t in tops if looks_like_submission_part_folder(t))
    has_root_exe = any(
        str(entry[1]).lower().endswith(".exe")
        for entry in result
        if len(str(entry[0])) > 0
    )

    should_merge = False
    if build_or_category_tops >= 2:
        should_merge = True
    elif build_or_category_tops >= 1 and (has_root_exe or len(tops) <= 4):
        should_merge = True
    elif tops and all(looks_like_submission_part_folder(t) for t in tops):
        should_merge = True
    elif len(tops) == 1 and len(result) > 1:
        # One wrapper folder split into multiple pseudo-students (root exe + subfolders).
        should_merge = True

    if not should_merge:
        return result

    stem = Path(archive_name).stem.strip() if archive_name else ""
    student_name: str | None = None
    if stem and len(stem) >= 3 and not looks_like_submission_part_folder(stem):
        student_name = stem
    elif len(identity_folders) == 1:
        student_name = identity_folders[0]
    return _merge_archive_result_entries(result, student_name=student_name)


def force_single_student_archive_result(
    result: list,
    *,
    archive_name: str = "",
) -> list:
    """Teacher chose «one student» archive — always one submission."""
    if len(result) <= 1:
        return result
    student_name: str | None = None
    stem = Path(archive_name).stem.strip() if archive_name else ""
    if stem and len(stem) >= 3 and not looks_like_submission_part_folder(stem):
        student_name = stem
    return _merge_archive_result_entries(result, student_name=student_name)


def _collect_tf_roots(result: list) -> set[str]:
    tf_re = re.compile(r"TF\s*\(\d+\)", re.I)
    roots: set[str] = set()
    for entry in result:
        arcs = entry[3] if len(entry) > 3 else []
        for arc in arcs:
            for part in Path(str(arc).replace("\\", "/")).parts:
                if tf_re.search(part):
                    roots.add(part.strip())
    for entry in result:
        name = str(entry[0]).strip()
        if tf_re.search(name):
            roots.add(name)
    return roots


def _collect_doc_identities(result: list) -> set[str]:
    try:
        from app.document_processor import extract_student_name_from_file
    except ImportError:
        return set()

    identities: set[str] = set()
    for entry in result:
        ps = str(entry[1])
        if not ps.lower().endswith(_DOC_EXTENSIONS):
            continue
        extracted = extract_student_name_from_file(ps)
        if extracted:
            identities.add(extracted.strip().lower())
    return identities


def count_distinct_archive_students(result: list) -> int:
    """
    Count likely separate students — by identity (TF id, document name),
    not merely top-level folder count.
    """
    if not result:
        return 0

    merged = consolidate_archive_student_results(list(result))
    if len(merged) <= 1:
        return len(merged)

    tf_roots = _collect_tf_roots(result)
    if len(tf_roots) >= 2:
        return len(tf_roots)
    if len(tf_roots) == 1:
        return 1

    doc_identities = _collect_doc_identities(result)
    if len(doc_identities) >= 2:
        return len(doc_identities)
    if len(doc_identities) == 1:
        return 1

    names = [str(r[0]).strip() for r in result if str(r[0]).strip()]
    identity_folders = [n for n in names if looks_like_student_identity_folder(n)]
    if len(identity_folders) >= 2:
        return len(identity_folders)
    if len(identity_folders) == 1:
        return 1

    part_folders = sum(1 for n in names if looks_like_submission_part_folder(n))
    if part_folders >= 2:
        return 1

    # Multiple sibling folders with no conflicting student identity → one bundle.
    return 1


def reject_single_mode_for_multi_student_archive(
    result: list,
    *,
    archive_name: str = "",
) -> dict | None:
    """
    Block «طالب واحد» when archive clearly contains multiple student folders.
    Returns error dict for API, or None if OK to proceed.

    Note: when the teacher explicitly chose single-student archive mode, main.py
    skips this check and always merges — this guard is for ambiguous call sites only.
    """
    n = count_distinct_archive_students(result)
    if n < 2:
        return None
    label = f"«{archive_name}»" if archive_name else "الأرشيف"
    return {
        "ok": False,
        "code": "multi_student_archive_in_single_mode",
        "student_count_detected": n,
        "message_ar": (
            f"الأرشيف {label} يحتوي {n} مجلد(ات) طلاب منفصلة. "
            "استخدم زر «عدة طلاب» (ZIP/RAR — مجلد لكل طالب) وليس «طالب واحد → ZIP/RAR». "
            "إذا كان الأرشيف داخل مجلد «New folder»، النظام يفكّه تلقائياً في وضع عدة طلاب."
        ),
    }


def consolidate_archive_student_results(result: list) -> list:
    """
    Safety net: one student RAR split into category folders → merge to one submission.
    """
    if len(result) == 1:
        name = str(result[0][0])
        if name.startswith("_student_bundle"):
            paths = list(result[0][2]) if len(result[0]) > 2 else [str(result[0][1])]
            arcs = list(result[0][3]) if len(result[0]) > 3 else []
            resolved = resolve_bundle_student_name(
                str(result[0][1]), arcs or paths, all_paths=paths
            )
            if resolved:
                entry = result[0]
                return [(resolved, entry[1], list(entry[2]), list(entry[3]) if len(entry) > 3 else [])]
        return result

    if len(result) <= 1:
        return result

    names = [str(r[0]) for r in result]

    if any(is_generic_wrapper_folder(n) for n in names):
        return result

    if all(
        looks_like_project_category_folder(n) or n.startswith("_student_bundle")
        for n in names
    ):
        return _merge_archive_result_entries(result)

    tf_re = re.compile(r"TF\s*\(\d+\)", re.I)
    student_roots: set[str] = set()
    for entry in result:
        arcs = entry[3] if len(entry) > 3 else []
        for arc in arcs:
            parts = Path(str(arc).replace("\\", "/")).parts
            if not parts:
                continue
            if is_generic_wrapper_folder(parts[0]) and len(parts) >= 2:
                if tf_re.search(parts[1]):
                    student_roots.add(parts[1])
                continue
            if tf_re.search(parts[0]):
                student_roots.add(parts[0])
    if len(student_roots) == 1 and len(result) <= 2:
        return _merge_archive_result_entries(result)

    part_count = sum(1 for n in names if looks_like_submission_part_folder(n))
    if part_count >= 2:
        return _merge_archive_result_entries(result)

    try:
        from app.document_processor import extract_student_name_from_file
    except ImportError:
        return result

    doc_names: list[str] = []
    _doc_scanned = 0
    for entry in result:
        ps = str(entry[1])
        if not ps.lower().endswith(_DOC_EXTENSIONS):
            continue
        if _doc_scanned >= 8:
            break
        _doc_scanned += 1
        extracted = extract_student_name_from_file(ps)
        if extracted:
            doc_names.append(extracted.strip())
    if doc_names:
        unique = {n.lower(): n for n in doc_names}
        if len(unique) == 1:
            return _merge_archive_result_entries(
                result, student_name=next(iter(unique.values()))
            )

    return result


def unwrap_single_wrapper_folder(
    extracted_files: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], str | None]:
    """
    Unwrap archives that use one generic container folder (e.g. «New folder/studentA/…»).
    Does NOT unwrap student-named folders (e.g. «Ahmad … TF(77644)/وثائق/…»).
    Returns (updated_files, wrapper_name_or_none).
    """
    if not extracted_files:
        return extracted_files, None

    tops: set[str] = set()
    seconds: set[str] = set()
    has_direct_wrapper_files = False
    for arc_path, _ in extracted_files:
        parts = Path(arc_path.replace("\\", "/")).parts
        if len(parts) == 2:
            tops.add(parts[0])
            has_direct_wrapper_files = True
        elif len(parts) >= 3:
            tops.add(parts[0])
            seconds.add(parts[1])

    generic_wrappers = [
        t for t in tops
        if is_generic_wrapper_folder(t) and not looks_like_student_identity_folder(t)
    ]
    if generic_wrappers:
        wrapper_set = set(generic_wrappers)
        out: list[tuple[str, str]] = []
        for arc_path, disk in extracted_files:
            parts = Path(arc_path.replace("\\", "/")).parts
            if len(parts) >= 2 and parts[0] in wrapper_set:
                out.append(("/".join(parts[1:]), disk))
            else:
                out.append((arc_path, disk))
        inner, inner_wrap = unwrap_single_wrapper_folder(out)
        return inner, generic_wrappers[0] if len(generic_wrappers) == 1 else inner_wrap

    if len(tops) != 1:
        return extracted_files, None

    wrapper = next(iter(tops))
    if looks_like_student_identity_folder(wrapper):
        return extracted_files, None
    should_unwrap = is_generic_wrapper_folder(wrapper) or looks_like_multi_student_bundle(seconds)
    if not should_unwrap:
        return extracted_files, None
    if is_generic_wrapper_folder(wrapper) and len(seconds) < 1 and not has_direct_wrapper_files:
        return extracted_files, None
    out = []
    for arc_path, disk in extracted_files:
        parts = Path(arc_path.replace("\\", "/")).parts
        if len(parts) >= 2 and parts[0] == wrapper:
            out.append(("/".join(parts[1:]), disk))
        else:
            out.append((arc_path, disk))
    return out, wrapper


def strip_archive_wrapper_prefix(path: str, wrapper: str | None) -> str:
    if not wrapper:
        return path
    parts = Path(path.replace("\\", "/")).parts
    if len(parts) >= 2 and parts[0] == wrapper:
        return "/".join(parts[1:])
    return path


def path_has_ignored_segment(rel: str, ignore: frozenset[str]) -> bool:
    parts = [p.lower() for p in PurePosixPath(rel.replace("\\", "/")).parts]
    return any(p in ignore for p in parts)


def _archive_member_visible(rel: str) -> bool:
    fname = PurePosixPath(rel.replace("\\", "/")).name
    return not fname.startswith(".") and not fname.startswith("__")


def archive_list_timeout_seconds(archive_bytes: int) -> int:
    """Scale `unrar lb` timeout for large Godot/Unity RAR uploads."""
    mb = max(1, archive_bytes // (1024 * 1024))
    return min(900, max(120, 90 + (mb // 40) * 30))


def _archive_extract_sort_key(path: str) -> tuple[int, str]:
    """Extract docs/code first; large game .exe last (PRO RAR UX)."""
    ext = PurePosixPath(path).suffix.lower()
    if ext in {".docx", ".pdf", ".doc", ".odt", ".txt", ".md"}:
        return (0, path)
    if ext in {".py", ".java", ".cs", ".cpp", ".c", ".js", ".ts", ".html", ".gd", ".gml", ".lua"}:
        return (1, path)
    if PurePosixPath(path).name.lower() in _GAMEMAKER_RUNTIME_FILENAMES:
        return (2, path)
    if ext == ".pck":
        return (2, path)
    if ext == ".exe":
        return (9, path)
    return (5, path)


def rar_member_uncompressed_size(
    archive_path: str,
    member_name: str,
    *,
    rar_handle=None,
) -> int:
    try:
        import rarfile  # type: ignore[import-untyped]

        _apply_rarfile_unrar_tool()
        if rar_handle is not None:
            return int(rar_handle.getinfo(member_name).file_size or 0)
        with rarfile.RarFile(archive_path, "r") as rf:
            return int(rf.getinfo(member_name).file_size or 0)
    except Exception:
        return 0


def archive_ui_percent(
    *,
    phase: str,
    frac: float | None = None,
    listed: int = 0,
) -> int:
    """Map archive sub-phases to UI percent (listing 8–18%, extract 20–45%)."""
    if phase == "listing":
        return min(18, 8 + max(0, listed) // 20)
    if phase == "manifest":
        return 19
    if phase == "extract" and frac is not None:
        return min(45, 20 + round(max(0.0, min(1.0, frac)) * 25))
    return 13


def archive_extract_timeout_seconds(grading_mode: str | None) -> int:
    """Outer asyncio guard for full archive pipeline (extract + nested)."""
    raw = (os.getenv("ARCHIVE_EXTRACT_TIMEOUT_SECONDS") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    try:
        from app.grading_mode_policy import is_fast_grading_mode

        if is_fast_grading_mode(grading_mode):
            return 1200
    except Exception:
        pass
    return 2400


def list_rar_members_fast(archive_path: str, *, timeout: int = 600) -> list[str]:
    """Fast bare file list via `unrar lb` (handles huge Godot/Unity archives)."""
    return list(
        iter_rar_member_paths(
            archive_path,
            skip_dir_names=frozenset(),
            timeout=timeout,
        )
    )


def iter_rar_member_paths(
    archive_path: str,
    *,
    skip_dir_names: frozenset[str],
    timeout: int,
    on_list_progress=None,
):
    """Stream RAR member paths from `unrar lb` — avoids loading huge namelist() in Python."""
    import subprocess
    import time

    tool = find_unrar_tool()
    if not tool:
        raise RarToolUnavailableError(
            "لا يمكن قراءة ملف RAR: أداة unrar غير مثبّتة على الخادم. "
            "ثبّت 'unrar' (Linux: apt-get install unrar / unrar-free) أو اضبط "
            "AI_GRADER_UNRAR_PATH، أو اطلب من الطالب رفع ملف ZIP بدلاً من RAR. "
            "(No unrar-compatible tool found; refusing to treat the archive as empty.)"
        )
    proc = subprocess.Popen(
        [tool, "lb", archive_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    started = time.monotonic()
    listed = 0
    try:
        for raw in proc.stdout:
            if time.monotonic() - started > timeout:
                proc.kill()
                raise TimeoutError(f"unrar lb exceeded {timeout}s for {Path(archive_path).name}")
            ln = raw.decode("utf-8", errors="replace").strip().replace("\\", "/")
            if not ln:
                continue
            decoded = collapse_redundant_archive_path(ln)
            if not _archive_member_visible(decoded):
                continue
            if skip_dir_names and path_has_ignored_segment(decoded, skip_dir_names):
                continue
            listed += 1
            if on_list_progress and listed % 25 == 0:
                try:
                    on_list_progress(listed)
                except Exception:
                    pass
            yield decoded
    finally:
        if on_list_progress and listed:
            try:
                on_list_progress(listed)
            except Exception:
                pass
        try:
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)


def _archive_student_group_key(decoded: str) -> str:
    """Top-level folder / root bucket for selective archive extraction."""
    parts = PurePosixPath(decoded).parts
    if len(parts) >= 2 and parts[0].lower() == "full":
        return parts[1] if len(parts) > 2 else parts[0]
    if len(parts) >= 2:
        return parts[0]
    return "__root__"


_ARCHIVE_DISPLAY_PATH_CAP = 2500

_DOC_PRIORITY = {".docx": 0, ".pdf": 1, ".doc": 2, ".odt": 3, ".txt": 4, ".md": 5}
_GAMEMAKER_RUNTIME_FILENAMES = frozenset({"data.win", "options.ini"})
# Self-contained runnable game projects/builds worth extracting from any archive.
_RUNNABLE_GAME_EXTENSIONS = frozenset({".sb3", ".sb2"})
_RUNNABLE_GAME_BASENAMES = frozenset({"data.win"})
_NESTED_ARCHIVE_EXTENSIONS_INNER = frozenset({".zip", ".rar", ".7z"})
# Name hints that a nested archive holds a playable build (e.g. «(.exe)بعد التعديل.zip»).
_NESTED_BUILD_NAME_HINTS = (
    "exe", "build", "game", "win", "html5", "release", "export",
    "بعد التعديل", "قبل التعديل", "اللعبة", "العبة", "لعبة", "تشغيل",
)


def is_runtime_nested_archive(decoded: str) -> bool:
    """True for nested .zip/.rar/.7z whose name suggests a playable game build."""
    p = PurePosixPath(decoded.replace("\\", "/"))
    if p.suffix.lower() not in _NESTED_ARCHIVE_EXTENSIONS_INNER:
        return False
    name = p.name.lower()
    return any(hint in name for hint in _NESTED_BUILD_NAME_HINTS)


def is_runnable_game_artifact(decoded: str) -> bool:
    """True for Scratch (.sb3/.sb2) projects or GameMaker build (data.win)."""
    p = PurePosixPath(decoded.replace("\\", "/"))
    return p.suffix.lower() in _RUNNABLE_GAME_EXTENSIONS or p.name.lower() in _RUNNABLE_GAME_BASENAMES


def gamemaker_runtime_siblings_for_exe(
    group_paths: list[str],
    chosen_exe: str,
) -> set[str]:
    """Pair ``data.win`` / ``options.ini`` with the game ``.exe`` selected for extract."""
    exe_parent = PurePosixPath(chosen_exe).parent.as_posix().lower()
    siblings: set[str] = set()
    for decoded in group_paths:
        name = PurePosixPath(decoded).name.lower()
        if name not in _GAMEMAKER_RUNTIME_FILENAMES:
            continue
        if PurePosixPath(decoded).parent.as_posix().lower() == exe_parent:
            siblings.add(decoded)
    return siblings


def _member_worth_indexing(
    decoded: str,
    *,
    skip_extract_ext: frozenset[str],
    gradable_extensions: tuple[str, ...],
    should_skip_extract,
) -> bool:
    """Skip asset noise when indexing RAR members (Godot .import, images, …)."""
    ext = PurePosixPath(decoded).suffix.lower()
    if is_runnable_game_artifact(decoded):
        return True
    if is_runtime_nested_archive(decoded):
        return True
    if ext in skip_extract_ext:
        return False
    if is_junk_primary_candidate(decoded):
        return False
    if should_skip_extract(decoded):
        return False
    if ext in {".docx", ".pdf", ".doc", ".odt", ".txt", ".md"}:
        return True
    if ext in {".py", ".java", ".cs", ".cpp", ".c", ".js", ".ts", ".html", ".gd", ".gml", ".lua"}:
        return True
    if ext in {".exe", ".pck", ".x86_64"}:
        return True
    return ext != ".exe" and any(decoded.lower().endswith(e) for e in gradable_extensions)


def _pick_best_doc_path(paths: list[str]) -> str:
    docs = [p for p in paths if PurePosixPath(p).suffix.lower() in _DOC_PRIORITY]
    if not docs:
        return paths[0]
    return min(docs, key=lambda p: (_DOC_PRIORITY.get(PurePosixPath(p).suffix.lower(), 9), p))


def selective_extract_rar(
    archive_path: str,
    extract_dir: Path,
    *,
    skip_dir_names: frozenset[str],
    gradable_extensions: tuple[str, ...],
    on_progress=None,
    on_list_progress=None,
    on_manifest=None,
    max_extract_files: int = 300,
    grading_mode: str | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    List RAR members and extract only gradable files, skipping Library/Temp/etc.
    Avoids bulk unrar on multi-GB Godot/Unity archives (WinError / rc=9 on long paths).
    Returns ([(rel_key, disk_path), ...], display_paths for UI).
    """
    _apply_rarfile_unrar_tool()

    makedirs_safe(extract_dir)
    extracted: list[tuple[str, str]] = []
    display: list[str] = []

    _DOC_EXT = {".docx", ".pdf", ".doc", ".odt", ".txt", ".md"}
    _CODE_EXT = {
        ".py", ".java", ".cs", ".cpp", ".c", ".js", ".ts", ".html", ".gd", ".gml", ".lua",
    }
    _SKIP_EXTRACT_EXT = frozenset({".import", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tscn"})

    try:
        from app.grading_mode_policy import should_skip_archive_extract_to_disk
    except ImportError:
        def should_skip_archive_extract_to_disk(path: str, grading_mode: str | None) -> bool:
            _ = (path, grading_mode)
            return False

    def _should_skip(path: str) -> bool:
        return should_skip_archive_extract_to_disk(path, grading_mode)

    def _should_extract_member(decoded: str) -> bool:
        return _member_worth_indexing(
            decoded,
            skip_extract_ext=_SKIP_EXTRACT_EXT,
            gradable_extensions=gradable_extensions,
            should_skip_extract=_should_skip,
        )

    try:
        archive_bytes = os.path.getsize(archive_path)
    except OSError:
        archive_bytes = 0
    list_timeout = archive_list_timeout_seconds(archive_bytes)

    by_student: dict[str, list[str]] = {}
    indexed = 0
    try:
        for decoded in iter_rar_member_paths(
            archive_path,
            skip_dir_names=skip_dir_names,
            timeout=list_timeout,
            on_list_progress=on_list_progress,
        ):
            if len(display) < _ARCHIVE_DISPLAY_PATH_CAP:
                display.append(decoded)
            if not _member_worth_indexing(
                decoded,
                skip_extract_ext=_SKIP_EXTRACT_EXT,
                gradable_extensions=gradable_extensions,
                should_skip_extract=_should_skip,
            ):
                continue
            indexed += 1
            by_student.setdefault(_archive_student_group_key(decoded), []).append(decoded)
    except TimeoutError as exc:
        raise RuntimeError(
            f"انتهت مهلة قراءة قائمة ملفات RAR ({list_timeout // 60} دقيقة). "
            "احذف مجلدات Library و.godot/_build ثم اضغط ZIP."
        ) from exc

    if not by_student:
        raise RuntimeError(
            "لم يُعثر على ملفات Word/PDF/كود/لعبة مدعومة داخل RAR — "
            "احذف مجلدات Library و.godot/_build ثم اضغط ZIP."
        )

    to_extract: set[str] = set()
    for group_key, paths in by_student.items():
        docs: list[str] = []
        code_scored: list[tuple[tuple[int, int], str]] = []
        exe_candidates: list[str] = []
        for decoded in paths:
            ext = PurePosixPath(decoded).suffix.lower()
            if is_runnable_game_artifact(decoded) or is_runtime_nested_archive(decoded):
                # Scratch .sb3 / GameMaker data.win / nested build .zip → always keep
                to_extract.add(decoded)
                continue
            if not _should_extract_member(decoded):
                continue
            if ext in _DOC_EXT:
                docs.append(decoded)
            elif ext == ".exe" and is_primary_game_executable(decoded):
                exe_candidates.append(decoded)
            elif ext in _CODE_EXT:
                code_scored.append((_source_code_pick_score(decoded), decoded))
            elif ext != ".exe" and any(
                decoded.lower().endswith(e) for e in gradable_extensions
            ):
                if ext not in _SKIP_EXTRACT_EXT:
                    code_scored.append((_source_code_pick_score(decoded), decoded))
        if docs:
            if group_key == "__root__" and len(docs) > 1:
                to_extract.update(docs)
            else:
                to_extract.add(_pick_best_doc_path(docs))
        if exe_candidates:
            chosen_exe = min(
                exe_candidates, key=lambda p: (len(PurePosixPath(p).parts), p.lower())
            )
            try:
                from app.grading_mode_policy import pro_should_skip_game_exe_disk_extract

                if pro_should_skip_game_exe_disk_extract(
                    chosen_exe,
                    group_paths=paths,
                    grading_mode=grading_mode,
                ):
                    print(
                        f"📦 [RAR-SEL] PRO skip exe disk extract (Godot bundle indexed): "
                        f"{Path(chosen_exe).name}"
                    )
                else:
                    to_extract.add(chosen_exe)
                    to_extract.update(
                        gamemaker_runtime_siblings_for_exe(paths, chosen_exe)
                    )
            except ImportError:
                to_extract.add(chosen_exe)
                to_extract.update(
                    gamemaker_runtime_siblings_for_exe(paths, chosen_exe)
                )
        code_scored = _dedupe_code_scored(code_scored)
        _code_cap = max_archive_code_files_per_group(grading_mode, archive_bytes)
        to_extract.update(decoded for _, decoded in code_scored[:_code_cap])

    gradable_names = sorted(to_extract, key=_archive_extract_sort_key)
    _file_cap = min(
        max_extract_files,
        max_archive_extract_files(grading_mode, archive_bytes=archive_bytes),
    )
    if len(gradable_names) > _file_cap:
        protected = {
            name
            for name in gradable_names
            if PurePosixPath(name).name.lower() in _GAMEMAKER_RUNTIME_FILENAMES
            or is_runnable_game_artifact(name)
            or is_runtime_nested_archive(name)
            or (
                PurePosixPath(name).suffix.lower() == ".exe"
                and is_primary_game_executable(name)
            )
        }
        keep = list(dict.fromkeys([*protected, *gradable_names]))[:_file_cap]
        print(
            f"⚠️ [RAR-SEL] capping extraction {len(gradable_names)} → {len(keep)} "
            f"file(s) for {Path(archive_path).name}"
        )
        gradable_names = keep
    total = len(gradable_names)
    if on_manifest:
        try:
            on_manifest(len(by_student), total)
        except Exception:
            pass
    print(
        f"📦 [RAR-SEL] {Path(archive_path).name}: "
        f"{len(display)} visible ({indexed} indexed), {total} to extract "
        f"({len(by_student)} student group(s), skip Library/Temp/.godot)"
    )

    rar_handle = None
    try:
        import rarfile  # type: ignore[import-untyped]

        _apply_rarfile_unrar_tool()
        rar_handle = rarfile.RarFile(archive_path, "r")
    except Exception:
        rar_handle = None

    try:
        for idx, decoded in enumerate(gradable_names):
            member_size = rar_member_uncompressed_size(
                archive_path, decoded, rar_handle=rar_handle
            )
            try:
                from app.grading_mode_policy import pro_should_skip_game_exe_disk_extract

                group_key = _archive_student_group_key(decoded)
                group_paths = by_student.get(group_key, [])
                if pro_should_skip_game_exe_disk_extract(
                    decoded,
                    group_paths=group_paths,
                    member_size=member_size,
                    grading_mode=grading_mode,
                ):
                    print(
                        f"📦 [RAR-SEL] skip extract {Path(decoded).name} "
                        f"({member_size / (1024 * 1024):.1f} MB) — indexed in archive"
                    )
                    if on_progress:
                        try:
                            on_progress(idx, total, Path(decoded).name)
                        except Exception:
                            pass
                    continue
            except ImportError:
                pass

            print(
                f"📦 [RAR-SEL] extracting ({idx + 1}/{total}) "
                f"{Path(decoded).name} ({member_size / (1024 * 1024):.1f} MB)"
            )
            try:
                data = read_rar_member_bytes(archive_path, decoded, rar_handle=rar_handle)
                _out, rel_key = safe_archive_out_path(extract_dir, decoded)
                write_bytes_safe(_out, data)
                extracted.append((rel_key, str(_out)))
            except Exception as exc:
                print(f"⚠️ [RAR-SEL] skip {decoded}: {exc}")
                continue
            if on_progress:
                try:
                    on_progress(idx, total, Path(decoded).name)
                except Exception:
                    pass
    finally:
        if rar_handle is not None:
            try:
                rar_handle.close()
            except Exception:
                pass

    return extracted, display


def selective_extract_zip(
    archive_path: str,
    extract_dir: Path,
    *,
    skip_dir_names: frozenset[str],
    gradable_extensions: tuple[str, ...],
    on_progress=None,
    on_manifest=None,
    max_extract_files: int = 300,
    grading_mode: str | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    List ZIP members and extract only gradable files per student group.
    Mirrors selective_extract_rar — avoids extracting thousands of assets in BASIC.
    """
    import zipfile

    makedirs_safe(extract_dir)
    extracted: list[tuple[str, str]] = []
    display: list[str] = []
    gradable_names: list[str] = []

    _DOC_EXT = {".docx", ".pdf", ".doc", ".odt", ".txt", ".md"}
    _CODE_EXT = {
        ".py", ".java", ".cs", ".cpp", ".c", ".js", ".ts", ".html", ".gd", ".gml", ".lua",
    }
    _SKIP_EXTRACT_EXT = {".import", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tscn"}

    try:
        from app.grading_mode_policy import should_skip_archive_extract_to_disk
    except ImportError:
        def should_skip_archive_extract_to_disk(path: str, grading_mode: str | None) -> bool:
            _ = (path, grading_mode)
            return False

    def _decode_zip_name(raw_path: str) -> str:
        try:
            return raw_path.encode("cp437").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return raw_path

    def _should_extract_member(decoded: str) -> bool:
        ext = PurePosixPath(decoded).suffix.lower()
        if ext in _SKIP_EXTRACT_EXT:
            return False
        if is_junk_primary_candidate(decoded):
            return False
        if should_skip_archive_extract_to_disk(decoded, grading_mode):
            return False
        if ext == ".exe" and not is_primary_game_executable(decoded):
            return False
        if ext in _DOC_EXT or ext in _CODE_EXT:
            return True
        if ext == ".exe" and is_primary_game_executable(decoded):
            return True
        return ext != ".exe" and any(
            decoded.lower().endswith(e) for e in gradable_extensions
        )

    try:
        archive_bytes = os.path.getsize(archive_path)
    except OSError:
        archive_bytes = 0

    member_paths: list[str] = []
    name_to_info: dict[str, object] = {}
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            decoded = collapse_redundant_archive_path(_decode_zip_name(info.filename))
            name_to_info[decoded] = info
            if not _archive_member_visible(decoded):
                continue
            if path_has_ignored_segment(decoded, skip_dir_names):
                continue
            display.append(decoded)
            member_paths.append(decoded)

        by_student: dict[str, list[str]] = {}
        for decoded in member_paths:
            by_student.setdefault(_archive_student_group_key(decoded), []).append(decoded)

        to_extract: set[str] = set()
        for group_key, paths in by_student.items():
            docs: list[tuple[int, str]] = []
            code_scored: list[tuple[tuple[int, int], str]] = []
            exe_candidates: list[tuple[int, str]] = []
            for decoded in paths:
                ext = PurePosixPath(decoded).suffix.lower()
                if is_runnable_game_artifact(decoded) or is_runtime_nested_archive(decoded):
                    if name_to_info.get(decoded) is not None:
                        to_extract.add(decoded)
                    continue
                if not _should_extract_member(decoded):
                    continue
                info = name_to_info.get(decoded)
                if info is None:
                    continue
                try:
                    size = int(getattr(info, "file_size", 0) or 0)
                except Exception:
                    size = 0
                if ext in _DOC_EXT:
                    docs.append((size, decoded))
                elif ext == ".exe" and is_primary_game_executable(decoded):
                    exe_candidates.append((size, decoded))
                elif ext in _CODE_EXT:
                    code_scored.append((_source_code_pick_score(decoded), decoded))
                elif ext != ".exe" and any(
                    decoded.lower().endswith(e) for e in gradable_extensions
                ):
                    if ext not in _SKIP_EXTRACT_EXT:
                        code_scored.append((_source_code_pick_score(decoded), decoded))
            if docs:
                if group_key == "__root__" and len(docs) > 1:
                    to_extract.update(decoded for _, decoded in docs)
                else:
                    to_extract.add(max(docs, key=lambda x: x[0])[1])
            if exe_candidates:
                chosen_exe = max(exe_candidates, key=lambda x: x[0])[1]
                to_extract.add(chosen_exe)
                to_extract.update(
                    gamemaker_runtime_siblings_for_exe(paths, chosen_exe)
                )
            code_scored = _dedupe_code_scored(code_scored)
            _code_cap = max_archive_code_files_per_group(grading_mode, archive_bytes)
            to_extract.update(decoded for _, decoded in code_scored[:_code_cap])

        gradable_names = sorted(to_extract, key=_archive_extract_sort_key)
        _file_cap = min(
            max_extract_files,
            max_archive_extract_files(grading_mode, archive_bytes=archive_bytes),
        )
        if len(gradable_names) > _file_cap:
            protected = {
                name
                for name in gradable_names
                if PurePosixPath(name).name.lower() in _GAMEMAKER_RUNTIME_FILENAMES
                or is_runnable_game_artifact(name)
                or is_runtime_nested_archive(name)
                or (
                    PurePosixPath(name).suffix.lower() == ".exe"
                    and is_primary_game_executable(name)
                )
            }
            keep = list(dict.fromkeys([*protected, *gradable_names]))[:_file_cap]
            print(
                f"⚠️ [ZIP-SEL] capping extraction {len(gradable_names)} → {len(keep)} "
                f"file(s) for {Path(archive_path).name}"
            )
            gradable_names = keep
        total = len(gradable_names)
        if on_manifest:
            try:
                on_manifest(len(by_student), total)
            except Exception:
                pass
        print(
            f"📦 [ZIP-SEL] {Path(archive_path).name}: "
            f"{len(display)} visible, {total} to extract "
            f"({len(by_student)} student group(s))"
        )

        for idx, decoded in enumerate(gradable_names):
            if on_progress:
                try:
                    on_progress(idx, total, Path(decoded).name)
                except Exception:
                    pass
            info = name_to_info.get(decoded)
            if info is None:
                continue
            try:
                data = zf.read(info)  # type: ignore[arg-type]
                _out, rel_key = safe_archive_out_path(extract_dir, decoded)
                write_bytes_safe(_out, data)
                extracted.append((rel_key, str(_out)))
            except Exception as exc:
                print(f"⚠️ [ZIP-SEL] skip {decoded}: {exc}")
                continue

    return extracted, display


def bulk_extract_rar(archive_path: str, dest_dir: Path, *, timeout: int = 900) -> None:
    """
    Extract entire RAR to dest_dir via `unrar x` (fast; no per-file Unicode CLI issues).
    """
    import subprocess

    tool = find_unrar_tool()
    if not tool:
        raise RuntimeError("UnRAR tool not found")
    makedirs_safe(dest_dir)
    dest = str(dest_dir.resolve())
    if not dest.endswith(os.sep):
        dest += os.sep
    proc = subprocess.run(
        [tool, "x", "-o+", "-idq", "-inul", "-y", archive_path, dest],
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode not in (0, 1):
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(err.strip() or f"unrar x failed rc={proc.returncode}")


def read_rar_member_bytes(archive_path: str, member_name: str, *, rar_handle=None) -> bytes:
    """
    Read one RAR member without creating nested long paths on disk.
    Prefer rarfile (handles RAR5 + Unicode names); fall back to `unrar p`.
    """
    if rar_handle is not None:
        info = rar_handle.getinfo(member_name)
        return rar_handle.read(info)

    try:
        import rarfile  # type: ignore[import-untyped]

        _apply_rarfile_unrar_tool()
        with rarfile.RarFile(archive_path, "r") as rf:
            info = rf.getinfo(member_name)
            return rf.read(info)
    except Exception:
        return _unrar_pipe_bytes(archive_path, member_name)


def archive_should_use_selective_extract(
    entry_count: int,
    archive_bytes: int,
    grading_mode: str | None = None,
) -> bool:
    """
    Prefer selective extract for all archives — full extract of Godot/Unity/RAR
    trees (100–500+ files) can hang 30+ minutes at ~24% progress in PRO mode.
    """
    _ = grading_mode  # reserved — BASIC/PRO differ in max files, not strategy
    if archive_bytes >= 80 * 1024 * 1024:
        return True
    if entry_count > 25:
        return True
    return True


def max_archive_extract_files(grading_mode: str | None, *, archive_bytes: int = 0) -> int:
    """Cap files written to disk during selective archive extract."""
    try:
        from app.grading_mode_policy import is_fast_grading_mode, pro_fast_path_enabled

        if is_fast_grading_mode(grading_mode):
            return 200
        if pro_fast_path_enabled():
            if archive_bytes >= 80 * 1024 * 1024:
                return 36
            if archive_bytes >= 40 * 1024 * 1024:
                return 48
            return 60
    except Exception:
        pass
    return 100


def max_archive_code_files_per_group(
    grading_mode: str | None,
    archive_bytes: int = 0,
) -> int:
    try:
        from app.grading_mode_policy import is_fast_grading_mode

        base = 24 if is_fast_grading_mode(grading_mode) else 16
    except Exception:
        base = 16
    mb = archive_bytes // (1024 * 1024)
    if mb >= 200:
        return min(base, 6)
    if mb >= 80:
        return min(base, 8)
    if mb >= 40:
        return min(base, 12)
    return base


_NESTED_ZIP_RUNTIME_DIR = "_nested_runtime"
_NESTED_ZIP_MAX_BYTES = 512 * 1024 * 1024
_NESTED_ZIP_MAX_PER_STUDENT = 3
_NESTED_ZIP_SKIP_PARTS = frozenset(
    {"_flat", "_raw", "_nested_runtime", "__macosx"}
)


def _decode_zip_member_name(raw_path: str) -> str:
    try:
        return raw_path.encode("cp437").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return raw_path


def _zip_info_for_decoded_member(zf, decoded: str):
    for info in zf.infolist():
        if info.is_dir():
            continue
        member_decoded = collapse_redundant_archive_path(
            _decode_zip_member_name(info.filename)
        )
        if member_decoded == decoded:
            return info
    return None


def _subtree_has_loose_game_executable(root: Path) -> bool:
    """True when a primary game .exe already exists on disk (skip nested ZIP unpack)."""
    if not root.is_dir():
        return False
    for fp in root.rglob("*.exe"):
        if not fp.is_file():
            continue
        if any(part.lower() in _NESTED_ZIP_SKIP_PARTS for part in fp.parts):
            continue
        if is_primary_game_executable(str(fp)):
            return True
    return False


def _nested_zip_runtime_members(zf, members: list[str]) -> tuple[str, set[str]] | None:
    exe_candidates: list[tuple[int, str]] = []
    for decoded in members:
        if PurePosixPath(decoded).suffix.lower() != ".exe":
            continue
        if not is_primary_game_executable(decoded):
            continue
        info = _zip_info_for_decoded_member(zf, decoded)
        size = int(getattr(info, "file_size", 0) or 0) if info is not None else 0
        exe_candidates.append((size, decoded))
    if not exe_candidates:
        return None
    chosen_exe = max(exe_candidates, key=lambda x: x[0])[1]
    to_extract = {chosen_exe}
    to_extract.update(gamemaker_runtime_siblings_for_exe(members, chosen_exe))
    return chosen_exe, to_extract


def materialize_nested_zip_game_executables(
    extract_dir: Path,
    *,
    grading_mode: str | None = None,
) -> list[tuple[str, str]]:
    """
    Unpack nested ``.zip`` archives that contain a game ``.exe`` when no loose
  primary ``.exe`` exists in the same student subtree.

    Runtime-only archive prep — independent of AI provider (Gemini/Ollama).
    Skips subtrees that already have an extracted game build (no Gemini regression).
    """
    import zipfile

    _ = grading_mode
    extract_dir = extract_dir.resolve()
    if not extract_dir.is_dir():
        return []

    student_roots: list[Path] = []
    for child in extract_dir.iterdir():
        if child.is_dir() and child.name.lower() not in _NESTED_ZIP_SKIP_PARTS:
            student_roots.append(child)
    if not student_roots:
        student_roots = [extract_dir]

    results: list[tuple[str, str]] = []
    for student_root in student_roots:
        if _subtree_has_loose_game_executable(student_root):
            continue

        nested_zips = [
            zp
            for zp in student_root.rglob("*.zip")
            if zp.is_file()
            and not any(part.lower() in _NESTED_ZIP_SKIP_PARTS for part in zp.parts)
        ]
        nested_zips.sort(
            key=lambda p: p.stat().st_size if p.is_file() else 0,
            reverse=True,
        )

        unpacked = 0
        for zip_path in nested_zips:
            if unpacked >= _NESTED_ZIP_MAX_PER_STUDENT:
                break
            if _subtree_has_loose_game_executable(student_root):
                break
            try:
                zip_bytes = zip_path.stat().st_size
            except OSError:
                continue
            if zip_bytes > _NESTED_ZIP_MAX_BYTES:
                continue

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    members: list[str] = []
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        decoded = collapse_redundant_archive_path(
                            _decode_zip_member_name(info.filename)
                        )
                        if not _archive_member_visible(decoded):
                            continue
                        members.append(decoded)

                    picked = _nested_zip_runtime_members(zf, members)
                    if picked is None:
                        continue
                    chosen_exe, to_extract = picked
                    out_dir = zip_path.parent / _NESTED_ZIP_RUNTIME_DIR / _sanitize_segment(
                        zip_path.stem
                    )
                    makedirs_safe(out_dir)
                    written = 0
                    for member in sorted(to_extract):
                        info = _zip_info_for_decoded_member(zf, member)
                        if info is None:
                            continue
                        try:
                            data = zf.read(info)
                        except Exception as exc:
                            print(
                                f"⚠️ [ZIP-NESTED] skip {member} in {zip_path.name}: {exc}"
                            )
                            continue
                        out_path = out_dir / _sanitize_segment(
                            PurePosixPath(member).name, max_len=120
                        )
                        write_bytes_safe(out_path, data)
                        rel = out_path.relative_to(extract_dir).as_posix()
                        results.append((rel, str(out_path)))
                        written += 1
                    if written:
                        unpacked += 1
                        print(
                            f"📦 [ZIP-NESTED] {zip_path.name} → "
                            f"{written} runtime file(s) beside {chosen_exe}"
                        )
            except zipfile.BadZipFile:
                print(f"⚠️ [ZIP-NESTED] corrupt nested zip: {zip_path.name}")
            except Exception as exc:
                print(f"⚠️ [ZIP-NESTED] skip {zip_path.name}: {exc}")

    return results


def hash_submission_file(file_path: str, fallback_text: str = "") -> str:
    """Stable SHA-256 for cache/dedup: file bytes first, else raw extracted text."""
    if file_path:
        try:
            p = Path(file_path)
            if p.is_file():
                return hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            pass
    if fallback_text:
        return hashlib.sha256(fallback_text.encode("utf-8")).hexdigest()
    return ""


def build_grading_fingerprint(
    source_hash: str,
    reference_solution: dict,
    grading_criteria: list,
    selected_criteria: list,
    *,
    model_version: str = "",
    prompt_version: str = "",
) -> str:
    """Deterministic grading cache key — based on source file, not enriched prompt text.

    Determinism contract (Pearson: same work => same grade): the fingerprint binds the
    work + criteria AND the grader identity (model + prompt version). Any prompt or model
    change therefore invalidates the cache automatically, so stale grades are never reused
    across grader upgrades. If callers omit the versions we fall back to the active
    environment/prompt versions so existing call sites still benefit.
    """
    import json

    if not model_version:
        model_version = resolve_active_grading_model_version()
    if not prompt_version:
        prompt_version = GRADING_PROMPT_VERSION

    guide_text = json.dumps(reference_solution, ensure_ascii=False, sort_keys=True)
    criteria_text = json.dumps(
        [
            {"l": c.get("criteria_level", ""), "d": c.get("criteria_description", "")}
            for c in grading_criteria
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    payload = "|".join(
        [
            source_hash or "",
            guide_text,
            criteria_text,
            ",".join(sorted(selected_criteria or [])),
            f"model={model_version}",
            f"prompt={prompt_version}",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Bump GRADING_PROMPT_VERSION whenever the grading system/user prompt or scoring
# rubric semantics change, so cached grades from the old prompt are invalidated.
GRADING_PROMPT_VERSION = "btec_grading_prompt_2026_06"


def resolve_active_grading_model_version() -> str:
    """Best-effort identity of the model used for criterion grading.

    Reads the same environment the AI provider reads, without importing it (keeps this
    module import-light and avoids constructing a client just to read a name).
    """
    import os

    provider = (os.getenv("AI_PROVIDER", "gemini") or "gemini").strip().lower()
    if provider in ("gemini", "google"):
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    elif provider == "openrouter":
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-pro")
    elif provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "deepseek-coder")
    else:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    return f"{provider}:{model}"
