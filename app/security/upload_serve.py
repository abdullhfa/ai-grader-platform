"""Guarded upload file serving — replaces public StaticFiles mount for uploads/."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request  # type: ignore
from fastapi.responses import FileResponse  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.auth import get_current_user, user_is_admin

_UPLOAD_ROOT = Path("uploads").resolve()
_PUBLIC_PREFIXES = ("specification/", "config/")
_ADMIN_ONLY_PREFIXES = ("verification_receipts/",)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def can_access_upload(path: str, user) -> bool:
    rel = _norm_path(path)
    if any(rel.startswith(p) for p in _PUBLIC_PREFIXES):
        return True
    if user is None:
        return False
    if any(rel.startswith(p) for p in _ADMIN_ONLY_PREFIXES):
        return user_is_admin(user)
    return True


def resolve_upload_file(path: str) -> Path:
    rel = _norm_path(path)
    target = (_UPLOAD_ROOT / rel).resolve()
    if not str(target).startswith(str(_UPLOAD_ROOT)):
        raise HTTPException(status_code=404, detail="Not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return target


async def serve_upload_file(path: str, request: Request, db: Session) -> FileResponse:
    user = get_current_user(request, db)
    if not can_access_upload(path, user):
        raise HTTPException(status_code=403, detail="Forbidden")
    return FileResponse(resolve_upload_file(path))
