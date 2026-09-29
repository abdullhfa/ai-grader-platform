"""
Game grading verification policy (runtime first, code second, temp builds cleaned).

Policy implemented here (requested by the grading lead):

  A) Submission ships a runnable .exe
       -> run the game, verify every required mechanic (movement, jump, ...).
       -> any requirement the runtime could not confirm is re-checked in the
          student's SOURCE CODE (file:line evidence).

  B) Submission has NO .exe (source-only project)
       -> build a temporary .exe in an isolated temp workspace
          (GameMaker / Godot / Unity — the student's folder is never modified),
       -> run + verify exactly like (A), then code fallback for failures,
       -> ALWAYS delete the temporary build when finished (even on errors).

Assessment safety:
  * Runtime-verified  = observed in the running game (highest authority).
  * Code-verified     = implemented in code but NOT observed at runtime —
                        flagged `teacher_confirmation_required`.
  * Not verified      = neither runtime nor code evidence — never invented.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

POLICY_VERSION = "game_verification_policy_v1"

REQUIREMENT_LABELS_AR: Dict[str, str] = {
    "menu_navigation": "الدخول من القائمة إلى اللعب",
    "player_movement": "حركة اللاعب",
    "player_jump": "القفز",
    "score_system": "نظام النقاط",
    "win_lose_condition": "شرط الفوز/الخسارة",
    "collect_items": "جمع العناصر",
    "enemy_interaction": "تفاعل العدو",
    "timer_system": "المؤقت",
    "lives_system": "الأرواح/الصحة",
}

# runtime requirement id -> source-code mechanic ids (any match proves it)
REQUIREMENT_CODE_MAP: Dict[str, Sequence[str]] = {
    "menu_navigation": ("menu_ui",),
    "player_movement": ("player_movement",),
    "player_jump": ("player_jump",),
    "score_system": ("score_system",),
    "win_lose_condition": ("win_condition", "lose_condition"),
    "collect_items": ("collect_items",),
    "enemy_interaction": ("enemy_interaction",),
    "timer_system": ("timer_system",),
    "lives_system": ("lives_system", "health_system"),
}

DEFAULT_REQUIRED = ("player_movement", "player_jump", "score_system", "win_lose_condition")

# Flags written by the automated L4 verifier -> requirement id
_RUNTIME_FLAG_MAP = {
    "player_movement_verified": "player_movement",
    "jump_detected": "player_jump",
    "score_change_detected": "score_system",
}

_COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".godot", ".import", "Library", "Temp", "Logs", "obj", "build",
    "Builds", "__pycache__", "*.exe", "*.pck",
)


# =============================================================== reconciliation
def _runtime_results(gv: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Requirement results that were really observed while playing."""
    gv = gv if isinstance(gv, dict) else {}
    out: Dict[str, Dict[str, Any]] = {}
    entered = gv.get("gameplay_entered") is True
    package = gv.get("evidence_package") or {}
    rows = list(package.get("results") or [])
    rows += list((gv.get("movement_verification") or {}).get("requirement_results") or [])
    for row in rows:
        if not isinstance(row, dict) or not row.get("req_id"):
            continue
        rid = str(row["req_id"])
        verified = bool(row.get("verified")) and (entered or rid == "menu_navigation")
        prev = out.get(rid)
        if prev is None or (verified and not prev["verified"]):
            out[rid] = {
                "verified": verified,
                "reason": str(row.get("reason") or ""),
                "detail": str(row.get("detail") or ""),
                "confidence": float(row.get("confidence") or 0.0),
            }
    if entered:
        for flag, rid in _RUNTIME_FLAG_MAP.items():
            if gv.get(flag) is True:
                out.setdefault(rid, {"verified": True, "reason": flag, "detail": "", "confidence": 0.7})
                out[rid]["verified"] = True
        out.setdefault("menu_navigation", {"verified": True, "reason": "gameplay_entered", "detail": "", "confidence": 0.8})
    return out


def reconcile_game_requirements(
    gameplay_verification: Optional[Dict[str, Any]],
    source_mechanics: Optional[Dict[str, Any]],
    *,
    required_ids: Optional[Sequence[str]] = None,
    runtime_attempted: bool = True,
) -> Dict[str, Any]:
    """Runtime first; code check ONLY for requirements the runtime failed."""
    runtime = _runtime_results(gameplay_verification)
    mech = (source_mechanics or {}).get("mechanics") or {}
    ids: List[str] = list(required_ids or [])
    if not ids:
        ids = [r for r in runtime if r != "menu_navigation"] or list(DEFAULT_REQUIRED)
    seen: set = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]

    rows: List[Dict[str, Any]] = []
    for rid in ids:
        rt = runtime.get(rid) or {}
        row: Dict[str, Any] = {
            "req_id": rid,
            "label_ar": REQUIREMENT_LABELS_AR.get(rid, rid),
            "runtime_attempted": bool(runtime_attempted),
            "runtime_verified": bool(rt.get("verified")),
            "runtime_reason": rt.get("reason") or ("not_tested" if runtime_attempted else "no_runtime"),
            "code_checked": False,
            "code_verified": False,
            "code_evidence": [],
        }
        if row["runtime_verified"]:
            row["status"] = "runtime_verified"
            row["verified_by"] = "runtime"
            row["teacher_confirmation_required"] = False
            row["summary_ar"] = f"✅ {row['label_ar']}: تم التحقق أثناء تشغيل اللعبة."
        else:
            row["code_checked"] = True
            evidence: List[Dict[str, Any]] = []
            for cid in REQUIREMENT_CODE_MAP.get(rid, (rid,)):
                m = mech.get(cid) or {}
                if m.get("detected"):
                    evidence.extend(m.get("evidence") or [])
            row["code_verified"] = bool(evidence)
            row["code_evidence"] = evidence[:6]
            if evidence:
                first = evidence[0]
                where = f"{Path(str(first.get('file', ''))).name}:{first.get('line', 0)}"
                row["status"] = "code_verified_runtime_unconfirmed"
                row["verified_by"] = "source_code"
                row["teacher_confirmation_required"] = True
                row["summary_ar"] = (
                    f"⚠️ {row['label_ar']}: لم يُثبت أثناء التشغيل، لكنه مكتوب في الكود ({where}) — "
                    "يحتاج تأكيد المعلم."
                )
            else:
                row["status"] = "not_verified"
                row["verified_by"] = None
                row["teacher_confirmation_required"] = True
                row["summary_ar"] = f"❌ {row['label_ar']}: لم يُثبت بالتشغيل ولم يُعثر عليه في الكود."
        rows.append(row)

    counts = {
        "runtime_verified": sum(r["status"] == "runtime_verified" for r in rows),
        "code_verified": sum(r["status"] == "code_verified_runtime_unconfirmed" for r in rows),
        "not_verified": sum(r["status"] == "not_verified" for r in rows),
        "total": len(rows),
    }
    return {
        "version": POLICY_VERSION,
        "requirements": rows,
        "counts": counts,
        "all_requirements_met": counts["not_verified"] == 0 and bool(rows),
        "teacher_review_required": any(r["teacher_confirmation_required"] for r in rows),
        "summary_ar": [r["summary_ar"] for r in rows],
    }


# =============================================================== temporary build
def temp_build_enabled() -> bool:
    return os.environ.get("AI_GRADER_TEMP_BUILD", "1").strip().lower() not in ("0", "false", "no", "off")


def _safe_rmtree(path: Path, attempts: int = 6, delay: float = 0.5) -> Dict[str, Any]:
    """Delete a directory; retries because Windows keeps .exe locked briefly after kill."""
    last_err = ""
    for i in range(1, attempts + 1):
        if not path.exists():
            return {"deleted": True, "attempts": i - 1 or 1, "path": str(path)}
        try:
            shutil.rmtree(path, onerror=_chmod_retry)
        except OSError as exc:
            last_err = str(exc)
        if not path.exists():
            return {"deleted": True, "attempts": i, "path": str(path)}
        time.sleep(delay * i)
    return {"deleted": False, "attempts": attempts, "path": str(path), "error": last_err}


def _chmod_retry(func, p, _exc):  # pragma: no cover - windows read-only files
    try:
        os.chmod(p, 0o700)
        func(p)
    except OSError:
        pass


@dataclass
class TemporaryGameBuild:
    engine: str
    workspace: Path
    executable: Optional[Path] = None
    info: Dict[str, Any] = field(default_factory=dict)
    cleanup_result: Optional[Dict[str, Any]] = None

    @property
    def success(self) -> bool:
        return bool(self.executable and self.executable.is_file())

    def cleanup(self) -> Dict[str, Any]:
        if self.cleanup_result is None:
            self.cleanup_result = _safe_rmtree(self.workspace)
        return self.cleanup_result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": POLICY_VERSION,
            "engine": self.engine,
            "temporary": True,
            "success": self.success,
            "executable_name": self.executable.name if self.executable else None,
            "build_info": self.info,
            "cleanup": self.cleanup_result,
            "note_ar": "تم بناء ملف .exe مؤقت للتصحيح فقط، ويُحذف تلقائياً بعد انتهاء الفحص.",
        }


def _find_first(root: Optional[Path], files: Sequence[Path], pattern: str) -> Optional[Path]:
    for f in files:
        if f.name.lower() == pattern.lower() or (pattern.startswith("*") and f.suffix.lower() == pattern[1:].lower()):
            return f
    if root and root.is_dir():
        found = sorted(root.rglob(pattern), key=lambda p: (len(p.parts), str(p).lower()))
        return found[0] if found else None
    return None


def _unity_project_root(root: Optional[Path]) -> Optional[Path]:
    if not root or not root.is_dir():
        return None
    for ps in sorted(root.rglob("ProjectSettings"), key=lambda p: len(p.parts)):
        if ps.is_dir() and (ps.parent / "Assets").is_dir():
            return ps.parent
    return None


def prepare_temporary_executable(
    files: Sequence[Path],
    submission_root: Optional[Path],
) -> Optional[TemporaryGameBuild]:
    """Build a throw-away .exe for a source-only submission. Never raises."""
    if not temp_build_enabled():
        return None
    files = [Path(f) for f in files]
    root = Path(submission_root) if submission_root else None

    yyp = _find_first(root, files, "*.yyp")
    godot = _find_first(root, files, "project.godot")
    unity = _unity_project_root(root)
    if not (yyp or godot or unity):
        return None

    ws = Path(tempfile.mkdtemp(prefix="ai_grader_tmpbuild_"))
    try:
        if yyp:
            from app.runtime_engines.gamemaker.ide_builder import build_from_source_with_install_pause

            b = TemporaryGameBuild("gamemaker", ws)
            info = build_from_source_with_install_pause(yyp, ws / "gm")
            b.info = info
            exe = info.get("executable")
            if info.get("success") and exe and Path(str(exe)).is_file():
                b.executable = Path(str(exe))
            return b
        if godot:
            from app.runtime_engines.godot.export_runner import run_godot_export

            b = TemporaryGameBuild("godot", ws)
            copy_root = ws / "project"
            shutil.copytree(godot.parent, copy_root, ignore=_COPY_IGNORE)
            info = run_godot_export(copy_root)
            info.pop("static_analysis", None)
            b.info = info
            art = info.get("artifact")
            if info.get("success") and art and Path(str(art)).is_file():
                b.executable = Path(str(art))
            return b
        if unity:
            from app.runtime_engines.unity.build_runner import (
                UnityBuildConfig, resolve_unity_binary, run_unity_build,
            )

            b = TemporaryGameBuild("unity", ws)
            binary = resolve_unity_binary()
            if not binary:
                b.info = {"success": False, "error": "unity_binary_not_configured",
                          "reason_ar": "Unity غير مثبت على جهاز التصحيح (AI_GRADER_UNITY_BIN)."}
                return b
            copy_root = ws / "project"
            shutil.copytree(unity, copy_root, ignore=_COPY_IGNORE)
            out_exe = ws / "build" / "Game.exe"
            info = run_unity_build(UnityBuildConfig(
                project_path=copy_root, unity_path=binary,
                output_exe=out_exe, log_path=ws / "unity_build.log",
            ))
            info.pop("static_fallback", None)
            b.info = info
            if info.get("success") and out_exe.is_file():
                b.executable = out_exe
            return b
    except Exception as exc:  # never break grading because a build failed
        b = TemporaryGameBuild("unknown", ws, info={"success": False, "error": str(exc)})
        return b
    return None


# =============================================================== session cleanup
TEMP_BUILD_DIR_NAMES = ("gm_ide_build", "_tmp_build")


def register_temporary_build_dir(signals: Dict[str, Any], path: Path) -> None:
    dirs = signals.setdefault("temporary_build_dirs", [])
    if str(path) not in dirs:
        dirs.append(str(path))


def cleanup_session_temporary_builds(session: Any) -> Dict[str, Any]:
    """Delete every temporary build produced during a runtime session."""
    signals = getattr(session, "signals", None)
    signals = signals if isinstance(signals, dict) else {}
    targets: List[Path] = [Path(p) for p in signals.get("temporary_build_dirs") or []]
    ws = getattr(session, "workspace", None)
    if ws:
        targets += [Path(ws) / name for name in TEMP_BUILD_DIR_NAMES]
    results = []
    seen: set = set()
    for t in targets:
        key = str(t.resolve()) if t.exists() else str(t)
        if key in seen or not t.exists():
            continue
        seen.add(key)
        results.append(_safe_rmtree(t))
    report = {"deleted_all": all(r.get("deleted") for r in results), "items": results}
    signals["temporary_build_cleanup"] = report
    return report
