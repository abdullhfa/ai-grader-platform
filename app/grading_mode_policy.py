"""Subscription tier -> grading mode policy."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.grading_mode import GradingMode


FAST_PACKAGE_NAMES = {
    "basic",
    "starter",
    "trial",
    "student basic",
    "student standard",
}

DEEP_PACKAGE_NAMES = {
    "pro",
    "premium",
    "advanced",
    "ultimate",
    "enterprise",
    "standard",
    "student premium",
    "student pro",
}


def normalize_grading_mode_choice(value: str | None) -> str:
    """Map UI/API values (standard/pro/basic/fast/deep) to fast|deep wire format."""
    return GradingMode.from_wire(value).to_wire()


def grading_mode_display_label(mode: str) -> str:
    return "STANDARD" if normalize_grading_mode_choice(mode) == "fast" else "PRO"


def is_fast_grading_mode(grading_mode: str | None) -> bool:
    return normalize_grading_mode_choice(grading_mode) == "fast"


def fast_grading_flags(grading_mode: str | None) -> Dict[str, bool]:
    """Feature gates for STANDARD (fast) — lightweight runtime + docs; no gameplay agent."""
    fast = is_fast_grading_mode(grading_mode)
    return {
        "skip_runtime_observation": False,
        "fast_runtime_smoke": fast,
        "skip_godot_pck_analysis": fast,
        "skip_gameplay_video_inference": fast,
        "skip_l2_l3_corroborative": fast,
        "skip_heavy_governance_graphs": fast,
        "skip_ai_evidence_reasoning": fast,
        "skip_visual_verification": fast,
        "light_project_profile": fast,
        "compact_code_addon": fast,
        "skip_post_grade_artifact_rebuild": fast,
        "skip_institutional_resolution": fast,
        "skip_governance_drift": fast,
        "parallel_batch_grading": fast,
        "slim_submission_paths": fast,
        "minimal_artifact_inventory": fast,
        "skip_evidence_layer": fast,
        "skip_evidence_gate": fast,
        "ultra_light_project_profile": fast,
        "skip_post_grade_layers": fast,
        "skip_production_layers": fast,
        "skip_coverage_notice": fast,
        "selective_archive_extract": fast,
        "word_embedded_vision": fast,
        "basic_video_keyframes": fast,
        "enable_web_browser_automation": False,
        "enable_android_emulator_automation": False,
        "enable_gamemaker_runtime_verification": False,
        "enable_scratch_runtime_verification": False,
    }


# Do not write these to disk during ZIP extract in BASIC (still listed in UI).
BASIC_SKIP_EXTRACT_SUFFIXES = frozenset(
    {
        ".exe",
        ".win",
        ".dll",
        ".apk",
        ".pck",
        ".mp3",
        ".wav",
        ".ogg",
        ".m4a",
        ".flac",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".wmv",
        ".webm",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".ico",
        ".psd",
        ".yy",
        ".import",
    }
)

FAST_AI_MAX_RETRIES = 2
FAST_MAX_CODE_FILES = 10
PRO_MAX_CODE_FILES = 16
PRO_COMPACT_CHARS_PER_SIDE = 10_000
PRO_COMPACT_PER_FILE_CAP = 3_500
FAST_MAX_GUIDE_CHARS = 32_000


def format_fast_artifact_context(inventory: Dict[str, Any]) -> str:
    """Short artifact header for BASIC — same rules, less prompt bloat."""
    note = inventory.get("grading_mode_note_ar") or inventory.get("evidence_authority_note_ar") or ""
    has_code = inventory.get("has_source_code_artifacts")
    has_exe = inventory.get("has_executable_artifacts")
    return (
        "[BASIC — سجل artifacts مختصر]\n"
        f"كود مصدري: {'نعم' if has_code else 'لا'} | ملفات تنفيذية: {'نعم (لم تُشغَّل)' if has_exe else 'لا'}\n"
        f"{note}\n\n"
    )


# Defaults tuned for gemini-2.5-flash (override via .env).
FAST_BATCH_PARALLEL_STUDENTS = 8
FAST_MAX_SNAPSHOT_BYTES = 1_500_000
# Word/PDF embedded images in BASIC (override via .env). 10 matches package copy «حتى 10».
BASIC_MAX_VISION_IMAGES = 10
BASIC_MAX_VIDEO_KEYFRAMES = 5  # per video (not total)
BASIC_MAX_VIDEOS = 2
WORD_EMBEDDED_VISION_EXTENSIONS = frozenset({".docx", ".doc", ".pdf", ".pptx"})
# Local Ollama vision (e.g. qwen3-vl) is much slower — tighter cap unless overridden.
OLLAMA_BASIC_MAX_VISION_DEFAULT = 5
# Cap student corpus for local Ollama — large prompts crash the daemon on ~16GB RAM.
OLLAMA_MAX_PROMPT_CHARS = 14_000


def is_word_embedded_vision_document(path: str | None) -> bool:
    """True when the primary submission file can hold embedded BTEC evidence images."""
    return Path(path or "").suffix.lower() in WORD_EMBEDDED_VISION_EXTENSIONS


def basic_max_vision_images() -> int:
    """BASIC: max embedded Word/PDF/PPTX images for Vision."""
    raw = (os.getenv("BASIC_MAX_VISION_IMAGES") or str(BASIC_MAX_VISION_IMAGES)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = BASIC_MAX_VISION_IMAGES
    if n <= 0:
        return 0
    return max(1, min(n, 64))


def effective_basic_max_vision_images() -> int:
    """BASIC vision cap with a lower bound for slow local Ollama vision models."""
    cap = basic_max_vision_images()
    prov = (os.getenv("AI_PROVIDER") or "").strip().lower()
    if prov != "ollama":
        return cap
    raw = (
        os.getenv("OLLAMA_BASIC_MAX_VISION_IMAGES")
        or str(OLLAMA_BASIC_MAX_VISION_DEFAULT)
    ).strip()
    try:
        ollama_cap = int(raw)
    except ValueError:
        ollama_cap = OLLAMA_BASIC_MAX_VISION_DEFAULT
    if ollama_cap <= 0:
        return cap
    if cap <= 0:
        return max(1, min(ollama_cap, 64))
    return max(1, min(cap, ollama_cap, 64))


def basic_max_video_keyframes() -> int:
    """BASIC: max keyframes extracted per gameplay video (FFmpeg → Vision)."""
    raw = (os.getenv("BASIC_MAX_VIDEO_KEYFRAMES") or str(BASIC_MAX_VIDEO_KEYFRAMES)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = BASIC_MAX_VIDEO_KEYFRAMES
    return max(0, min(n, 8))


def basic_max_videos() -> int:
    """BASIC: max submission videos sampled for keyframes."""
    raw = (os.getenv("BASIC_MAX_VIDEOS") or str(BASIC_MAX_VIDEOS)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = BASIC_MAX_VIDEOS
    return max(1, min(n, 4))


def basic_max_video_keyframe_total() -> int:
    """Total Vision budget for all video keyframes in BASIC."""
    return basic_max_video_keyframes() * basic_max_videos()


def basic_shared_vision_cap() -> int:
    """Total Vision slots in BASIC: Word embedded + video keyframes."""
    word_cap = effective_basic_max_vision_images()
    video_total = basic_max_video_keyframe_total()
    return video_total if word_cap <= 0 else word_cap + video_total


# PRO: skip media/assets in ZIP (keep exe/win/pck/doc/code for runtime).
PRO_SKIP_EXTRACT_SUFFIXES = frozenset(
    {
        ".mp3",
        ".wav",
        ".ogg",
        ".m4a",
        ".flac",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".wmv",
        ".webm",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".tiff",
        ".ico",
        ".psd",
        ".yy",
        ".import",
    }
)

# PRO: quality-first — lower parallelism + fewer vision shots (see GEMINI_PRO_MODEL).
PRO_BATCH_PARALLEL_STUDENTS = 2
PRO_MAX_VISION_IMAGES = 5
PRO_MAX_VISION_IMAGES_DOC = 3
PRO_MAX_VISION_IMAGES_GAME = 5
PRO_MAX_PROMPT_CHARS = 32_000
_BATCH_PARALLEL_CAP = 12


def pro_fast_path_enabled() -> bool:
    """PRO speed path — skips GameMaker/browser runtime (default off: PRO runs the game)."""
    raw = (os.getenv("PRO_FAST_PATH") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def pro_max_prompt_chars() -> int:
    raw = (os.getenv("PRO_MAX_PROMPT_CHARS") or str(PRO_MAX_PROMPT_CHARS)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = PRO_MAX_PROMPT_CHARS
    return max(8_000, min(n, 64_000))


def ollama_max_prompt_chars() -> int:
    raw = (os.getenv("OLLAMA_MAX_PROMPT_CHARS") or str(OLLAMA_MAX_PROMPT_CHARS)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = OLLAMA_MAX_PROMPT_CHARS
    return max(6_000, min(n, 32_000))


def truncate_pro_student_text_for_ai(text: str, *, grading_mode: str | None) -> str:
    """Cap grading corpus for slow providers (PRO Gemini, local Ollama)."""
    prov = (os.getenv("AI_PROVIDER") or "").strip().lower()
    if prov == "ollama":
        cap = ollama_max_prompt_chars()
        if len(text) <= cap:
            return text
        head = int(cap * 0.65)
        tail = cap - head - 100
        return (
            text[:head]
            + "\n\n[… اختُصر نص التصحيح لـ Ollama — بداية ونهاية العمل محفوظتان …]\n\n"
            + text[-tail:]
        )
    if is_fast_grading_mode(grading_mode):
        return text
    cap = pro_max_prompt_chars()
    if len(text) <= cap:
        return text
    head = int(cap * 0.72)
    tail = cap - head - 120
    return (
        text[:head]
        + "\n\n[… اختُصر نص التصحيح PRO للسرعة — بداية ونهاية العمل محفوظتان …]\n\n"
        + text[-tail:]
    )


def pro_max_vision_images() -> int:
    raw = (os.getenv("PRO_MAX_VISION_IMAGES") or str(PRO_MAX_VISION_IMAGES)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = PRO_MAX_VISION_IMAGES
    return max(1, min(n, 10))


def pro_max_vision_images_for_submission(
    *,
    has_code_files: bool = False,
    has_executable_artifacts: bool = False,
    document_only: bool = False,
) -> int:
    """
    PRO vision cap: 3 screenshots for Word-only, 5 when code/exe present.
    Env PRO_MAX_VISION_IMAGES still caps the absolute maximum.
    """
    try:
        doc_cap = int(os.getenv("PRO_MAX_VISION_IMAGES_DOC", str(PRO_MAX_VISION_IMAGES_DOC)))
    except ValueError:
        doc_cap = PRO_MAX_VISION_IMAGES_DOC
    try:
        game_cap = int(os.getenv("PRO_MAX_VISION_IMAGES_GAME", str(PRO_MAX_VISION_IMAGES_GAME)))
    except ValueError:
        game_cap = PRO_MAX_VISION_IMAGES_GAME
    doc_cap = max(1, min(doc_cap, 10))
    game_cap = max(1, min(game_cap, 10))
    is_game_context = (has_code_files or has_executable_artifacts) and not document_only
    chosen = game_cap if is_game_context else doc_cap
    return min(chosen, pro_max_vision_images())


def batch_parallel_workers(grading_mode: str | None) -> int:
    """Concurrent students per batch (read from env at call time)."""
    fast = is_fast_grading_mode(grading_mode)
    env_key = (
        "FAST_BATCH_PARALLEL_STUDENTS"
        if fast
        else "PRO_BATCH_PARALLEL_STUDENTS"
    )
    default = FAST_BATCH_PARALLEL_STUDENTS if fast else PRO_BATCH_PARALLEL_STUDENTS
    raw = (os.getenv(env_key) or str(default)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = default
    return max(1, min(n, _BATCH_PARALLEL_CAP))


def deep_grading_flags(grading_mode: str | None) -> Dict[str, bool]:
    """PRO (deep) — Runtime/Vision + gemini-pro; skip admin-only governance layers."""
    deep = normalize_grading_mode_choice(grading_mode) == "deep"
    fast_pro = deep and pro_fast_path_enabled()
    return {
        "skip_runtime_observation": False,
        "skip_godot_pck_analysis": False,
        "skip_gameplay_video_inference": fast_pro,
        "skip_l2_l3_corroborative": deep,
        "skip_heavy_governance_graphs": deep,
        "skip_ai_evidence_reasoning": fast_pro,
        "skip_visual_verification": False,
        "light_project_profile": fast_pro,
        "compact_code_addon": deep,
        "skip_post_grade_artifact_rebuild": deep,
        "skip_institutional_resolution": fast_pro,
        "skip_governance_drift": deep,
        "skip_visual_verification_when_doc_vision_done": deep,
        "skip_gameplay_video_when_runtime_verified": deep,
        "parallel_batch_grading": deep,
        "slim_submission_paths": False,
        "minimal_artifact_inventory": False,
        "skip_evidence_layer": False,
        "skip_evidence_gate": False,
        "ultra_light_project_profile": False,
        "skip_post_grade_layers": fast_pro,
        "skip_production_layers": fast_pro,
        "skip_coverage_notice": fast_pro,
        "selective_archive_extract": deep,
        # PRO fast path: static runtime smoke only — skip emulator/browser/GM replay
        "enable_web_browser_automation": deep and not fast_pro,
        "enable_android_emulator_automation": deep and not fast_pro,
        "enable_gamemaker_runtime_verification": deep and not fast_pro,
        "enable_scratch_runtime_verification": deep and not fast_pro,
    }


def grading_flags(grading_mode: str | None) -> Dict[str, bool]:
    if is_fast_grading_mode(grading_mode):
        return fast_grading_flags(grading_mode)
    return deep_grading_flags(grading_mode)


def pro_should_skip_game_exe_disk_extract(
    path: str,
    *,
    group_paths: list[str],
    member_size: int = 0,
    grading_mode: str | None,
) -> bool:
    """
    PRO only: when Godot/game bundle (.pck / .gd / project.godot) exists in the same
    student group, do not extract large .exe from RAR to disk (inventory uses paths).
    BASIC is unchanged.
    """
    if is_fast_grading_mode(grading_mode):
        return False
    if normalize_grading_mode_choice(grading_mode) != "deep":
        return False
    if not path.lower().endswith(".exe"):
        return False
    joined = " ".join(group_paths).lower()
    has_bundle = (
        ".pck" in joined
        or ".gd" in joined
        or "project.godot" in joined
    )
    if not has_bundle:
        return False
    has_exe_member = any(p.lower().endswith(".exe") for p in group_paths)
    if not has_exe_member:
        return False
    # Keep smaller donor .exe for PCK pairing when large game exe was omitted from disk.
    if member_size > 120 * 1024 * 1024:
        return True
    return False


def _is_godot_editor_bundle_artifact(path: str) -> bool:
    """Godot editor shipped inside student ZIP — not the game build (PRO noise)."""
    name = (path or "").replace("\\", "/").split("/")[-1]
    lower = name.lower()
    if "godot" in lower and lower.endswith((".exe", ".zip", ".x86_64", ".app")):
        return True
    if lower.endswith(".exe"):
        try:
            from pathlib import Path
            from app.runtime_engines.godot.export_runner import is_godot_editor_executable

            if is_godot_editor_executable(Path(name)):
                return True
        except Exception:
            pass
    return False


def should_skip_archive_extract_to_disk(path: str, grading_mode: str | None) -> bool:
    """Skip heavy archive members on disk — BASIC skips binaries; PRO skips media only."""
    name = (path or "").replace("\\", "/").split("/")[-1].lower()
    if name.startswith("~$"):
        return True
    if normalize_grading_mode_choice(grading_mode) == "deep" and _is_godot_editor_bundle_artifact(
        path
    ):
        return True
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1]
    if is_fast_grading_mode(grading_mode):
        return ext in BASIC_SKIP_EXTRACT_SUFFIXES
    if normalize_grading_mode_choice(grading_mode) == "deep":
        return ext in PRO_SKIP_EXTRACT_SUFFIXES
    return False


_CODE_FILE_EXTENSIONS = frozenset(
    {
        ".py",
        ".java",
        ".cs",
        ".cpp",
        ".c",
        ".js",
        ".ts",
        ".html",
        ".jsx",
        ".tsx",
        ".rb",
        ".go",
        ".php",
        ".gml",
        ".gd",
        ".lua",
        ".yyp",
        ".pkt",
    }
)

_EXECUTABLE_FILE_EXTENSIONS = frozenset(
    {
        ".exe",
        ".apk",
        ".aab",
        ".ipa",
        ".app",
        ".pck",
        ".win",
    }
)


def enrich_student_submission_flags(student_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Infer code/exe flags from submission_paths — archive intake may key students
    under a folder name while display name comes from Word metadata.
    """
    paths = list(student_info.get("submission_paths") or [])
    primary = str(student_info.get("path") or "")
    if primary and primary not in paths:
        paths.insert(0, primary)

    has_code = bool(student_info.get("has_code_files"))
    has_exe = bool(student_info.get("has_executable_artifacts"))
    for raw in paths:
        try:
            ext = Path(raw).suffix.lower()
        except Exception:
            continue
        if ext in _CODE_FILE_EXTENSIONS:
            has_code = True
        if ext in _EXECUTABLE_FILE_EXTENSIONS:
            has_exe = True
        if has_code and has_exe:
            break

    student_info["has_code_files"] = has_code
    student_info["has_executable_artifacts"] = has_exe
    return student_info


def resolve_word_document_paths(
    primary_path: str,
    submission_paths: Optional[list[str]] = None,
) -> list[str]:
    """Word/PDF/RTF paths only — used for AI % and plagiarism document slice."""
    from pathlib import Path

    doc_ext = {".docx", ".doc", ".pdf", ".rtf"}
    paths: list[str] = []
    seen: set[str] = set()
    for raw in [primary_path, *(submission_paths or [])]:
        if not raw:
            continue
        try:
            rp = str(Path(raw).resolve())
        except OSError:
            rp = raw
        if rp in seen:
            continue
        if Path(rp).suffix.lower() in doc_ext and Path(rp).is_file():
            seen.add(rp)
            paths.append(rp)

    if not paths and primary_path:
        try:
            primary = Path(primary_path)
            if primary.is_file() and primary.suffix.lower() in doc_ext:
                paths = [str(primary.resolve())]
        except OSError:
            pass

    if len(paths) < 2 and primary_path:
        try:
            root = Path(primary_path).resolve().parent
            for _ in range(4):
                for doc in sorted(root.glob("*.docx"))[:6]:
                    rp = str(doc.resolve())
                    if rp not in seen and not doc.name.startswith("~$"):
                        seen.add(rp)
                        paths.append(rp)
                if root.parent == root:
                    break
                root = root.parent
        except OSError:
            pass

    def _sort_key(p: str) -> tuple[int, int]:
        name = Path(p).name.lower()
        try:
            size = Path(p).stat().st_size
        except OSError:
            size = 0
        aim_rank = 0 if "aim c" in name else (1 if "aim b" in name else 2)
        return (aim_rank, -size)

    paths.sort(key=_sort_key)
    return paths


def extract_fast_grading_text(
    primary_path: str,
    submission_paths: Optional[list[str]] = None,
) -> tuple[str, int]:
    """
    Extract full student-owned document text for BASIC (Word/PDF/RTF).
    No character or word limits — entire document content is sent for grading.
    """
    from pathlib import Path

    from app.document_processor import DocumentProcessor

    paths = resolve_word_document_paths(primary_path, submission_paths)

    parts: list[str] = []
    image_count = 0
    for doc_path in paths:
        try:
            text, imgs = DocumentProcessor.extract_text_with_image_count(doc_path)
        except Exception:
            text, imgs = "", 0
        image_count = max(image_count, imgs)
        body = (text or "").strip()
        if body:
            parts.append(f"=== {Path(doc_path).name} ===\n{body}")

    return ("\n\n".join(parts), image_count)


def build_ultra_light_project_profile(submission_paths: list[str]) -> Dict[str, Any]:
    """Path-only engine hints — no disk walk, no code sampling."""
    joined = " ".join(submission_paths).lower()
    engines: list[str] = []
    if ".gml" in joined or ".yyp" in joined or "gamemaker" in joined:
        engines.append("gamemaker")
    if ".gd" in joined or "project.godot" in joined or ".pck" in joined:
        engines.append("godot")
    if ".cs" in joined or ".unity" in joined:
        engines.append("unity")
    if ".py" in joined:
        engines.append("python_project")
    if ".pkt" in joined or "packet tracer" in joined:
        engines.append("cisco_packet_tracer")
    if not engines:
        engines = ["unknown_or_document_only"]
    gml_count = joined.count(".gml")
    gd_count = joined.count(".gd")
    return {
        "version": 1,
        "project_types": engines,
        "engines_detected": engines,
        "systems_detected": [],
        "code_quality": {"total_source_lines": 0, "oop_score": 0, "complexity_estimate": 0},
        "layout_evidence": [],
        "marker_files_found": [],
        "file_stats": {"unique_files": len(submission_paths), "extensions_top": []},
        "runtime_evidence": {"version": 1, "skipped_ultra_light": True},
        "notes_ar": (
            f"ملخص BASIC من مسارات الملفات فقط — محركات: {', '.join(engines)}؛ "
            f"ملفات GML≈{gml_count} GD≈{gd_count}. اقرأ نص الوورد/الكود في الـ prompt."
        ),
    }


def slim_artifact_inventory_for_snapshot(inventory: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep audit summary only — avoid multi‑MB JSON in SQLite."""
    if not inventory:
        return {}
    full_rt_obs = inventory.get("runtime_observation_report") or {}
    if isinstance(full_rt_obs, dict) and full_rt_obs.get("status") == "skipped_fast_mode":
        rt_obs = {"status": "skipped_fast_mode", "reason_ar": full_rt_obs.get("reason_ar", "")}
    else:
        rt_obs = {
            "status": full_rt_obs.get("status") if isinstance(full_rt_obs, dict) else "unknown",
            "runtime_verified": bool(full_rt_obs.get("runtime_verified")) if isinstance(full_rt_obs, dict) else False,
            "runtime_observed": bool(full_rt_obs.get("runtime_observed")) if isinstance(full_rt_obs, dict) else False,
            "engine": full_rt_obs.get("engine") if isinstance(full_rt_obs, dict) else None,
            "runtime_method": full_rt_obs.get("runtime_method") if isinstance(full_rt_obs, dict) else None,
            "game_launch_attempted": full_rt_obs.get("game_launch_attempted") if isinstance(full_rt_obs, dict) else None,
        }
        try:
            from app.runtime_evidence_package import _collect_runtime_screenshots

            shot_refs = _collect_runtime_screenshots(
                full_rt_obs if isinstance(full_rt_obs, dict) else {},
                inventory,
            )
            if shot_refs:
                rt_obs["runtime_screenshots"] = [
                    {
                        "path": s.get("path"),
                        "label": s.get("label"),
                        "status": s.get("status") or "captured",
                    }
                    for s in shot_refs[:6]
                    if isinstance(s, dict) and s.get("path")
                ]
        except Exception:
            pass
    out = {
        "version": inventory.get("version"),
        "grading_mode_note_ar": inventory.get("grading_mode_note_ar"),
        "has_executable_artifacts": inventory.get("has_executable_artifacts"),
        "has_source_code_artifacts": inventory.get("has_source_code_artifacts"),
        "runtime_evidence_level": inventory.get("runtime_evidence_level"),
        "runtime_observation_report": rt_obs,
        "documentation": {
            "status": (inventory.get("documentation") or {}).get("status"),
            "file_count": (inventory.get("documentation") or {}).get("file_count", 0),
            "files": [
                {"name": f.get("name"), "ext": f.get("ext")}
                for f in (inventory.get("documentation") or {}).get("files", [])[:4]
            ],
        },
        "source_code": {
            "status": (inventory.get("source_code") or {}).get("status"),
            "files": (inventory.get("source_code") or {}).get("files", [])[:12],
        },
        "embedded_screenshots": inventory.get("embedded_screenshots") or {},
        "vision_analysis_used": bool(inventory.get("vision_analysis_used")),
        "visual_evidence_summary": inventory.get("visual_evidence_summary") or {},
        "criterion_authority": inventory.get("criterion_authority") or [],
        "decision_provenance": inventory.get("decision_provenance") or {},
        "evidence_fingerprint": inventory.get("evidence_fingerprint") or {},
        "basic_video_keyframes_meta": {
            "videos_found": (inventory.get("basic_video_keyframes_meta") or {}).get("videos_found", 0),
            "frames_extracted": (inventory.get("basic_video_keyframes_meta") or {}).get("frames_extracted", 0),
            "sources": (inventory.get("basic_video_keyframes_meta") or {}).get("sources") or [],
        },
        "testing_evidence": {
            "status": (inventory.get("testing_evidence") or {}).get("status"),
        },
        "executable_artifacts": {
            "files": (inventory.get("executable_artifacts") or {}).get("files", [])[:8],
        },
        "source_code_artifacts": {
            "files": (inventory.get("source_code_artifacts") or {}).get("files", [])[:12],
        },
    }
    rt_pkg = inventory.get("runtime_evidence_package")
    if isinstance(rt_pkg, dict):
        out["runtime_evidence_package"] = rt_pkg
    gv = inventory.get("gameplay_verification")
    if isinstance(gv, dict) and gv:
        out["gameplay_verification"] = {
            k: gv.get(k)
            for k in (
                "version",
                "mode",
                "status",
                "l4_level",
                "automated_l4_level",
                "gameplay_entered",
                "player_movement_verified",
                "jump_detected",
                "score_change_detected",
                "mechanics_verified_count",
                "gameplay_window_screenshots",
                "menu_navigation",
            )
            if gv.get(k) is not None
        }
    rv = inventory.get("runtime_validation")
    if isinstance(rv, dict) and rv:
        out["runtime_validation"] = rv
    req_checklist = inventory.get("requirement_checklist")
    if isinstance(req_checklist, dict):
        out["requirement_checklist"] = req_checklist
    return out


def enrich_artifact_inventory_from_snapshot_meta(
    inventory: Dict[str, Any],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Restore evidence flags stripped from BASIC snapshots (persist + UI read)."""
    fp = snapshot.get("content_fingerprint") if isinstance(snapshot.get("content_fingerprint"), dict) else {}
    word_count = int(fp.get("word_count") or 0)
    image_count = int(fp.get("image_count") or 0)
    file_path = str(snapshot.get("file_path") or "")

    doc = inventory.setdefault("documentation", {})
    if isinstance(doc, dict):
        doc_path: Path | None = None
        if file_path:
            fp_obj = Path(file_path)
            if fp_obj.is_file() and fp_obj.suffix.lower() in (".docx", ".doc", ".pdf", ".odt"):
                doc_path = fp_obj
            elif fp_obj.is_dir():
                try:
                    for candidate in sorted(fp_obj.rglob("*")):
                        if candidate.is_file() and candidate.suffix.lower() in (".docx", ".doc", ".pdf", ".odt"):
                            if not candidate.name.startswith("~$"):
                                doc_path = candidate
                                break
                except OSError:
                    pass
        if word_count > 200 or doc_path is not None or file_path.lower().endswith((".docx", ".doc", ".pdf", ".odt")):
            if not doc.get("files"):
                if doc_path is not None:
                    doc["files"] = [{"name": doc_path.name, "ext": doc_path.suffix.lower() or ".docx"}]
                else:
                    ext = Path(file_path).suffix.lower() if file_path else ".docx"
                    doc["files"] = [{"name": Path(file_path).name or "submission.docx", "ext": ext or ".docx"}]
            if doc.get("status") not in ("analyzed", "detected"):
                doc["status"] = "analyzed"
            doc["file_count"] = max(int(doc.get("file_count") or 0), 1)

    if image_count > 0:
        emb = inventory.setdefault("embedded_screenshots", {})
        if isinstance(emb, dict):
            emb["count"] = max(int(emb.get("count") or 0), min(image_count, 99))

    if inventory.get("has_source_code_artifacts"):
        src = inventory.setdefault("source_code", {})
        if isinstance(src, dict) and not src.get("files"):
            src["status"] = "detected"
            src["files"] = [{"name": "project sources", "ext": ".gd"}]

    ves = snapshot.get("visual_evidence_summary")
    if isinstance(ves, dict):
        try:
            from app.visual_evidence_registry import sync_visual_evidence_to_inventory

            sync_visual_evidence_to_inventory(inventory, ves)
        except Exception:
            pass
    elif image_count > 0:
        # Legacy snapshots: do not mark vision as used when only counted, not analyzed.
        inventory["vision_analysis_used"] = bool(snapshot.get("vision_analysis_used"))

    auth = snapshot.get("criterion_authority")
    if isinstance(auth, list) and auth:
        inventory["criterion_authority"] = auth

    sub_paths = snapshot.get("submission_paths") or []
    if isinstance(sub_paths, list):
        scratch_paths = [
            str(p)
            for p in sub_paths
            if str(p).lower().endswith((".sb3", ".sb2", ".sb"))
        ]
        if scratch_paths:
            rt = inventory.setdefault("runtime_artifacts", {})
            if isinstance(rt, dict):
                rt["scratch_detected"] = True
                rt["scratch_signals"] = {
                    "detected": True,
                    "project_files": [Path(p).name for p in scratch_paths[:6]],
                    "sb3_present": any(p.lower().endswith(".sb3") for p in scratch_paths),
                }
                rt["executables_detected"] = True
            exe = inventory.setdefault("executable_artifacts", {})
            if isinstance(exe, dict):
                if not exe.get("files"):
                    exe["files"] = [
                        {
                            "name": Path(p).name,
                            "path": p,
                            "ext": Path(p).suffix.lower(),
                            "artifact_kind": "scratch_project",
                        }
                        for p in scratch_paths[:6]
                    ]
                if exe.get("status") not in ("observed_runtime_advisory",):
                    exe["status"] = "detected_not_executed"
            src = inventory.setdefault("source_code", {})
            if isinstance(src, dict) and not src.get("files"):
                src["files"] = [
                    {
                        "name": Path(p).name,
                        "path": p,
                        "ext": Path(p).suffix.lower(),
                        "source_kind": "scratch_project",
                    }
                    for p in scratch_paths[:6]
                ]
                src["status"] = "detected"
            inventory["has_executable_artifacts"] = True
            inventory["has_source_code_artifacts"] = True

    return inventory


def compact_snapshot_for_storage(
    payload: Dict[str, Any],
    grading_mode: str | None,
) -> Dict[str, Any]:
    """Shrink grading snapshot for DB — critical for BASIC batches (30 students)."""
    if not is_fast_grading_mode(grading_mode):
        return payload
    out = dict(payload)
    out.pop("student_text", None)
    out.pop("plagiarism_text", None)
    out.pop("authority_replay", None)
    out.pop("governance_drift", None)
    out.pop("mitigation_records", None)
    out.pop("evidence_trace_graph", None)
    if "artifact_inventory" in out:
        inv = slim_artifact_inventory_for_snapshot(
            out.get("artifact_inventory") if isinstance(out.get("artifact_inventory"), dict) else {}
        )
        inv = enrich_artifact_inventory_from_snapshot_meta(inv, out)
        inv["criteria_results"] = out.get("criteria_results") or []
        if not inv.get("criterion_authority"):
            inv["criterion_authority"] = out.get("criterion_authority") or []
        if not inv.get("decision_provenance"):
            inv["decision_provenance"] = out.get("decision_provenance") or {}
        if not inv.get("evidence_fingerprint"):
            inv["evidence_fingerprint"] = out.get("evidence_fingerprint") or {}
        try:
            from app.academic_explainability import attach_academic_explainability

            attach_academic_explainability(inv, grading_mode=grading_mode)
        except Exception:
            pass
        out["artifact_inventory"] = inv
        if inv.get("decision_provenance") and not out.get("decision_provenance"):
            out["decision_provenance"] = inv["decision_provenance"]
        if inv.get("evidence_fingerprint") and not out.get("evidence_fingerprint"):
            out["evidence_fingerprint"] = inv["evidence_fingerprint"]
        if out.get("academic_decision_digest") is None and out.get("grade_level") is not None:
            try:
                from app.explainability_migration import academic_decision_digest_from_snapshot

                out["academic_decision_digest"] = academic_decision_digest_from_snapshot(out)
            except Exception:
                pass
        # Keep explainability_layer in sync so stale layer rows are not served after regrade.
        diag = inv.get("missing_evidence_diagnostics") if isinstance(inv.get("missing_evidence_diagnostics"), dict) else {}
        out["explainability_layer"] = {
            "version": "v2",
            "governance_intent": inv.get("governance_intent") or {},
            "missing_evidence_diagnostics": diag,
            "extraction_coverage": inv.get("extraction_coverage") or {},
            "evidence_lineage": inv.get("evidence_lineage") or out.get("evidence_lineage") or {},
        }
    prof = out.get("project_profile_persisted")
    if isinstance(prof, dict) and prof:
        try:
            from app.project_intelligence.evidence_schema import slim_profile_for_persistence

            out["project_profile_persisted"] = slim_profile_for_persistence(prof)
        except Exception:
            out.pop("project_profile_persisted", None)
    for key in ("evidence_layer", "assessment_trace"):
        val = out.get(key)
        if isinstance(val, dict) and len(json.dumps(val, ensure_ascii=False)) > 80_000:
            out[key] = {"status": "trimmed_fast_mode", "note_ar": "مختصر في وضع BASIC"}
    try:
        blob = json.dumps(out, ensure_ascii=False)
        if len(blob) > FAST_MAX_SNAPSHOT_BYTES:
            out["snapshot_trimmed"] = True
            out.pop("evidence_layer", None)
            out.pop("assessment_trace", None)
            out.pop("grading_coverage_notice", None)
    except Exception:
        pass
    return out


def resolve_grading_policy(package_name: str | None) -> Dict[str, Any]:
    """Return deterministic grading profile for a subscription package."""
    name = (package_name or "").strip().lower()
    if name in FAST_PACKAGE_NAMES:
        return {
            "grading_mode": "fast",
            "max_retries": 0,
            "vision_enabled": False,
            "label_ar": "Basic — تصحيح سريع",
            "description_ar": (
                "STANDARD — Flash سريع + Runtime خفيف (launch + sweep قصير، بدون Agent). "
                "Word ~2–3 د + Vision لصور Word (حتى 10). 30 طالب ≈ 8 معاً (~25–50 د)."
            ),
        }
    if name in DEEP_PACKAGE_NAMES:
        return {
            "grading_mode": "deep",
            "max_retries": None,  # fallback to production config
            "vision_enabled": True,
            "label_ar": "Pro — تصحيح دقيق وموثّق",
            "description_ar": (
                "Pro — gemini-2.5-pro + Runtime + 5 صور؛ كود مضغوط؛ بدون حوكمة إدارية/L2-L3. "
                "Word ~12–22 د، لعبة ~20–40 د. 30 طالب ≈ 2 معاً (~3–6 ساعات)."
            ),
        }
    return {
        "grading_mode": "deep",
        "max_retries": None,
        "vision_enabled": True,
        "label_ar": "افتراضي — تحقق كامل",
        "description_ar": (
            "تحقق كامل: تشغيل اللعبة عند الحاجة، ربط بمعايير BTEC، وإمكانية "
            "إنشاء سجل تقييم تفصيلي من «إنشاء سجلات التقييم»."
        ),
    }
