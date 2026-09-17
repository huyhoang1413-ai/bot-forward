"""Authentication: DB team-members + the .env super-admin, via signed session.

Login tries a DB ``User`` first, then falls back to the ``.env`` super-admin.
Session identity: ``user_id`` (None = super-admin), ``username``, ``is_admin``,
``team_id`` (None = super-admin / no team).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import Bot, Team, User
from app.pw import hash_password, verify_password

router = APIRouter()

# Fixed dummy hash: verified when a username is unknown so login timing does not
# reveal whether the account exists (anti-enumeration).
_DUMMY_HASH = hash_password("dummy-password-for-constant-time")


def is_authed(request: Request) -> bool:
    return bool(request.session.get("username"))


def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def team_id(request: Request) -> int | None:
    return request.session.get("team_id")


def authenticate(session: Session, username: str, password: str) -> dict | None:
    """Return an identity dict for valid credentials, else None.

    Constant-time-ish: always spends a hash when the user is unknown.
    """
    uname = (username or "").strip().lower()
    user = session.exec(select(User).where(User.username == uname)).first()
    if user and verify_password(password, user.password_hash):
        team = session.get(Team, user.team_id) if user.team_id else None
        return {
            "user_id": user.id,
            "username": user.username,
            "is_admin": False,
            "team_id": user.team_id,
            "team_name": team.name if team else None,
        }
    if user is None:
        verify_password(password, _DUMMY_HASH)  # burn time -> no enumeration

    s = get_settings()
    user_ok = hmac.compare_digest(username or "", s.admin_username)
    pw_ok = hmac.compare_digest(password or "", s.admin_password)
    if user_ok and pw_ok:
        return {
            "user_id": None,
            "username": s.admin_username,
            "is_admin": True,
            "team_id": None,
            "team_name": None,
        }
    return None


def require_auth(request: Request) -> None:
    """Dependency: any logged-in identity (redirect to /login otherwise)."""
    if not is_authed(request):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )


def require_super_admin(request: Request) -> None:
    """Dependency: only the .env super-admin (403 for team members)."""
    require_auth(request)
    if not is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def is_bot_unlocked(request: Request, bot_id: int) -> bool:
    return bot_id in request.session.get("unlocked_bots", [])


def unlock_bot(request: Request, bot_id: int) -> None:
    ids = list(request.session.get("unlocked_bots", []))
    if bot_id not in ids:
        ids.append(bot_id)
        request.session["unlocked_bots"] = ids


def require_bot_access(
    bot_id: int, request: Request, session: Session = Depends(get_session)
) -> None:
    """Dependency for every /bots/{id} route. Enforces, in order:
    1. logged in, 2. team ownership (super-admin bypass) — cross-team => 403,
    3. per-bot access password unlock (redirect to the unlock page)."""
    require_auth(request)
    bot = session.get(Bot, bot_id)
    if bot is not None and not is_admin(request):
        if bot.team_id != team_id(request):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)  # IDOR
    if bot and bot.access_password_hash and not is_bot_unlocked(request, bot_id):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/bots/{bot_id}/unlock"},
        )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    ident = authenticate(session, username, password)
    if ident is None:
        return RedirectResponse("/login?error=1", status_code=status.HTTP_303_SEE_OTHER)
    request.session.clear()  # rotate session -> anti-fixation
    request.session.update(ident)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
