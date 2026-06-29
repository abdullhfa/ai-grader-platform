"""
PRO-only Web Runtime Browser Automation.

Playwright + Chromium headless (primary), Selenium (secondary fallback).
Navigation tests, per-step screenshots, DOM validation, error detection.
"""
from __future__ import annotations

import importlib
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.runtime_engines.web.playwright_runner import find_web_entry_point

logger = logging.getLogger("ai_grader.runtime.web.browser")

_NAV_SCENARIOS: Tuple[Dict[str, Any], ...] = (
    {"id": "homepage", "keywords": ("index", "home", "main", "start", "الرئيسية", "الرئيسيه")},
    {"id": "login", "keywords": ("login", "signin", "sign-in", "log-in", "تسجيل الدخول", "دخول")},
    {"id": "register", "keywords": ("register", "signup", "sign-up", "sign_up", "التسجيل", "انشاء حساب", "إنشاء حساب")},
    {"id": "search", "keywords": ("search", "find", "query", "بحث", "البحث")},
    {"id": "crud", "keywords": ("create", "edit", "delete", "update", "add", "crud", "manage", "admin", "إضافة", "تعديل", "حذف")},
)

_SKIP_DIRS = frozenset({"node_modules", ".git", "vendor", "dist", "build", ".next"})


def _file_uri(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) >= 2 and resolved[1] == ":":
        return "file:///" + resolved
    return "file://" + resolved


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def discover_html_pages(root: Path, *, max_pages: int = 24) -> List[Path]:
    """Collect HTML entry points under submission root."""
    if root.is_file() and root.suffix.lower() in {".html", ".htm"}:
        return [root]
    if not root.is_dir():
        return []

    pages: List[Path] = []
    for pattern in ("*.html", "*.htm"):
        for p in sorted(root.rglob(pattern)):
            if any(part.lower() in _SKIP_DIRS for part in p.parts):
                continue
            if p.is_file():
                pages.append(p)
            if len(pages) >= max_pages:
                break
    if not pages:
        return []
    entry = find_web_entry_point(root)
    if entry and entry in pages:
        pages.remove(entry)
        pages.insert(0, entry)
    elif entry:
        pages.insert(0, entry)
    return pages[:max_pages]


def classify_page_scenario(page: Path) -> str:
    blob = _norm(page.stem) + " " + _norm(page.parent.name)
    try:
        head = page.read_text(encoding="utf-8", errors="replace")[:8000].lower()
        blob += " " + head
    except OSError:
        pass
    for scenario in _NAV_SCENARIOS:
        if scenario["id"] == "homepage" and page.name.lower() in ("index.html", "index.htm", "home.html"):
            return "homepage"
        if any(kw in blob for kw in scenario["keywords"]):
            return str(scenario["id"])
    return "other"


def _pick_scenario_pages(pages: List[Path]) -> List[Dict[str, Any]]:
    """One page per navigation scenario when possible."""
    chosen: Dict[str, Dict[str, Any]] = {}
    for page in pages:
        sid = classify_page_scenario(page)
        if sid not in chosen or sid == "homepage":
            chosen[sid] = {"scenario": sid, "path": page}
    order = ["homepage", "login", "register", "search", "crud", "other"]
    out: List[Dict[str, Any]] = []
    for sid in order:
        if sid in chosen:
            out.append(chosen[sid])
    for sid, row in chosen.items():
        if sid not in order:
            out.append(row)
    return out


def _audit_dom_playwright(page: Any) -> Dict[str, Any]:
    try:
        return page.evaluate(
            """() => {
                const q = (s) => document.querySelectorAll(s).length;
                const menus = q('nav') + q('[role="navigation"]') + q('.menu, .navbar, #menu, #nav');
                return {
                    buttons: q('button') + q('input[type="button"]') + q('input[type="submit"]') + q('a.btn, a.button'),
                    forms: q('form'),
                    tables: q('table'),
                    menus: menus,
                    links: q('a[href]'),
                    inputs: q('input, textarea, select'),
                    headings: q('h1, h2, h3'),
                };
            }"""
        )
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _audit_dom_selenium(driver: Any) -> Dict[str, Any]:
    try:
        By = importlib.import_module("selenium.webdriver.common.by").By

        def count(css: str) -> int:
            return len(driver.find_elements(By.CSS_SELECTOR, css))

        return {
            "buttons": count("button") + count('input[type="button"]') + count('input[type="submit"]'),
            "forms": count("form"),
            "tables": count("table"),
            "menus": count("nav") + count('[role="navigation"]'),
            "links": count("a[href]"),
            "inputs": count("input") + count("textarea") + count("select"),
            "headings": count("h1") + count("h2") + count("h3"),
        }
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _start_php_server(root: Path, port: int = 8765) -> Optional[subprocess.Popen]:
    php = shutil.which("php")
    if not php:
        return None
    php_files = list(root.rglob("*.php"))
    php_files = [p for p in php_files if not any(d in _SKIP_DIRS for d in p.parts)]
    if not php_files:
        return None
    entry = root / "index.php"
    if not entry.is_file():
        entry = php_files[0].parent / "index.php"
        if not entry.is_file():
            entry = php_files[0]
    try:
        proc = subprocess.Popen(
            [php, "-S", f"127.0.0.1:{port}", "-t", str(root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(root),
        )
        time.sleep(0.8)
        if proc.poll() is not None:
            return None
        return proc
    except OSError as exc:
        logger.info("PHP built-in server unavailable: %s", exc)
        return None


def _base_url_for_entry(entry: Path, root: Path, php_proc: Optional[subprocess.Popen], port: int) -> str:
    if php_proc:
        rel = entry.relative_to(root).as_posix() if entry.is_relative_to(root) else entry.name
        return f"http://127.0.0.1:{port}/{rel}"
    return _file_uri(entry)


def _run_with_playwright(
    *,
    root: Path,
    steps: List[Dict[str, Any]],
    base_resolver: Callable[[Path], str],
    out_dir: Path,
    timeout_ms: int,
) -> Dict[str, Any]:
    sync_api = importlib.import_module("playwright.sync_api")
    sync_playwright = sync_api.sync_playwright

    console_errors: List[str] = []
    page_errors: List[str] = []
    http_errors: List[str] = []
    navigation_steps: List[Dict[str, Any]] = []
    screenshots: List[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})

        def _on_console(msg: Any) -> None:
            if msg.type == "error":
                console_errors.append(msg.text[:500])

        def _on_page_error(exc: Any) -> None:
            page_errors.append(str(exc)[:500])

        def _on_request_failed(req: Any) -> None:
            failure = req.failure
            err_text = failure if isinstance(failure, str) else getattr(failure, "error_text", "") or str(failure)
            http_errors.append(f"{req.method} {req.url} — {err_text}"[:500])

        page.on("console", _on_console)
        page.on("pageerror", _on_page_error)
        page.on("requestfailed", _on_request_failed)

        for idx, step in enumerate(steps):
            entry: Path = step["path"]
            scenario = step["scenario"]
            url = base_resolver(entry)
            step_record: Dict[str, Any] = {
                "scenario": scenario,
                "path": str(entry),
                "url": url,
                "navigation_ok": False,
            }
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                step_record["navigation_ok"] = True
                if resp and resp.status >= 400:
                    http_errors.append(f"HTTP {resp.status} {url}"[:500])
                    step_record["http_status"] = resp.status
            except Exception as exc:
                page_errors.append(f"navigation_{scenario}: {exc}"[:500])
                step_record["error"] = str(exc)[:300]

            page.wait_for_timeout(min(800, timeout_ms // 4))
            dom = _audit_dom_playwright(page)
            step_record["dom"] = dom

            shot = out_dir / f"nav_{idx:02d}_{scenario}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                screenshots.append(str(shot))
                step_record["screenshot"] = str(shot)
            except Exception as exc:
                step_record["screenshot_error"] = str(exc)[:200]

            if scenario in ("login", "register", "search") and dom.get("forms", 0) > 0:
                try:
                    page.locator("input[type=text], input[type=email], input[type=search], input:not([type])").first.fill(
                        "test@example.com" if scenario != "search" else "test",
                        timeout=2000,
                    )
                    if scenario != "search":
                        pwd = page.locator('input[type="password"]')
                        if pwd.count() > 0:
                            pwd.first.fill("TestPass123!", timeout=1500)
                    submit = page.locator('button[type="submit"], input[type="submit"], button')
                    if submit.count() > 0:
                        submit.first.click(timeout=2000)
                        page.wait_for_timeout(600)
                        after_shot = out_dir / f"nav_{idx:02d}_{scenario}_after.png"
                        page.screenshot(path=str(after_shot), full_page=True)
                        screenshots.append(str(after_shot))
                        step_record["interaction"] = "form_submit_attempted"
                except Exception as exc:
                    step_record["interaction_error"] = str(exc)[:200]

            navigation_steps.append(step_record)

        browser.close()

    dom_totals = {
        "buttons": sum((s.get("dom") or {}).get("buttons", 0) for s in navigation_steps),
        "forms": sum((s.get("dom") or {}).get("forms", 0) for s in navigation_steps),
        "tables": sum((s.get("dom") or {}).get("tables", 0) for s in navigation_steps),
        "menus": sum((s.get("dom") or {}).get("menus", 0) for s in navigation_steps),
    }
    nav_ok = sum(1 for s in navigation_steps if s.get("navigation_ok"))
    return {
        "success": nav_ok > 0,
        "method": "playwright_browser_automation",
        "engine": "playwright_chromium_headless",
        "navigation_steps": navigation_steps,
        "screenshots": screenshots,
        "console_errors": console_errors[:30],
        "page_errors": page_errors[:30],
        "http_errors": http_errors[:30],
        "signals": {
            "navigation_ok_count": nav_ok,
            "navigation_total": len(navigation_steps),
            "dom_validation": dom_totals,
            "console_error_count": len(console_errors),
            "page_error_count": len(page_errors),
            "http_error_count": len(http_errors),
            "screenshot_count": len(screenshots),
            "functional_smoke_pass": nav_ok > 0 and not page_errors and len(http_errors) <= 2,
        },
    }


def _run_with_selenium(
    *,
    steps: List[Dict[str, Any]],
    base_resolver: Callable[[Path], str],
    out_dir: Path,
    timeout_ms: int,
) -> Dict[str, Any]:
    webdriver = importlib.import_module("selenium.webdriver")
    options_mod = importlib.import_module("selenium.webdriver.chrome.options")
    chrome_options = options_mod.Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--no-sandbox")

    console_errors: List[str] = []
    page_errors: List[str] = []
    http_errors: List[str] = []
    navigation_steps: List[Dict[str, Any]] = []
    screenshots: List[str] = []

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(max(5, timeout_ms // 1000))

    try:
        for idx, step in enumerate(steps):
            entry: Path = step["path"]
            scenario = step["scenario"]
            url = base_resolver(entry)
            step_record: Dict[str, Any] = {
                "scenario": scenario,
                "path": str(entry),
                "url": url,
                "navigation_ok": False,
            }
            try:
                driver.get(url)
                step_record["navigation_ok"] = True
            except Exception as exc:
                page_errors.append(f"navigation_{scenario}: {exc}"[:500])
                step_record["error"] = str(exc)[:300]

            time.sleep(0.5)
            step_record["dom"] = _audit_dom_selenium(driver)
            shot = out_dir / f"nav_{idx:02d}_{scenario}.png"
            try:
                driver.save_screenshot(str(shot))
                screenshots.append(str(shot))
                step_record["screenshot"] = str(shot)
            except Exception as exc:
                step_record["screenshot_error"] = str(exc)[:200]
            navigation_steps.append(step_record)

        try:
            logs = driver.get_log("browser")
            for row in logs:
                if row.get("level") == "SEVERE":
                    console_errors.append(str(row.get("message", ""))[:500])
        except Exception:
            pass
    finally:
        driver.quit()

    nav_ok = sum(1 for s in navigation_steps if s.get("navigation_ok"))
    dom_totals = {
        "buttons": sum((s.get("dom") or {}).get("buttons", 0) for s in navigation_steps),
        "forms": sum((s.get("dom") or {}).get("forms", 0) for s in navigation_steps),
        "tables": sum((s.get("dom") or {}).get("tables", 0) for s in navigation_steps),
        "menus": sum((s.get("dom") or {}).get("menus", 0) for s in navigation_steps),
    }
    return {
        "success": nav_ok > 0,
        "method": "selenium_browser_automation",
        "engine": "selenium_chromium_headless",
        "navigation_steps": navigation_steps,
        "screenshots": screenshots,
        "console_errors": console_errors[:30],
        "page_errors": page_errors[:30],
        "http_errors": http_errors[:30],
        "signals": {
            "navigation_ok_count": nav_ok,
            "navigation_total": len(navigation_steps),
            "dom_validation": dom_totals,
            "console_error_count": len(console_errors),
            "page_error_count": len(page_errors),
            "http_error_count": len(http_errors),
            "screenshot_count": len(screenshots),
            "functional_smoke_pass": nav_ok > 0 and not page_errors,
        },
    }


def run_web_browser_automation(
    root: Path,
    entry: Optional[Path] = None,
    *,
    timeout_ms: int = 20000,
    screenshot_dir: Optional[Path] = None,
    max_steps: int = 8,
) -> Dict[str, Any]:
    """
    PRO Web Runtime Browser Automation — navigation, screenshots, DOM, errors.
    """
    root = root.resolve()
    entry = entry or find_web_entry_point(root)
    if not entry or not entry.is_file():
        return {
            "success": False,
            "method": "none",
            "error": "web_entry_not_found",
            "signals": {},
            "screenshots": [],
        }

    pages = discover_html_pages(root)
    if entry not in pages:
        pages.insert(0, entry)
    steps = _pick_scenario_pages(pages)[:max_steps]
    if not steps:
        steps = [{"scenario": "homepage", "path": entry}]

    out_dir = screenshot_dir or (root / ".web_browser_automation")
    out_dir.mkdir(parents=True, exist_ok=True)

    php_port = 8765
    php_proc = _start_php_server(root, port=php_port)

    def base_resolver(page_path: Path) -> str:
        return _base_url_for_entry(page_path, root, php_proc, php_port)

    result: Dict[str, Any]
    try:
        try:
            importlib.import_module("playwright.sync_api")
            result = _run_with_playwright(
                root=root,
                steps=steps,
                base_resolver=base_resolver,
                out_dir=out_dir,
                timeout_ms=timeout_ms,
            )
        except ImportError:
            try:
                importlib.import_module("selenium.webdriver")
                result = _run_with_selenium(
                    steps=steps,
                    base_resolver=base_resolver,
                    out_dir=out_dir,
                    timeout_ms=timeout_ms,
                )
            except ImportError:
                from app.runtime_engines.web.playwright_runner import _static_web_analysis

                result = _static_web_analysis(entry)
                result["browser_automation_unavailable"] = True
                result["note"] = "Install playwright or selenium for PRO browser automation"
    finally:
        if php_proc:
            try:
                php_proc.terminate()
                php_proc.wait(timeout=3)
            except Exception:
                try:
                    php_proc.kill()
                except Exception:
                    pass

    result["web_browser_automation"] = {
        "version": "web_browser_automation_v1",
        "scenarios_planned": [s["scenario"] for s in steps],
        "php_server_used": php_proc is not None,
        "entry": str(entry),
        "root": str(root),
    }
    return result


def submission_has_web_artifacts(root: Path) -> bool:
    return bool(discover_html_pages(root, max_pages=1))
