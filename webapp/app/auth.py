"""Single-admin authentication via signed session cookie."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.models import Bot

router = APIRouter()


def is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


def require_admin(request: Request) -> None:
    """Dependency: redirect to /login when not authenticated."""
    if not is_authed(request):
        # 303 with Location -> browser redirects to the login page.
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )


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
    """Dependency: if the bot has an access password, require it to be unlocked
    in this session (else redirect to the per-bot unlock page)."""
    bot = session.get(Bot, bot_id)
    if bot and bot.access_password_hash and not is_bot_unlocked(request, bot_id):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/bots/{bot_id}/unlock"},
        )


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    expected = get_settings().admin_password
    # Constant-time comparison to avoid timing attacks.
    if hmac.compare_digest(password, expected):
        request.session["authed"] = True
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/login?error=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
