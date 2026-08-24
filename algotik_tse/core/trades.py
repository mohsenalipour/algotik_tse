"""Exact individual-trade retrieval for current and historical sessions.

This module is deliberately separate from :mod:`intraday`.  The legacy
``stock_intraday`` API exposes either today's ticks or historical cumulative
snapshots; ``get_trades`` exposes the provider's individual transaction rows
with one stable schema for both periods.
"""

import datetime
import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from numbers import Integral

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from .._clock import TEHRAN_TZ, tehran_today
from ..exceptions import ConnectionError, DataParsingError, InvalidParameterError
from ..http_client import safe_get
from ..settings import settings
from .conventions import coerce_financial_date
from .resolver import resolve_instrument

TRADE_COLUMNS = [
    "InsCode",
    "Symbol",
    "GregorianDate",
    "JalaliDate",
    "TradeNo",
    "Time",
    "Timestamp",
    "Price",
    "Volume",
    "Value",
    "Canceled",
    "Source",
]

TRADE_RAW_COLUMNS = TRADE_COLUMNS + [
    "qTitNgJ",
    "iSensVarP",
    "pPhSeaCotJ",
    "pPbSeaCotJ",
    "iAnuTran",
    "xqVarPJDrPRf",
    "RawInsCode",
    "RawDate",
    "RawTime",
    "RawCanceled",
]

_RAW_FIELDS = (
    "qTitNgJ",
    "iSensVarP",
    "pPhSeaCotJ",
    "pPbSeaCotJ",
    "iAnuTran",
    "xqVarPJDrPRf",
)


def _typed_empty(raw=False):
    columns = TRADE_RAW_COLUMNS if raw else TRADE_COLUMNS
    frame = pd.DataFrame(columns=columns)
    for column in ("InsCode", "Symbol", "JalaliDate", "Time", "Source"):
        frame[column] = pd.Series(dtype="string")
    frame["GregorianDate"] = pd.Series(dtype="object")
    frame["Timestamp"] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    for column in ("TradeNo", "Price", "Volume", "Value"):
        frame[column] = pd.Series(dtype="Int64")
    frame["Canceled"] = pd.Series(dtype="boolean")
    if raw:
        for column in _RAW_FIELDS:
            frame[column] = pd.Series(dtype="object")
        frame["RawInsCode"] = pd.Series(dtype="object")
        frame["RawDate"] = pd.Series(dtype="object")
        frame["RawTime"] = pd.Series(dtype="object")
        frame["RawCanceled"] = pd.Series(dtype="object")
    return frame


def _request_budget(value):
    candidate = getattr(settings, "trade_max_requests", 250) if value is None else value
    if isinstance(candidate, bool):
        raise InvalidParameterError("max_requests must be a positive integer")
    try:
        numeric = float(candidate)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("max_requests must be a positive integer") from exc
    if not math.isfinite(numeric) or numeric <= 0 or not numeric.is_integer():
        raise InvalidParameterError("max_requests must be a positive integer")
    return int(numeric)


def _date(value, name):
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _requested_dates(start, end, max_dates):
    today = tehran_today()
    if start is None and end is None:
        first = last = today
    elif start is None:
        first = last = _date(end, "end")
    else:
        first = _date(start, "start")
        last = today if end is None else _date(end, "end")
    if first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    if last > today:
        raise InvalidParameterError("end cannot be after Tehran today")
    result = []
    cursor = first
    while cursor <= last:
        # Iran's exchange is closed Thursday and Friday. Official holidays
        # cannot be inferred locally; an empty provider envelope is valid.
        if cursor.weekday() not in (3, 4):
            result.append(cursor)
            if len(result) > max_dates:
                raise InvalidParameterError(
                    "trade range requires at least {} requests, exceeding "
                    "max_requests={}".format(len(result), max_dates)
                )
        cursor += datetime.timedelta(days=1)
    return result


def _integer(value, *, field, context, required=False):
    if value is None or value is pd.NA or value == "":
        if required:
            raise DataParsingError("{}: {} is missing".format(context, field))
        return pd.NA
    if isinstance(value, bool):
        raise DataParsingError("{}: {} must be an integer".format(context, field))
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise DataParsingError("{}: {} must be an integer".format(context, field))
        if abs(value) > 2**53:
            raise DataParsingError(
                "{}: {} float exceeds lossless integer precision".format(context, field)
            )
        return int(value)
    text = str(value).strip()
    try:
        numeric = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise DataParsingError(
            "{}: {} must be an integer".format(context, field)
        ) from exc
    if not numeric.is_finite() or numeric != numeric.to_integral_value():
        raise DataParsingError("{}: {} must be an integer".format(context, field))
    return int(numeric)


def _provider_date(value, requested_date, context):
    if value is None or value is pd.NA or str(value).strip() in {"", "0"}:
        return requested_date
    numeric = _integer(value, field="dEven", context=context, required=True)
    text = str(numeric).zfill(8)
    if len(text) != 8:
        raise DataParsingError("{}: dEven is not YYYYMMDD".format(context))
    try:
        actual = datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise DataParsingError("{}: dEven is not a valid date".format(context)) from exc
    if actual != requested_date:
        raise DataParsingError(
            "{}: provider dEven {} does not match requested {}".format(
                context, text, requested_date.isoformat()
            )
        )
    return actual


def _provider_identity(value, requested_code, context):
    if value is None or value is pd.NA or str(value).strip() in {"", "0"}:
        return requested_code
    actual = str(_integer(value, field="insCode", context=context, required=True))
    if actual != requested_code:
        raise DataParsingError(
            "{}: provider insCode {} does not match requested {}".format(
                context, actual, requested_code
            )
        )
    return requested_code


def _trade_time(value, context):
    raw = _integer(value, field="hEven", context=context, required=True)
    text = str(raw).zfill(6)
    if len(text) != 6:
        raise DataParsingError("{}: hEven is not HHMMSS".format(context))
    try:
        value = datetime.time(int(text[:2]), int(text[2:4]), int(text[4:]))
    except ValueError as exc:
        raise DataParsingError("{}: hEven is not a valid time".format(context)) from exc
    return value


def _canceled(value, context):
    if value is None or value is pd.NA or value == "":
        return pd.NA
    if value is True or value == 1 or str(value).strip().lower() in {"1", "true"}:
        return True
    if value is False or value == 0 or str(value).strip().lower() in {"0", "false"}:
        return False
    raise DataParsingError("{}: canceled must be 0/1 or boolean".format(context))


def _records(payload, envelope, context):
    if not isinstance(payload, Mapping):
        raise DataParsingError("{}: response JSON must be an object".format(context))
    if envelope not in payload:
        raise DataParsingError(
            "{}: response lacks {!r} envelope".format(context, envelope)
        )
    records = payload[envelope]
    if records is None:
        return []
    if not isinstance(records, list):
        raise DataParsingError("{}: {!r} must be a list".format(context, envelope))
    return records


def _parse_day(records, requested_date, identity, source, raw=False):
    rows = []
    for position, record in enumerate(records):
        context = "{}/{} row {}".format(
            identity["InsCode"], requested_date.isoformat(), position
        )
        if not isinstance(record, Mapping):
            raise DataParsingError("{}: trade row must be an object".format(context))
        ins_code = _provider_identity(
            record.get("insCode"), identity["InsCode"], context
        )
        trade_date = _provider_date(record.get("dEven"), requested_date, context)
        trade_no = _integer(
            record.get("nTran"), field="nTran", context=context, required=True
        )
        clock = _trade_time(record.get("hEven"), context)
        price = _integer(record.get("pTran"), field="pTran", context=context)
        volume = _integer(record.get("qTitTran"), field="qTitTran", context=context)
        if price is not pd.NA and price <= 0:
            raise DataParsingError("{}: pTran must be positive".format(context))
        if volume is not pd.NA and volume < 0:
            raise DataParsingError("{}: qTitTran cannot be negative".format(context))
        canceled = _canceled(record.get("canceled"), context)
        row = {
            "InsCode": ins_code,
            "Symbol": identity["Symbol"],
            "GregorianDate": trade_date,
            "JalaliDate": JalaliDate.to_jalali(trade_date).isoformat(),
            "TradeNo": trade_no,
            "Time": clock.isoformat(),
            "Timestamp": pd.Timestamp(
                datetime.datetime.combine(trade_date, clock), tz=TEHRAN_TZ
            ),
            "Price": price,
            "Volume": volume,
            "Value": pd.NA if price is pd.NA or volume is pd.NA else price * volume,
            "Canceled": canceled,
            "Source": source,
        }
        if raw:
            row.update({field: record.get(field) for field in _RAW_FIELDS})
            row.update(
                {
                    "RawInsCode": record.get("insCode"),
                    "RawDate": record.get("dEven"),
                    "RawTime": record.get("hEven"),
                    "RawCanceled": record.get("canceled"),
                }
            )
        rows.append(row)
    return rows


def _cast(frame, raw=False):
    if frame.empty:
        return _typed_empty(raw)
    frame = frame.reindex(columns=TRADE_RAW_COLUMNS if raw else TRADE_COLUMNS).copy()
    for column in ("InsCode", "Symbol", "JalaliDate", "Time", "Source"):
        frame[column] = frame[column].astype("string")
    for column in ("TradeNo", "Price", "Volume", "Value"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    frame["Canceled"] = frame["Canceled"].astype("boolean")
    frame["Timestamp"] = pd.to_datetime(
        frame["Timestamp"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Tehran")
    return frame


def _attach_attrs(frame, *, request_count, failures, coverage, reconciliation):
    frame.attrs.update(
        {
            "request_count": int(request_count),
            "trade_request_count": int(request_count),
            "request_budget_scope": "trade_endpoint_only",
            "resolver_request_count": None,
            "resolver_request_count_known": False,
            "total_request_count": None,
            "failures": tuple(failures),
            "partial": bool(failures),
            "source_coverage": tuple(coverage),
            "no_backfill": False,
            "reconciliation": dict(reconciliation),
            "provider": "tsetmc",
            "identity_validation": "canonical_path_with_nonzero_row_validation",
            "date_validation": "canonical_path_with_nonzero_row_validation",
        }
    )
    return frame


def get_trades(
    symbol=None,
    *,
    ins_code=None,
    start=None,
    end=None,
    include_canceled=False,
    max_requests=None,
    raw=False,
    progress=True,
):
    """Return individual TSETMC trades with one live/history schema.

    Dates accept Jalali or Gregorian ISO forms. With no dates, Tehran today is
    requested. Thursday and Friday are excluded before the hard request-budget
    check, which runs before instrument resolution or any network call.
    ``max_requests`` caps only Trade endpoint calls. The central resolver may
    perform provider requests but does not expose a count, so provenance attrs
    explicitly leave resolver and total request counts unknown.

    Historical requests always use TSETMC's lossless ``.../false`` endpoint.
    Provider rows with null identity or zero date inherit the canonical request
    path; any non-zero identity/date is validated exactly.
    """
    if not isinstance(include_canceled, bool):
        raise InvalidParameterError("include_canceled must be bool")
    if not isinstance(raw, bool):
        raise InvalidParameterError("raw must be bool")
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    budget = _request_budget(max_requests)
    dates = _requested_dates(start, end, budget)
    # Identity remains validated even when the date interval contains only
    # closed weekdays. The range/cap guard above still guarantees that an
    # over-budget request performs no resolver or provider network work.
    reference = resolve_instrument(symbol, ins_code=ins_code, asset_type="auto")
    if reference.asset_type in {"index", "industry"}:
        raise InvalidParameterError("individual trades are unavailable for indices")
    identity = {
        "InsCode": str(reference.ins_code),
        "Symbol": reference.symbol if reference.symbol is not None else symbol,
    }
    identity["Symbol"] = (
        pd.NA if identity["Symbol"] is None else str(identity["Symbol"])
    )
    if not dates:
        result = _attach_attrs(
            _typed_empty(raw),
            request_count=0,
            failures=(),
            coverage=(),
            reconciliation={
                "provider_rows": 0,
                "parsed_rows": 0,
                "canceled_filtered": 0,
                "duplicates_removed": 0,
                "returned_rows": 0,
            },
        )
        result.attrs["resolved_ins_code"] = identity["InsCode"]
        result.attrs["resolved_symbol"] = identity["Symbol"]
        return result

    today = tehran_today()
    rows = []
    failures = []
    coverage = []
    provider_rows = 0
    for position, requested_date in enumerate(dates, start=1):
        is_live = requested_date == today
        source = "tsetmc_trade_live" if is_live else "tsetmc_trade_history"
        envelope = "trade" if is_live else "tradeHistory"
        deven = requested_date.strftime("%Y%m%d")
        url = (
            settings.url_intraday_trades.format(identity["InsCode"])
            if is_live
            else settings.url_trade_history.format(identity["InsCode"], deven)
        )
        if progress:
            print(
                "{}/{}: Getting trades of {} for {}".format(
                    position, len(dates), identity["Symbol"], requested_date
                )
            )
        try:
            response = safe_get(url)
            if response is None or getattr(response, "status_code", None) != 200:
                status = None if response is None else response.status_code
                raise ConnectionError("HTTP status {}".format(status))
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise DataParsingError(
                    "{}/{}: response is not valid JSON".format(
                        identity["InsCode"], deven
                    )
                ) from exc
            records = _records(
                payload, envelope, "{}/{}".format(identity["InsCode"], deven)
            )
            provider_rows += len(records)
            rows.extend(_parse_day(records, requested_date, identity, source, raw=raw))
            coverage.append(
                {
                    "date": requested_date.isoformat(),
                    "source": source,
                    "rows": len(records),
                }
            )
        except DataParsingError:
            raise
        except (ConnectionError, requests.exceptions.RequestException) as exc:
            failures.append(
                {
                    "date": requested_date.isoformat(),
                    "source": source,
                    "error": str(exc),
                }
            )

    frame = _cast(pd.DataFrame(rows), raw=raw)
    parsed_count = len(frame)
    before_dedupe = len(frame)
    if not frame.empty:
        frame = frame.sort_values(
            ["GregorianDate", "TradeNo"], kind="mergesort"
        ).drop_duplicates(["GregorianDate", "TradeNo"], keep="last")
        frame = frame.reset_index(drop=True)
    duplicates_removed = before_dedupe - len(frame)
    before_cancel = len(frame)
    if not include_canceled and not frame.empty:
        frame = frame.loc[frame["Canceled"].ne(True) | frame["Canceled"].isna()]
        frame = frame.reset_index(drop=True)
    canceled_filtered = before_cancel - len(frame)
    return _attach_attrs(
        frame,
        request_count=len(dates),
        failures=failures,
        coverage=coverage,
        reconciliation={
            "provider_rows": provider_rows,
            "parsed_rows": parsed_count,
            "canceled_filtered": canceled_filtered,
            "duplicates_removed": duplicates_removed,
            "returned_rows": len(frame),
        },
    )


def get_live_trades(
    symbol=None,
    *,
    ins_code=None,
    include_canceled=False,
    max_requests=None,
    raw=False,
    progress=True,
):
    """Return Tehran today's individual trades using :func:`get_trades`."""
    return get_trades(
        symbol,
        ins_code=ins_code,
        include_canceled=include_canceled,
        max_requests=max_requests,
        raw=raw,
        progress=progress,
    )


__all__ = ["TRADE_COLUMNS", "TRADE_RAW_COLUMNS", "get_trades", "get_live_trades"]
