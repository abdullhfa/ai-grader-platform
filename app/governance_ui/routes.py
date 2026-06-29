"""Examiner investigation UI routes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.governance.audit_log import read_audit_log
from app.governance.examiner_mode import load_examiner_review, parse_session_ref
from app.governance.replay_viewer import find_sessions_for_submission
from app.governance_ui.presenters.replay_presenter import present_replay_investigation
from app.routes.deps import app_title

router = APIRouter(prefix="/governance/examiner", tags=["governance-ui"])

_templates = Jinja2Templates(directory="app/governance_ui/templates")
_templates.env.globals["app_title"] = app_title()
_templates.env.filters["tojson"] = lambda v, indent=None: json.dumps(v, ensure_ascii=False, indent=indent)


def _list_all_sessions() -> List[Dict[str, str]]:
    root = Path("uploads/replay_snapshots")
    sessions: List[Dict[str, str]] = []
    if not root.is_dir():
        return sessions
    for sub_dir in sorted(root.iterdir()):
        if not sub_dir.is_dir():
            continue
        for sess_dir in sorted(sub_dir.iterdir()):
            if sess_dir.is_dir():
                sessions.append({
                    "submission_key": sub_dir.name,
                    "session_id": sess_dir.name,
                })
    return sessions


def _list_all_appeals() -> List[Dict[str, Any]]:
    root = Path("uploads/appeals/cases")
    cases = []
    if not root.is_dir():
        return cases
    for fp in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            cases.append(json.loads(fp.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return cases


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def examiner_dashboard(request: Request):
    return _templates.TemplateResponse(
        "examiner_dashboard.html",
        {"request": request, "app_title": app_title(), "sessions": _list_all_sessions()},
    )


@router.get("/review/{submission_key}/{session_id}", response_class=HTMLResponse)
async def examiner_replay_review(request: Request, submission_key: str, session_id: str):
    session_ref = f"{submission_key}/{session_id}"
    try:
        review = load_examiner_review(session_ref)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    investigation = present_replay_investigation(review)
    return _templates.TemplateResponse(
        "replay_viewer.html",
        {"request": request, "app_title": app_title(), "investigation": investigation},
    )


@router.get("/audit/{session_ref:path}", response_class=HTMLResponse)
async def examiner_audit_viewer(request: Request, session_ref: str):
    try:
        _, session_id = parse_session_ref(session_ref)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _templates.TemplateResponse(
        "audit_viewer.html",
        {
            "request": request,
            "app_title": app_title(),
            "session_ref": session_ref,
            "events": read_audit_log(session_id),
        },
    )


@router.get("/appeals", response_class=HTMLResponse)
async def examiner_appeals_queue(request: Request):
    return _templates.TemplateResponse(
        "appeal_review.html",
        {"request": request, "app_title": app_title(), "appeals": _list_all_appeals()},
    )


def register_governance_ui(app) -> None:
    """Mount static assets and UI router."""
    from fastapi.staticfiles import StaticFiles

    static_dir = Path("app/governance_ui/static")
    if static_dir.is_dir():
        app.mount(
            "/governance-ui/static",
            StaticFiles(directory=str(static_dir)),
            name="governance_ui_static",
        )
    app.include_router(router)
