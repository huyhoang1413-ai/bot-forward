# Research: Auth + RBAC for Multi-User FastAPI with Starlette Sessions

**Date:** 2026-09-17  
**Scope:** Login flow design, session identity, FastAPI dependency guards, password management, security hardening, guard migration.

---

## 1. Login Flow Design

### Recommended Pattern: DB-First with `.env` Fallback

**Why:** Constant-time protection + username enumeration prevention (OWASP).

```python
# auth.py
import hmac
import hashlib
from fastapi import HTTPException, status
from app.pw import verify_password
from app.models import User

async def authenticate_user(username: str, password: str, db_session) -> dict:
    """
    Try DB user first, then fallback to .env super-admin.
    Returns: {"user_id": int | None, "username": str, "is_admin": bool, "team_id": int | None}
    Timing-safe: always hash even if user not found.
    """
    # 1. Try database lookup
    db_user = await db_session.execute(
        select(User).where(User.username == username)
    )
    db_user = db_user.scalar_one_or_none()
    
    if db_user and verify_password(password, db_user.password_hash):
        return {
            "user_id": db_user.id,
            "username": db_user.username,
            "is_admin": False,
            "team_id": db_user.team_id,
        }
    
    # 2. Constant-time hash even if user not found (prevent timing enumeration)
    dummy_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        b"dummy_salt",
        100_000,
    )
    
    # 3. Try .env super-admin (static comparison, constant-time)
    env_user = os.getenv("ADMIN_USERNAME")
    env_pass = os.getenv("ADMIN_PASSWORD")
    
    if username == env_user and hmac.compare_digest(password, env_pass):
        return {
            "user_id": None,
            "username": env_user,
            "is_admin": True,
            "team_id": None,
        }
    
    # 4. Always raise 401 (same response regardless)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )
```

### Session Keys Recommendation (KISS)

Store minimal, constant keys in `request.session`:
- `user_id`: `int | None` (None = super-admin from .env)
- `username`: `str`
- `is_admin`: `bool` (True only if .env super-admin)
- `team_id`: `int | None` (None = super-admin or no team)

**Why:** No redundant role lookups on each request; immutable during session.

---

## 2. Session Identity for `.env` Admin

### Recommendation: Pure `.env` (No User Row)

**Option A (Recommended — KISS):**  
Keep super-admin as pure `.env` identity with `user_id=None`, `team_id=None`.

**Pros:**
- Single source of truth for super-admin (`.env`).
- No DB migration needed.
- Clear separation: admin (`.env`) vs. team members (DB).

**Cons:**
- Must handle `user_id=None` throughout (audit logs, bot creation, etc.).

**Option B (Considered, Not Recommended):**  
Create a hardcoded User row for `.env` admin (e.g., `id=1, username=ADMIN_USERNAME, team_id=NULL`).

**Cons:**
- Complicates startup (seed logic), sync with `.env`, and password changes.
- YAGNI: adds row without clear benefit.

### Edge Cases for Super-Admin

1. **Bot creation:** Super-admin creates bot without `team_id`. Routes check `team_id=None` → allow all bots.
2. **Audit logging:** Store `user_id=None` or special marker for `.env` admin.
3. **Password changes:** Super-admin password only via `.env` edit + restart.

---

## 3. FastAPI Dependency Guards

### Three Dependencies (Separation of Concerns)

```python
# dependencies.py
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

async def require_auth(request: Request) -> dict:
    """Any logged-in user (DB or .env admin)."""
    session_data = request.session
    if not session_data.get("user_id") and not session_data.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"location": "/login"}
        )
    return session_data

async def require_super_admin(request: Request) -> dict:
    """Only .env super-admin (is_admin=True, team_id=None)."""
    session_data = request.session
    if not session_data.get("is_admin") or session_data.get("team_id") is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return session_data

async def require_team_bot_access(
    bot_id: int,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """User can access bot only if: super-admin OR bot.team_id == user.team_id."""
    if session_data.get("is_admin"):
        return session_data
    
    bot = await db.execute(select(Bot).where(Bot.id == bot_id))
    bot = bot.scalar_one_or_none()
    if not bot or bot.team_id != session_data.get("team_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    
    return session_data
```

### Redirect vs. 403

- **303 redirect to /login:** Session missing entirely (use `require_auth`).
- **403 Forbidden:** User logged in but lacks permission (use `require_super_admin`).

### Combining with Existing `require_bot_access`

Existing per-bot password unlock (`require_bot_access`) gates per-session temporary access. Stack dependencies:

```python
@app.post("/bots/{bot_id}/unlock")
async def unlock_bot(
    bot_id: int,
    password: str,
    session_data: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Unlock bot with password; set session["bot_{bot_id}_unlocked"] = True."""
    session_data_check = await require_team_bot_access(bot_id, session_data, db)
    # ... password check, then session["bot_{bot_id}_unlocked"] = True
```

---

## 4. Password & Account Management

### Reuse `pw.py` Functions

Existing PBKDF2 `hash_password` / `verify_password` are sufficient. No change needed.

### Admin Endpoints for User/Team Creation

```python
# Only super-admin can create users
@app.post("/admin/users", dependencies=[Depends(require_super_admin)])
async def create_user(
    username: str,
    password: str,
    team_id: int | None,
    db: AsyncSession = Depends(get_db),
):
    """Create new user or team member."""
    # Validation
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password too short")
    
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Create
    hashed = hash_password(password)
    user = User(username=username, password_hash=hashed, team_id=team_id)
    db.add(user)
    await db.commit()
    return {"id": user.id, "username": user.username}

@app.post("/admin/teams", dependencies=[Depends(require_super_admin)])
async def create_team(name: str, db: AsyncSession = Depends(get_db)):
    """Create new team."""
    team = Team(name=name)
    db.add(team)
    await db.commit()
    return {"id": team.id, "name": team.name}
```

### Self Change-Password (Optional, Deferred)

Recommend **defer** to Phase 2. Requires:
- `/me/password` endpoint (POST old_password, new_password).
- Rate-limiting to prevent brute force.
- Session not invalidated (or re-auth flow).

---

## 5. Security Hardening

### Session Fixation

**Starlette does NOT auto-rotate session IDs on login.** Manually rotate:

```python
# login endpoint
@app.post("/login")
async def login(username: str, password: str, request: Request, db: AsyncSession = Depends(get_db)):
    auth_data = await authenticate_user(username, password, db)
    
    # CRITICAL: Rotate session to prevent fixation
    request.session.clear()
    request.session["user_id"] = auth_data["user_id"]
    request.session["username"] = auth_data["username"]
    request.session["is_admin"] = auth_data["is_admin"]
    request.session["team_id"] = auth_data["team_id"]
    
    return {"status": "ok"}
```

### Logout

Clear session entirely:

```python
@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}
```

### Constant-Time Comparison

- Use `hmac.compare_digest()` for `.env` admin password (shown above).
- Use `pw.verify_password()` for DB users (already timing-safe if using PBKDF2).

### Username Enumeration Prevention

- Always hash password (dummy if user not found) before checking `.env` admin.
- Return generic "Invalid credentials" for all failure cases.
- Avoid DB exceptions that leak user existence (wrap in generic 401).

### SessionMiddleware Cookie Flags

Already configured correctly in current setup:
```python
SessionMiddleware(
    app,
    secret_key=SECRET_KEY,
    https_only=True,  # prod only
    same_site="lax",  # or "strict"
    max_age=86400,    # 24h
)
```

**Verify in prod:** `https_only=True` enforced.

---

## 6. Guard Migration: `require_admin` → `require_auth` + `require_super_admin`

### Migration Map

| Old Route | Old Guard | New Guard | Notes |
|-----------|-----------|-----------|-------|
| `/login` | None | None | Entry point |
| `/bots` | `require_admin` | `require_auth` | Any logged-in user sees their team's bots |
| `/admin/users` | `require_admin` | `require_super_admin` | Only `.env` admin |
| `/admin/teams` | `require_admin` | `require_super_admin` | Only `.env` admin |
| `/bots/{id}` | `require_admin` + `require_bot_access` | `require_auth` + `require_team_bot_access` + `require_bot_access` | Stacked checks |

### Renaming Steps

1. Rename `require_admin()` → `require_auth()`.
2. Add new `require_super_admin()`.
3. Update all route decorators.
4. Test: Ensure team users can't access other teams' bots.

---

## 7. Sources & References

- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [FastAPI Security Tutorial](https://fastapi.tiangolo.com/tutorial/security/)
- [Starlette SessionMiddleware Documentation](https://www.starlette.io/middleware/)
- [FastAPI Dependency Injection & RBAC (Auth0)](https://developer.auth0.com/resources/code-samples/api/fastapi/basic-role-based-access-control)

---

## Unresolved Questions

1. **Session Backend:** Should sessions persist server-side (Redis/DB) or remain client-side (signed cookies)? Current cookie-only model works for small teams; clarify scaling requirement.
2. **Bot Password vs. Team Auth:** Should per-bot unlock passwords be deprecated in favor of team-level auth? Current design stacks both; clarify intended UX.
3. **Audit Logging Scope:** Should all user/team creation/deletion/password changes be logged? Not specified; recommend yes for compliance.
4. **Self Change-Password:** Phase 1 or Phase 2? Deferred unless explicitly required.
5. **IP-Based Session Validation:** Should sessions be bound to user IP (resilience vs. mobile users)? Current design doesn't; OWASP recommends optional.
6. **Rate-Limiting on Login:** Should login be rate-limited (brute force protection)? Not mentioned; recommend yes.
