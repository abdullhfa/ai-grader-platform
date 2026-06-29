"""Institutional readiness routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.institutional.readiness_report import build_institutional_readiness_report

router = APIRouter(tags=["institutional"])


@router.get("/api/institutional/readiness")
async def institutional_readiness_api(db: Session = Depends(get_db)):
    return build_institutional_readiness_report(db)
