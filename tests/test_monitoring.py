"""Sentry wiring: started only when a DSN is configured."""

import monitoring


def test_sentry_stays_off_without_dsn(monkeypatch):
    calls = []
    monkeypatch.setenv("SENTRY_DSN", "")
    monkeypatch.setattr(monitoring.sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    monitoring.init_sentry()
    assert calls == []


def test_sentry_starts_with_a_dsn(monkeypatch):
    calls = []
    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/0")
    monkeypatch.setattr(monitoring.sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    monitoring.init_sentry()
    assert calls == [{"dsn": "https://key@o0.ingest.sentry.io/0"}]


def test_exceptions_are_forwarded_to_sentry(monkeypatch):
    sent = []
    monkeypatch.setattr(monitoring.sentry_sdk, "capture_exception", sent.append)
    error = RuntimeError("boom")
    monitoring.log_exception(error)
    assert sent == [error]