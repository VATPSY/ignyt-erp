import os
import hmac
import hashlib
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.db import get_session
from app.models import User, UserAuditLog
from app.schemas import UserAuditRead, UserCreate, UserRead, UserUpdate

router = APIRouter(tags=["auth"])

SESSION_COOKIE = "erp_session"
SECRET = os.getenv("ERP_SECRET", "dev-secret")


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _sign(value: str) -> str:
    return hmac.new(SECRET.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_value(user_id: int) -> str:
    payload = str(user_id)
    signature = _sign(payload)
    return f"{payload}:{signature}"


def parse_session_value(value: str) -> Optional[int]:
    try:
        payload, signature = value.split(":", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        return int(payload)
    except ValueError:
        return None


def get_current_user(request: Request, session: Session) -> Optional[User]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    user_id = parse_session_value(raw)
    if not user_id:
        return None
    return session.get(User, user_id)


def require_permission(request: Request, session: Session, key: str, mode: str = "read") -> User:
    user = get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.permissions == "*":
        return user
    permissions = [] if not user.permissions else user.permissions.split(",")
    if f"{key}:{mode}" not in permissions and f"{key}:write" not in permissions:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


def require_any_permission(
    request: Request, session: Session, keys: List[str], mode: str = "read"
) -> User:
    user = get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.permissions == "*":
        return user
    permissions = [] if not user.permissions else user.permissions.split(",")
    for key in keys:
        if f"{key}:{mode}" in permissions or f"{key}:write" in permissions:
            return user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


def ensure_admin_seed(session: Session) -> None:
    existing = session.exec(select(User)).first()
    if existing:
        return
    admin = User(username="admin", password_hash=_hash_password("admin"), permissions="*")
    session.add(admin)
    session.commit()


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    ensure_admin_seed(session)
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or user.password_hash != _hash_password(password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(SESSION_COOKIE, create_session_value(user.id), httponly=True)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/api/me", response_model=UserRead)
def me(request: Request, session: Session = Depends(get_session)):
    user = get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    permissions = [] if not user.permissions else user.permissions.split(",")
    if user.permissions == "*":
        permissions = ["*"]
    return UserRead(id=user.id, username=user.username, permissions=permissions)


@router.get("/api/users", response_model=List[UserRead])
def list_users(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "profile_settings", "read")
    users = session.exec(select(User)).all()
    result = []
    for item in users:
        permissions = [] if not item.permissions else item.permissions.split(",")
        if item.permissions == "*":
            permissions = ["*"]
        result.append(UserRead(id=item.id, username=item.username, permissions=permissions))
    return result


@router.get("/api/user-logs", response_model=List[UserAuditRead])
def list_user_logs(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "profile_settings", "read")
    logs = session.exec(select(UserAuditLog).order_by(UserAuditLog.id.desc())).all()
    result = []
    for log in logs:
        permissions = [] if not log.permissions else log.permissions.split(",")
        if log.permissions == "*":
            permissions = ["*"]
        result.append(
            UserAuditRead(
                id=log.id,
                actor=log.actor,
                action=log.action,
                target_username=log.target_username,
                permissions=permissions,
                created_at=log.created_at,
            )
        )
    return result


@router.post("/api/users", response_model=UserRead)
def create_user(payload: UserCreate, request: Request, session: Session = Depends(get_session)):
    user = require_permission(request, session, "profile_settings", "write")
    existing = session.exec(select(User).where(User.username == payload.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    permissions = ",".join(payload.permissions)
    new_user = User(
        username=payload.username,
        password_hash=_hash_password(payload.password),
        permissions=permissions,
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    session.add(
        UserAuditLog(
            actor=user.username,
            action="CREATE",
            target_username=new_user.username,
            permissions=permissions,
        )
    )
    session.commit()
    return UserRead(id=new_user.id, username=new_user.username, permissions=payload.permissions)


@router.put("/api/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    session: Session = Depends(get_session),
):
    user = require_permission(request, session, "profile_settings", "write")
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    action_parts = []
    if payload.password:
        target.password_hash = _hash_password(payload.password)
        action_parts.append("RESET_PASSWORD")
    if payload.permissions is not None:
        target.permissions = ",".join(payload.permissions)
        action_parts.append("UPDATE_PERMISSIONS")
    session.add(target)
    session.commit()
    session.refresh(target)
    if action_parts:
        session.add(
            UserAuditLog(
                actor=user.username,
                action=" & ".join(action_parts),
                target_username=target.username,
                permissions=target.permissions,
            )
        )
        session.commit()
    permissions = [] if not target.permissions else target.permissions.split(",")
    if target.permissions == "*":
        permissions = ["*"]
    return UserRead(id=target.id, username=target.username, permissions=permissions)


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "profile_settings", "write")
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(target)
    session.commit()
    return {"ok": True}
