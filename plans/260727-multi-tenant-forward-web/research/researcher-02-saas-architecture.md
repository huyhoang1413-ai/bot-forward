# Web SaaS Architecture for Multi-Tenant Telegram Bot Forwarding

## 1. Secure Bot Token Storage

**Problem:** Telegram bot tokens grant full control of user bots. Never store plaintext.

**Recommended Approach:**
- **Encryption at Rest:** Use Fernet (AES-128-CBC + HMAC-SHA256) from Python's `cryptography` library for simplicity
- **Alternative:** AES-256-GCM if higher assurance needed (requires 12-byte nonce per encryption, more complex)
- **Key Management:**
  - Store Master Encryption Key (KEK) in environment variables or AWS Secrets Manager / HashiCorp Vault
  - Never commit KEK to git
  - Rotate KEK every 30-90 days (re-encrypt all tokens with new key)
  - Use unique, random nonce for every encryption operation (AES-GCM)
- **In Transit:** Enforce TLS 1.3+ for all API endpoints
- **Database:** Store only encrypted ciphertext + metadata (bot_id, created_at, updated_at)

**Implementation Pattern:**
```python
from cryptography.fernet import Fernet
kek = os.getenv("BOT_TOKEN_KEK")  # Load from env/secrets manager
cipher = Fernet(kek)
encrypted_token = cipher.encrypt(user_bot_token.encode())
# Store encrypted_token in DB
```

**References:** [Comparitech Fernet](https://www.comparitech.com/blog/information-security/what-is-fernet/), [API Payload Security](https://medium.com/@raditya.mit/api-payload-security-encryption-strategies-every-developer-should-know-e9eb051c1ef9), [API Key Management](https://www.serverion.com/uncategorized/10-api-key-management-best-practices/)

---

## 2. Recommended Python Web Stack

**Stack:** FastAPI + SQLModel + PostgreSQL

**Why:**
- **FastAPI:** Async-native (matches python-telegram-bot's async design), automatic OpenAPI docs, fast validation via Pydantic
- **SQLModel:** Bridges Pydantic + SQLAlchemy, cleaner ORM for FastAPI integration
- **PostgreSQL:** ACID compliance, Row-Level Security (RLS) for tenant isolation, proven at scale

**Frontend (MVP-focused):**
- **Server-rendered (recommended for MVP):** Jinja2 templates + HTMX for interactivity without JS complexity
- **SPA fallback:** React/Next.js only if team prefers, adds deployment complexity (separate build step, CDN)

**References:** [FastAPI Multi-Tenant SaaS](https://medium.com/@hjparmar1944/fastapi-multi-tenant-saas-without-pain-9ef960085bf4), [Multi-Tenant Architecture with FastAPI](https://medium.com/@koushiksathish3/multi-tenant-architecture-with-fastapi-design-patterns-and-pitfalls-aa3f9e75bf8c), [Creating Multi-Tenant SaaS APIs with FastAPI and SQLModel](https://medium.com/@connect.hashblock/creating-multi-tenant-saas-apis-with-fastapi-and-sqlmodel-257061379f4e)

---

## 3. Data Model Schema

```sql
-- Users (SaaS accounts)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

-- Bots (user's registered Telegram bots)
CREATE TABLE bots (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    telegram_bot_id BIGINT NOT NULL,
    bot_username VARCHAR(255),
    token_encrypted BYTEA NOT NULL,  -- Fernet-encrypted token
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(owner_id, telegram_bot_id)
);

-- Forwarding routes/bridges
CREATE TABLE routes (
    id SERIAL PRIMARY KEY,
    bot_id INTEGER NOT NULL REFERENCES bots(id),
    source_chat_id BIGINT NOT NULL,
    dest_chat_id BIGINT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(bot_id, source_chat_id, dest_chat_id)
);

-- Webhooks tracking (for PT bot update delivery)
CREATE TABLE webhook_log (
    id SERIAL PRIMARY KEY,
    bot_id INTEGER NOT NULL REFERENCES bots(id),
    update_id BIGINT NOT NULL,
    status VARCHAR(50),
    processed_at TIMESTAMP DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE bots ENABLE ROW LEVEL SECURITY;
ALTER TABLE routes ENABLE ROW LEVEL SECURITY;

-- RLS Policy: users see only their own bots
CREATE POLICY bot_owner_isolation ON bots
    USING (owner_id = current_user_id());  -- Requires user context in session/JWT
```

---

## 4. Website Authentication

**MVP Approach (simplest):**
- **Email + Password:** Use bcrypt for hashing, store password_hash only
- **Session-based:** Use secure, HttpOnly cookies (FastAPI `SessionMiddleware`)
- **Alternative:** Magic link (email-only, no password) for faster onboarding

**Lightweight OAuth fallback:** GitHub/Google OAuth for "Sign up with GitHub" (optional, not MVP critical)

**Multi-Tenant Isolation:**
- Middleware injects `current_user_id` from session/JWT
- RLS policies enforce: user cannot query/modify bots/routes they don't own
- Frontend: Load only their own bots/routes

---

## 5. Onboarding Flow & Chat ID Discovery

**Step 1: Token Registration**
- User pastes bot token in web UI
- Backend calls `bot.get_me()` to validate token (fails immediately if fake)
- Save encrypted token + telegram_bot_id to `bots` table
- Return success

**Step 2: Bot Admin Setup**
- UI shows instructions: "Add bot to your group as administrator"
- User adds bot to source group in Telegram

**Step 3: Chat ID Discovery**
- **Option A (Cleaner):** Bot responds to `/chatid` command → returns group's `chat_id` + `chat_title`
- **Option B:** Listen to all updates, extract `chat_id` from first message received, store in webhook_log
- Recommend **Option A** for explicit user control; less noisy

**Step 4: Configure Bridge**
- User enters source_chat_id + dest_chat_id in web UI
- Backend validates user owns the bot and both chat_ids are real
- Create route record
- Forwarding active immediately

**Webhook Delivery & Ordering:**
Telegram delivers webhook updates in order and waits for HTTP 200 response before sending next update. This is critical for message ordering in multi-tenant setups. Each bot instance must acknowledge quickly.

**References:** [Python-Telegram-Bot Webhooks](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks), [Multi-Bot Design](https://911programming.wordpress.com/2019/04/24/python-telegram-bot-webhook-handler-a-multi-bot-multi-language-design-4/), [Telegram Bot on Cloud Run](https://medium.com/@alexander.tyutin/running-a-production-ready-webhook-telegram-bot-on-google-cloud-run-a-security-first-approach-57b589ff8e48)

---

## 6. Deployment Architecture (VPS-focused, MVP cost-minimal)

**Recommended: Docker Compose on VPS**

```yaml
version: '3.8'
services:
  web:
    build: .
    environment:
      DATABASE_URL: postgresql://user:pass@db/bot_forward
      BOT_TOKEN_KEK: ${BOT_TOKEN_KEK}
      WEBHOOK_SECRET: ${WEBHOOK_SECRET}
    ports:
      - "8000:8000"
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: bot_forward
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  reverse_proxy:
    image: caddy:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  caddy_data:
```

**Reverse Proxy (Caddy):**
- Terminates TLS (Let's Encrypt auto-renewal)
- Routes `/webhook/bot/<bot_id>` → FastAPI instance
- Handles multiple bot webhooks (bypasses Telegram's 4-port limit)

**Cost Estimate:**
- Linode/DigitalOcean/Hetzner: $5–10/mo for single-core VPS
- Domain: $10–12/year
- S3/backups: negligible at MVP scale

**Scaling Path (when needed):**
- Multi-container FastAPI (Docker Swarm/Kubernetes)
- CloudFlare CDN for static assets
- AWS RDS for managed Postgres
- Separate webhook receiver + forwarding worker queues (Redis-backed)

**References:** [Deploy Telegram Bot on VPS](https://cloud.servermall.com/blog/how-to-host-a-telegram-bot-on-a-vps-pythonnode-js-systemd-docker-webhook-and-https/), [Webhook + Reverse Proxy Design](https://medium.com/@erdavtyan/architecting-highly-scalable-serverless-telegram-bots-5da2bb8fab61)

---

## Summary: MVP Feature Set

| Feature | Approach | Effort |
|---------|----------|--------|
| Token storage | Fernet encryption + PostgreSQL | ~2 days |
| User auth | Email+password + sessions | ~1 day |
| Bot registration | Token validation via `get_me()` | ~1 day |
| Chat ID discovery | `/chatid` bot command | ~1 day |
| Route configuration | Web UI form + RLS isolation | ~2 days |
| Webhook server | FastAPI + Caddy reverse proxy | ~2 days |
| Deployment | Docker Compose on VPS | ~1 day |

**Total MVP scope: ~10 dev days (single developer)**

---

## Unresolved Questions

1. **Key Rotation Procedure:** Exactly how to re-encrypt all stored tokens during KEK rotation without downtime?
2. **Multi-Region Failover:** Should webhook backup handler catch missed updates via polling `/getUpdates` if webhook fails?
3. **Rate Limits:** Telegram rate-limits message sends (30 msgs/sec per bot per chat). How to queue forwarder jobs?
4. **Admin Dashboard:** Should MVPs include logs/analytics (message count, errors) or defer to v2?
5. **Bot Token Compromise:** Recovery flow if user's token leaks (revoke, regenerate, re-register)?
