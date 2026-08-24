"""Internal Tehran-aware clock helpers.

The package supports Python 3.8, where :mod:`zoneinfo` is not guaranteed to
exist.  Iran no longer observes daylight saving time, so a fixed UTC+03:30
fallback is correct for current market observations when the IANA database is
unavailable.  ``_utc_now`` is deliberately a tiny seam for deterministic tests.
"""

import datetime

try:  # Python 3.9+ with an available IANA time-zone database.
    from zoneinfo import ZoneInfo

    try:
        TEHRAN_TZ = ZoneInfo("Asia/Tehran")
    except Exception:  # pragma: no cover - depends on host tzdata availability
        TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
except ImportError:  # pragma: no cover - Python 3.8
    TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))


def _utc_now():
    """Return the current aware UTC datetime (test injection seam)."""

    return datetime.datetime.now(datetime.timezone.utc)


def tehran_now():
    """Return the current timezone-aware datetime in Tehran."""

    now = _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return now.astimezone(TEHRAN_TZ)


def tehran_today():
    """Return the current Tehran calendar date."""

    return tehran_now().date()
