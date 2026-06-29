"""
PRO-only Android Emulator Farm + UI Automation.

Targets Flutter / Kotlin / Java submissions with APK install on:
  - Android Emulator (adb)
  - Genymotion (adb-compatible)
  - Firebase Test Lab (optional gcloud hook)

UI automation: Appium (primary when server available), adb/uiautomator (fallback).
Espresso when androidTest instrumentation APK is present.

Scenarios: launch, login, registration, navigation, CRUD — with screenshots + screen record.
"""
from __future__ import annotations

import importlib
import logging
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.runtime_engines.android.project_probe import (
    detect_project_stack,
    extract_package_name_from_apk,
    find_apk_artifact,
)
from app.runtime_observation_sandbox import analyze_apk

logger = logging.getLogger("ai_grader.runtime.android")

_UI_SCENARIOS: Tuple[Dict[str, Any], ...] = (
    {"id": "launch", "keywords": ()},
    {"id": "login", "keywords": ("login", "sign in", "signin", "log in", "دخول", "تسجيل الدخول")},
    {"id": "registration", "keywords": ("register", "sign up", "signup", "create account", "التسجيل", "حساب جديد")},
    {"id": "navigation", "keywords": ("home", "menu", "nav", "dashboard", "الرئيسية", "قائمة")},
    {"id": "crud", "keywords": ("add", "create", "edit", "delete", "update", "save", "إضافة", "تعديل", "حذف")},
)


def _resolve_adb() -> Optional[str]:
    adb = shutil.which("adb")
    if adb:
        return adb
    home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if home:
        candidate = Path(home) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if candidate.is_file():
            return str(candidate)
    return None


def _run_adb(adb: str, args: List[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [adb, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
    )


def _list_devices(adb: str) -> List[Dict[str, str]]:
    proc = _run_adb(adb, ["devices", "-l"], timeout=15)
    devices: List[Dict[str, str]] = []
    for line in (proc.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line or "offline" in line:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        meta = " ".join(parts[2:]).lower()
        farm = "android_emulator"
        if "genymotion" in meta or "vbox" in serial.lower():
            farm = "genymotion"
        elif serial.startswith("emulator-"):
            farm = "android_emulator"
        devices.append({"serial": serial, "farm": farm, "meta": meta})
    return devices


def _try_boot_emulator(adb: str) -> Optional[str]:
    """Boot AVD from AI_GRADER_ANDROID_AVD when no device is online."""
    avd = os.environ.get("AI_GRADER_ANDROID_AVD", "").strip()
    emulator = shutil.which("emulator")
    if not avd or not emulator:
        return None
    try:
        subprocess.Popen(
            [emulator, "-avd", avd, "-no-audio", "-no-boot-anim"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            time.sleep(3)
            devs = _list_devices(adb)
            if devs:
                return devs[0]["serial"]
    except OSError as exc:
        logger.info("Emulator boot skipped: %s", exc)
    return None


def _pick_device(adb: str) -> Tuple[Optional[str], Optional[str], List[str]]:
    errors: List[str] = []
    devices = _list_devices(adb)
    if not devices:
        serial = _try_boot_emulator(adb)
        if serial:
            return serial, "android_emulator", errors
        errors.append("no_android_device_online")
        return None, None, errors
    dev = devices[0]
    return dev["serial"], dev["farm"], errors


def _adb_shell(adb: str, serial: str, cmd: str, *, timeout: int = 20) -> Tuple[int, str, str]:
    proc = _run_adb(adb, ["-s", serial, "shell", cmd], timeout=timeout)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _screenshot(adb: str, serial: str, out: Path) -> bool:
    remote = "/sdcard/grader_cap.png"
    code, _, _ = _adb_shell(adb, serial, f"screencap -p {remote}", timeout=15)
    if code != 0:
        return False
    pull = _run_adb(adb, ["-s", serial, "pull", remote, str(out)], timeout=20)
    return pull.returncode == 0 and out.is_file()


def _screen_record(adb: str, serial: str, out: Path, seconds: int = 12) -> bool:
    remote = "/sdcard/grader_record.mp4"
    _adb_shell(adb, serial, f"rm {remote}", timeout=5)
    proc = subprocess.run(
        [adb, "-s", serial, "shell", "screenrecord", "--time-limit", str(seconds), remote],
        capture_output=True,
        timeout=seconds + 10,
    )
    if proc.returncode != 0:
        return False
    pull = _run_adb(adb, ["-s", serial, "pull", remote, str(out)], timeout=30)
    return pull.returncode == 0 and out.is_file()


def _uiautomator_dump(adb: str, serial: str) -> str:
    remote = "/sdcard/grader_ui.xml"
    _adb_shell(adb, serial, f"uiautomator dump {remote}", timeout=15)
    proc = _run_adb(adb, ["-s", serial, "shell", "cat", remote], timeout=15)
    return proc.stdout or ""


def _find_clickable_by_keywords(ui_xml: str, keywords: Tuple[str, ...]) -> Optional[Tuple[int, int]]:
    if not ui_xml.strip():
        return None
    try:
        root = ET.fromstring(ui_xml)
    except ET.ParseError:
        return None

    for node in root.iter("node"):
        text = _norm(f"{node.attrib.get('text', '')} {node.attrib.get('content-desc', '')}")
        if keywords and not any(kw in text for kw in keywords):
            continue
        bounds = node.attrib.get("bounds", "")
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        return ((x1 + x2) // 2, (y1 + y2) // 2)
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _launch_app(adb: str, serial: str, package: str) -> bool:
    code, out, err = _adb_shell(
        adb,
        serial,
        f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
        timeout=15,
    )
    return code == 0 or "Events injected" in out or "Events injected" in err


def _install_apk(adb: str, serial: str, apk: Path) -> Tuple[bool, str]:
    proc = _run_adb(adb, ["-s", serial, "install", "-r", "-g", str(apk)], timeout=120)
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0 and "Success" in out
    return ok, out[-500:]


def _logcat_errors(adb: str, serial: str) -> List[str]:
    proc = _run_adb(
        adb,
        ["-s", serial, "logcat", "-d", "-t", "80", "*:E"],
        timeout=15,
    )
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return lines[-25:]


def _try_espresso_instrument(adb: str, serial: str, root: Path, app_package: str) -> Dict[str, Any]:
    """Run Espresso/androidTest if a test APK is bundled."""
    test_apks = [
        p
        for p in root.rglob("*androidTest*.apk")
        if p.is_file()
    ] + [
        p
        for p in root.rglob("*-debug-androidTest.apk")
        if p.is_file()
    ]
    if not test_apks:
        return {"ran": False, "reason": "no_androidTest_apk"}

    test_apk = test_apks[0]
    ok, detail = _install_apk(adb, serial, test_apk)
    if not ok:
        return {"ran": False, "reason": "test_apk_install_failed", "detail": detail}

    runner = f"{app_package}.test/androidx.test.runner.AndroidJUnitRunner"
    code, out, err = _adb_shell(
        adb,
        serial,
        f"am instrument -w -r -e debug false {runner}",
        timeout=90,
    )
    return {
        "ran": True,
        "engine": "espresso_instrumentation",
        "success": code == 0,
        "output_tail": (out + err)[-800:],
    }


def _try_appium_scenarios(
    apk: Path,
    package: str,
    screenshot_dir: Path,
    scenarios: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    server = os.environ.get("APPIUM_SERVER_URL", "http://127.0.0.1:4723")
    try:
        appium_webdriver = importlib.import_module("appium.webdriver")
        options_mod = importlib.import_module("appium.options.android").UiAutomator2Options
    except Exception:
        return None

    steps: List[Dict[str, Any]] = []
    screenshots: List[str] = []
    errors: List[str] = []

    try:
        opts = options_mod()
        opts.app = str(apk.resolve())
        opts.app_package = package
        opts.auto_grant_permissions = True
        opts.new_command_timeout = 60
        driver = appium_webdriver.Remote(server, options=opts)

        for idx, scenario in enumerate(scenarios):
            sid = scenario["id"]
            step: Dict[str, Any] = {"scenario": sid, "engine": "appium"}
            try:
                if sid != "launch":
                    kws = scenario.get("keywords") or ()
                    for kw in kws[:3]:
                        try:
                            el = driver.find_element("xpath", f"//*[contains(@text,'{kw}')]")
                            el.click()
                            step["interaction"] = f"tap:{kw}"
                            break
                        except Exception:
                            continue
                time.sleep(0.8)
                shot = screenshot_dir / f"appium_{idx:02d}_{sid}.png"
                driver.get_screenshot_as_file(str(shot))
                screenshots.append(str(shot))
                step["screenshot"] = str(shot)
                step["success"] = True
            except Exception as exc:
                step["success"] = False
                step["error"] = str(exc)[:200]
                errors.append(str(exc)[:200])
            steps.append(step)

        try:
            driver.quit()
        except Exception:
            pass
    except Exception as exc:
        return {"attempted": True, "success": False, "error": str(exc)[:300]}

    return {
        "attempted": True,
        "success": any(s.get("success") for s in steps),
        "engine": "appium_uiautomator2",
        "steps": steps,
        "screenshots": screenshots,
        "errors": errors,
    }


def _firebase_test_lab_stub(apk: Path) -> Dict[str, Any]:
    if not os.environ.get("FIREBASE_TEST_LAB", "").strip().lower() in ("1", "true", "yes"):
        return {"enabled": False}
    gcloud = shutil.which("gcloud")
    if not gcloud:
        return {"enabled": True, "status": "skipped", "reason": "gcloud_not_in_path"}
    return {
        "enabled": True,
        "status": "manual_queue",
        "reason": "Configure gcloud firebase test android run for CI offload",
        "apk": str(apk),
    }


def _run_adb_ui_scenarios(
    adb: str,
    serial: str,
    package: str,
    screenshot_dir: Path,
    scenarios: List[Dict[str, Any]],
) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    screenshots: List[str] = []

    if not _launch_app(adb, serial, package):
        return {"success": False, "error": "launch_failed", "steps": [], "screenshots": []}

    for idx, scenario in enumerate(scenarios):
        sid = scenario["id"]
        step: Dict[str, Any] = {"scenario": sid, "engine": "adb_uiautomator"}
        ui = _uiautomator_dump(adb, serial)
        step["dom_hint"] = {
            "has_buttons": "clickable=\"true\"" in ui,
            "has_forms": "class=\"android.widget.EditText\"" in ui,
            "has_lists": "RecyclerView" in ui or "ListView" in ui,
        }
        if sid != "launch":
            coords = _find_clickable_by_keywords(ui, tuple(scenario.get("keywords") or ()))
            if coords:
                _adb_shell(adb, serial, f"input tap {coords[0]} {coords[1]}", timeout=5)
                step["tap"] = coords
                time.sleep(0.6)
        shot = screenshot_dir / f"adb_{idx:02d}_{sid}.png"
        if _screenshot(adb, serial, shot):
            screenshots.append(str(shot))
            step["screenshot"] = str(shot)
            step["success"] = True
        else:
            step["success"] = False
        steps.append(step)

    return {
        "success": any(s.get("success") for s in steps),
        "engine": "adb_uiautomator",
        "steps": steps,
        "screenshots": screenshots,
    }


def run_android_mobile_automation(
    root: Path,
    *,
    apk_path: Optional[Path] = None,
    timeout_seconds: int = 45,
    screenshot_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    PRO Android Emulator Farm — install APK, UI scenarios, screenshots, screen record.
    """
    root = root.resolve()
    probe = detect_project_stack(root)
    apk = apk_path or (Path(probe["apk_path"]) if probe.get("apk_path") else None) or find_apk_artifact(root)

    out_dir = screenshot_dir or (root / ".android_automation")
    out_dir.mkdir(parents=True, exist_ok=True)

    static_apk = analyze_apk(apk) if apk and apk.is_file() else None
    base_result: Dict[str, Any] = {
        "success": False,
        "method": "none",
        "project_probe": probe,
        "static_apk_analysis": static_apk,
        "signals": {},
        "screenshots": [],
        "screen_recordings": [],
        "ui_steps": [],
        "console_errors": [],
    }

    if not apk or not apk.is_file():
        base_result["method"] = "static_only"
        base_result["error"] = "no_apk_for_emulator"
        base_result["note"] = (
            "Flutter/Kotlin/Java source detected but no APK — build required for emulator run"
            if probe["platform_type"] != "none"
            else "no_android_artifacts"
        )
        base_result["signals"] = {
            "android_project_detected": probe["platform_type"] != "none",
            "platform_type": probe["platform_type"],
            "functional_smoke_pass": False,
        }
        return base_result

    package = extract_package_name_from_apk(apk) or (static_apk or {}).get("package_name")
    if not package:
        base_result["method"] = "static_only"
        base_result["error"] = "package_name_unknown"
        return base_result

    adb = _resolve_adb()
    if not adb:
        base_result["method"] = "static_only"
        base_result["error"] = "adb_not_found"
        base_result["note"] = "Install Android SDK platform-tools (adb) for PRO emulator automation"
        base_result["signals"]["apk_structure_valid"] = bool((static_apk or {}).get("valid"))
        return base_result

    serial, farm, boot_errors = _pick_device(adb)
    if not serial:
        base_result["method"] = "static_only"
        base_result["error"] = "no_emulator_device"
        base_result["boot_errors"] = boot_errors
        base_result["note"] = "Start Android Emulator / Genymotion or set AI_GRADER_ANDROID_AVD"
        return base_result

    install_ok, install_detail = _install_apk(adb, serial, apk)
    if not install_ok:
        base_result["method"] = "adb_install_failed"
        base_result["error"] = install_detail
        return base_result

    scenarios = [{"id": s["id"], "keywords": s["keywords"]} for s in _UI_SCENARIOS]
    record_path = out_dir / "session_record.mp4"
    record_ok = _screen_record(adb, serial, record_path, seconds=min(15, timeout_seconds // 2))
    recordings = [str(record_path)] if record_ok else []

    appium_result = _try_appium_scenarios(apk, package, out_dir, scenarios)
    if appium_result and appium_result.get("success"):
        ui_result = appium_result
        method = "appium_android_automation"
    else:
        ui_result = _run_adb_ui_scenarios(adb, serial, package, out_dir, scenarios)
        method = "adb_android_automation"

    espresso = _try_espresso_instrument(adb, serial, root, package)
    log_errors = _logcat_errors(adb, serial)
    firebase = _firebase_test_lab_stub(apk)

    steps = ui_result.get("steps") or (appium_result or {}).get("steps") or []
    screenshots = ui_result.get("screenshots") or (appium_result or {}).get("screenshots") or []
    nav_ok = sum(1 for s in steps if s.get("success"))

    signals = {
        "android_project_detected": True,
        "platform_type": probe["platform_type"],
        "emulator_farm": farm,
        "device_serial": serial,
        "package_name": package,
        "navigation_ok_count": nav_ok,
        "navigation_total": len(scenarios),
        "screenshot_count": len(screenshots),
        "screen_recording_count": len(recordings),
        "console_error_count": len(log_errors),
        "apk_installed": install_ok,
        "functional_smoke_pass": install_ok and nav_ok > 0 and len(log_errors) < 15,
        "espresso_ran": bool(espresso.get("ran")),
        "appium_attempted": bool(appium_result and appium_result.get("attempted")),
    }

    return {
        "success": install_ok and nav_ok > 0,
        "method": method,
        "engine": ui_result.get("engine") or "adb_uiautomator",
        "project_probe": probe,
        "static_apk_analysis": static_apk,
        "signals": signals,
        "screenshots": screenshots,
        "screen_recordings": recordings,
        "ui_steps": steps,
        "console_errors": log_errors,
        "espresso": espresso,
        "appium": appium_result,
        "firebase_test_lab": firebase,
        "android_mobile_automation": {
            "version": "android_mobile_automation_v1",
            "scenarios_planned": [s["id"] for s in scenarios],
            "emulator_farm": farm,
            "apk": str(apk),
            "package": package,
        },
    }
