# Phase 03 — Testing, Deployment & Docs

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-scaffold-and-config.md), [Phase 02](phase-02-forwarding-engine.md)
- Research: [researcher-02](research/researcher-02-architecture-ops.md) (deployment, project structure)
- Docs: python-dotenv, systemd https://www.freedesktop.org/software/systemd/man/systemd.service.html , Docker https://docs.docker.com/ , NSSM https://nssm.cc/

## Overview
- **Date**: 2026-07-22
- **Description**: Add real (no-mock) unit tests for config loading and routing logic, write deployment instructions for Windows (Task Scheduler / NSSM), Linux VPS (systemd), and Docker, and author the README with full setup + bot-admin instructions.
- **Priority**: Medium (hardening + usability)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Per project rule: **no mock/fake data in tests** — test pure logic (config parse, RouteTable expansion) with real YAML/dict inputs; do NOT hit Telegram network in unit tests.
- Long polling → no public URL needed; keep-alive is the real deployment concern (auto-restart on crash/reboot).
- Docker `restart: unless-stopped` is the most portable keep-alive; systemd best on Linux VPS; Task Scheduler/NSSM on Windows.

## Requirements
- `tests/test_config.py`: real temp `.env` + `routes.yaml` → assert parsed `Config`; assert `ValueError` on missing token / malformed bridge.
- `tests/test_router.py`: `from_bridges([[1,2],[2,3]])` → assert `destinations(2) == [1,3]`, bidirectional, deduped.
- `Dockerfile` + `docker-compose.yml` (`restart: unless-stopped`, mounts `.env` + `routes.yaml`).
- Deployment docs for all three targets.
- `README.md`: create bot via @BotFather, disable privacy / make admin, get chat ids via `/chatid`, fill config, run.

## Architecture
```
tests/
├── test_config.py
└── test_router.py
Dockerfile
docker-compose.yml
deploy/
├── windows-task-scheduler.md   # + optional NSSM service
├── systemd-bot-forward.service
└── README-deploy.md
README.md
```
`Dockerfile`: `python:3.11-slim`, copy `bot/`, `pip install -r requirements.txt`, `CMD ["python","-m","bot"]`.
`systemd` unit: `Restart=always`, `WorkingDirectory`, `ExecStart=/opt/bot/.venv/bin/python -m bot`, `EnvironmentFile=/opt/bot/.env`.

## Related code files
- `tests/test_config.py`, `tests/test_router.py` (new)
- `Dockerfile`, `docker-compose.yml` (new)
- `deploy/*` (new), `README.md` (new)

## Implementation Steps
1. Write `test_router.py` (pure logic; fastest win).
2. Write `test_config.py` using `tmp_path` fixtures writing real `.env`/`routes.yaml`.
3. Run `pytest` → all green.
4. Write `Dockerfile` + `docker-compose.yml`; build image; run against test token to confirm boot.
5. Write `deploy/` docs: Windows Task Scheduler (+NSSM), systemd unit file, Docker.
6. Write `README.md`: end-to-end setup incl. **bot must be admin in both groups** and privacy-mode note.

## Todo list
- [ ] test_router.py (bidirectional, dedup)
- [ ] test_config.py (valid + error cases, real temp files)
- [ ] pytest green
- [ ] Dockerfile + docker-compose.yml, build boots
- [ ] deploy docs (Windows / systemd / Docker)
- [ ] README.md full setup guide

## Success Criteria
- `pytest` passes with real inputs, no mocks/network.
- `docker compose up` starts the bot and it logs loaded bridges.
- A new user can follow README from zero (create bot → admin in groups → config → run) and get a working bridge.

## Risk Assessment
- **Low**. Test brittleness if config API changes → keep tests on stable public functions.
- Docker on Windows needs Desktop/WSL2 → note alternative (Task Scheduler) for pure-Windows users.

## Security Considerations
- `.gitignore` prevents committing `.env`, real `routes.yaml`, `bot.log`.
- Docker/systemd read token via env/EnvironmentFile, not baked into image.
- README warns: never share bot token; revoke via @BotFather if leaked.

## Next steps
- v2 backlog (out of current scope): edit-sync via SQLite message-id map, album/media-group grouping (`send_media_group`), keyword/media filters, header/footer, dynamic `/addroute` admin commands.
