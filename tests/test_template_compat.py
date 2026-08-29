from starlette.requests import Request

from app.template_compat import Jinja2Templates


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 5557),
        }
    )


def test_legacy_template_response_signature_works_on_new_starlette(tmp_path):
    (tmp_path / "page.html").write_text("Hello {{ value }}", encoding="utf-8")
    templates = Jinja2Templates(directory=str(tmp_path))
    request = _request()

    response = templates.TemplateResponse(
        "page.html", {"request": request, "value": "World"}
    )

    assert response.status_code == 200
    assert response.body == b"Hello World"


def test_new_template_response_signature_still_works(tmp_path):
    (tmp_path / "page.html").write_text("OK", encoding="utf-8")
    templates = Jinja2Templates(directory=str(tmp_path))
    request = _request()

    response = templates.TemplateResponse(request, "page.html", {"request": request})

    assert response.body == b"OK"
