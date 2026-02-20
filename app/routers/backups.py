from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.backups import run_backup
from app.db import get_session
from app.routers.auth import require_permission

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.post("/run")
def backup_now(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "profile_settings", "write")
    try:
        result = run_backup(session)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
