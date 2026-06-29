"""Godot headless export runner — preset discovery, multi-preset retry, static fallback."""
from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.runtime.process_watchdog import run_with_watchdog

# Official Godot editor bundles shipped inside student zips — not the student's game build.
_GODOT_EDITOR_EXE_RE = re.compile(
    r"^godot_v\d+[\w.\-]*\.exe$|^godot\.exe$|^godot4\.exe$|^godot\.windows\.",
    re.IGNORECASE,
)
_GODOT_EDITOR_PATH_HINTS = (
    "أدوات التصدير",
    "export templates",
    "godot_v4.",
    "godot_v3.",
    "/tools/",
    "\\tools\\",
    "editor_data",
)


def is_godot_editor_executable(path: Path) -> bool:
    """True for Godot Engine editor binaries, not student export wrappers."""
    if path.suffix.lower() not in {".exe", ".x86_64"}:
        return False
    name = path.name.lower()
    if "console" in name:
        return True
    if _GODOT_EDITOR_EXE_RE.match(name):
        return True
    lower = str(path).lower()
    if "godot" in name and any(hint in lower for hint in _GODOT_EDITOR_PATH_HINTS):
        return True
    try:
        if path.stat().st_size > 95_000_000 and "godot" in name:
            return True
    except OSError:
        pass
    return False


def _score_godot_runnable(path: Path, project_root: Optional[Path]) -> int:
    """Higher score = more likely a student game build (not the editor)."""
    if not path.is_file():
        return -10_000
    ext = path.suffix.lower()
    if ext not in {".exe", ".x86_64", ".pck"}:
        return -10_000
    if ext in {".exe", ".x86_64"} and is_godot_editor_executable(path):
        return -10_000

    score = 0
    lower = str(path).lower()
    if project_root:
        try:
            path.resolve().relative_to(project_root.resolve())
            score += 40
        except ValueError:
            pass
    if any(tok in lower for tok in ("تشغيل", "ملفات تشغيل", "run", "build", "export", "release", "dist")):
        score += 35
    # Prefer final / improved builds over prototype / first draft (BTEC v1 vs v2 folders)
    _final_hints = (
        "final", "نهائي", "النهائية", "improved", "محسن", "polish", "release",
        "v2", "_v2", "ver2", "نسخة2",
    )
    _early_hints = (
        "first", "farst", "prototype", "draft", "initial", "اول", "أول",
        "v1", "_v1", "ver1", "نسخة1", "proto",
    )
    if any(h in lower for h in _final_hints):
        score += 45
    if any(h in lower for h in _early_hints):
        score -= 25
    if ext == ".pck":
        score += 25
        paired = path.with_suffix(".exe")
        if paired.is_file() and not is_godot_editor_executable(paired):
            score += 60
    if ext in {".exe", ".x86_64"}:
        paired = path.with_suffix(".pck")
        if paired.is_file():
            score += 60
        name = path.name.lower()
        if name not in ("godot.exe", "godot4.exe") and "godot_v" not in name:
            score += 25
        try:
            size = path.stat().st_size
            if 500_000 < size < 85_000_000:
                score += 15
        except OSError:
            pass
    return score


def find_godot_runnable_artifacts(root: Path) -> Dict[str, Optional[Path]]:
    """Best student game .exe / .pck under a submission tree."""
    project_root = find_godot_project_root(root)
    search = root if root.is_dir() else root.parent
    if not search.is_dir():
        return {"project_root": project_root, "executable": None, "pck": None}

    best_exe: Optional[Path] = None
    best_pck: Optional[Path] = None
    best_exe_score = -10_000
    best_pck_score = -10_000

    for fp in search.rglob("*"):
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        if ext in {".exe", ".x86_64"}:
            sc = _score_godot_runnable(fp, project_root)
            if sc > best_exe_score:
                best_exe_score = sc
                best_exe = fp
        elif ext == ".pck":
            sc = _score_godot_runnable(fp, project_root)
            if sc > best_pck_score:
                best_pck_score = sc
                best_pck = fp

    if best_pck is not None:
        paired = best_pck.with_suffix(".exe")
        if paired.is_file() and not is_godot_editor_executable(paired):
            if best_exe is None or _score_godot_runnable(paired, project_root) >= best_exe_score:
                best_exe = paired
                best_exe_score = _score_godot_runnable(paired, project_root)

    return {"project_root": project_root, "executable": best_exe, "pck": best_pck}


def _pick_donor_exe(
    pck: Path,
    *,
    donor: Optional[Path] = None,
    search_root: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Optional[Path]:
    """Nearest compatible .exe when pck has no matching stem."""
    if donor and donor.is_file() and not is_godot_editor_executable(donor):
        return donor
    search = pck.parent if pck.is_file() else (search_root or Path("."))
    candidates: List[Tuple[int, Path]] = []
    if search.is_dir():
        for fp in search.glob("*.exe"):
            if fp.is_file() and not is_godot_editor_executable(fp) and "console" not in fp.name.lower():
                candidates.append((_score_godot_runnable(fp, project_root), fp))
    if search_root and search_root.is_dir():
        for fp in search_root.rglob("*.exe"):
            if fp.is_file() and not is_godot_editor_executable(fp) and "console" not in fp.name.lower():
                sc = _score_godot_runnable(fp, project_root)
                if sc > -1000:
                    candidates.append((sc, fp))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def resolve_pck_exe_pairing(
    root: Path,
    *,
    pck: Optional[Path] = None,
    donor_exe: Optional[Path] = None,
    session_id: str = "",
) -> Dict[str, Any]:
    """
    Godot export pairing: when final.pck exists without final.exe, copy donor exe into
    a temp folder renamed to match the pck stem so the wrapper loads the right pack.
    """
    layout = find_godot_runnable_artifacts(root)
    pck_path = pck or layout.get("pck")
    donor = donor_exe or layout.get("executable")
    meta: Dict[str, Any] = {
        "paired": False,
        "native_pair": False,
        "pck": str(pck_path) if pck_path else None,
        "donor_exe": str(donor) if donor else None,
    }
    empty: Dict[str, Any] = {
        "paired_executable": donor,
        "run_cwd": donor.parent if donor else None,
        "pck": pck_path,
        "needs_cleanup": False,
        "pairing_meta": meta,
    }
    if not pck_path or not pck_path.is_file():
        return empty

    target_exe = pck_path.with_suffix(".exe")
    if target_exe.is_file() and not is_godot_editor_executable(target_exe):
        meta["native_pair"] = True
        meta["paired"] = True
        meta["paired_executable"] = str(target_exe)
        return {
            "paired_executable": target_exe,
            "run_cwd": pck_path.parent,
            "pck": pck_path,
            "needs_cleanup": False,
            "pairing_meta": meta,
        }

    picked = _pick_donor_exe(
        pck_path,
        donor=donor,
        search_root=root if root.is_dir() else root.parent,
        project_root=layout.get("project_root"),
    )
    if not picked:
        meta["error"] = "no_donor_exe_for_pck"
        return empty

    sid = session_id or uuid.uuid4().hex[:12]
    safe_key = re.sub(r"[^\w\-]+", "_", root.name)[:48] or "submission"
    temp_root = (
        Path("uploads") / "runtime_sessions" / "pck_pairing" / safe_key / sid
    )
    temp_root.mkdir(parents=True, exist_ok=True)
    paired_exe = temp_root / target_exe.name
    paired_pck = temp_root / pck_path.name
    shutil.copy2(picked, paired_exe)
    if pck_path.resolve() != paired_pck.resolve():
        shutil.copy2(pck_path, paired_pck)

    meta.update(
        {
            "paired": True,
            "temp_dir": str(temp_root.resolve()),
            "paired_executable": str(paired_exe),
            "paired_pck": str(paired_pck),
            "donor_exe": str(picked),
            "target_pck_stem": pck_path.stem,
        }
    )
    return {
        "paired_executable": paired_exe,
        "run_cwd": temp_root,
        "pck": paired_pck,
        "needs_cleanup": True,
        "pairing_meta": meta,
    }


def cleanup_pck_pairing(pairing_meta: Optional[Dict[str, Any]]) -> None:
    if not pairing_meta or not pairing_meta.get("temp_dir"):
        return
    try:
        shutil.rmtree(str(pairing_meta["temp_dir"]), ignore_errors=True)
    except Exception:
        pass


def build_godot_smoke_observation(
    smoke: Dict[str, Any],
    *,
    pairing_meta: Optional[Dict[str, Any]] = None,
    pck_smoke: Optional[Dict[str, Any]] = None,
    pck_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Normalize exe smoke into orchestrator-compatible observation dict."""
    from app.runtime_evidence_promotion import assess_runtime_evidence_promotion

    stable = smoke.get("smoke_result") in ("stable_window", "launch_ok")
    shots = smoke.get("runtime_screenshots") or []
    promotion = assess_runtime_evidence_promotion(
        {
            "runtime_observed": bool(smoke.get("attempted") and stable),
            "runtime_screenshots": shots,
            "legacy_observation": smoke,
            "platform_analyses": [{"signals": {"legacy_observation": smoke}}],
        }
    )
    status = "completed" if stable else ("partial" if smoke.get("attempted") else "failed")
    summary_ar = promotion.get("summary_ar") or (
        "تشغيل Godot export — ملاحظة L4 (ليست verification مؤسسية)"
        if stable
        else "لم يُثبت تشغيل مستقر"
    )
    obs: Dict[str, Any] = {
        "status": status,
        "observation_mode": "godot_pck_pairing_smoke",
        "runtime_observed": bool(smoke.get("attempted")),
        "runtime_verified": bool(promotion.get("partial_runtime_verified")),
        "partial_runtime_verified": bool(promotion.get("partial_runtime_verified")),
        "runtime_screenshots": shots,
        "runtime_evidence_promotion": promotion,
        "observation_summary_ar": summary_ar,
        "smoke_result": smoke.get("smoke_result"),
        "artifact_analyses": [smoke] if smoke.get("attempted") else [],
        "pck_pairing": pairing_meta or {},
        "crash_detected": (smoke.get("signals") or {}).get("crash") == "observed",
    }
    if pck_path:
        obs["target_pck"] = str(pck_path)
    if pck_smoke:
        obs["pck_smoke"] = pck_smoke
        state_val = pck_smoke.get("state_validation")
        if isinstance(state_val, dict):
            obs["godot_state_validation"] = state_val
        if pck_smoke.get("success"):
            obs["runtime_observed"] = True
    if smoke.get("visual_observation"):
        obs["visual_observation"] = smoke["visual_observation"]
    return obs


def resolve_godot_binary() -> Optional[Path]:
    env = os.environ.get("AI_GRADER_GODOT_BIN") or os.environ.get("GODOT_BIN")
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    for name in ("godot", "godot4", "Godot_v4.exe", "Godot.exe"):
        try:
            proc = subprocess.run(
                ["where" if os.name == "nt" else "which", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                line = (proc.stdout or "").strip().splitlines()[0]
                if line and Path(line).is_file():
                    return Path(line)
        except Exception:
            continue
    return None


def find_godot_project_root(root: Path) -> Optional[Path]:
    if root.is_file() and root.name.lower() == "project.godot":
        return root.parent
    if root.is_dir():
        direct = root / "project.godot"
        if direct.is_file():
            return root
        for candidate in root.rglob("project.godot"):
            if ".godot" in candidate.parts:
                continue
            return candidate.parent
    return None


def find_godot_executable(root: Path) -> Optional[Path]:
    """Student game .exe (never the Godot editor bundle)."""
    layout = find_godot_runnable_artifacts(root)
    return layout.get("executable")


def find_godot_pck_pack(root: Path) -> Optional[Path]:
    layout = find_godot_runnable_artifacts(root)
    return layout.get("pck")


def run_godot_main_pack_smoke(
    pck_path: Path,
    *,
    godot_bin: Optional[Path] = None,
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    """Launch exported .pck with the system Godot binary (--main-pack)."""
    binary = godot_bin or resolve_godot_binary()
    if not binary or not binary.is_file():
        return {
            "success": False,
            "error": "godot_binary_not_configured",
            "hint": "Set AI_GRADER_GODOT_BIN to your Godot 4 editor executable path",
        }
    pck = pck_path.resolve()
    if not pck.is_file():
        return {"success": False, "error": "pck_missing"}

    cmd = [
        str(binary.resolve()),
        "--main-pack",
        str(pck),
        "--resolution",
        "1280x720",
    ]
    result = run_with_watchdog(
        cmd,
        timeout_seconds=timeout_seconds,
        cwd=str(pck.parent),
    )
    success = bool(result.get("success")) and int(result.get("exit_code") or 1) == 0
    stderr_tail = str(result.get("stderr_tail") or "")
    stdout_tail = str(result.get("stdout_tail") or "")
    log_blob = f"{stderr_tail}\n{stdout_tail}"
    log_errors = len(re.findall(r"\b(ERROR|FATAL|SCRIPT ERROR|Failed)\b", log_blob, re.I))
    state_validation = {
        "launch_ok": bool(result.get("success")),
        "exit_ok": int(result.get("exit_code") or 1) == 0,
        "log_error_count": log_errors,
        "state_ok": success and log_errors == 0,
        "method": "godot_pck_state_validation_v1",
    }
    return {
        "success": success and state_validation["state_ok"],
        "method": "godot_main_pack_smoke",
        "command": cmd,
        "exit_code": result.get("exit_code"),
        "stderr_tail": stderr_tail[-500:] if stderr_tail else "",
        "stdout_tail": stdout_tail[-500:] if stdout_tail else "",
        "pck": str(pck),
        "godot_binary": str(binary),
        "state_validation": state_validation,
    }


def _strip_ini_value(value: str) -> str:
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _parse_export_presets(project_root: Path) -> List[Dict[str, str]]:
    cfg_path = project_root / "export_presets.cfg"
    if not cfg_path.is_file():
        return []

    parser = configparser.ConfigParser()
    try:
        parser.read(cfg_path, encoding="utf-8")
    except configparser.Error:
        return []

    presets: List[Dict[str, str]] = []
    for section in parser.sections():
        if not section.startswith("preset."):
            continue
        name = _strip_ini_value(parser.get(section, "name", fallback=""))
        platform = _strip_ini_value(parser.get(section, "platform", fallback=""))
        export_path = _strip_ini_value(parser.get(section, "export_path", fallback=""))
        if name:
            presets.append({"name": name, "platform": platform, "export_path": export_path})
    return presets


def _preferred_export_presets(presets: List[Dict[str, str]]) -> List[str]:
    """Order presets: Windows Desktop first, then other desktop, then Web."""
    if not presets:
        return ["Windows Desktop"]

    def rank(preset: Dict[str, str]) -> Tuple[int, str]:
        platform = (preset.get("platform") or "").lower()
        name = (preset.get("name") or "").lower()
        if "windows" in platform or "windows" in name:
            return (0, name)
        if any(k in platform for k in ("linux", "macos", "mac")):
            return (1, name)
        if "web" in platform or "web" in name:
            return (3, name)
        return (2, name)

    ordered = sorted(presets, key=rank)
    return [p["name"] for p in ordered if p.get("name")]


def _read_project_godot_metadata(project_root: Path) -> Dict[str, Any]:
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        return {"ok": False, "error": "project_godot_missing"}

    try:
        text = project_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    name_match = re.search(r'config/name\s*=\s*"([^"]+)"', text)
    main_scene = re.search(r'run/main_scene\s*=\s*"([^"]+)"', text)
    return {
        "ok": True,
        "project_name": name_match.group(1) if name_match else project_root.name,
        "main_scene": main_scene.group(1) if main_scene else None,
        "has_main_scene": bool(main_scene),
    }


def validate_godot_scenes(project_root: Path) -> Dict[str, Any]:
    """Scene validation for corrupted/partial Godot projects."""
    main_scene = _read_project_godot_metadata(project_root).get("main_scene")
    tscn_files = [
        str(fp.relative_to(project_root))
        for fp in project_root.rglob("*.tscn")
        if fp.is_file() and not any(p.startswith(".") for p in fp.parts)
    ][:40]
    main_present = bool(main_scene and (project_root / main_scene.replace("res://", "")).is_file())
    return {
        "scene_count": len(tscn_files),
        "main_scene": main_scene,
        "main_scene_present": main_present,
        "validation_passed": bool(tscn_files) and (main_present or len(tscn_files) >= 1),
        "sample_scenes": tscn_files[:8],
    }


def ensure_default_export_preset(project_root: Path) -> Dict[str, Any]:
    """Bootstrap minimal export preset when missing."""
    cfg_path = project_root / "export_presets.cfg"
    if cfg_path.is_file():
        return {"created": False, "path": str(cfg_path)}
    content = (
        '[preset.0]\nname="Windows Desktop"\nplatform="Windows Desktop"\n'
        'runnable=true\nexport_filter="all_resources"\nexport_path="build/game.exe"\n'
    )
    try:
        cfg_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"created": False, "error": str(exc)}
    return {"created": True, "path": str(cfg_path)}


def analyze_godot_project(project_root: Path) -> Dict[str, Any]:
    """Static project analysis when export/runtime is unavailable."""
    metadata = _read_project_godot_metadata(project_root)
    presets = _parse_export_presets(project_root)
    scene_validation = validate_godot_scenes(project_root)

    gd_files: List[str] = []
    tscn_files: List[str] = []
    for fp in project_root.rglob("*"):
        if not fp.is_file() or any(part.startswith(".") for part in fp.parts):
            continue
        if fp.suffix.lower() == ".gd" and len(gd_files) < 20:
            gd_files.append(str(fp.relative_to(project_root)))
        elif fp.suffix.lower() == ".tscn" and len(tscn_files) < 20:
            tscn_files.append(str(fp.relative_to(project_root)))

    godot_bin = resolve_godot_binary()
    result: Dict[str, Any] = {
        "mode": "godot_static_analysis",
        "metadata": metadata,
        "export_presets": presets,
        "godot_binary_configured": bool(godot_bin),
        "godot_binary_path": str(godot_bin) if godot_bin else None,
        "script_count": len(gd_files),
        "scene_count": len(tscn_files),
        "sample_scripts": gd_files[:8],
        "sample_scenes": tscn_files[:8],
        "scene_validation": scene_validation,
        "runnable_build_present": bool(
            find_godot_executable(project_root) or find_godot_pck_pack(project_root)
        ),
    }
    result["completeness_hint"] = _completeness_score(result)
    return result


def _completeness_score(analysis: Dict[str, Any]) -> float:
    score = 0.30
    meta = analysis.get("metadata") or {}
    if meta.get("ok"):
        score += 0.20
    if meta.get("has_main_scene"):
        score += 0.10
    if analysis.get("script_count", 0) >= 1:
        score += 0.10
    if analysis.get("scene_count", 0) >= 1:
        score += 0.10
    if analysis.get("export_presets"):
        score += 0.10
    if analysis.get("runnable_build_present"):
        score += 0.20
    elif analysis.get("godot_binary_configured"):
        score += 0.10
    return min(1.0, score)


def run_godot_export(
    project_root: Path,
    *,
    godot_bin: Optional[Path] = None,
    export_preset: Optional[str] = None,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Attempt headless Godot export — tries configured presets in priority order."""
    project_file = project_root / "project.godot"
    if not project_file.is_file():
        return {"success": False, "error": "project_godot_missing"}

    binary = godot_bin or resolve_godot_binary()
    if not binary:
        return {
            "success": False,
            "error": "godot_binary_not_configured",
            "hint": "Set AI_GRADER_GODOT_BIN to Godot executable path",
            "static_analysis": analyze_godot_project(project_root),
        }

    presets = _parse_export_presets(project_root)
    if not presets:
        ensure_default_export_preset(project_root)
        presets = _parse_export_presets(project_root)
    preset_names = [export_preset] if export_preset else _preferred_export_presets(presets)
    preset_names = [p for p in preset_names if p]

    output_dir = project_root / "build"
    output_dir.mkdir(parents=True, exist_ok=True)
    attempts: List[Dict[str, Any]] = []

    for preset_name in preset_names:
        preset_cfg = next((p for p in presets if p.get("name") == preset_name), None)
        if preset_cfg and preset_cfg.get("export_path"):
            output_exe = project_root / preset_cfg["export_path"]
        else:
            safe = re.sub(r"[^\w\-]+", "_", preset_name).strip("_") or "game"
            output_exe = output_dir / f"{safe}.exe"

        output_exe.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(binary),
            "--headless",
            "--path",
            str(project_root),
            "--export-release",
            preset_name,
            str(output_exe),
        ]
        attempt: Dict[str, Any] = {
            "preset": preset_name,
            "command": cmd,
            "output": str(output_exe),
        }
        result = run_with_watchdog(cmd, timeout_seconds=timeout_seconds, cwd=str(project_root))
        attempt["exit_code"] = result.get("exit_code")
        attempt["stderr_tail"] = result.get("stderr_tail")
        attempt["stdout_tail"] = result.get("stdout_tail")
        attempt["success"] = bool(result.get("success")) and output_exe.is_file()
        if output_exe.is_file():
            attempt["artifact"] = str(output_exe)
        if result.get("error"):
            attempt["error"] = result.get("error")
            if result.get("watchdog_kill"):
                attempt["watchdog_kill"] = result.get("watchdog_kill")

        attempts.append(attempt)
        if attempt.get("success"):
            return {
                "success": True,
                "exit_code": attempt.get("exit_code"),
                "artifact": attempt.get("artifact"),
                "preset_used": preset_name,
                "attempts": attempts,
                "method": "godot_headless_export",
            }

    last = attempts[-1] if attempts else {}
    return {
        "success": False,
        "error": last.get("error") or "godot_export_failed",
        "exit_code": last.get("exit_code"),
        "stderr_tail": last.get("stderr_tail"),
        "stdout_tail": last.get("stdout_tail"),
        "attempts": attempts,
        "presets_tried": preset_names,
        "hint": _export_failure_hint(last, presets),
        "static_analysis": analyze_godot_project(project_root),
        "method": "godot_headless_export",
    }


def _export_failure_hint(last_attempt: Dict[str, Any], presets: List[Dict[str, str]]) -> str:
    stderr = (last_attempt.get("stderr_tail") or "").lower()
    if "no export template" in stderr or "export template" in stderr:
        return "Install Godot export templates for the target platform"
    if not presets:
        return "Add export_presets.cfg with a Windows Desktop preset in the Godot editor"
    if "invalid export preset" in stderr or "preset" in stderr:
        return "Verify export preset names match export_presets.cfg exactly"
    return "Check Godot export logs; ensure project opens headless without errors"
