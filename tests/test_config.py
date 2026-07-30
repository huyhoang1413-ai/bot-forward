"""Tests for load_config — uses real temp files, no mocks."""

import pytest

from bot.config import load_config


def _write(tmp_path, env_body: str, routes_body: str):
    env = tmp_path / ".env"
    routes = tmp_path / "routes.yaml"
    env.write_text(env_body, encoding="utf-8")
    routes.write_text(routes_body, encoding="utf-8")
    return env, routes


def test_valid_config(tmp_path):
    env, routes = _write(
        tmp_path,
        "BOT_TOKEN=123:abc\n",
        "bridges:\n  - [-100111, -100222]\nlog_level: DEBUG\n",
    )
    cfg = load_config(env, routes)
    assert cfg.token == "123:abc"
    assert cfg.bridges == [(-100111, -100222)]
    assert cfg.log_level == "DEBUG"


def test_missing_token_raises(tmp_path):
    env, routes = _write(tmp_path, "BOT_TOKEN=\n", "bridges:\n  - [1, 2]\n")
    with pytest.raises(ValueError, match="BOT_TOKEN"):
        load_config(env, routes)


def test_missing_routes_file_raises(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=123:abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Routes file not found"):
        load_config(env, tmp_path / "does_not_exist.yaml")


def test_empty_bridges_raises(tmp_path):
    env, routes = _write(tmp_path, "BOT_TOKEN=123:abc\n", "bridges: []\n")
    with pytest.raises(ValueError, match="No bridges"):
        load_config(env, routes)


def test_bridge_with_wrong_length_raises(tmp_path):
    env, routes = _write(
        tmp_path, "BOT_TOKEN=123:abc\n", "bridges:\n  - [1, 2, 3]\n"
    )
    with pytest.raises(ValueError, match="pair of two chat ids"):
        load_config(env, routes)


def test_bridge_to_self_raises(tmp_path):
    env, routes = _write(tmp_path, "BOT_TOKEN=123:abc\n", "bridges:\n  - [5, 5]\n")
    with pytest.raises(ValueError, match="links a group to itself"):
        load_config(env, routes)


def test_invalid_log_level_raises(tmp_path):
    env, routes = _write(
        tmp_path,
        "BOT_TOKEN=123:abc\n",
        "bridges:\n  - [1, 2]\nlog_level: LOUD\n",
    )
    with pytest.raises(ValueError, match="Invalid log_level"):
        load_config(env, routes)
