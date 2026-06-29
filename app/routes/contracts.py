"""Frozen platform contract API."""
from __future__ import annotations

from fastapi import APIRouter

from app.contracts.freeze_registry import build_freeze_report, validate_platform_contracts

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.get("/freeze")
async def contract_freeze_api():
    return build_freeze_report()


@router.get("/validate")
async def contract_validate_api():
    return validate_platform_contracts()
