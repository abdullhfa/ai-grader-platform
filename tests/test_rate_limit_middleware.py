"""Regression tests for global RateLimitMiddleware exemptions."""
from __future__ import annotations

from starlette.requests import Request

from app.production.hardening import is_rate_limit_exempt, rate_limit_response


def test_batch_results_page_exempt_from_rate_limit():
    assert is_rate_limit_exempt("GET", "/batch-results/43") is True


def test_batch_grade_progress_polling_exempt():
    assert is_rate_limit_exempt("GET", "/api/batch-grade-progress/12") is True


def test_api_post_still_rate_limited():
    assert is_rate_limit_exempt("POST", "/api/batch-grade/12") is False
    assert is_rate_limit_exempt("POST", "/api/preflight-evidence/12") is False


def test_rate_limit_response_html_for_page_navigation():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/batch-results/43",
        "headers": [(b"accept", b"text/html,application/xhtml+xml")],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": None,
    }
    request = Request(scope)
    response = rate_limit_response(request, retry_after_seconds=60)
    assert response.status_code == 429
    assert "text/html" in response.headers.get("content-type", "")
    assert "تم تجاوز حد الطلبات" in response.body.decode("utf-8")
