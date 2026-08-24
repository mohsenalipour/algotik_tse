"""Financial date and compounding conventions used by :mod:`algotik_tse`.

The helpers in this module deliberately use Gregorian calendar arithmetic.
Jalali inputs are accepted as a convenience, converted once, and then the
selected day-count convention is applied without inventing a business-day or
Iranian-holiday calendar.
"""

import calendar
import datetime as _datetime
import math

import pandas as pd
from persiantools.jdatetime import JalaliDate

SUPPORTED_DAY_COUNTS = (
    "ACT/365F",
    "ACT/360",
    "30E/360",
    "ACT/ACT-ISDA",
)
SUPPORTED_COMPOUNDING = ("effective", "continuous", "nominal")


def validate_frequency(value, name="frequency"):
    """Return a strictly positive integer frequency without truncation."""
    if isinstance(value, bool):
        raise ValueError("{} must be a positive integer".format(name))
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValueError("{} must be a positive integer".format(name))
    if not math.isfinite(numeric) or numeric <= 0 or not numeric.is_integer():
        raise ValueError("{} must be a positive integer".format(name))
    return int(numeric)


def coerce_financial_date(value, name="date"):
    """Return *value* as a Gregorian :class:`datetime.date`.

    Accepted values are ``date``/``datetime``/``pandas.Timestamp`` and ISO-like
    Gregorian or Jalali strings (``YYYY-MM-DD``, ``YYYY/MM/DD``, ``YYYYMMDD``).
    Years 1300--1599 are interpreted as Jalali. Timestamps are reduced to their
    calendar date; no timezone or settlement-time assumption is made.
    """
    if value is None:
        raise ValueError("{} is required".format(name))
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, _datetime.datetime):
        return value.date()
    if isinstance(value, _datetime.date):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("{} is required".format(name))
    normalized = text.replace("/", "-")
    if len(normalized) == 8 and normalized.isdigit():
        normalized = "{}-{}-{}".format(normalized[:4], normalized[4:6], normalized[6:])
    try:
        year_text, month_text, day_text = normalized.split("-")[:3]
        year, month, day = int(year_text), int(month_text), int(day_text)
    except (TypeError, ValueError):
        raise ValueError("{} must be a Gregorian or Jalali ISO date".format(name))
    try:
        if 1300 <= year <= 1599:
            return JalaliDate(year, month, day).to_gregorian()
        return _datetime.date(year, month, day)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid {}: {!r}".format(name, value)) from exc


def _is_leap(year):
    return calendar.isleap(year)


def day_count_fraction(start, end, convention="ACT/365F"):
    """Calculate the year fraction between two dates.

    Supported conventions are ``ACT/365F``, ``ACT/360``, ``30E/360`` and
    ``ACT/ACT-ISDA``. The interval is start-inclusive/end-exclusive, matching
    ordinary Python date subtraction. ``end`` must be strictly after ``start``.
    """
    start_date = coerce_financial_date(start, "start")
    end_date = coerce_financial_date(end, "end")
    if end_date <= start_date:
        raise ValueError("end must be after start")
    key = str(convention).strip().upper().replace(" ", "")
    aliases = {
        "ACT365F": "ACT/365F",
        "ACT/365": "ACT/365F",
        "ACT360": "ACT/360",
        "30E360": "30E/360",
        "ACTACTISDA": "ACT/ACT-ISDA",
        "ACT/ACT": "ACT/ACT-ISDA",
    }
    key = aliases.get(key.replace("-", ""), key)
    if key == "ACT/365F":
        return (end_date - start_date).days / 365.0
    if key == "ACT/360":
        return (end_date - start_date).days / 360.0
    if key == "30E/360":
        d1 = min(start_date.day, 30)
        d2 = min(end_date.day, 30)
        days_360 = (
            (end_date.year - start_date.year) * 360
            + (end_date.month - start_date.month) * 30
            + d2
            - d1
        )
        return days_360 / 360.0
    if key == "ACT/ACT-ISDA":
        fraction = 0.0
        cursor = start_date
        while cursor.year < end_date.year:
            boundary = _datetime.date(cursor.year + 1, 1, 1)
            fraction += (boundary - cursor).days / (
                366.0 if _is_leap(cursor.year) else 365.0
            )
            cursor = boundary
        fraction += (end_date - cursor).days / (
            366.0 if _is_leap(cursor.year) else 365.0
        )
        return fraction
    raise ValueError(
        "unsupported day-count convention {!r}; choose from {}".format(
            convention, ", ".join(SUPPORTED_DAY_COUNTS)
        )
    )


def discount_factor_from_rate(rate, time, compounding="effective", frequency=1):
    """Convert an annual rate and year fraction to a discount factor."""
    rate = float(rate)
    time = float(time)
    if not math.isfinite(rate) or not math.isfinite(time):
        raise ValueError("rate and time must be finite")
    if time < 0:
        raise ValueError("time cannot be negative")
    kind = str(compounding).strip().lower()
    if kind == "continuous":
        return math.exp(-rate * time)
    if kind == "effective":
        if rate <= -1.0:
            raise ValueError("effective annual rate must be greater than -1")
        return (1.0 + rate) ** (-time)
    if kind == "nominal":
        frequency = validate_frequency(frequency)
        if rate <= -frequency:
            raise ValueError("nominal annual rate must be greater than -frequency")
        return (1.0 + rate / frequency) ** (-frequency * time)
    raise ValueError(
        "unsupported compounding {!r}; choose from {}".format(
            compounding, ", ".join(SUPPORTED_COMPOUNDING)
        )
    )


def rate_from_discount_factor(
    discount_factor, time, compounding="effective", frequency=1
):
    """Convert a positive discount factor to an annualized rate."""
    discount_factor = float(discount_factor)
    time = float(time)
    if not math.isfinite(discount_factor) or not math.isfinite(time):
        raise ValueError("discount_factor and time must be finite")
    if discount_factor <= 0:
        raise ValueError("discount_factor must be positive")
    if time <= 0:
        raise ValueError("time must be positive")
    continuous = -math.log(discount_factor) / time
    kind = str(compounding).strip().lower()
    if kind == "continuous":
        return continuous
    if kind == "effective":
        return math.exp(continuous) - 1.0
    if kind == "nominal":
        frequency = validate_frequency(frequency)
        return frequency * (math.exp(continuous / frequency) - 1.0)
    raise ValueError(
        "unsupported compounding {!r}; choose from {}".format(
            compounding, ", ".join(SUPPORTED_COMPOUNDING)
        )
    )


__all__ = [
    "SUPPORTED_DAY_COUNTS",
    "SUPPORTED_COMPOUNDING",
    "coerce_financial_date",
    "day_count_fraction",
    "discount_factor_from_rate",
    "rate_from_discount_factor",
    "validate_frequency",
]
