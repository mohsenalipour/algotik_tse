"""Major-shareholder snapshots for one TSETMC instrument.

TSETMC labels a position with the next trading session after the trades and
transfers that produced it. The public ``shareholders(date=...)`` API keeps
its long-standing contract: ``date`` is the trade date and the returned
``date`` is the provider's effective date. Explicit trade/effective columns
remove that otherwise easy-to-miss distinction.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from algotik_tse._clock import tehran_today
from algotik_tse.core.conventions import coerce_financial_date
from algotik_tse.core.resolver import normalize_instrument_text
from algotik_tse.core.search import search_stock
from algotik_tse.exceptions import (
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)
from algotik_tse.http_client import safe_get
from algotik_tse.settings import settings

SHAREHOLDER_COLUMNS = [
    "share_holder_name",
    "number_of_shares",
    "percentage_of_shares",
    "change_state",
    "change_amount",
    "date",
    "share_holder_id",
    "trade_date",
    "effective_date",
    "trade_date_jalali",
    "effective_date_jalali",
    "identity_quality",
    "change_quality",
    "source",
]

_SOURCE_LATEST = "tsetmc_instrument_shareholder_last"
_SOURCE_DATED = "tsetmc_instrument_shareholder_by_date"
_FREQUENCIES = frozenset(("daily", "weekly", "monthly"))


def _date(value, name="date"):
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _date_text(value):
    if value is None or value is pd.NA:
        return pd.NA
    return value.strftime("%Y%m%d")


def _jalali_text(value):
    if value is None or value is pd.NA:
        return pd.NA
    return JalaliDate.to_jalali(value).isoformat()


def _provider_date(value):
    try:
        text = str(int(value)).zfill(8)
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataParsingError("TSETMC shareholder date must be YYYYMMDD") from exc


def _number(value, default=float("nan")):
    if value is None or value is pd.NA:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _integer(value, default=pd.NA):
    number = _number(value)
    if not math.isfinite(number):
        return default
    return int(number)


def _positive_int(value, name, maximum=None):
    if isinstance(value, bool):
        raise InvalidParameterError("{} must be a positive integer".format(name))
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(
            "{} must be a positive integer".format(name)
        ) from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise InvalidParameterError("{} must be a positive integer".format(name))
    result = int(number)
    if maximum is not None and result > maximum:
        raise InvalidParameterError("{} cannot exceed {}".format(name, maximum))
    return result


def _records(response, envelope, context):
    if response is None or getattr(response, "status_code", 200) != 200:
        raise ConnectionError("{} request failed".format(context))
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise DataParsingError("{} returned invalid JSON".format(context)) from exc
    if not isinstance(payload, Mapping) or envelope not in payload:
        raise DataParsingError("{} lacks {!r} envelope".format(context, envelope))
    rows = payload[envelope]
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise DataParsingError("{} envelope must be a list".format(context))
    if any(not isinstance(row, Mapping) for row in rows):
        raise DataParsingError("{} rows must be objects".format(context))
    return rows


def _fetch_records(url, envelope, context):
    try:
        response = safe_get(url)
    except requests.exceptions.RequestException as exc:
        raise ConnectionError("{} request failed".format(context)) from exc
    return _records(response, envelope, context)


def _resolve(symbol, ins_code, asset_type):
    selector = symbol
    if (selector is None or str(selector).strip() == "") and ins_code is not None:
        selector = str(ins_code)
    web_id = search_stock(
        search_txt="" if selector is None else selector,
        ins_code=ins_code,
        asset_type=asset_type,
    )
    if web_id is None or str(web_id).strip() == "":
        raise StockNotFoundError("instrument was not found")
    return str(web_id)


def _historical_groups(rows):
    groups = {}
    for row in rows:
        value_date = _provider_date(row.get("dEven"))
        groups.setdefault(value_date, []).append(row)
    return groups


def _unique_holdings(rows):
    """Map exact normalized names to holdings only when identity is unique."""
    values = {}
    duplicates = set()
    for row in rows or []:
        key = normalize_instrument_text(row.get("shareHolderName"))
        if not key or key in values:
            duplicates.add(key)
            continue
        values[key] = _integer(row.get("numberOfShares"))
    for key in duplicates:
        values.pop(key, None)
    return values


def _snapshot_frame(
    rows,
    *,
    effective_date,
    trade_date=None,
    previous_rows=None,
    source,
    date_is_provider_supplied=True,
):
    previous = _unique_holdings(previous_rows)
    current_keys = [
        normalize_instrument_text(row.get("shareHolderName")) for row in rows
    ]
    current_counts = pd.Series(current_keys, dtype="object").value_counts().to_dict()
    output = []
    for row, key in zip(rows, current_keys):
        if not key or row.get("numberOfShares") is None:
            raise DataParsingError(
                "shareholder rows require shareHolderName and numberOfShares"
            )
        holdings = _integer(row.get("numberOfShares"))
        if previous_rows is None:
            change_amount = _integer(row.get("changeAmount"), default=0)
            change_quality = "provider_value"
        elif key and current_counts.get(key) == 1 and key in previous:
            change_amount = holdings - previous[key]
            change_quality = "exact_normalized_name"
        else:
            # A newly visible major holder did not necessarily acquire its
            # entire disclosed position on this day. Leave the daily change
            # unknown instead of inventing it from a missing prior row.
            change_amount = pd.NA
            change_quality = "unmatched_or_ambiguous"
        token = _integer(row.get("shareHolderShareID"))
        if token is pd.NA:
            fallback = _integer(row.get("shareHolderID"))
            token = fallback if fallback is not pd.NA and fallback != 0 else pd.NA
        output.append(
            {
                "share_holder_name": normalize_instrument_text(
                    row.get("shareHolderName")
                ),
                "number_of_shares": holdings,
                "percentage_of_shares": _number(row.get("perOfShares")),
                "change_state": _integer(row.get("change")),
                "change_amount": change_amount,
                # ``date`` is retained for backward compatibility and is the
                # provider effective date, not the transaction date.
                "date": _date_text(effective_date),
                "share_holder_id": token,
                "trade_date": _date_text(trade_date),
                "effective_date": _date_text(effective_date),
                "trade_date_jalali": _jalali_text(trade_date),
                "effective_date_jalali": _jalali_text(effective_date),
                "identity_quality": "snapshot_record_token",
                "change_quality": change_quality,
                "source": source,
            }
        )
    frame = pd.DataFrame(output, columns=SHAREHOLDER_COLUMNS)
    for column in (
        "number_of_shares",
        "change_state",
        "change_amount",
        "share_holder_id",
    ):
        frame[column] = pd.array(frame[column], dtype="Int64")
    frame["percentage_of_shares"] = pd.to_numeric(
        frame["percentage_of_shares"], errors="coerce"
    ).astype("Float64")
    frame.attrs.update(
        {
            "source": source,
            "date_semantics": (
                "effective_date is the next published trading-session label "
                "after trade_date"
            ),
            "date_is_provider_supplied": bool(date_is_provider_supplied),
            "change_includes_non_trade_transfers": True,
            "during_session_represents_previous_completed_session": True,
            "is_authoritative_register": False,
            "official_verification_required": True,
            "stable_shareholder_id_available": False,
            "share_holder_id_scope": "provider snapshot/history token",
            "is_complete_major_shareholder_list": False,
        }
    )
    return frame


def _dated_snapshot(web_id, requested_date):
    rows = _fetch_records(
        settings.url_share_holders_history.format(
            web_id, requested_date.strftime("%Y%m%d")
        ),
        "shareShareholder",
        "dated shareholders",
    )
    groups = _historical_groups(rows)
    if not groups:
        return _snapshot_frame(
            [],
            effective_date=requested_date,
            trade_date=requested_date,
            source=_SOURCE_DATED,
        )
    dates = sorted(groups)
    trade_candidates = [value for value in dates if value <= requested_date]
    trade_date = max(trade_candidates) if trade_candidates else dates[0]
    later = [value for value in dates if value > trade_date]
    effective_date = min(later) if later else trade_date
    previous_rows = groups.get(trade_date) if effective_date != trade_date else None
    frame = _snapshot_frame(
        groups[effective_date],
        effective_date=effective_date,
        trade_date=trade_date,
        previous_rows=previous_rows,
        source=_SOURCE_DATED,
    )
    frame.attrs.update(
        {
            "requested_date": requested_date.isoformat(),
            "provider_dates": tuple(value.isoformat() for value in dates),
            "trade_date": trade_date.isoformat(),
            "effective_date": effective_date.isoformat(),
        }
    )
    return frame


def shareholders(
    symbol="",
    date=None,
    include_id=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
):
    """Return the latest or post-close major-shareholder snapshot.

    ``date`` retains the historical API semantics: it is the trade date. The
    returned legacy ``date`` column is the TSETMC effective label, normally the
    next trading session. TSETMC states that changes may include non-trade
    transfers and that the public list is informational rather than an
    authoritative ownership register.
    """
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "shh_id" in kwargs:
        include_id = kwargs.pop("shh_id")
    if not isinstance(include_id, bool):
        print("Error processing shareholders: include_id must be bool")
        return None
    try:
        web_id = _resolve(symbol, ins_code, asset_type)
        if date is None:
            rows = _fetch_records(
                settings.url_last_share_holders.format(web_id),
                "shareHolder",
                "latest shareholders",
            )
            today = tehran_today()
            # The latest endpoint reports dEven=0. Keep the legacy retrieval
            # date, but mark it as client-derived in metadata.
            frame = _snapshot_frame(
                rows,
                effective_date=today,
                source=_SOURCE_LATEST,
                date_is_provider_supplied=False,
            )
            frame.attrs["effective_date"] = today.isoformat()
        else:
            frame = _dated_snapshot(web_id, _date(date))
        frame.attrs["ins_code"] = web_id
        if not include_id:
            frame = frame.drop(columns=["share_holder_id"])
        return frame
    except StockNotFoundError:
        print("Stock Not Found, Please try again ...")
        return None
    except requests.exceptions.RequestException:
        print("Connection Error!!!")
        return None
    except Exception as exc:
        print("Error processing shareholders: {}".format(exc))
        return None


def _select_frequency(sessions, frequency):
    if frequency == "daily":
        return sessions
    grouped = {}
    for value in sessions:
        if frequency == "weekly":
            # Iranian exchange week begins on Saturday.
            key = value - datetime.timedelta(days=(value.weekday() - 5) % 7)
        else:
            key = _jalali_text(value)[:7]
        grouped[key] = value
    return sorted(grouped.values())


def get_shareholder_history(
    symbol="",
    start=None,
    end=None,
    frequency="daily",
    max_requests=60,
    include_id=False,
    progress=True,
    *,
    ins_code=None,
    asset_type="auto",
):
    """Return major-shareholder snapshots over an effective-date range.

    ``start`` and ``end`` refer to TSETMC's published effective dates. For
    daily data, one dated request normally contains two consecutive effective
    snapshots. The planner queries every other session, verifies coverage and
    retries missing dates within the explicit ``max_requests`` budget.
    """
    if start is None or end is None:
        raise InvalidParameterError("start and end are required")
    first = _date(start, "start")
    last = _date(end, "end")
    if first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    if not isinstance(frequency, str) or frequency.lower() not in _FREQUENCIES:
        raise InvalidParameterError("frequency must be daily, weekly, or monthly")
    frequency = frequency.lower()
    budget = _positive_int(max_requests, "max_requests", 1000)
    if not isinstance(include_id, bool) or not isinstance(progress, bool):
        raise InvalidParameterError("include_id and progress must be bool")
    web_id = _resolve(symbol, ins_code, asset_type)

    from algotik_tse.core.market_reference import get_trading_calendar

    calendar = get_trading_calendar(
        start=first - datetime.timedelta(days=14),
        end=last,
        market="all",
        include_closed=False,
        limit=5000,
    )
    all_sessions = sorted(
        {value for value in calendar.loc[calendar["IsTradingDay"], "GregorianDate"]}
    )
    sessions = [value for value in all_sessions if first <= value <= last]
    selected = _select_frequency(sessions, frequency)
    if not selected:
        result = _snapshot_frame([], effective_date=first, source=_SOURCE_DATED)
        result.attrs.update(
            {
                "frequency": frequency,
                "coverage_start": None,
                "coverage_end": None,
                "shareholder_requests_used": 0,
                "max_requests": budget,
            }
        )
        if not include_id:
            result = result.drop(columns=["share_holder_id"])
        return result

    planned = selected[::2] if frequency == "daily" else selected
    if len(planned) > budget:
        raise InvalidParameterError(
            "requested history needs at least {} shareholder requests, exceeding "
            "max_requests={}".format(len(planned), budget)
        )
    selected_set = set(selected)
    snapshots = {}
    requests_used = 0
    for index, query_date in enumerate(planned, 1):
        if progress:
            print(
                "Fetching shareholder snapshot pair {}/{}...".format(
                    index, len(planned)
                )
            )
        rows = _fetch_records(
            settings.url_share_holders_history.format(
                web_id, query_date.strftime("%Y%m%d")
            ),
            "shareShareholder",
            "shareholder history",
        )
        requests_used += 1
        for value_date, value_rows in _historical_groups(rows).items():
            if value_date in selected_set:
                snapshots[value_date] = value_rows

    missing = [value for value in selected if value not in snapshots]
    if requests_used + len(missing) > budget:
        raise InvalidParameterError(
            "provider pair coverage left {} missing dates; retries would exceed "
            "max_requests={}".format(len(missing), budget)
        )
    for query_date in missing:
        rows = _fetch_records(
            settings.url_share_holders_history.format(
                web_id, query_date.strftime("%Y%m%d")
            ),
            "shareShareholder",
            "shareholder history",
        )
        requests_used += 1
        groups = _historical_groups(rows)
        if query_date in groups:
            snapshots[query_date] = groups[query_date]

    unresolved = [value for value in selected if value not in snapshots]
    frames = []
    # The first selected snapshot has no predecessor inside the requested
    # range, so its change must remain unknown rather than use the provider's
    # unreliable zero-valued ``changeAmount`` field.
    previous_rows = []
    previous_session = {
        value: all_sessions[index - 1] if index else None
        for index, value in enumerate(all_sessions)
    }
    for value_date in selected:
        if value_date not in snapshots:
            continue
        frames.append(
            _snapshot_frame(
                snapshots[value_date],
                effective_date=value_date,
                trade_date=previous_session.get(value_date),
                previous_rows=previous_rows,
                source=_SOURCE_DATED,
            )
        )
        previous_rows = snapshots[value_date]
    if frames:
        result = pd.concat(frames, ignore_index=True)
        result = result.sort_values(
            ["effective_date", "percentage_of_shares"],
            ascending=[True, False],
            ignore_index=True,
        )
    else:
        result = _snapshot_frame([], effective_date=first, source=_SOURCE_DATED)
    result.attrs.update(
        {
            "source": _SOURCE_DATED,
            "ins_code": web_id,
            "frequency": frequency,
            "date_basis": "effective_date",
            "coverage_start": selected[0].isoformat(),
            "coverage_end": selected[-1].isoformat(),
            "requested_snapshot_count": len(selected),
            "returned_snapshot_count": len(snapshots),
            "missing_effective_dates": tuple(value.isoformat() for value in unresolved),
            "shareholder_requests_used": requests_used,
            "max_requests": budget,
            "pair_request_optimization": frequency == "daily",
            "change_period": frequency,
            "change_identity_method": "exact normalized holder name only",
            "change_includes_non_trade_transfers": True,
            "during_session_represents_previous_completed_session": True,
            "is_authoritative_register": False,
            "official_verification_required": True,
            "stable_shareholder_id_available": False,
            "is_complete_major_shareholder_list": False,
        }
    )
    if not include_id:
        result = result.drop(columns=["share_holder_id"])
    if progress:
        print(
            "Done. {} effective snapshots fetched with {} shareholder requests.".format(
                len(snapshots), requests_used
            )
        )
    return result


__all__ = ["SHAREHOLDER_COLUMNS", "shareholders", "get_shareholder_history"]
