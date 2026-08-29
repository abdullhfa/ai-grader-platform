import inspect

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

import main  # noqa: F401  Ensures the production compatibility patch is installed.


def test_patched_form_parser_accepts_current_starlette_signature():
    signature = inspect.signature(StarletteRequest._get_form)

    assert "max_files" in signature.parameters
    assert "max_fields" in signature.parameters
    assert "max_part_size" in signature.parameters


def test_multipart_field_larger_than_starlette_default_is_parsed():
    app = FastAPI()

    @app.post("/upload")
    async def upload(request: Request):
        form = await request.form()
        return {"size": len(str(form["payload"]))}

    payload = "x" * (1024 * 1024 + 4096)
    response = TestClient(app).post(
        "/upload",
        files={"payload": (None, payload, "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {"size": len(payload)}
