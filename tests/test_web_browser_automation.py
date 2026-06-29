"""Tests for PRO web browser automation helpers."""
from pathlib import Path

from app.grading_mode_policy import fast_grading_flags, deep_grading_flags
from app.runtime_engines.web.browser_automation import (
    classify_page_scenario,
    discover_html_pages,
    run_web_browser_automation,
)


def test_pro_only_browser_automation_flag():
    assert fast_grading_flags("fast")["enable_web_browser_automation"] is False
    assert deep_grading_flags("deep")["enable_web_browser_automation"] is True


def test_classify_navigation_scenarios(tmp_path: Path):
    login = tmp_path / "login.html"
    login.write_text("<html><form><input type='password'></form></html>", encoding="utf-8")
    assert classify_page_scenario(login) == "login"

    search = tmp_path / "search.html"
    search.write_text("<html><form action='search'><input name='q'></form></html>", encoding="utf-8")
    assert classify_page_scenario(search) == "search"


def test_discover_html_pages(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html><body>Home</body></html>", encoding="utf-8")
    (tmp_path / "about.html").write_text("<html><body>About</body></html>", encoding="utf-8")
    pages = discover_html_pages(tmp_path)
    assert len(pages) >= 2
    assert pages[0].name.lower() == "index.html"


def test_browser_automation_static_fallback(tmp_path: Path):
    entry = tmp_path / "index.html"
    entry.write_text(
        "<!DOCTYPE html><html><head><title>Test</title></head>"
        "<body><nav><a href='#'>Home</a></nav><form><button>Go</button></form></body></html>",
        encoding="utf-8",
    )
    result = run_web_browser_automation(tmp_path, entry, timeout_ms=5000)
    assert result.get("method") in (
        "playwright_browser_automation",
        "selenium_browser_automation",
        "static_only",
    )
    assert "web_browser_automation" in result
