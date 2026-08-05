"""Shared UTC helpers for contract defaults."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)
