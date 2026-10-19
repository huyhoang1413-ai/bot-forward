"""Server-rendered admin UI (Jinja2, plain HTML forms)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app import services, telegram_api
from app.auth import require_auth, require_bot_access, unlock_bot
from app.db import get_session
from app.forwarding import is_valid_label, is_valid_username
from app.auth import require_super_admin
from app.models import Bot, Route, Team
from app.pw import verify_password

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# How many assigned senders to preview inline in a group's dropdown before
# linking out to the dedicated (search + paginate) manager page.
INLINE_PREVIEW = 20


def _opt_int(v: str) -> int | None:
    """Parse an optional integer form field: blank -> None."""
    v = (v or "").strip()
    return int(v) if v else None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: int = 0):
    return templates.TemplateResponse(
        request, "login.html", {"error": bool(error)}
    )


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def dashboard(request: Request, session: Session = Depends(get_session)):
    admin = bool(request.session.get("is_admin"))
    tid = request.session.get("team_id")
    bots = services.visible_bots(session, tid, admin)
    counts = {
        b.id: len(session.exec(select(Route).where(Route.bot_id == b.id)).all())
        for b in bots
    }
    team_name_by_id = {t.id: t.name for t in services.list_teams(session)} if admin else {}
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"bots": bots, "counts": counts,
         "is_admin": admin,
         "teams": services.list_teams(session) if admin else [],
         "team_name_by_id": team_name_by_id,
         "error": request.query_params.get("error")},
    )


@router.post("/bots", dependencies=[Depends(require_auth)])
async def create_bot(
    request: Request,
    token: str = Form(...),
    access_password: str = Form(""),
    team_id: str = Form(""),
    session: Session = Depends(get_session),
):
    # Owning team: super-admin picks (blank = admin-only); a member -> own team.
    if request.session.get("is_admin"):
        owner_team_id = int(team_id) if team_id.strip() else None
    else:
        owner_team_id = request.session.get("team_id")
        if owner_team_id is None:
            return RedirectResponse("/?error=no_team", status_code=status.HTTP_303_SEE_OTHER)
    try:
        bot = await services.add_bot(
            session, token, access_password, team_id=owner_team_id
        )
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
    dependencies=[Depends(require_auth)],
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


@router.post("/bots/{bot_id}/unlock", dependencies=[Depends(require_auth)])
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
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
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
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def bot_detail(bot_id: int, request: Request, session: Session = Depends(get_session)):
    bot = session.get(Bot, bot_id)
    if not bot:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    routes = session.exec(select(Route).where(Route.bot_id == bot_id)).all()

    # Distinct source groups (in insertion order), for the routes list.
    source_groups: list[int] = []
    for r in routes:
        if r.source_chat_id not in source_groups:
            source_groups.append(r.source_chat_id)

    senders_count = services.count_senders(session, bot_id)

    # Which group's dropdown to keep open (after an inline add/remove).
    try:
        open_group = int(request.query_params.get("g", ""))
    except (TypeError, ValueError):
        open_group = None
    if open_group not in source_groups:
        open_group = None

    # Per group: a capped preview of assigned senders + total (inline management).
    # Capped so a 500-sender group doesn't dump 500 rows into the page; the
    # dedicated page handles search/full list when total exceeds the preview.
    assigned_preview: dict[int, list] = {}
    group_totals: dict[int, int] = {}
    for g in source_groups:
        items, total = services.list_group_senders(
            session, bot_id, g, page=0, page_size=INLINE_PREVIEW
        )
        assigned_preview[g] = items
        group_totals[g] = total

    return templates.TemplateResponse(
        request,
        "bot_detail.html",
        {
            "bot": bot,
            "routes": routes,
            "source_groups": source_groups,
            "senders_count": senders_count,
            "assigned_preview": assigned_preview,
            "group_totals": group_totals,
            "open_group": open_group,
            "inline_preview": INLINE_PREVIEW,
            "has_password": bool(bot.access_password_hash),
            "error": request.query_params.get("error"),
        },
    )


def _page_ctx(total: int, page: int, page_size: int) -> dict:
    """Common pagination context (1-based display, 0-based `page`)."""
    total_pages = max(1, -(-total // page_size))
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_prev": page > 0,
        "has_next": page + 1 < total_pages,
    }


@router.get(
    "/bots/{bot_id}/senders", response_class=HTMLResponse,
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def senders_page(
    bot_id: int, request: Request, q: str = "", page: int = 0,
    session: Session = Depends(get_session),
):
    bot = session.get(Bot, bot_id)
    if not bot:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    items, total = services.list_senders(session, bot_id, q, page)
    ctx = {
        "bot": bot, "items": items, "q": q,
        "error": request.query_params.get("error"),
        **_page_ctx(total, page, services.PAGE_SIZE),
    }
    return templates.TemplateResponse(request, "senders.html", ctx)


@router.get(
    "/bots/{bot_id}/groups/{source_chat_id}/senders", response_class=HTMLResponse,
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def group_senders_page(
    bot_id: int, source_chat_id: int, request: Request,
    q: str = "", page: int = 0, aq: str = "", apage: int = 0,
    session: Session = Depends(get_session),
):
    bot = session.get(Bot, bot_id)
    if not bot or not services._is_bot_source(session, bot_id, source_chat_id):
        return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)
    picker, ptotal = services.search_unassigned(session, bot_id, source_chat_id, q, page)
    assigned, atotal = services.list_group_senders(session, bot_id, source_chat_id, aq, apage)
    pctx = _page_ctx(ptotal, page, services.PAGE_SIZE)
    actx = _page_ctx(atotal, apage, services.PAGE_SIZE)
    return templates.TemplateResponse(
        request, "group_senders.html",
        {
            "bot": bot, "source_chat_id": source_chat_id,
            "picker": picker, "assigned": assigned,
            "q": q, "aq": aq,
            # picker paging
            "p_total": ptotal, "p_page": page, "p_total_pages": pctx["total_pages"],
            "p_has_prev": pctx["has_prev"], "p_has_next": pctx["has_next"],
            # assigned paging
            "a_total": atotal, "a_page": apage, "a_total_pages": actx["total_pages"],
            "a_has_prev": actx["has_prev"], "a_has_next": actx["has_next"],
        },
    )


@router.post(
    "/bots/{bot_id}/groups/{source_chat_id}/senders/{sender_id}/add",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def group_add(
    bot_id: int, source_chat_id: int, sender_id: int,
    session: Session = Depends(get_session),
):
    services.add_group_sender(session, bot_id, source_chat_id, sender_id)
    return RedirectResponse(
        f"/bots/{bot_id}/groups/{source_chat_id}/senders",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/bots/{bot_id}/groups/{source_chat_id}/senders/{sender_id}/remove",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def group_remove(
    bot_id: int, source_chat_id: int, sender_id: int,
    session: Session = Depends(get_session),
):
    services.remove_group_sender(session, bot_id, source_chat_id, sender_id)
    return RedirectResponse(
        f"/bots/{bot_id}/groups/{source_chat_id}/senders",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _group_detail_redirect(bot_id: int, source_chat_id: int, error: str = "") -> RedirectResponse:
    """Back to the bot-detail page with this group's dropdown open (+ anchor)."""
    q = f"&error={error}" if error else ""
    return RedirectResponse(
        f"/bots/{bot_id}?g={source_chat_id}{q}#g{source_chat_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/bots/{bot_id}/groups/{source_chat_id}/senders-inline/add",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def group_inline_add(
    bot_id: int, source_chat_id: int,
    username: str = Form(...), label: str = Form(""),
    session: Session = Depends(get_session),
):
    if not is_valid_username(username):
        return _group_detail_redirect(bot_id, source_chat_id, "bad_username")
    if label.strip() and not is_valid_label(label):
        return _group_detail_redirect(bot_id, source_chat_id, "bad_label")
    services.add_sender_by_username(session, bot_id, source_chat_id, username, label=label)
    return _group_detail_redirect(bot_id, source_chat_id)


@router.post(
    "/bots/{bot_id}/groups/{source_chat_id}/senders-inline/{sender_id}/remove",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def group_inline_remove(
    bot_id: int, source_chat_id: int, sender_id: int,
    session: Session = Depends(get_session),
):
    services.remove_group_sender(session, bot_id, source_chat_id, sender_id)
    return _group_detail_redirect(bot_id, source_chat_id)


@router.post(
    "/bots/{bot_id}/routes",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def create_route(
    bot_id: int,
    source_chat_id: int = Form(...),
    dest_chat_id: int = Form(...),
    bidirectional: bool = Form(False),
    source_thread_id: str = Form(""),
    dest_thread_id: str = Form(""),
    session: Session = Depends(get_session),
):
    services.add_route(
        session, bot_id, source_chat_id, dest_chat_id, bidirectional,
        source_thread_id=_opt_int(source_thread_id),
        dest_thread_id=_opt_int(dest_thread_id),
    )
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/routes/{route_id}/edit",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def edit_route(
    bot_id: int,
    route_id: int,
    source_chat_id: int = Form(...),
    dest_chat_id: int = Form(...),
    source_thread_id: str = Form(""),
    dest_thread_id: str = Form(""),
    session: Session = Depends(get_session),
):
    services.update_route(
        session, route_id, bot_id, source_chat_id, dest_chat_id,
        source_thread_id=_opt_int(source_thread_id),
        dest_thread_id=_opt_int(dest_thread_id),
    )
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/routes/{route_id}/delete",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def remove_route(bot_id: int, route_id: int, session: Session = Depends(get_session)):
    services.delete_route(session, route_id, bot_id=bot_id)
    return RedirectResponse(f"/bots/{bot_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/delete",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def remove_bot(bot_id: int, session: Session = Depends(get_session)):
    await services.remove_bot(session, bot_id)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/bots/{bot_id}/allowed",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def create_allowed(
    bot_id: int,
    username: str = Form(...),
    label: str = Form(""),
    session: Session = Depends(get_session),
):
    if not is_valid_username(username):
        return RedirectResponse(
            f"/bots/{bot_id}/senders?error=bad_username",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if label.strip() and not is_valid_label(label):
        return RedirectResponse(
            f"/bots/{bot_id}/senders?error=bad_label",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    services.add_allowed_sender(session, bot_id, username, label=label)
    return RedirectResponse(
        f"/bots/{bot_id}/senders", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/bots/{bot_id}/allowed/{allowed_id}/delete",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def remove_allowed(
    bot_id: int, allowed_id: int, session: Session = Depends(get_session)
):
    services.delete_allowed_sender(session, allowed_id, bot_id=bot_id)
    return RedirectResponse(
        f"/bots/{bot_id}/senders", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post(
    "/bots/{bot_id}/allowed/{allowed_id}/label",
    dependencies=[Depends(require_auth), Depends(require_bot_access)],
)
async def edit_allowed_label(
    bot_id: int,
    allowed_id: int,
    label: str = Form(""),
    session: Session = Depends(get_session),
):
    if label.strip() and not is_valid_label(label):
        return RedirectResponse(
            f"/bots/{bot_id}/senders?error=bad_label",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    services.update_allowed_label(session, allowed_id, label, bot_id=bot_id)
    return RedirectResponse(
        f"/bots/{bot_id}/senders", status_code=status.HTTP_303_SEE_OTHER
    )


# --- Super-admin: teams & users management ---

@router.get(
    "/admin", response_class=HTMLResponse,
    dependencies=[Depends(require_super_admin)],
)
async def admin_page(request: Request, session: Session = Depends(get_session)):
    teams = services.list_teams(session)
    team_name_by_id = {t.id: t.name for t in teams}
    users = services.list_users(session)
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "teams": teams,
            "users": users,
            "team_name_by_id": team_name_by_id,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/teams", dependencies=[Depends(require_super_admin)])
async def admin_create_team(
    name: str = Form(...), session: Session = Depends(get_session)
):
    ok = services.create_team(session, name)
    return RedirectResponse(
        "/admin" + ("" if ok else "?error=team"), status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/teams/{team_id}/delete", dependencies=[Depends(require_super_admin)])
async def admin_delete_team(team_id: int, session: Session = Depends(get_session)):
    ok = services.delete_team(session, team_id)
    return RedirectResponse(
        "/admin" + ("" if ok else "?error=team_not_empty"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/users", dependencies=[Depends(require_super_admin)])
async def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    team_id: int = Form(...),
    session: Session = Depends(get_session),
):
    if len(password) < 3:
        return RedirectResponse("/admin?error=pw_short", status_code=status.HTTP_303_SEE_OTHER)
    ok = services.create_user(session, username, password, team_id)
    return RedirectResponse(
        "/admin" + ("" if ok else "?error=user"), status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/admin/users/{user_id}/delete", dependencies=[Depends(require_super_admin)])
async def admin_delete_user(user_id: int, session: Session = Depends(get_session)):
    services.delete_user(session, user_id)
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/users/{user_id}/password", dependencies=[Depends(require_super_admin)])
async def admin_reset_password(
    user_id: int, password: str = Form(...), session: Session = Depends(get_session)
):
    if len(password) < 3:
        return RedirectResponse("/admin?error=pw_short", status_code=status.HTTP_303_SEE_OTHER)
    services.reset_user_password(session, user_id, password)
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
