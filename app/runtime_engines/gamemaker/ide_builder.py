"""
GameMaker source-project auto-build (Igor / IDE) for no-EXE submissions.

When a student submits only the source project (.yyp + .gml) without a
compiled executable, this module attempts a local headless build using the
GameMaker runtime compiler (Igor.exe) installed on the grading machine, so
the game can still be launched and smoke-tested like a normal EXE submission.

Design:
  - Igor.exe is headless (no GUI dialogs) → safe for automated batch grading.
  - Everything is bounded by timeouts and never raises out of build_from_source.
  - All failures return a structured Arabic reason so the report can explain
    exactly why the auto-build was not possible (e.g. IDE not installed).
  - Deterministic: tool discovery sorts candidates, commands are fixed.

Environment overrides:
  AI_GRADER_GAMEMAKER_IGOR        — full path to Igor.exe
  AI_GRADER_GAMEMAKER_RUNTIME     — full path to a runtime-x.y.z folder
  AI_GRADER_GAMEMAKER_USER_DIR    — GameMakerStudio2 user folder (license)
  AI_GRADER_GAMEMAKER_IDE_BUILD   — "0"/"false" disables auto-build entirely
  AI_GRADER_GAMEMAKER_BUILD_TIMEOUT — seconds (default 180)

Pause-and-wait for install (see ``build_from_source_with_install_pause``):
  AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS — max seconds to pause while
      GameMaker is not yet installed on a Windows grading machine, polling
      periodically, before giving up on this attempt and reporting a clear
      "⏸ paused — install GameMaker then re-grade" status instead (default
      60s — a short grace window, not a multi-hour block; "0" disables
      waiting entirely and behaves like plain ``build_from_source``; raise
      this explicitly for an unattended job where blocking longer is fine).
  AI_GRADER_GAMEMAKER_INSTALL_POLL_SECONDS — how often to re-check for a
      newly-installed GameMaker while paused (default 20s).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BUILDER_VERSION = "gamemaker_ide_builder_v1"
_DEFAULT_INSTALL_POLL_SECONDS = 20
# Default is a short grace window, not a multi-hour block: a batch worker
# stuck asleep for hours with no visible progress looks like a hang, and a
# real GameMaker install (download + license + first-run) takes far longer
# than any request should block for. The default flow is therefore:
#   not installed right now -> report "⏸ paused, install GameMaker" on this
#   student immediately (visible in the results dashboard) -> teacher
#   installs GameMaker (on their own time) -> teacher re-grades this student
#   -> build now succeeds automatically. Raise
#   AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS explicitly if a long in-request
#   wait is actually wanted (e.g. an unattended overnight batch job).
_DEFAULT_INSTALL_MAX_WAIT_SECONDS = 60

_RUNTIME_VER_RE = re.compile(r"runtime-(\d+)\.(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)


def auto_build_enabled() -> bool:
    return os.environ.get("AI_GRADER_GAMEMAKER_IDE_BUILD", "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _runtime_sort_key(p: Path) -> tuple:
    m = _RUNTIME_VER_RE.search(p.name)
    if not m:
        return (0, 0, 0, 0)
    return tuple(int(g) for g in m.groups())


def _candidate_runtime_roots() -> List[Path]:
    roots: List[Path] = []
    env_rt = os.environ.get("AI_GRADER_GAMEMAKER_RUNTIME", "").strip()
    if env_rt:
        roots.append(Path(env_rt))
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    for vendor_dir in ("GameMakerStudio2", "GameMakerStudio2-LTS", "GameMaker"):
        cache = Path(program_data) / vendor_dir / "Cache" / "runtimes"
        if cache.is_dir():
            try:
                runtimes = sorted(
                    (d for d in cache.iterdir() if d.is_dir() and "runtime-" in d.name.lower()),
                    key=_runtime_sort_key,
                    reverse=True,
                )
                roots.extend(runtimes)
            except OSError:
                continue
    return roots


def _find_igor(runtime_root: Path) -> Optional[Path]:
    for rel in (
        Path("bin") / "igor" / "windows" / "x64" / "Igor.exe",
        Path("bin") / "igor" / "windows" / "x86" / "Igor.exe",
        Path("bin") / "Igor.exe",
    ):
        candidate = runtime_root / rel
        if candidate.is_file():
            return candidate
    return None


def _find_user_dir() -> Optional[Path]:
    env_user = os.environ.get("AI_GRADER_GAMEMAKER_USER_DIR", "").strip()
    if env_user and Path(env_user).is_dir():
        return Path(env_user)
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    for vendor_dir in ("GameMakerStudio2", "GameMakerStudio2-LTS", "GameMaker"):
        base = Path(appdata) / vendor_dir
        if not base.is_dir():
            continue
        try:
            # User folders look like "username_123456"; pick deterministically.
            users = sorted(
                d
                for d in base.iterdir()
                if d.is_dir() and re.match(r".+_\d+$", d.name)
            )
        except OSError:
            continue
        for user in users:
            if (user / "license.plist").is_file() or any(user.glob("*.json")):
                return user
        if users:
            return users[0]
    return None


def discover_gamemaker_tools() -> Dict[str, Any]:
    """Locate Igor.exe + runtime + user/license folder on this machine."""
    env_igor = os.environ.get("AI_GRADER_GAMEMAKER_IGOR", "").strip()
    igor: Optional[Path] = Path(env_igor) if env_igor and Path(env_igor).is_file() else None
    runtime: Optional[Path] = None

    for rt in _candidate_runtime_roots():
        if not rt.is_dir():
            continue
        found = _find_igor(rt) if igor is None else igor
        if found:
            igor = found
            runtime = rt
            break
    if igor is not None and runtime is None:
        # Igor given via env; infer runtime root from its path if possible.
        for parent in igor.parents:
            if _RUNTIME_VER_RE.search(parent.name):
                runtime = parent
                break

    user_dir = _find_user_dir()
    return {
        "igor": str(igor) if igor else None,
        "runtime": str(runtime) if runtime else None,
        "user_dir": str(user_dir) if user_dir else None,
        "available": bool(igor and runtime),
    }


def _build_timeout() -> int:
    try:
        return max(60, int(os.environ.get("AI_GRADER_GAMEMAKER_BUILD_TIMEOUT", "180")))
    except ValueError:
        return 180


def _extract_built_zip(zip_path: Path, dest: Path) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if len(names) > 4000:
                return {"ok": False, "reason": "built_zip_too_many_entries"}
            zf.extractall(dest)
    except (zipfile.BadZipFile, OSError) as exc:
        return {"ok": False, "reason": f"built_zip_extract_failed:{exc}"}
    exe = next((p for p in sorted(dest.rglob("*.exe"))), None)
    data_win = next((p for p in sorted(dest.rglob("data.win"))), None)
    return {
        "ok": bool(exe),
        "exe": str(exe) if exe else None,
        "data_win": str(data_win) if data_win else None,
    }


def build_from_source(
    yyp_path: Path,
    workspace: Path,
    *,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Attempt a headless Windows build of a GameMaker source project.

    Returns a dict:
      attempted / success / executable / data_win / reason / reason_ar / tools
    Never raises.
    """
    result: Dict[str, Any] = {
        "version": BUILDER_VERSION,
        "attempted": False,
        "success": False,
        "executable": None,
        "data_win": None,
        "reason": None,
        "reason_ar": None,
        "tools": {},
    }
    try:
        if not auto_build_enabled():
            result["reason"] = "auto_build_disabled"
            result["reason_ar"] = "البناء التلقائي معطل عبر الإعدادات (AI_GRADER_GAMEMAKER_IDE_BUILD=0)."
            return result
        if sys.platform != "win32":
            result["reason"] = "windows_only"
            result["reason_ar"] = "بناء مشاريع GameMaker متاح على Windows فقط."
            return result
        yyp = Path(yyp_path)
        if not yyp.is_file():
            result["reason"] = "yyp_missing"
            result["reason_ar"] = "ملف المشروع .yyp غير موجود."
            return result

        tools = discover_gamemaker_tools()
        result["tools"] = tools
        if not tools.get("available"):
            result["reason"] = "gamemaker_runtime_not_installed"
            result["reason_ar"] = (
                "لم يُعثر على GameMaker (Igor.exe/runtime) على جهاز التصحيح — "
                "ثبّت GameMaker أو اضبط AI_GRADER_GAMEMAKER_IGOR. "
                "سيُعتمد التحليل الثابت للكود فقط."
            )
            return result

        igor = Path(str(tools["igor"]))
        runtime = Path(str(tools["runtime"]))
        user_dir = tools.get("user_dir")

        out_dir = workspace / "gm_ide_build"
        cache_dir = out_dir / "cache"
        temp_dir = out_dir / "temp"
        pkg_dir = out_dir / "package"
        for d in (out_dir, cache_dir, temp_dir, pkg_dir):
            d.mkdir(parents=True, exist_ok=True)
        zip_out = pkg_dir / "game.zip"

        timeout = timeout_seconds or _build_timeout()
        base_cmd = [
            str(igor),
            f"-project={yyp}",
            f"-runtimePath={runtime}",
            f"-cache={cache_dir}",
            f"-temp={temp_dir}",
        ]
        if user_dir:
            base_cmd.append(f"-user={user_dir}")

        cmd_variants = [
            base_cmd + [f"-of={pkg_dir / 'game.win'}", f"-tf={zip_out}", "--", "Windows", "PackageZip"],
            base_cmd + [f"-of={pkg_dir / 'game.win'}", f"-tf={zip_out}", "Windows", "PackageZip"],
        ]

        last_err = ""
        result["attempted"] = True
        for cmd in cmd_variants:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(yyp.parent),
                )
            except subprocess.TimeoutExpired:
                last_err = f"build_timeout_{timeout}s"
                continue
            except OSError as exc:
                last_err = str(exc)
                continue
            if proc.returncode == 0 and zip_out.is_file():
                extracted = _extract_built_zip(zip_out, pkg_dir / "extracted")
                if extracted.get("ok"):
                    result["success"] = True
                    result["executable"] = extracted.get("exe")
                    result["data_win"] = extracted.get("data_win")
                    result["reason"] = "igor_package_zip"
                    result["reason_ar"] = "تم بناء اللعبة تلقائياً من المشروع المصدري (Igor)."
                    return result
                last_err = str(extracted.get("reason"))
                continue
            tail = ((proc.stderr or "") + (proc.stdout or ""))[-500:]
            last_err = tail.strip() or f"exit_{proc.returncode}"

        result["reason"] = f"igor_build_failed:{last_err[:300]}"
        result["reason_ar"] = (
            "فشل البناء التلقائي للمشروع المصدري (Igor) — "
            "سيُعتمد التحليل الثابت للكود. التفاصيل التقنية مسجلة للتدقيق."
        )
        return result
    except Exception as exc:  # pragma: no cover — must never break grading
        result["reason"] = f"builder_error:{exc}"
        result["reason_ar"] = "خطأ غير متوقع في أداة البناء — تم تجاوز البناء التلقائي."
        return result


def _install_poll_seconds() -> int:
    try:
        return max(
            5,
            int(os.environ.get(
                "AI_GRADER_GAMEMAKER_INSTALL_POLL_SECONDS",
                str(_DEFAULT_INSTALL_POLL_SECONDS),
            )),
        )
    except ValueError:
        return _DEFAULT_INSTALL_POLL_SECONDS


def _install_max_wait_seconds() -> int:
    try:
        return max(
            0,
            int(os.environ.get(
                "AI_GRADER_GAMEMAKER_INSTALL_WAIT_SECONDS",
                str(_DEFAULT_INSTALL_MAX_WAIT_SECONDS),
            )),
        )
    except ValueError:
        return _DEFAULT_INSTALL_MAX_WAIT_SECONDS


def build_from_source_with_install_pause(
    yyp_path: Path,
    workspace: Path,
    *,
    timeout_seconds: Optional[int] = None,
    on_status: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Same return contract as ``build_from_source`` — with one addition: when
    the *only* reason the build did not run is "GameMaker/Igor is not
    installed on this (Windows) grading machine", this pauses and re-polls
    for a bounded window instead of instantly giving up, so a source-only
    submission is picked back up automatically the moment GameMaker is
    installed — no re-upload, no manual re-grade click required.

    Any other reason (not Windows, auto-build disabled by admin, .yyp
    missing, or a real build failure) is returned immediately exactly like
    ``build_from_source`` — waiting cannot fix those, so it never blocks.

    ``on_status`` (optional) is called with a short event name and the
    current result dict at three points: when the pause begins, if/when
    GameMaker is detected mid-wait and the build resumes, and when the wait
    is exhausted without success — so a caller can surface a live "⏸ paused,
    waiting for GameMaker install" message (e.g. into session events/UI
    progress) without this module needing to know how that UI works.
    """
    result = build_from_source(yyp_path, workspace, timeout_seconds=timeout_seconds)
    if result.get("success"):
        return result
    if result.get("reason") != "gamemaker_runtime_not_installed":
        # windows_only / auto_build_disabled / yyp_missing / a real build
        # failure — none of these are fixed by waiting, so don't wait.
        return result

    max_wait = _install_max_wait_seconds()
    if max_wait <= 0:
        result["paused"] = False
        result["wait_skipped_reason"] = "install_wait_disabled"
        return result

    poll = _install_poll_seconds()
    waited = 0
    result["paused"] = True
    result["reason_ar"] = (
        "⏸ التصحيح مُعلّق: لم يُعثر على GameMaker على جهاز التصحيح. "
        "ثبّت GameMaker على هذا الجهاز الآن — سيكتشف النظام التثبيت تلقائياً "
        "ويكمل بناء وتشغيل وتصحيح هذا الطالب دون الحاجة لإعادة الرفع أو "
        "إعادة الضغط على زر التصحيح."
    )
    if callable(on_status):
        try:
            on_status("gamemaker_install_paused", dict(result))
        except Exception:
            pass

    while waited < max_wait:
        step = min(poll, max_wait - waited)
        time.sleep(step)
        waited += step
        tools = discover_gamemaker_tools()
        if not tools.get("available"):
            continue
        retried = build_from_source(yyp_path, workspace, timeout_seconds=timeout_seconds)
        retried["resumed_after_install_wait_seconds"] = waited
        if retried.get("success"):
            retried["reason_ar"] = (
                "✅ تم اكتشاف تثبيت GameMaker أثناء الانتظار — استؤنف التصحيح "
                "تلقائياً وتم بناء المشروع وتشغيله."
            )
        if callable(on_status):
            try:
                on_status(
                    "gamemaker_install_detected_resumed"
                    if retried.get("success")
                    else "gamemaker_install_detected_build_failed",
                    dict(retried),
                )
            except Exception:
                pass
        # Tools are now available whether or not this particular build
        # attempt succeeded — further waiting won't fix a real build error,
        # so stop polling either way and return the outcome.
        return retried

    result["wait_exhausted_seconds"] = waited
    result["reason"] = "gamemaker_runtime_not_installed"
    result["reason_ar"] = (
        "⏸ لم يتم تثبيت GameMaker خلال مهلة الانتظار — تم اعتماد التحليل "
        "الثابت للكود مؤقتاً لهذا الطالب فقط. ثبّت GameMaker ثم أعد تصحيح "
        "هذا الطالب لإكمال البناء والتشغيل الفعلي تلقائياً."
    )
    if callable(on_status):
        try:
            on_status("gamemaker_install_wait_timeout", dict(result))
        except Exception:
            pass
    return result
