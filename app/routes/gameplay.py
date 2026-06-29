"""Gameplay analysis API routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/gameplay", tags=["gameplay"])


class GameplayAnalyzeRequest(BaseModel):
    submission_key: str = Field(..., description="Student/submission key used in runtime_sessions path")
    session_id: str = Field(..., description="Runtime session UUID")
    async_mode: bool = False


@router.post("/analyze")
async def gameplay_analyze_api(req: GameplayAnalyzeRequest) -> Dict[str, Any]:
    artifact_root = Path("uploads/runtime_sessions") / req.submission_key / req.session_id
    if not artifact_root.is_dir():
        raise HTTPException(status_code=404, detail="Runtime session artifacts not found")

    if req.async_mode:
        from app.tasks.celery_app import is_celery_enabled
        from app.tasks.worker_tasks import gameplay_analysis_task

        if not is_celery_enabled():
            raise HTTPException(status_code=503, detail="Celery not enabled")
        task = gameplay_analysis_task.delay(req.submission_key, req.session_id)
        return {"status": "queued", "task_id": task.id}

    from app.gameplay_ai.pipeline import analyze_gameplay_artifacts

    return analyze_gameplay_artifacts(req.submission_key, req.session_id)


@router.get("/analysis/{submission_key}/{session_id}")
async def gameplay_analysis_get_api(submission_key: str, session_id: str) -> Dict[str, Any]:
    path = (
        Path("uploads/runtime_sessions")
        / submission_key
        / session_id
        / "gameplay_analysis"
        / "analysis.json"
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Gameplay analysis not found")
    import json

    return json.loads(path.read_text(encoding="utf-8"))
