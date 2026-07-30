# Phase 01 — Project Scaffold & Configuration

## Context links
- Parent plan: [plan.md](plan.md)
- Research: [researcher-01](research/researcher-01-libraries-api.md), [researcher-02](research/researcher-02-architecture-ops.md)
- Depends on: none (first phase)
- Docs: python-telegram-bot https://docs.python-telegram-bot.org/ ; python-dotenv https://pypi.org/project/python-dotenv/ ; PyYAML https://pyyaml.org/

## Overview
- **Date**: 2026-07-22
- **Description**: Create project skeleton, dependency list, secret/config loading (`.env` + `routes.yaml`), routing-table build, and logging. Foundation for the forwarding engine.
- **Priority**: High (blocker for all)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Only the bot token is a secret → `.env`. Routes are non-secret structured data → `routes.yaml` (readable, comments).
- Bidirectional bridge = load a `bridges: [[A, B], …]` list and expand each pair into two directed routes A→B and B→A.
- Supergroup chat_ids are large negatives (`-100…`); must be stored as ints.
- Config must fail fast with a clear error if token missing or a bridge malformed (junior-dev friendly).

## Requirements
- Python 3.11+.
- `requirements.txt`: `python-telegram-bot[rate-limiter]>=21`, `PyYAML>=6`, `python-dotenv>=1`; dev: `pytest>=8`.
- `.env.example` with `BOT_TOKEN=` placeholder; real `.env` git-ignored.
- `config/routes.example.yaml` documenting bridge format.
- Config loader validates: token present, each bridge has exactly 2 distinct int chat_ids, no duplicate directed routes.

## Architecture
```
bot/
├── __init__.py
├── __main__.py     # (stub here; filled in Phase 02)
├── config.py       # load_config() -> Config(token, bridges, log_level)
└── router.py       # (created Phase 02)
config/routes.example.yaml
.env.example
.gitignore
requirements.txt
```
`config.py`:
- `load_config(env_path, yaml_path) -> Config` dataclass: `token: str`, `bridges: list[tuple[int,int]]`, `log_level: str`.
- `setup_logging(level)` → console + `RotatingFileHandler("bot.log")`, format `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.

`routes.example.yaml`:
```yaml
# Each bridge links two groups; messages flow BOTH ways.
# Get a group's id by adding the bot and sending /chatid in that group.
bridges:
  - [-1001111111111, -1002222222222]
# add more pairs as needed
log_level: INFO
```

## Related code files
- `bot/config.py` (new)
- `config/routes.example.yaml` (new)
- `.env.example`, `.gitignore`, `requirements.txt`, `bot/__init__.py`, `bot/__main__.py` (new stubs)

## Implementation Steps
1. Create folder tree + empty `bot/__init__.py`.
2. Write `requirements.txt` and create/activate a venv; `pip install -r requirements.txt`.
3. Write `.env.example` (`BOT_TOKEN=`) and `.gitignore` (`.env`, `bot.log`, `__pycache__/`, `.venv/`, `routes.yaml`).
4. Write `config/routes.example.yaml` as above.
5. Implement `bot/config.py`: dotenv load, YAML parse, `Config` dataclass, validation (raise `ValueError` with clear messages), `setup_logging()`.
6. Add `bot/__main__.py` stub that calls `load_config()` and logs the loaded bridges (verifies wiring).

## Todo list
- [ ] Folder tree + package init
- [ ] requirements.txt + venv install
- [ ] .env.example + .gitignore
- [ ] routes.example.yaml
- [ ] config.py loader + validation + logging
- [ ] __main__ stub prints loaded config

## Success Criteria
- `python -m bot` with a valid `.env` + `routes.yaml` logs the parsed bridge list without error.
- Missing token or malformed bridge raises a clear `ValueError` (verified manually).
- No secret committed (`.env` git-ignored).

## Risk Assessment
- **Low**. Main risk: wrong chat_id type (str vs int) → enforce int cast in validation. YAML indentation errors → ship a working example.

## Security Considerations
- Token only in `.env`, never in YAML or code. `.gitignore` covers `.env` and real `routes.yaml`.
- Do not log the token (log only bridge ids + count).

## Next steps
Proceed to [Phase 02](phase-02-forwarding-engine.md) — build routing table + message handler on top of this config.
