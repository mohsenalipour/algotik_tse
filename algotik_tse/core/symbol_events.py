"""TSETMC-native event timeline for one exact instrument."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
from collections.abc import Iterable
from numbers import Integral

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from .._clock import tehran_now
from ..exceptions import ConnectionError, DataParsingError, InvalidParameterError
from ..http_client import safe_get
from ..settings import settings
from .conventions import coerce_financial_date
from .price_adjustments import get_price_adjustments
from .resolver import normalize_instrument_text, resolve_instrument

SYMBOL_EVENT_COLUMNS = [
    "EventID",
    "EventType",
    "InsCode",
    "Symbol",
    "Name",
    "GregorianDate",
    "JalaliDate",
    "Timestamp",
    "Title",
    "Description",
    "OldValue",
    "NewValue",
    "ChangeValue",
    "Source",
    "FetchedAt",
]

_VALID_KINDS = ("messages", "capital_changes", "price_adjustments")


def _typed_empty():
    frame = pd.DataFrame(columns=SYMBOL_EVENT_COLUMNS)
    for column in (
        "EventID",
        "EventType",
        "InsCode",
        "Symbol",
        "Name",
        "JalaliDate",
        "Title",
        "Description",
        "Source",
    ):
        frame[column] = pd.Series(dtype="string")
    frame["GregorianDate"] = pd.Series(dtype="object")
    for column in ("OldValue", "NewValue", "ChangeValue"):
        frame[column] = pd.Series(dtype="Float64")
    for column in ("Timestamp", "FetchedAt"):
        frame[column] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    return frame


def _cast(rows):
    if not rows:
        return _typed_empty()
    result = pd.DataFrame(rows).reindex(columns=SYMBOL_EVENT_COLUMNS)
    empty = _typed_empty()
    for column in SYMBOL_EVENT_COLUMNS:
        if column in {"Timestamp", "FetchedAt"}:
            result[column] = pd.to_datetime(
                result[column], errors="coerce", utc=True
            ).dt.tz_convert("Asia/Tehran")
        else:
            result[column] = result[column].astype(empty[column].dtype)
    return result


def _date(value, name):
    if value is None:
        return None
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _provider_date(value, context):
    if isinstance(value, bool) or isinstance(value, float):
        raise DataParsingError("{} must be an exact YYYYMMDD date".format(context))
    if isinstance(value, Integral):
        text = str(int(value))
    else:
        text = "" if value is None else str(value).strip()
    if len(text) != 8 or not text.isascii() or not text.isdigit():
        raise DataParsingError("{} must be an exact YYYYMMDD date".format(context))
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise DataParsingError("{} is not a valid date".format(context)) from exc


def _number(value, field, context):
    if value is None or isinstance(value, bool):
        raise DataParsingError("{}.{} must be numeric".format(context, field))
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataParsingError("{}.{} must be numeric".format(context, field)) from exc
    if not math.isfinite(result) or result < 0:
        raise DataParsingError(
            "{}.{} must be finite and non-negative".format(context, field)
        )
    return result


def _response_payload(response, envelope, context):
    try:
        payload = response.json()
    except (ValueError, AttributeError, TypeError) as exc:
        raise DataParsingError("{} returned invalid JSON".format(context)) from exc
    records = payload.get(envelope) if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise DataParsingError(
            "{} response requires a {} list".format(context, envelope)
        )
    return records


def _fetch_json(url, envelope, context):
    try:
        response = safe_get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ConnectionError("{} request failed".format(context)) from exc
    return _response_payload(response, envelope, context)


def _kinds(value):
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable):
        values = list(value)
    else:
        raise InvalidParameterError("kinds must be a string or iterable of strings")
    normalized = []
    for item in values:
        key = str(item).strip().lower()
        if key not in _VALID_KINDS:
            raise InvalidParameterError(
                "kinds values must be among: {}".format(", ".join(_VALID_KINDS))
            )
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise InvalidParameterError("kinds must not be empty")
    return tuple(normalized)


def _limit(value):
    if isinstance(value, bool):
        raise InvalidParameterError("limit must be a non-negative integer")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("limit must be a non-negative integer") from exc
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise InvalidParameterError("limit must be a non-negative integer")
    return int(number)


def _stable_event_id(kind, values):
    serialized = json.dumps(
        [kind, *values], ensure_ascii=False, separators=(",", ":"), default=str
    )
    return "{}:{}".format(
        kind, hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
    )


def _message_timestamp(day, value, context):
    if value in (None, ""):
        return pd.NaT
    if isinstance(value, bool):
        raise DataParsingError("{}.hEven must be HHMMSS".format(context))
    try:
        raw = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataParsingError("{}.hEven must be HHMMSS".format(context)) from exc
    hour, minute, second = raw // 10000, raw % 10000 // 100, raw % 100
    try:
        return pd.Timestamp(
            datetime.datetime.combine(day, datetime.time(hour, minute, second)),
            tz="Asia/Tehran",
        )
    except ValueError as exc:
        raise DataParsingError("{}.hEven is invalid".format(context)) from exc


def _base_row(identity, event_date, fetched_at):
    return {
        "InsCode": identity.ins_code,
        "Symbol": identity.symbol or pd.NA,
        "Name": identity.name or pd.NA,
        "GregorianDate": event_date,
        "JalaliDate": JalaliDate.to_jalali(event_date).isoformat(),
        "FetchedAt": fetched_at,
    }


def get_symbol_events(
    symbol=None,
    start=None,
    end=None,
    kinds=_VALID_KINDS,
    limit=100,
    ascending=False,
    progress=True,
    *,
    ins_code=None,
    max_requests=3,
):
    """Return a unified TSETMC-native timeline for one exact instrument.

    Supported kinds are supervisor ``messages``, ``capital_changes`` and
    ``price_adjustments``.  Assembly, DPS, board and financial disclosures are
    deliberately excluded because they are Codal products rather than native
    TSETMC market data.
    """
    selected_kinds = _kinds(kinds)
    first, last = _date(start, "start"), _date(end, "end")
    if first is not None and last is not None and first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    row_limit = _limit(limit)
    if not isinstance(ascending, bool):
        raise InvalidParameterError("ascending must be bool")
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    request_budget = _limit(max_requests)
    if request_budget < len(selected_kinds):
        raise InvalidParameterError(
            (
                "selected kinds require {} source requests, "
                "exceeding max_requests={}"
            ).format(len(selected_kinds), request_budget)
        )
    identity = resolve_instrument(
        symbol,
        ins_code=ins_code,
        asset_type="auto",
        require_active=False,
    )
    fetched_at = tehran_now()
    rows = []

    if "messages" in selected_kinds:
        records = _fetch_json(
            settings.url_symbol_messages.format(identity.ins_code),
            "msg",
            "TSETMC symbol messages",
        )
        for index, record in enumerate(records):
            context = "msg[{}]".format(index)
            if not isinstance(record, dict):
                raise DataParsingError("{} must be an object".format(context))
            event_date = _provider_date(record.get("dEven"), context + ".dEven")
            if first is not None and event_date < first:
                continue
            if last is not None and event_date > last:
                continue
            provider_id = record.get("tseMsgIdn")
            event_id = (
                "message:{}".format(provider_id)
                if provider_id not in (None, "")
                else _stable_event_id(
                    "message",
                    [
                        identity.ins_code,
                        event_date,
                        record.get("hEven"),
                        record.get("tseTitle"),
                        record.get("tseDesc"),
                    ],
                )
            )
            rows.append(
                {
                    **_base_row(identity, event_date, fetched_at),
                    "EventID": event_id,
                    "EventType": "supervisor_message",
                    "Timestamp": _message_timestamp(
                        event_date, record.get("hEven"), context
                    ),
                    "Title": normalize_instrument_text(record.get("tseTitle")) or pd.NA,
                    "Description": normalize_instrument_text(record.get("tseDesc"))
                    or pd.NA,
                    "OldValue": pd.NA,
                    "NewValue": pd.NA,
                    "ChangeValue": pd.NA,
                    "Source": "tsetmc_symbol_messages",
                }
            )

    if "capital_changes" in selected_kinds:
        records = _fetch_json(
            settings.url_capital_increase.format(identity.ins_code),
            "instrumentShareChange",
            "TSETMC capital changes",
        )
        seen = set()
        for index, record in enumerate(records):
            context = "instrumentShareChange[{}]".format(index)
            if not isinstance(record, dict):
                raise DataParsingError("{} must be an object".format(context))
            event_date = _provider_date(record.get("dEven"), context + ".dEven")
            old = _number(record.get("numberOfShareOld"), "numberOfShareOld", context)
            new = _number(record.get("numberOfShareNew"), "numberOfShareNew", context)
            key = (event_date, old, new)
            if key in seen:
                continue
            seen.add(key)
            if first is not None and event_date < first:
                continue
            if last is not None and event_date > last:
                continue
            rows.append(
                {
                    **_base_row(identity, event_date, fetched_at),
                    "EventID": _stable_event_id(
                        "capital_change", [identity.ins_code, *key]
                    ),
                    "EventType": "capital_change",
                    "Timestamp": pd.NaT,
                    "Title": "تغییر تعداد سهام شرکت",
                    "Description": pd.NA,
                    "OldValue": old,
                    "NewValue": new,
                    "ChangeValue": new - old,
                    "Source": "tsetmc_instrument_share_change",
                }
            )

    if "price_adjustments" in selected_kinds:
        adjustments = get_price_adjustments(
            ins_code=identity.ins_code,
            start=first,
            end=last,
            progress=progress,
        )
        for record in adjustments.to_dict(orient="records"):
            event_date = record["GregorianDate"]
            old = record["UnadjustedClosingPrice"]
            new = record["AdjustedClosingPrice"]
            rows.append(
                {
                    **_base_row(identity, event_date, fetched_at),
                    "EventID": _stable_event_id(
                        "price_adjustment",
                        [
                            identity.ins_code,
                            event_date,
                            old,
                            new,
                            record.get("CorporateTypeCode"),
                        ],
                    ),
                    "EventType": "price_adjustment",
                    "Timestamp": pd.NaT,
                    "Title": "تعدیل قیمت ثبت شده در TSETMC",
                    "Description": pd.NA,
                    "OldValue": old,
                    "NewValue": new,
                    "ChangeValue": old - new,
                    "Source": "tsetmc_price_adjustment",
                }
            )

    result = _cast(rows)
    if not result.empty:
        result = result.drop_duplicates("EventID", keep="first")
        result = result.sort_values(
            ["GregorianDate", "Timestamp", "EventID"],
            ascending=[ascending, ascending, ascending],
            kind="mergesort",
            na_position="last",
        )
        if row_limit:
            result = result.head(row_limit)
        result = result.reset_index(drop=True)
    result.attrs.update(
        {
            "analysis": "symbol_events",
            "source": "tsetmc_native_market_data",
            "sources": selected_kinds,
            "ins_code": identity.ins_code,
            "symbol": identity.symbol,
            "identity_provenance": identity.provenance,
            "fetched_at": fetched_at,
            "request_count": len(selected_kinds),
            "max_requests": request_budget,
            "codal_included": False,
            "excluded_disclosure_kinds": (
                "assemblies",
                "dividends",
                "board_members",
                "financial_statements",
            ),
            "price_adjustment_is_not_confirmed_dps": True,
            "no_fuzzy_join": True,
        }
    )
    return result


__all__ = ["SYMBOL_EVENT_COLUMNS", "get_symbol_events"]
