# Phase 01 — Web App Skeleton, Config, DB, Crypto, Admin Auth

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: none (first phase)
- Research: [researcher-02](research/researcher-02-saas-architecture.md) (stack, schema, token crypto, auth)
- Docs: FastAPI https://fastapi.tiangolo.com/ ; SQLModel https://sqlmodel.tiangolo.com/ ; cryptography/Fernet https://cryptography.io/en/latest/fernet/

## Overview
- **Date**: 2026-07-27
- **Description**: Stand up the FastAPI project, environment config, DB engine + models (`Bot`, `Route`), Fernet token encryption helper, and single-admin session login. Foundation for all later phases.
- **Priority**: High (blocker)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Single-admin panel → **no `users` table, no RLS**. One `ADMIN_PASSWORD` (hashed compare) + signed session cookie. Big simplification vs the multi-tenant research schema.
- Bot tokens are as sensitive as passwords → **encrypt at rest with Fernet**; KEK from env `BOT_TOKEN_KEK`, never in DB/git.
- Store `telegram_bot_id`, `username`, `token_encrypted`, `status`, `webhook_secret` per bot; routes are directed `(source_chat_id → dest_chat_id)`.
- Keep DB access thin (SQLModel) so SQLite could swap in for local dev.

## Requirements
- `webapp/` package; `requirements.txt` (fastapi, uvicorn[standard], sqlmodel, psycopg[binary], cryptography, jinja2, python-multipart, itsdangerous, python-telegram-bot>=21; dev: pytest, httpx).
- `config.py` reads env: `ADMIN_PASSWORD`, `SESSION_SECRET`, `BOT_TOKEN_KEK`, `DATABASE_URL`, `PUBLIC_URL`, `WEBHOOK_SECRET_SALT`. Fail fast if missing.
- `models.py`: `Bot`, `Route` SQLModel tables.
- `crypto.py`: `encrypt_token()/decrypt_token()` via Fernet(KEK).
- `auth.py`: `/login` (form), `/logout`, `require_admin` dependency using signed session cookie (`SessionMiddleware` / itsdangerous).
- Health route `GET /healthz`.

## Architecture
```
webapp/
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI(), SessionMiddleware, include routers, create_db_and_tables()
│   ├── config.py      # Settings from env (pydantic BaseSettings), fail-fast
│   ├── db.py          # engine, get_session(), init
│   ├── models.py      # Bot, Route
│   ├── crypto.py      # Fernet encrypt/decrypt
│   └── auth.py        # login/logout, require_admin dependency
├── requirements.txt
└── .env.example
```
Models (SQLModel):
```python
class Bot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    telegram_bot_id: int = Field(index=True, unique=True)
    username: str
    token_encrypted: bytes
    webhook_secret: str
    status: str = "active"          # active | disabled | invalid

class Route(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    source_chat_id: int = Field(index=True)
    dest_chat_id: int
    enabled: bool = True
```

## Related code files
- `webapp/app/{main,config,db,models,crypto,auth}.py` (new)
- `webapp/requirements.txt`, `webapp/.env.example` (new)
- Reuse concept from existing `bot/config.py` (fail-fast env pattern).

## Implementation Steps
1. Create `webapp/` tree + `requirements.txt`; venv install.
2. `config.py` — pydantic `Settings`, load env, fail-fast on missing secrets; generate a `Fernet` from `BOT_TOKEN_KEK`.
3. `crypto.py` — encrypt/decrypt helpers + unit-testable.
4. `db.py` + `models.py` — engine, `create_db_and_tables()`.
5. `auth.py` — login form posts password → compare → set session; `require_admin` guards protected routes.
6. `main.py` — wire middleware, routers, startup table creation, `/healthz`.

## Todo list
- [ ] webapp skeleton + requirements + .env.example
- [ ] config.py fail-fast settings + Fernet
- [ ] crypto.py encrypt/decrypt
- [ ] db.py + models.py (Bot, Route)
- [ ] auth.py single-admin login/session + require_admin
- [ ] main.py wiring + /healthz + table creation

## Success Criteria
- `uvicorn app.main:app` boots; `/healthz` returns 200.
- Wrong password rejected; correct password sets session and reaches a protected stub page.
- Round-trip `decrypt_token(encrypt_token(t)) == t`; ciphertext ≠ plaintext.
- Missing env secret raises a clear error at startup.

## Risk Assessment
- **Medium**: KEK mismanagement → tokens unreadable if KEK changes. Document KEK backup. Generate KEK via `Fernet.generate_key()`.
- **Low**: session cookie config (HttpOnly, Secure in prod).

## Security Considerations
- KEK + SESSION_SECRET + ADMIN_PASSWORD only in env, never committed. `.gitignore` covers `.env`.
- Cookies `HttpOnly`, `SameSite=Lax`, `Secure` (behind Caddy TLS). Constant-time password compare.
- Never log tokens or KEK.

## Next steps
Proceed to [Phase 02](phase-02-bot-lifecycle.md) — add/remove bots and register webhooks on top of these models.
