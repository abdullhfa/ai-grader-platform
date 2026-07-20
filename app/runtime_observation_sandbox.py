"""
L4 Governed Runtime Observation Sandbox — observation only, not verification.

Analyzes .apk / .pck / .exe under controlled conditions (timeout, no auto Achieved language).
Output: runtime_signal_graph → criterion mapping → grading adjudication support.
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.runtime_interaction_trace import (
    INTERACTION_AT_SECONDS,
    apply_interaction_signals,
    build_interaction_trace_report,
    run_interaction_burst,
)
from app.runtime_observation_contract import CONTRACT_ID, RUNTIME_SIGNAL_SCHEMA
from app.runtime_process_restriction import RuntimeProcessGuard, dismiss_windows_file_dialogs
from app.runtime_telemetry_graph import merge_analyses_to_telemetry_graph
from app.visual_state_classification import (
    build_visual_audit_summary,
    classify_visual_state_from_image,
    compute_extended_visual_stats,
)

OBSERVATION_MODE = "controlled_static_and_smoke"
FAST_OBSERVATION_MODE = "controlled_fast_smoke"
MAX_SMOKE_SECONDS = 12  # STANDARD default; PRO uses resolve_smoke_timeout_seconds()
MAX_ARTIFACTS = 6
UNITY_LOG_MAX_BYTES = 256_000
RUNTIME_SCREENSHOT_OFFSETS = (("launch", 2.0), ("mid_runtime", 5.0), ("pre_exit", -0.75))
FAST_RUNTIME_SCREENSHOT_OFFSETS = (("launch", 2.0),)


def resolve_runtime_screenshot_offsets(
    grading_mode: str | None = None,
) -> tuple[tuple[str, float], ...]:
    """STANDARD: launch only (+ interaction shots). PRO: full offset set."""
    try:
        from app.grading_mode_policy import is_fast_grading_mode

        if is_fast_grading_mode(grading_mode):
            return FAST_RUNTIME_SCREENSHOT_OFFSETS
    except Exception:
        if (grading_mode or "").strip().lower() in ("fast", "basic", "standard"):
            return FAST_RUNTIME_SCREENSHOT_OFFSETS
    return RUNTIME_SCREENSHOT_OFFSETS


def is_fast_runtime_smoke(grading_mode: str | None = None) -> bool:
    try:
        from app.grading_mode_policy import is_fast_grading_mode

        return is_fast_grading_mode(grading_mode)
    except Exception:
        return (grading_mode or "").strip().lower() in ("fast", "basic", "standard")


def resolve_smoke_timeout_seconds(grading_mode: str | None = None) -> int:
    """Mode-aware smoke window — PRO 30–45s (default 40), FAST 12s."""
    try:
        from app.core.production_config import resolve_sandbox_timeout_seconds

        return resolve_sandbox_timeout_seconds(grading_mode)
    except Exception:
        return MAX_SMOKE_SECONDS


def _safe_path(p: Path) -> bool:
    try:
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def _unity_data_dir_for_exe(path: Path) -> Optional[Path]:
    expected = path.parent / f"{path.stem}_Data"
    if expected.is_dir():
        return expected
    try:
        siblings = [p for p in path.parent.iterdir() if p.is_dir() and p.name.endswith("_Data")]
    except OSError:
        return None
    if len(siblings) == 1:
        return siblings[0]
    for sibling in siblings:
        if sibling.name.lower().startswith(path.stem.lower()):
            return sibling
    return None


def detect_unity_build_for_exe(path: Path) -> Dict[str, Any]:
    """Detect whether an .exe appears to be a Unity player build."""
    data_dir = _unity_data_dir_for_exe(path)
    unity_player = path.parent / "UnityPlayer.dll"
    globalgamemanagers = data_dir / "globalgamemanagers" if data_dir else None
    boot_config = data_dir / "boot.config" if data_dir else None
    managed_dir = data_dir / "Managed" if data_dir else None
    detected = bool(
        (data_dir and data_dir.is_dir())
        or unity_player.is_file()
        or (globalgamemanagers and globalgamemanagers.is_file())
    )
    confidence = "none"
    if detected:
        confidence = "high" if data_dir and unity_player.is_file() else "medium"
    return {
        "detected": detected,
        "confidence": confidence,
        "exe_path": str(path),
        "data_dir": str(data_dir) if data_dir else "",
        "unity_player_dll": unity_player.is_file(),
        "globalgamemanagers": bool(globalgamemanagers and globalgamemanagers.is_file()),
        "boot_config": bool(boot_config and boot_config.is_file()),
        "managed_dir": bool(managed_dir and managed_dir.is_dir()),
    }


def _read_text_tail(path: Path, max_bytes: int = UNITY_LOG_MAX_BYTES) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(max(0, size - max_bytes))
            raw = fh.read(max_bytes)
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _safe_artifact_stem(name: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_")
    return (safe or "runtime_artifact")[:80]


def _runtime_session_id(session_ctx: Optional[Dict[str, Any]] = None) -> str:
    ctx = session_ctx or {}
    existing = str(ctx.get("runtime_session_id") or "").strip()
    if existing:
        return existing
    return f"ros_{uuid.uuid4().hex[:12]}"


def _runtime_submission_key(session_ctx: Optional[Dict[str, Any]] = None) -> str:
    ctx = session_ctx or {}
    if ctx.get("submission_id") is not None:
        return f"submission_{ctx['submission_id']}"
    student = str(ctx.get("student_name") or "").strip()
    if student:
        return _safe_artifact_stem(student)
    return "unknown_submission"


def _runtime_screenshot_dir(
    path: Path,
    *,
    session_ctx: Optional[Dict[str, Any]] = None,
) -> Path:
    root = Path("uploads") / "debug" / "runtime_screenshots"
    session_id = _runtime_session_id(session_ctx)
    submission_key = _runtime_submission_key(session_ctx)
    return root / submission_key / session_id / _safe_artifact_stem(path.stem)


def capture_runtime_screenshot(
    path: Path,
    *,
    label: str,
    elapsed_seconds: float,
    session_ctx: Optional[Dict[str, Any]] = None,
    process_pid: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Process-owned game-window screenshot capture.

    This is visual runtime evidence only; it does not prove gameplay correctness.
    """
    session_id = _runtime_session_id(session_ctx)
    record: Dict[str, Any] = {
        "label": label,
        "capture_type": label,
        "timestamp_sec": round(elapsed_seconds, 2),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "runtime_session_id": session_id,
        "submission_key": _runtime_submission_key(session_ctx),
        "status": "unavailable",
        "mode": "process_owned_window_capture",
        "path": "",
        "errors": [],
        "authority": "advisory_visual_runtime_only",
        "window_visible": False,
    }
    if sys.platform != "win32":
        record["errors"].append("screenshot_windows_only")
        return record
    try:
        from PIL import ImageGrab  # type: ignore
    except Exception as exc:
        record["errors"].append(f"pillow_imagegrab_unavailable:{exc.__class__.__name__}")
        return record

    try:
        out_dir = _runtime_screenshot_dir(path, session_ctx=session_ctx)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time() * 1000)
        out_path = out_dir / f"{label}_{stamp}.png"
        capture_bbox = None
        game_bbox = None
        try:
            from app.window_focus_manager import (
                classify_capture_scope,
                focus_game_window,
                pin_game_window_for_sandbox,
                resolve_game_window_bbox,
            )

            pin_game_window_for_sandbox(artifact_path=path, process_pid=process_pid)
            focus_game_window(process_pid=process_pid)
            game_bbox = resolve_game_window_bbox(
                artifact_path=path,
                process_pid=process_pid,
            )
            if not game_bbox:
                record["errors"].append("RUNTIME_CAPTURE_LOST")
                record["capture_scope"] = "capture_lost"
                return record
            capture_bbox = game_bbox
            image = ImageGrab.grab(bbox=game_bbox)
            record["capture_scope"] = classify_capture_scope(
                capture_bbox=capture_bbox,
                game_bbox=game_bbox,
            )
            record["game_window_bbox"] = list(game_bbox) if game_bbox else None
        except Exception as exc:
            record["errors"].append(f"RUNTIME_CAPTURE_LOST:{exc.__class__.__name__}")
            record["capture_scope"] = "capture_lost"
            return record
        image.save(out_path)
        classified = classify_visual_state_from_image(image)
        stats = classified.get("visual_stats") or compute_extended_visual_stats(image)
        record.update({
            "status": "captured",
            "path": str(out_path),
            "size_bytes": out_path.stat().st_size,
            "width": stats.get("width", getattr(image, "width", None)),
            "height": stats.get("height", getattr(image, "height", None)),
            "resolution": stats.get("resolution"),
            "window_visible": bool(stats.get("window_visible")),
            "visual_stats": stats,
            "visual_state": classified.get("visual_state", "unknown"),
            "visual_state_confidence": classified.get("visual_state_confidence", 0.0),
            "classification_mode": classified.get("classification_mode"),
            "classification_reasons": classified.get("classification_reasons", []),
            "capture_bbox": list(capture_bbox) if capture_bbox else None,
            "game_window_detected": bool(game_bbox),
            "process_pid": process_pid,
        })
        from app.runtime_screenshot_validation import validate_runtime_screenshot_record

        record = validate_runtime_screenshot_record(record)
    except Exception as exc:
        record["errors"].append(str(exc))
    return record


def summarize_runtime_screenshots(screenshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    from app.runtime_screenshot_validation import filter_gameplay_screenshots

    captured = [s for s in screenshots if s.get("status") == "captured"]
    rejected = [s for s in screenshots if s.get("status") == "rejected"]
    gameplay_captured = filter_gameplay_screenshots(screenshots)
    game_window_captured = [
        s for s in captured if str(s.get("capture_scope") or "") == "game_window"
    ]
    black_possible = [
        s for s in captured
        if s.get("visual_state") == "black_screen"
        or (s.get("visual_stats") or {}).get("black_screen_possible") is True
    ]
    audit = build_visual_audit_summary(screenshots)
    states = audit.get("visual_states_observed") or []
    return {
        "runtime_screenshot_count": len(gameplay_captured),
        "runtime_screenshot_raw_count": len(captured),
        "runtime_screenshot_rejected_count": len(rejected),
        "runtime_game_window_screenshot_count": len(game_window_captured),
        "runtime_non_game_window_screenshot_count": max(0, len(captured) - len(game_window_captured)),
        "runtime_screenshots": screenshots,
        "visual_runtime_evidence": "present" if gameplay_captured else "unavailable",
        "black_screen_possible": bool(black_possible),
        "visual_states_observed": states,
        "visual_runtime_confidence": audit.get("visual_runtime_confidence", 0.0),
        "freeze_possible": (audit.get("freeze_detection") or {}).get("freeze_possible", False),
        "observed_visual_elements": audit.get("observed_visual_elements", []),
        "unverified_gameplay": audit.get("unverified_gameplay", []),
        "human_validation_required": audit.get("human_validation_required", []),
        "visual_audit_summary": audit,
        "authority_note_ar": (
            "لقطات runtime + visual_state استشاريان على ظهور output فقط — "
            "لا تثبت جودة gameplay أو تحقق معايير C.P5/C.P6."
        ),
    }


def parse_unity_player_log(log_text: str) -> Dict[str, Any]:
    """
    Extract bounded Unity Player.log signals.

    These are runtime hints only; they never prove gameplay correctness.
    """
    text = log_text or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    unity_version = ""
    for pat in (
        r"Initialize engine version:\s*([^\s]+)",
        r"Unity Player\s*\[?([0-9][^\]\s]+)",
    ):
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            unity_version = m.group(1)
            break

    error_re = re.compile(
        r"\b(error|exception|failed to load|missingreference|nullreference|"
        r"indexoutofrange|stack trace|fatal|crash|abort|access violation)\b",
        re.IGNORECASE,
    )
    crash_re = re.compile(
        r"\b(crash|fatal|abort|access violation|mono crash|native crash)\b",
        re.IGNORECASE,
    )
    scene_re = re.compile(
        r"\b(loadscene|loading level|scene manager|activatescene|unloadtime|"
        r"scene loaded|level loaded)\b",
        re.IGNORECASE,
    )
    input_re = re.compile(
        r"\b(input system|inputmanager|input module|input initialized)\b",
        re.IGNORECASE,
    )

    errors = [ln[:240] for ln in lines if error_re.search(ln)]
    crashes = [ln[:240] for ln in lines if crash_re.search(ln)]
    scenes = [ln[:240] for ln in lines if scene_re.search(ln)]
    input_lines = [ln[:240] for ln in lines if input_re.search(ln)]

    return {
        "unity_version_hint": unity_version,
        "error_count": len(errors),
        "exception_count": sum(1 for ln in errors if "exception" in ln.lower()),
        "crash_signal_count": len(crashes),
        "crash_signals": crashes[:8],
        "error_signals": errors[:10],
        "scene_load_signals": scenes[:8],
        "input_system_signals": input_lines[:6],
        "log_line_count": len(lines),
        "authority_note_ar": (
            "Player.log signals are runtime hints only — لا تثبت صحة gameplay أو تحقق المعيار."
        ),
    }


def _candidate_unity_log_paths(path: Path, *, since: float) -> List[Path]:
    candidates: List[Path] = []
    data_dir = _unity_data_dir_for_exe(path)
    local_candidates = [
        path.parent / "Player.log",
        path.parent / "output_log.txt",
    ]
    if data_dir:
        local_candidates.extend([
            data_dir / "output_log.txt",
            data_dir / "Player.log",
        ])
    try:
        local_candidates.extend(path.parent.glob("*BackUpThisFolder*/output_log.txt"))
    except OSError:
        pass
    candidates.extend(p for p in local_candidates if p.is_file())

    if sys.platform == "win32":
        local_low = Path.home() / "AppData" / "LocalLow"
        if local_low.is_dir():
            try:
                company_dirs = [p for p in local_low.iterdir() if p.is_dir()][:80]
            except OSError:
                company_dirs = []
            for company_dir in company_dirs:
                try:
                    product_dirs = [p for p in company_dir.iterdir() if p.is_dir()][:120]
                except OSError:
                    continue
                for product_dir in product_dirs:
                    log = product_dir / "Player.log"
                    try:
                        if log.is_file() and log.stat().st_mtime >= since - 5:
                            candidates.append(log)
                    except OSError:
                        continue

    unique: Dict[str, Path] = {}
    for candidate in candidates:
        unique[str(candidate)] = candidate
    return sorted(
        unique.values(),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )[:8]


def collect_unity_log_observation(path: Path, *, since: float) -> Dict[str, Any]:
    """Collect and parse the most relevant Unity log candidate."""
    logs = _candidate_unity_log_paths(path, since=since)
    log_infos: List[Dict[str, Any]] = []
    selected_text = ""
    selected_path: Optional[Path] = None
    for log in logs:
        try:
            stat = log.stat()
        except OSError:
            continue
        info = {
            "path": str(log),
            "size_bytes": stat.st_size,
            "modified_after_launch": stat.st_mtime >= since - 1,
        }
        log_infos.append(info)
        if selected_path is None and stat.st_size > 0:
            selected_path = log
            selected_text = _read_text_tail(log)

    parsed = parse_unity_player_log(selected_text) if selected_text else {
        "unity_version_hint": "",
        "error_count": 0,
        "exception_count": 0,
        "crash_signal_count": 0,
        "crash_signals": [],
        "error_signals": [],
        "scene_load_signals": [],
        "input_system_signals": [],
        "log_line_count": 0,
        "authority_note_ar": (
            "Player.log was not available — runtime meaning remains unverified."
        ),
    }
    parsed.update({
        "player_log_found": selected_path is not None,
        "selected_log_path": str(selected_path) if selected_path else "",
        "candidate_logs": log_infos,
        "candidate_log_count": len(log_infos),
    })
    return parsed


def analyze_apk(path: Path) -> Dict[str, Any]:
    """Static APK structure analysis (zip-based — no install)."""
    out: Dict[str, Any] = {
        "artifact": path.name,
        "type": "apk",
        "valid": False,
        "signals": {},
        "errors": [],
    }
    if not _safe_path(path):
        out["errors"].append("file_missing_or_empty")
        return out
    try:
        if not zipfile.is_zipfile(path):
            out["errors"].append("not_valid_zip")
            return out
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            lower = {n.lower() for n in names}
            has_dex = any(n.endswith("classes.dex") or "/classes.dex" in n.lower() for n in names)
            has_manifest = "androidmanifest.xml" in lower
            has_assets = any(n.lower().startswith("assets/") for n in names)
            has_lib = any(n.lower().startswith("lib/") for n in names)
            has_res = any(n.lower().startswith("res/") for n in names)
            godot_hints = any(
                "godot" in n.lower() or n.lower().endswith(".pck") for n in names
            )
            package_name = None
            if has_manifest:
                try:
                    raw = zf.read("AndroidManifest.xml")
                    m = re.search(rb'package=["\']([^"\']+)["\']', raw)
                    if m:
                        package_name = m.group(1).decode("utf-8", errors="replace")
                except Exception:
                    pass
            out["valid"] = has_dex and has_manifest
            out["package_name"] = package_name
            out["entry_count"] = len(names)
            out["size_bytes"] = path.stat().st_size
            out["signals"] = {
                "apk_structure_valid": out["valid"],
                "scene_loaded": "unknown",
                "has_dex": has_dex,
                "has_manifest": has_manifest,
                "has_assets": has_assets,
                "has_native_libs": has_lib,
                "has_resources": has_res,
                "godot_content_hint": godot_hints,
                "crash": "none" if out["valid"] else "observed",
            }
    except Exception as exc:
        out["errors"].append(str(exc))
    return out


def analyze_godot_pck(path: Path) -> Dict[str, Any]:
    """Parse Godot PCK header + scan for game resource hints."""
    out: Dict[str, Any] = {
        "artifact": path.name,
        "type": "pck",
        "valid": False,
        "signals": {},
        "errors": [],
    }
    if not _safe_path(path):
        out["errors"].append("file_missing_or_empty")
        return out
    try:
        data = path.read_bytes()[: min(path.stat().st_size, 2_000_000)]
        magic_idx = data.find(b"GDPC")
        if magic_idx < 0:
            out["errors"].append("godot_pck_magic_not_found")
            return out
        out["valid"] = True
        out["magic_offset"] = magic_idx
        # Heuristic content scan
        blob = data.decode("latin-1", errors="ignore").lower()
        has_scenes = ".tscn" in blob or ".scn" in blob
        has_gd = ".gd" in blob
        has_project = "project.godot" in blob
        has_audio = ".ogg" in blob or ".wav" in blob or ".mp3" in blob
        has_sprites = ".png" in blob or ".webp" in blob
        gd_hits = blob.count(".gd")
        scene_hits = blob.count(".tscn") + blob.count(".scn")
        out["signals"] = {
            "godot_pck_valid": True,
            "scene_loaded": "yes" if has_scenes else "partial",
            "player_moved": "unknown",
            "has_scenes": has_scenes,
            "has_gdscript": has_gd,
            "has_project_config": has_project,
            "has_audio_assets": has_audio,
            "has_sprite_assets": has_sprites,
            "gd_script_hits": gd_hits,
            "scene_hits": scene_hits,
            "crash": "none",
        }
        out["size_bytes"] = path.stat().st_size
    except Exception as exc:
        out["errors"].append(str(exc))
    return out


def smoke_test_windows_exe(
    path: Path,
    *,
    timeout: int = MAX_SMOKE_SECONDS,
    capture_screenshots: bool = False,
    enable_interaction_trace: bool = False,
    session_ctx: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    screenshot_offsets: Optional[tuple[tuple[str, float], ...]] = None,
    grading_mode: str | None = None,
) -> Dict[str, Any]:
    """Limited smoke test — process launch + stability window (Windows)."""
    out: Dict[str, Any] = {
        "artifact": path.name,
        "type": "exe",
        "attempted": False,
        "signals": {},
        "runtime_screenshots": [],
        "interaction_trace": None,
        "runtime_session_id": _runtime_session_id(session_ctx),
        "errors": [],
    }
    if not _safe_path(path):
        out["errors"].append("file_missing_or_empty")
        return out
    if path.suffix.lower() != ".exe":
        out["errors"].append("not_exe")
        return out
    if "console" in path.name.lower():
        out["errors"].append("skipped_console_wrapper")
        return out
    if sys.platform != "win32":
        out["errors"].append("smoke_test_windows_only")
        out["signals"] = {"runtime_launch_attempted": False, "crash": "unknown"}
        return out

    launch_cwd = cwd or path.parent
    search_root: Optional[Path] = None
    if session_ctx:
        for key in ("submission_root", "project_root", "search_root"):
            raw = session_ctx.get(key)
            if raw:
                search_root = Path(str(raw))
                break
        submission_paths = session_ctx.get("submission_paths") or []
        if search_root is None and submission_paths:
            first = Path(str(submission_paths[0]))
            search_root = first.parent if first.is_file() else first

    try:
        from app.runtime_engines.gamemaker.project_probe import assess_gamemaker_exe_launch

        launch_assessment = assess_gamemaker_exe_launch(path, search_root=search_root)
        out["gamemaker_launch_assessment"] = launch_assessment
        if launch_assessment.get("is_gamemaker"):
            launch_cwd = Path(launch_assessment.get("runtime_cwd") or launch_cwd)
            if not launch_assessment.get("launch_allowed"):
                out["attempted"] = False
                out["launch_cwd"] = str(launch_cwd)
                out["smoke_result"] = "skipped_missing_data_win"
                out["errors"].append("gamemaker_missing_data_win")
                out["signals"] = {
                    "runtime_launch_attempted": False,
                    "runtime_stable": False,
                    "crash": "unknown",
                    "gamemaker_static_only": True,
                    "gamemaker_skip_reason": launch_assessment.get("skip_reason"),
                }
                return out
    except Exception as exc:
        out["errors"].append(f"gamemaker_launch_assessment_failed:{exc}")

    out["attempted"] = True
    out["launch_cwd"] = str(launch_cwd)
    proc = None
    guard: Optional[RuntimeProcessGuard] = None
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [str(path)],
            cwd=str(launch_cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        guard = RuntimeProcessGuard(proc.pid)
        launch_started = time.time()
        offsets = screenshot_offsets
        if offsets is None and grading_mode is not None:
            offsets = resolve_runtime_screenshot_offsets(grading_mode)
        if offsets is None:
            offsets = RUNTIME_SCREENSHOT_OFFSETS
        screenshot_targets: List[Tuple[str, float]] = []
        if capture_screenshots:
            for label, raw_offset in offsets:
                offset = (timeout + raw_offset) if raw_offset < 0 else raw_offset
                if 0.5 <= offset < timeout:
                    screenshot_targets.append((label, offset))
        captured_labels: set = set()
        interaction_done = False
        pre_interaction_shot: Optional[Dict[str, Any]] = None
        deadline = time.time() + timeout
        exit_code = None
        while time.time() < deadline:
            exit_code = proc.poll()
            guard.scan_once()
            if proc.pid:
                dismissed = dismiss_windows_file_dialogs(root_pid=proc.pid)
                if dismissed:
                    out.setdefault("signals", {})["file_dialog_dismissed"] = dismissed
            if exit_code is not None:
                break
            elapsed = time.time() - launch_started
            for label, target in screenshot_targets:
                if label not in captured_labels and elapsed >= target:
                    shot = capture_runtime_screenshot(
                        path,
                        label=label,
                        elapsed_seconds=elapsed,
                        session_ctx=session_ctx,
                        process_pid=proc.pid if proc else None,
                    )
                    out["runtime_screenshots"].append(shot)
                    captured_labels.add(label)
                    if label == "launch" and shot.get("status") == "captured":
                        pre_interaction_shot = shot
            if (
                enable_interaction_trace
                and not interaction_done
                and proc.poll() is None
                and elapsed >= INTERACTION_AT_SECONDS
            ):
                if pre_interaction_shot is None:
                    pre_interaction_shot = capture_runtime_screenshot(
                        path,
                        label="pre_interaction",
                        elapsed_seconds=elapsed,
                        session_ctx=session_ctx,
                        process_pid=proc.pid if proc else None,
                    )
                    out["runtime_screenshots"].append(pre_interaction_shot)

                def _capture_shot(*_args: Any, **kwargs: Any) -> Dict[str, Any]:
                    # gameplay_verifier passes artifact_path positionally; closure `path` is authoritative.
                    kwargs.pop("process_pid", None)
                    return capture_runtime_screenshot(
                        path,
                        session_ctx=session_ctx,
                        process_pid=proc.pid if proc else None,
                        **kwargs,
                    )

                try:
                    from app.gameplay_verifier import run_automated_gameplay_verification

                    gameplay_verification = run_automated_gameplay_verification(
                        artifact_path=path,
                        process_pid=proc.pid if proc else None,
                        capture_screenshot=_capture_shot,
                        elapsed_seconds=elapsed,
                    )
                    out["gameplay_verification"] = gameplay_verification
                    for shot in gameplay_verification.get("extra_screenshots") or []:
                        if isinstance(shot, dict) and shot not in out["runtime_screenshots"]:
                            out["runtime_screenshots"].append(shot)
                    movement = gameplay_verification.get("movement_verification") or {}
                    pre_shot = movement.get("screenshots", [None])[0] if movement.get("screenshots") else pre_interaction_shot
                    post_shot = movement.get("screenshots", [None, None])[1] if len(movement.get("screenshots") or []) > 1 else pre_interaction_shot
                    trace = build_interaction_trace_report(
                        {
                            "mode": gameplay_verification.get("mode"),
                            "authority": gameplay_verification.get("authority"),
                            "platform": gameplay_verification.get("platform"),
                            "status": gameplay_verification.get("status"),
                            "inputs_sent": [{"type": "automated_l4", "sent": True}],
                            "input_count": 1,
                            "errors": [],
                            "does_not_verify_gameplay": gameplay_verification.get("does_not_verify_gameplay"),
                            "human_playtest_required": gameplay_verification.get("human_playtest_required"),
                            "authority_note_ar": gameplay_verification.get("authority_note_ar"),
                        },
                        pre_screenshot=pre_shot if isinstance(pre_shot, dict) else pre_interaction_shot,
                        post_screenshot=post_shot if isinstance(post_shot, dict) else pre_interaction_shot,
                    )
                    trace.update({
                        "l4_level": gameplay_verification.get("l4_level"),
                        "automated_l4_level": gameplay_verification.get("automated_l4_level"),
                        "gameplay_entered": gameplay_verification.get("gameplay_entered"),
                        "player_movement_verified": gameplay_verification.get("player_movement_verified"),
                        "jump_detected": gameplay_verification.get("jump_detected"),
                        "score_change_detected": gameplay_verification.get("score_change_detected"),
                        "mechanics_verified_count": gameplay_verification.get("mechanics_verified_count"),
                        "gameplay_window_screenshots": gameplay_verification.get("gameplay_window_screenshots"),
                        "menu_navigation": gameplay_verification.get("menu_navigation"),
                        "movement_verification": movement,
                    })
                    if movement.get("horizontal_shift") is not None:
                        trace["visual_delta_score"] = movement.get("horizontal_shift")
                    if gameplay_verification.get("l4_level") in ("L4_full", "L4_partial"):
                        trace["does_not_verify_gameplay"] = False
                        trace["human_playtest_required"] = False
                        trace["player_movement_verified"] = bool(
                            gameplay_verification.get("player_movement_verified")
                        )
                except Exception as exc:
                    burst = run_interaction_burst()
                    time.sleep(0.35)
                    post_shot = capture_runtime_screenshot(
                        path,
                        label="post_interaction",
                        elapsed_seconds=time.time() - launch_started,
                        session_ctx=session_ctx,
                        process_pid=proc.pid if proc else None,
                    )
                    out["runtime_screenshots"].append(post_shot)
                    trace = build_interaction_trace_report(
                        burst,
                        pre_screenshot=pre_interaction_shot,
                        post_screenshot=post_shot,
                    )
                    trace.setdefault("errors", []).append(str(exc))
                out["interaction_trace"] = trace
                apply_interaction_signals(out.setdefault("signals", {}), trace)
                interaction_done = True
            time.sleep(0.4)
        still_running = proc.poll() is None
        if still_running:
            out["signals"] = {
                "runtime_launch_attempted": True,
                "runtime_stable": True,
                "scene_loaded": "partial",
                "player_moved": "unknown",
                "crash": "none",
                "process_ran_seconds": timeout,
            }
            out["smoke_result"] = "stable_window"
        elif exit_code == 0:
            out["signals"] = {
                "runtime_launch_attempted": True,
                "runtime_stable": "partial",
                "scene_loaded": "partial",
                "crash": "none",
                "exit_code": exit_code,
            }
            out["smoke_result"] = "launch_ok"
        else:
            out["signals"] = {
                "runtime_launch_attempted": True,
                "runtime_stable": False,
                "crash": "observed",
                "exit_code": exit_code,
            }
            out["smoke_result"] = "early_exit"
    except Exception as exc:
        out["errors"].append(str(exc))
        out["signals"] = {"runtime_launch_attempted": True, "crash": "observed"}
        out["smoke_result"] = "launch_error"
    finally:
        if guard:
            restriction = guard.finalize()
            out["process_restriction"] = restriction
            signals = out.setdefault("signals", {})
            signals["suspicious_spawn_detected"] = bool(
                restriction.get("suspicious_spawn_detected")
            )
            if restriction.get("suspicious_spawn_detected"):
                out.setdefault("errors", []).append("suspicious_child_process_detected")
        elif proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
    if capture_screenshots:
        out["visual_observation"] = summarize_runtime_screenshots(out.get("runtime_screenshots") or [])
    return out


def observe_unity_windows_exe(
    path: Path,
    *,
    timeout: int = MAX_SMOKE_SECONDS,
    session_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Unity-aware wrapper around the generic Windows EXE smoke observation."""
    ctx = dict(session_ctx or {})
    ctx.setdefault("runtime_session_id", _runtime_session_id(ctx))
    launched_at = time.time()
    build = detect_unity_build_for_exe(path)
    out = smoke_test_windows_exe(
        path,
        timeout=timeout,
        capture_screenshots=True,
        enable_interaction_trace=True,
        session_ctx=ctx,
    )
    out["engine"] = "unity"
    out["unity_build"] = build

    logs = collect_unity_log_observation(path, since=launched_at)
    unity_observation = {
        "unity_build_detected": bool(build.get("detected")),
        "unity_build_confidence": build.get("confidence"),
        "player_log_found": bool(logs.get("player_log_found")),
        "selected_log_path": logs.get("selected_log_path", ""),
        "candidate_log_count": logs.get("candidate_log_count", 0),
        "unity_version_hint": logs.get("unity_version_hint", ""),
        "error_count": logs.get("error_count", 0),
        "exception_count": logs.get("exception_count", 0),
        "crash_signal_count": logs.get("crash_signal_count", 0),
        "scene_load_signal_count": len(logs.get("scene_load_signals") or []),
        "input_system_signal_count": len(logs.get("input_system_signals") or []),
        "crash_signals": logs.get("crash_signals", []),
        "error_signals": logs.get("error_signals", []),
        "scene_load_signals": logs.get("scene_load_signals", []),
        "input_system_signals": logs.get("input_system_signals", []),
        "candidate_logs": logs.get("candidate_logs", []),
        "visual_runtime_evidence": (out.get("visual_observation") or {}).get(
            "visual_runtime_evidence", "unavailable"
        ),
        "runtime_screenshot_count": (out.get("visual_observation") or {}).get(
            "runtime_screenshot_count", 0
        ),
        "black_screen_possible": (out.get("visual_observation") or {}).get(
            "black_screen_possible", False
        ),
        "visual_states_observed": (out.get("visual_observation") or {}).get(
            "visual_states_observed", []
        ),
        "visual_runtime_confidence": (out.get("visual_observation") or {}).get(
            "visual_runtime_confidence", 0.0
        ),
        "freeze_possible": (out.get("visual_observation") or {}).get(
            "freeze_possible", False
        ),
        "interaction_trace": out.get("interaction_trace"),
        "interaction_input_sent": (out.get("signals") or {}).get("interaction_input_sent"),
        "visual_response_to_input": (out.get("signals") or {}).get(
            "visual_response_to_input", "unknown"
        ),
        "runtime_session_id": ctx.get("runtime_session_id"),
        "authority_note_ar": (
            "Unity runtime observation records launch/log signals only; "
            "screenshots/logs لا تثبت gameplay correctness ولا تمنح Achieved تلقائياً."
        ),
    }
    out["unity_observation"] = unity_observation

    signals = out.setdefault("signals", {})
    signals["unity_build_detected"] = bool(build.get("detected"))
    signals["player_log_found"] = bool(logs.get("player_log_found"))
    signals["unity_version_hint"] = logs.get("unity_version_hint", "")
    signals["unity_log_error_count"] = logs.get("error_count", 0)
    signals["unity_log_crash_signal_count"] = logs.get("crash_signal_count", 0)
    signals["visual_runtime_evidence"] = (out.get("visual_observation") or {}).get(
        "visual_runtime_evidence", "unavailable"
    )
    signals["runtime_screenshot_count"] = (out.get("visual_observation") or {}).get(
        "runtime_screenshot_count", 0
    )
    signals["black_screen_possible"] = (out.get("visual_observation") or {}).get(
        "black_screen_possible", False
    )
    signals["unity_scene_load_hint"] = (
        "partial" if logs.get("scene_load_signals") else "unknown"
    )
    if logs.get("scene_load_signals") and signals.get("scene_loaded") in (None, "unknown"):
        signals["scene_loaded"] = "partial"
    if logs.get("crash_signal_count") and out.get("smoke_result") not in ("stable_window", "launch_ok"):
        signals["crash"] = "observed"
    trace = out.get("interaction_trace") or {}
    if trace:
        apply_interaction_signals(signals, trace)

    out["observation_summary_ar"] = (
        "تمت ملاحظة Unity build بشكل محكوم: launch/log/visual/interaction traces — "
        "ليست verification نهائية للعبة."
    )
    return out


def _pick_primary_artifacts(paths: List[Path]) -> Tuple[List[Path], List[Path], List[Path]]:
    apks, pcks, exes = [], [], []
    try:
        from app.runtime_engines.godot.export_runner import is_godot_editor_executable
    except Exception:
        is_godot_editor_executable = None  # type: ignore

    for p in paths:
        ext = p.suffix.lower()
        if ext in {".apk", ".aab"}:
            apks.append(p)
        elif ext == ".pck":
            pcks.append(p)
        elif ext == ".exe":
            if is_godot_editor_executable and is_godot_editor_executable(p):
                continue
            exes.append(p)
    apks.sort(key=lambda x: x.stat().st_size, reverse=True)
    pcks.sort(key=lambda x: x.stat().st_size, reverse=True)
    exes = [e for e in exes if "console" not in e.name.lower()]
    exes.sort(key=lambda x: x.stat().st_size, reverse=True)
    return apks[:MAX_ARTIFACTS], pcks[:MAX_ARTIFACTS], exes[:2]


def build_runtime_signal_graph(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge per-artifact signals into governed signal graph."""
    merged: Dict[str, Any] = {k: "unknown" for k in RUNTIME_SIGNAL_SCHEMA}
    any_valid_apk = any(
        a.get("type") == "apk" and a.get("valid") for a in analyses
    )
    any_valid_pck = any(
        a.get("type") == "pck" and a.get("valid") for a in analyses
    )
    smoke_ok = any(
        a.get("smoke_result") in ("stable_window", "launch_ok") for a in analyses if a.get("type") == "exe"
    )
    launch_partial = any(
        a.get("smoke_result") == "launch_ok" for a in analyses if a.get("type") == "exe"
    )
    crash = any(
        (a.get("signals") or {}).get("crash") == "observed"
        and a.get("smoke_result") not in ("stable_window", "launch_ok")
        for a in analyses
    )

    exe_scene_hint = any(
        (a.get("signals") or {}).get("scene_loaded") in ("yes", "partial")
        or (a.get("signals") or {}).get("unity_scene_load_hint") == "partial"
        for a in analyses
        if a.get("type") == "exe"
    )
    player_moved = any(
        (a.get("signals") or {}).get("player_moved") == "detected"
        for a in analyses
    )
    interaction_input = any(
        (a.get("signals") or {}).get("interaction_input_sent") == "yes"
        for a in analyses
    )
    visual_input_response = any(
        (a.get("signals") or {}).get("visual_response_to_input") == "partial"
        for a in analyses
    )

    merged["scene_loaded"] = (
        "yes" if any_valid_pck else ("partial" if (smoke_ok or any_valid_apk or exe_scene_hint) else "no")
    )
    merged["player_moved"] = "detected" if player_moved else "unknown"
    merged["score_changed"] = "unknown"
    merged["collision_events"] = "unknown"
    merged["level_transition"] = "partial" if any_valid_pck else "unknown"
    merged["crash"] = "observed" if crash and not smoke_ok else "none"
    merged["interaction_input_sent"] = "yes" if interaction_input else "no"
    merged["visual_response_to_input"] = (
        "partial" if visual_input_response else ("unknown" if interaction_input else "none")
    )
    merged["automated_interaction_observed"] = "yes" if interaction_input else "no"

    return {
        "contract_id": CONTRACT_ID,
        "mode": OBSERVATION_MODE,
        "signals": merged,
        "artifact_analyses": analyses,
        "engine_observations": [
            {
                "engine": a.get("engine"),
                "artifact": a.get("artifact"),
                "unity_observation": a.get("unity_observation"),
                "visual_observation": a.get("visual_observation"),
            }
            for a in analyses
            if a.get("engine") or a.get("unity_observation")
        ],
        "observation_summary_ar": (
            "runtime observations collected under controlled conditions — "
            "لا تُعد verification مؤسسية ولا تثبت gameplay."
        ),
    }


def observe_runtime_artifacts(
    submission_paths: Optional[List[str]] = None,
    *,
    enable_smoke_test: bool = True,
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    student_name: str = "",
    grading_mode: str | None = None,
) -> Dict[str, Any]:
    """
    Run L4 observation sandbox on executable artifacts in submission paths.
    """
    paths = [Path(p) for p in (submission_paths or []) if p]
    files = [p for p in paths if p.is_file()]
    apks, pcks, exes = _pick_primary_artifacts(files)

    if not apks and not pcks and not exes:
        return {
            "status": "no_artifacts",
            "contract_id": CONTRACT_ID,
            "observation_summary_ar": "لا ملفات .exe/.apk/.pck للملاحظة.",
            "runtime_signal_graph": None,
        }

    session_ctx = {
        "runtime_session_id": f"ros_{uuid.uuid4().hex[:12]}",
        "submission_id": submission_id,
        "batch_id": batch_id,
        "student_name": student_name,
        "submission_paths": [str(p) for p in paths],
    }
    submission_root = paths[0].parent if paths and paths[0].is_file() else (paths[0] if paths else None)
    if submission_root is not None:
        session_ctx["submission_root"] = str(submission_root)

    analyses: List[Dict[str, Any]] = []
    smoke_timeout = resolve_smoke_timeout_seconds(grading_mode)
    for apk in apks:
        analyses.append(analyze_apk(apk))
    for pck in pcks:
        analyses.append(analyze_godot_pck(pck))
    if enable_smoke_test and exes:
        # Prefer main game exe (largest non-console)
        primary_exe = exes[0]
        if detect_unity_build_for_exe(primary_exe).get("detected"):
            analyses.append(
                observe_unity_windows_exe(
                    primary_exe,
                    timeout=smoke_timeout,
                    session_ctx=session_ctx,
                )
            )
        else:
            analyses.append(
                smoke_test_windows_exe(
                    primary_exe,
                    timeout=smoke_timeout,
                    capture_screenshots=True,
                    enable_interaction_trace=True,
                    session_ctx=session_ctx,
                    grading_mode=grading_mode,
                )
            )

    graph = build_runtime_signal_graph(analyses)
    telemetry_graph = merge_analyses_to_telemetry_graph(
        analyses,
        contract_id=CONTRACT_ID,
        observation_mode=OBSERVATION_MODE,
    )
    any_valid = any(a.get("valid") for a in analyses if a.get("type") in ("apk", "pck"))
    smoke_ok = any(
        a.get("smoke_result") in ("stable_window", "launch_ok") for a in analyses
    )
    unity_runtime_observed = any(
        a.get("engine") == "unity"
        and a.get("smoke_result") in ("stable_window", "launch_ok")
        for a in analyses
    )
    launch_partial = any(
        a.get("smoke_result") == "launch_ok" for a in analyses if a.get("type") == "exe"
    )
    crash = any(
        (a.get("signals") or {}).get("crash") == "observed"
        and a.get("smoke_result") not in ("stable_window", "launch_ok")
        for a in analyses
    )
    static_strong = any_valid and sum(
        1 for a in analyses if a.get("valid") and a.get("type") in ("apk", "pck")
    ) >= 2
    crash_only = crash and not smoke_ok and not static_strong

    runtime_observed = smoke_ok or (static_strong and not crash_only) or (
        any_valid and launch_partial
    )
    runtime_verified = False if unity_runtime_observed else (
        smoke_ok
        or (static_strong and not crash_only)
        or (any_valid and launch_partial)
    )
    level = 4 if (smoke_ok or (any_valid and len(analyses) >= 2)) else (3 if any_valid else 1)

    gv_levels = [
        str((a.get("gameplay_verification") or {}).get("l4_level") or "")
        for a in analyses
        if isinstance(a.get("gameplay_verification"), dict)
    ]
    l4_automated = any(level in ("L4_full", "L4_partial") for level in gv_levels)

    result = {
        "status": "completed",
        "contract_id": CONTRACT_ID,
        "observation_mode": OBSERVATION_MODE,
        "runtime_observed": runtime_observed,
        "runtime_verified": runtime_verified,
        "runtime_observation": "completed",
        "runtime_evidence_level": level,
        "runtime_signal_graph": graph,
        "runtime_telemetry_graph": telemetry_graph,
        "artifact_analyses": analyses,
        "unity_observation_summary": [
            a.get("unity_observation")
            for a in analyses
            if a.get("unity_observation")
        ],
        "visual_observation_summary": [
            a.get("visual_observation")
            for a in analyses
            if a.get("visual_observation")
        ],
        "runtime_screenshots": [
            shot
            for a in analyses
            for shot in (a.get("runtime_screenshots") or [])
            if isinstance(shot, dict)
        ],
        "interaction_trace_summary": [
            a.get("interaction_trace")
            for a in analyses
            if isinstance(a.get("interaction_trace"), dict)
        ],
        "gameplay_verification": next(
            (a.get("gameplay_verification") for a in analyses if isinstance(a.get("gameplay_verification"), dict)),
            None,
        ),
        "runtime_session_id": session_ctx.get("runtime_session_id"),
        "runtime_session_context": session_ctx,
        "observation_summary_ar": graph.get("observation_summary_ar"),
        "human_authority_required": not l4_automated,
        "language_note_ar": (
            "ملاحظات runtime: L4 آلي يثبت gameplay بدون مراجعة بشرية عند نجاح MenuNavigator+Movement."
            if l4_automated
            else (
                "ملاحظات runtime استشارية/تشغيلية — runtime observation remains advisory "
                "until automated L4 or human review."
            )
        ),
    }
    try:
        from app.mechanics_verifier import verify_mechanics

        result["mechanics_verification"] = verify_mechanics(
            result,
            inventory={"gameplay_verification": result.get("gameplay_verification")},
        )
    except Exception:
        pass
    return result


def format_observation_for_grading(observation: Dict[str, Any]) -> str:
    """Inject into AI / adjudication context."""
    if observation.get("status") != "completed":
        return ""
    lines = [
        "=== RUNTIME OBSERVATION SANDBOX (L4 — controlled) ===",
        observation.get("observation_summary_ar", ""),
        f"runtime_observed: {observation.get('runtime_observed')}",
        f"runtime_verified (smoke/structure): {observation.get('runtime_verified')}",
        f"runtime_evidence_level: L{observation.get('runtime_evidence_level', 0)}",
    ]
    sig = (observation.get("runtime_signal_graph") or {}).get("signals") or {}
    for k, v in sig.items():
        lines.append(f"  signal {k}: {v}")
    for a in observation.get("artifact_analyses") or []:
        lines.append(
            f"  - {a.get('type')} {a.get('artifact')}: valid={a.get('valid')} "
            f"smoke={a.get('smoke_result', 'n/a')}"
        )
        if a.get("engine") == "unity":
            u = a.get("unity_observation") or {}
            restriction = a.get("process_restriction") or {}
            lines.append(
                "    Unity observation: "
                f"build={u.get('unity_build_detected')} "
                f"player_log={u.get('player_log_found')} "
                f"version={u.get('unity_version_hint') or 'unknown'} "
                f"errors={u.get('error_count', 0)} crashes={u.get('crash_signal_count', 0)} "
                f"screenshots={u.get('runtime_screenshot_count', 0)} "
                f"black_screen_possible={u.get('black_screen_possible', False)}"
            )
            if restriction:
                lines.append(
                    "    Process restriction: "
                    f"suspicious_spawn={restriction.get('suspicious_spawn_detected')} "
                    f"max_process_count={restriction.get('max_process_count', 0)}"
                )
            visual = a.get("visual_observation") or {}
            lines.append(
                f"    visual confidence={visual.get('visual_runtime_confidence', 0)} "
                f"states={visual.get('visual_states_observed', [])} "
                f"freeze_possible={visual.get('freeze_possible', False)}"
            )
            for shot in visual.get("runtime_screenshots") or []:
                if shot.get("status") == "captured":
                    lines.append(
                        f"    visual evidence {shot.get('label')}: {shot.get('path')} "
                        f"state={shot.get('visual_state', 'unknown')} "
                        "(advisory only)"
                    )
            trace = a.get("interaction_trace") or {}
            if trace:
                lines.append(
                    "    Interaction trace (L5 advisory): "
                    f"status={trace.get('status')} "
                    f"inputs={trace.get('input_count', 0)} "
                    f"visual_response={trace.get('visual_response_to_input')} "
                    f"delta={trace.get('visual_delta_score')} "
                    "— does NOT verify gameplay"
                )
    lines.append(
        "⛔ presence/launch/logs/screenshots ≠ achievement — استخدم هذه الملاحظات لـ C.P5/C.P6 مع مراجعة بشرية."
    )
    lines.append(
        "⛔ runtime screenshots prove only a captured visual surface/output; they do not prove mechanics, scoring, physics, win/loss, or user experience."
    )
    return "\n".join(lines)
