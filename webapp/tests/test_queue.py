"""Pure retry/backoff logic for the outbox worker (no mocks)."""

from app.queue import MAX_ATTEMPTS, backoff_seconds, plan_retry


def test_backoff_grows_and_caps_at_60():
    assert backoff_seconds(1) == 2
    assert backoff_seconds(2) == 4
    assert backoff_seconds(3) == 8
    assert backoff_seconds(10) == 60  # capped


def test_plan_retry_reschedules_pending_before_max():
    status, attempts, delay = plan_retry(attempts=0)
    assert status == "pending"
    assert attempts == 1
    assert delay == backoff_seconds(1)


def test_plan_retry_honors_retry_after():
    status, attempts, delay = plan_retry(attempts=1, retry_after=7.0)
    assert status == "pending"
    assert delay == 7.0


def test_plan_retry_marks_failed_after_max_attempts():
    status, attempts, _ = plan_retry(attempts=MAX_ATTEMPTS - 1)
    assert status == "failed"
    assert attempts == MAX_ATTEMPTS
