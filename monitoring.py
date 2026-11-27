"""Sentry logging. Sentry stays off when SENTRY_DSN is not set (local tests)."""

import os

import sentry_sdk
from dotenv import load_dotenv

load_dotenv()


def init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        # No personal-data option: by default Sentry does not send IP addresses or user data.
        # (sentry-sdk 3 removed the send_default_pii option shown in older tutorials.)
        sentry_sdk.init(dsn=dsn)


def log_action(message: str, **details) -> None:
    """Record a business action (employee created, contract signed...) in Sentry.

    Only ids go in the details, never emails or passwords.
    """
    with sentry_sdk.new_scope() as scope:
        scope.set_context("action", details)
        sentry_sdk.capture_message(message, level="info")


def log_exception(error: Exception) -> None:
    sentry_sdk.capture_exception(error)