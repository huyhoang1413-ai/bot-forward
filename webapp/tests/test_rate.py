"""Configurable rate-limit settings (real Settings, no mocks)."""

from app.config import Settings, get_settings


def test_rate_defaults_are_conservative():
    s = get_settings()
    assert s.rate_overall_per_sec == 25.0
    assert s.rate_group_interval_sec == 3.5


def test_rate_can_be_overridden_via_env(monkeypatch):
    monkeypatch.setenv("RATE_OVERALL_PER_SEC", "10")
    monkeypatch.setenv("RATE_GROUP_INTERVAL_SEC", "5")
    s = Settings()  # fresh instance re-reads environment
    assert s.rate_overall_per_sec == 10.0
    assert s.rate_group_interval_sec == 5.0


def test_limiter_builds_from_configured_values():
    from telegram.ext import AIORateLimiter

    s = get_settings()
    limiter = AIORateLimiter(
        overall_max_rate=s.rate_overall_per_sec,
        overall_time_period=1.0,
        group_max_rate=1,
        group_time_period=s.rate_group_interval_sec,
        max_retries=3,
    )
    assert limiter is not None
