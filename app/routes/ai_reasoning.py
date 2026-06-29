"""AI evidence reasoning API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ai-reasoning", tags=["ai-reasoning"])


class ReasoningRequest(BaseModel):
    submission_key: str
    grading_result: Dict[str, Any] = Field(default_factory=dict)
    artifact_inventory: Optional[Dict[str, Any]] = None
    gameplay_analysis: Optional[Dict[str, Any]] = None
    grading_criteria: Optional[List[Dict[str, Any]]] = None


@router.post("/run")
async def run_reasoning_api(req: ReasoningRequest) -> Dict[str, Any]:
    from app.ai_reasoning.orchestrator import run_evidence_reasoning

    return run_evidence_reasoning(
        submission_key=req.submission_key,
        grading_result=req.grading_result,
        artifact_inventory=req.artifact_inventory,
        gameplay_analysis=req.gameplay_analysis,
        grading_criteria=req.grading_criteria,
    )
