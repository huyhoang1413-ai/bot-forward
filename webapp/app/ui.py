"""Server-rendered admin UI (Jinja2, plain HTML forms)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app import services, telegram_api
from app.auth import require_admin, require_bot_access, unlock_bot
from app.db import get_session
from app.forwarding import is_valid_label, is_valid_username
from app.models import AllowedSender, Bot, Route
from app.pw import verify_password

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: int = 0):
    return templates.TemplateResponse(
        request, "login.html", {"error": bool(error)}
    )


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def dashboard(request: Request, session: Session = Depends(get_session)):
    bots = session.exec(select(Bot)).all()
    counts = {
        b.id: len(session.exec(select(Route).where(Route.bot_id == b.id)).all())
        for b in bots
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"bots": bots, "counts": counts,
         "error": request.query_params.get("error")},
    )


@router.post("/bots", dependencies=[Depends(require_admin)])
async def create_bot(
    request: Request,
    token: str = Form(...),
    access_password: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        bot = await services.add_bot(session, token, access_password)
    except telegram_api.InvalidTokenError:
        return RedirectResponse("/?error=invalid_token", status_code=status.HTTP_303_SEE_OTHER)
    except services.DuplicateBotError:
        return RedirectResponse("/?error=duplicate", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        return RedirectResponse("/?error=webhook", status_code=status.HTTP_303_SEE_OTHER)
    if access_password.strip():
        unlock_bot(request, bot.id)  # creator set it -> no need to re-enter now
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/bots/{bot_id}/unlock", response_class=HTMLResponse,
    dependencies=[Depends(require_admin)],
)
async def unlock_page(
    bot_id: int, request: Request, error: int = 0,
    session: Session = Depends(get_session),
):
    bot = session.get(Bot, bot_id)
    if not bot or not bot.access_password_hash:
        return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "unlock.html", {"bot": bot, "error": bool(error)}
    )


@router.post("/bots/{bot_id}/unlock", dependencies=[Depends(require_admin)])
async def do_unlock(
    bot_id: int, request: Request, password: str = Form(...),
    session: Session = Depends(get_session),
):
    bot = session.get(Bot, bot_id)
    if bot and bot.access_password_hash and verify_password(password, bot.access_password_hash):
        unlock_bot(request, bot_id)
        return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(
        f"/bots/{bot_id}/unlock?error=1", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/bots/{bot_id}/password",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def set_password(
    bot_id: int,
    request: Request,
    password: str = Form(""),
    session: Session = Depends(get_session),
):
    services.set_bot_password(session, bot_id, password)
    if password.strip():
        unlock_bot(request, bot_id)  # you just set it -> stay unlocked this session
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/bots/{bot_id}", response_class=HTMLResponse,
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def bot_detail(bot_id: int, request: Request, session: Session = Depends(get_session)):
    bot = session.get(Bot, bot_id)
    if not bot:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    routes = session.exec(select(Route).where(Route.bot_id == bot_id)).all()

    # Distinct source groups (in insertion order) + their allowlists.
    source_groups: list[int] = []
    for r in routes:
        if r.source_chat_id not in source_groups:
            source_groups.append(r.source_chat_id)
    allowed: dict[int, list[AllowedSender]] = {g: [] for g in source_groups}
    for row in session.exec(
        select(AllowedSender).where(AllowedSender.bot_id == bot_id)
    ).all():
        allowed.setdefault(row.source_chat_id, []).append(row)

    return templates.TemplateResponse(
        request,
        "bot_detail.html",
        {
            "bot": bot,
            "routes": routes,
            "source_groups": source_groups,
            "allowed": allowed,
            "has_password": bool(bot.access_password_hash),
            "error": request.query_params.get("error"),
        },
    )


@router.post(
    "/bots/{bot_id}/routes",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def create_route(
    bot_id: int,
    source_chat_id: int = Form(...),
    dest_chat_id: int = Form(...),
    bidirectional: bool = Form(False),
    session: Session = Depends(get_session),
):
    services.add_route(session, bot_id, source_chat_id, dest_chat_id, bidirectional)
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/routes/{route_id}/delete",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def remove_route(bot_id: int, route_id: int, session: Session = Depends(get_session)):
    services.delete_route(session, route_id, bot_id=bot_id)
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/delete",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def remove_bot(bot_id: int, session: Session = Depends(get_session)):
    await services.remove_bot(session, bot_id)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/allowed",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def create_allowed(
    bot_id: int,
    source_chat_id: int = Form(...),
    username: str = Form(...),
    label: str = Form(""),
    both_ways: bool = Form(False),
    session: Session = Depends(get_session),
):
    if not is_valid_username(username):
        return RedirectResponse(
            f"/bots/{bot_id}?error=bad_username", status_code=status.HTTP_303_SEE_OTHER
        )
    if label.strip() and not is_valid_label(label):
        return RedirectResponse(
            f"/bots/{bot_id}?error=bad_label", status_code=status.HTTP_303_SEE_OTHER
        )
    # Only allow adding to a real source group of this bot (avoids orphan rows).
    valid_source = session.exec(
        select(Route.source_chat_id).where(
            Route.bot_id == bot_id, Route.source_chat_id == source_chat_id
        )
    ).first()
    if valid_source is None:
        return RedirectResponse(
            f"/bots/{bot_id}?error=bad_source", status_code=status.HTTP_303_SEE_OTHER
        )
    services.add_allowed_sender(
        session, bot_id, source_chat_id, username, both_ways, label=label
    )
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/allowed/{allowed_id}/delete",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def remove_allowed(
    bot_id: int, allowed_id: int, session: Session = Depends(get_session)
):
    services.delete_allowed_sender(session, allowed_id, bot_id=bot_id)
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/allowed/{allowed_id}/label",
    dependencies=[Depends(require_admin), Depends(require_bot_access)],
)
async def edit_allowed_label(
    bot_id: int,
    allowed_id: int,
    label: str = Form(""),
    session: Session = Depends(get_session),
):
    if label.strip() and not is_valid_label(label):
        return RedirectResponse(
            f"/bots/{bot_id}?error=bad_label", status_code=status.HTTP_303_SEE_OTHER
        )
    services.update_allowed_label(session, allowed_id, label, bot_id=bot_id)
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)
