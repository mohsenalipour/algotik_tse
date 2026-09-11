"""Market-wide reference, calendar, auction and bulk daily data.

The public JSON endpoints are preferred whenever they expose the required
contract.  TSETMC's exact TOP feed is only available to web-service
subscribers; credentials are accepted per call and are never persisted.
"""

import datetime
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from persiantools import characters
from persiantools.jdatetime import JalaliDate

from .._clock import tehran_today
from ..exceptions import ConnectionError, DataParsingError, InvalidParameterError
from ..http_client import safe_get
from ..settings import settings
from .conventions import coerce_financial_date

_MARKETS = {
    "tse": (1, "tse", "32097828799138957"),
    "bourse": (1, "tse", "32097828799138957"),
    "بورس": (1, "tse", "32097828799138957"),
    "ifb": (2, "ifb", "43685683301327984"),
    "farabourse": (2, "ifb", "43685683301327984"),
    "فرابورس": (2, "ifb", "43685683301327984"),
}

_TSE_PREFIXES = {"IRO1", "IRR1", "IRT1"}
_IFB_PREFIXES = {
    "IRO3",
    "IRO5",
    "IRO6",
    "IRO7",
    "IRR3",
    "IRR5",
    "IRR7",
    "IRT3",
    "IRB3",
    "IRB4",
}
_OTHER_PREFIXES = {"IRO4", "IRO9", "IROF", "IROA", "IROB", "IRB5", "IRB6", "IRB7"}
_COMMODITY_PREFIXES = {"IRBK", "IRK1", "IRTK"}
_ENERGY_PREFIXES = {"IRBE", "IRBZ", "IRTE", "IREK", "IRE9"}

_STOCK_PREFIXES = {"IRO1", "IRO2", "IRO3", "IRO4", "IRO5", "IRO7"}
_RIGHT_PREFIXES = {"IRR1", "IRR3", "IRR5", "IRR7"}
_FUND_PREFIXES = {"IRT1", "IRT3", "IRTE", "IRTK"}
_BOND_PREFIXES = {"IRB3", "IRB4", "IRB5", "IRB6", "IRB7", "IRBS"}
_OPTION_PREFIXES = {"IRO9", "IROF", "IROA", "IROB"}
_FUTURE_PREFIXES = {"IRO4"}

CALENDAR_COLUMNS = [
    "Market",
    "Flow",
    "GregorianDate",
    "JalaliDate",
    "IsTradingDay",
    "ReferenceIndex",
    "ReferenceInsCode",
    "Source",
]

MARKET_VALUE_COLUMNS = [
    "Market",
    "Flow",
    "GregorianDate",
    "JalaliDate",
    "MarketValue",
    "Change",
    "ChangePct",
    "Source",
]

INDEX_IMPACT_COLUMNS = [
    "Market",
    "Flow",
    "GregorianDate",
    "JalaliDate",
    "Rank",
    "InsCode",
    "Symbol",
    "Name",
    "Close",
    "Impact",
    "Direction",
    "AbsSharePct",
    "Source",
]

MARKET_TRADE_COLUMNS = [
    "Market",
    "MarketClassification",
    "AssetType",
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "GregorianDate",
    "JalaliDate",
    "TradeCount",
    "Volume",
    "Value",
    "Open",
    "High",
    "Low",
    "Close",
    "Last",
    "PreviousClose",
    "Change",
    "ChangePct",
    "Source",
]

MARKET_ACTIVITY_COLUMNS = [
    "Market",
    "GregorianDate",
    "JalaliDate",
    "InstrumentCount",
    "TradedInstrumentCount",
    "TradeCount",
    "Volume",
    "Value",
    "AverageTradeValue",
    "Source",
]

INSTRUMENT_MASTER_COLUMNS = [
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "EnglishName",
    "CompanyCode",
    "CompanyISIN",
    "Market",
    "MarketGroup",
    "Industry",
    "AssetType",
    "InstrumentStatus",
    "Active",
    "Source",
]

INSTRUMENT_CHANGE_COLUMNS = [
    "ChangeType",
    "InsCode",
    "Field",
    "OldValue",
    "NewValue",
    "Symbol",
    "Source",
]

TOP_COLUMNS = [
    "Market",
    "Flow",
    "InsCode",
    "Symbol",
    "Name",
    "GregorianDate",
    "JalaliDate",
    "Time",
    "TheoreticalOpeningPrice",
    "TheoreticalVolume",
    "RemainderSide",
    "RemainderVolume",
    "TheoreticalBuyVolume",
    "TheoreticalBuyPrice",
    "TheoreticalSellPrice",
    "TheoreticalSellVolume",
    "ChangePct",
    "Source",
]


def _empty(columns):
    return pd.DataFrame(columns=columns)


def _date(value, name):
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _integer(value, default=pd.NA):
    if value is None or value is pd.NA or str(value).strip() in {"", "None", "nan"}:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return int(number)


def _number(value, default=float("nan")):
    if value is None or value is pd.NA or str(value).strip() in {"", "None", "nan"}:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _provider_date(value, fallback=None):
    raw = fallback if value in (None, "", 0, "0") else value
    if isinstance(raw, datetime.date):
        return raw
    text = str(_integer(raw, default="")).zfill(8)
    if len(text) != 8 or not text.isdigit():
        raise DataParsingError("TSETMC date must be YYYYMMDD")
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise DataParsingError("TSETMC date is invalid: {}".format(text)) from exc


def _jalali(value):
    return JalaliDate.to_jalali(value).isoformat()


def _market_specs(market, allow_all=True):
    if not isinstance(market, str):
        raise InvalidParameterError("market must be a string")
    key = market.strip().lower()
    if allow_all and key in {"all", "همه"}:
        return [(1, "tse", "32097828799138957"), (2, "ifb", "43685683301327984")]
    if key not in _MARKETS:
        valid = "all, tse/bourse/بورس, ifb/farabourse/فرابورس"
        raise InvalidParameterError("market must be one of: {}".format(valid))
    return [_MARKETS[key]]


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


def _json_records(response, envelope, context):
    try:
        payload = response.json()
    except ValueError as exc:
        raise DataParsingError("{} returned invalid JSON".format(context)) from exc
    if not isinstance(payload, Mapping) or envelope not in payload:
        raise DataParsingError("{} lacks {!r} envelope".format(context, envelope))
    rows = payload[envelope]
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise DataParsingError("{} envelope must be a list".format(context))
    return rows


def get_trading_calendar(
    start=None,
    end=None,
    market="all",
    include_closed=False,
    limit=90,
):
    """Return published TSE/IFB trading sessions from official index history.

    With no explicit range, the latest ``limit`` sessions per market are
    returned.  ``include_closed=True`` expands an explicit/observed range to
    calendar days and flags dates absent from the reference index history.
    """
    if not isinstance(include_closed, bool):
        raise InvalidParameterError("include_closed must be bool")
    limit = _positive_int(limit, "limit", 5000)
    first = None if start is None else _date(start, "start")
    last = None if end is None else _date(end, "end")
    if first is not None and last is not None and first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    rows = []
    reference_names = {"tse": "شاخص کل", "ifb": "شاخص کل فرابورس"}
    for flow, label, code in _market_specs(market):
        response = safe_get(settings.url_instrument_calendar.format(code))
        records = _json_records(response, "indexB2", "trading calendar")
        dates = sorted({_provider_date(item.get("dEven")) for item in records})
        if first is not None:
            dates = [value for value in dates if value >= first]
        if last is not None:
            dates = [value for value in dates if value <= last]
        if first is None and last is None:
            dates = dates[-limit:]
        observed = set(dates)
        if include_closed and (dates or (first is not None and last is not None)):
            range_first = first or dates[0]
            range_last = last or dates[-1]
            expanded = []
            cursor = range_first
            while cursor <= range_last:
                expanded.append(cursor)
                cursor += datetime.timedelta(days=1)
            dates = expanded
        for value in dates:
            rows.append(
                {
                    "Market": label,
                    "Flow": flow,
                    "GregorianDate": value,
                    "JalaliDate": _jalali(value),
                    "IsTradingDay": value in observed,
                    "ReferenceIndex": reference_names[label],
                    "ReferenceInsCode": code,
                    "Source": "tsetmc_index_history",
                }
            )
    frame = pd.DataFrame(rows, columns=CALENDAR_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["GregorianDate", "Flow"], ignore_index=True)
        frame["Flow"] = frame["Flow"].astype("Int64")
        frame["IsTradingDay"] = frame["IsTradingDay"].astype("boolean")
    frame.attrs.update(
        {
            "source": "tsetmc_index_history",
            "calendar_semantics": "published_reference_index_sessions",
            "include_closed": include_closed,
        }
    )
    return frame


def get_market_value_history(
    start=None,
    end=None,
    market="all",
    limit=90,
):
    """Return historical market capitalization for TSE and/or IFB."""
    limit = _positive_int(limit, "limit", 5000)
    first = None if start is None else _date(start, "start")
    last = None if end is None else _date(end, "end")
    if first is not None and last is not None and first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    fetch_limit = 5000 if first is not None or last is not None else limit
    rows = []
    for flow, label, _ in _market_specs(market):
        response = safe_get(settings.url_market_value_history.format(flow, fetch_limit))
        records = _json_records(response, "marketValue", "market value history")
        for item in records:
            value_date = _provider_date(item.get("deven"))
            if first is not None and value_date < first:
                continue
            if last is not None and value_date > last:
                continue
            rows.append(
                {
                    "Market": label,
                    "Flow": flow,
                    "GregorianDate": value_date,
                    "JalaliDate": _jalali(value_date),
                    "MarketValue": _number(item.get("marketCap")),
                    "Source": "tsetmc_market_value_by_flow",
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = _empty(MARKET_VALUE_COLUMNS)
    else:
        frame = frame.sort_values(["Market", "GregorianDate"], ignore_index=True)
        frame["Change"] = frame.groupby("Market")["MarketValue"].diff()
        frame["ChangePct"] = (
            frame.groupby("Market")["MarketValue"].pct_change(fill_method=None) * 100
        )
        frame = frame.reindex(columns=MARKET_VALUE_COLUMNS)
        frame["Flow"] = frame["Flow"].astype("Int64")
    frame.attrs.update(
        {"source": "tsetmc_market_value_by_flow", "unit": "rial", "limit": fetch_limit}
    )
    return frame


def get_index_impact(date=None, market="all", top=10, direction="both"):
    """Return the symbols with the largest official impact on market indices."""
    top = _positive_int(top, "top", 1000)
    if direction not in {"both", "positive", "negative"}:
        raise InvalidParameterError("direction must be both, positive, or negative")
    requested = None if date is None else _date(date, "date")
    rows = []
    for flow, label, _ in _market_specs(market):
        value_date = requested
        if value_date is None:
            latest = get_market_value_history(market=label, limit=1)
            if latest.empty:
                continue
            value_date = latest["GregorianDate"].max()
        response = safe_get(
            settings.url_index_impact.format(value_date.strftime("%Y%m%d"), flow, top)
        )
        records = _json_records(response, "instEffect", "index impact")
        parsed = []
        for item in records:
            impact = _number(item.get("instEffectValue"))
            if direction == "positive" and not impact > 0:
                continue
            if direction == "negative" and not impact < 0:
                continue
            instrument = item.get("instrument") or {}
            parsed.append(
                {
                    "Market": label,
                    "Flow": flow,
                    "GregorianDate": value_date,
                    "JalaliDate": _jalali(value_date),
                    "InsCode": str(
                        item.get("insCode") or instrument.get("insCode") or ""
                    ),
                    "Symbol": instrument.get("lVal18AFC"),
                    "Name": instrument.get("lVal30") or instrument.get("lSoc30"),
                    "Close": _number(item.get("pClosing")),
                    "Impact": impact,
                    "Direction": (
                        "positive"
                        if impact > 0
                        else "negative" if impact < 0 else "zero"
                    ),
                    "Source": "tsetmc_index_inst_effect",
                }
            )
        denominator = sum(abs(item["Impact"]) for item in parsed)
        parsed.sort(key=lambda item: abs(item["Impact"]), reverse=True)
        for rank, item in enumerate(parsed, start=1):
            item["Rank"] = rank
            item["AbsSharePct"] = (
                abs(item["Impact"]) / denominator * 100 if denominator else float("nan")
            )
            rows.append(item)
    frame = pd.DataFrame(rows, columns=INDEX_IMPACT_COLUMNS)
    if not frame.empty:
        frame["Flow"] = frame["Flow"].astype("Int64")
        frame["Rank"] = frame["Rank"].astype("Int64")
        frame["InsCode"] = frame["InsCode"].astype("string")
    frame.attrs.update(
        {
            "source": "tsetmc_index_inst_effect",
            "abs_share_denominator": "absolute impact of returned rows per market",
            "direction": direction,
        }
    )
    return frame


def _market_from_isin(isin):
    prefix = str(isin or "")[:4].upper()
    if prefix in _TSE_PREFIXES:
        return "tse"
    if prefix in _IFB_PREFIXES:
        return "ifb"
    if prefix in _OTHER_PREFIXES:
        return "other"
    if prefix in _COMMODITY_PREFIXES:
        return "commodity"
    if prefix in _ENERGY_PREFIXES:
        return "energy"
    return "unknown"


def _asset_type_from_isin(isin):
    prefix = str(isin or "")[:4].upper()
    if prefix in _RIGHT_PREFIXES:
        return "right"
    if prefix in _FUND_PREFIXES:
        return "fund"
    if prefix in _BOND_PREFIXES:
        return "bond"
    if prefix in _OPTION_PREFIXES:
        return "option"
    if prefix in _FUTURE_PREFIXES:
        return "future"
    if prefix == "IRO6":
        return "mortgage"
    if prefix in {"IRBK", "IRK1"}:
        return "commodity"
    if prefix in {"IRBE", "IRBZ", "IREK", "IRE9"}:
        return "energy"
    if prefix in _STOCK_PREFIXES:
        return "stock"
    return "unknown"


def get_market_trades(date=None, market="all", progress=True):
    """Return the official bulk daily summary for every instrument.

    Despite TSETMC's legacy service name ``TradeOneDayAll``, rows are daily
    instrument summaries, not individual transaction prints.  Use
    :func:`get_trades` for transaction-level data.
    """
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    specs = _market_specs(market)
    allowed = {item[1] for item in specs}
    if date is None:
        latest = get_market_value_history(market="tse", limit=1)
        if latest.empty:
            requested = tehran_today()
        else:
            requested = latest["GregorianDate"].max()
    else:
        requested = _date(date, "date")
    response = safe_get(
        settings.url_market_trades_by_date.format(requested.strftime("%Y%m%d"))
    )
    records = _json_records(
        response,
        "closingPriceDailyHistoryWithInstDetails",
        "market daily trades",
    )
    rows = []
    for item in records:
        isin = str(item.get("instrumentID") or "")
        market_label = _market_from_isin(isin)
        if market.strip().lower() not in {"all", "همه"} and market_label not in allowed:
            continue
        previous = _number(item.get("priceYesterday"))
        close = _number(item.get("pClosing"))
        change = _number(item.get("priceChange"), close - previous)
        change_pct = (
            change / previous * 100
            if previous and math.isfinite(previous) and math.isfinite(change)
            else float("nan")
        )
        rows.append(
            {
                "Market": market_label,
                "MarketClassification": "isin_prefix",
                "AssetType": _asset_type_from_isin(isin),
                "InsCode": str(item.get("insCode") or ""),
                "ISIN": isin,
                "Symbol": item.get("lVal18AFC"),
                "Name": item.get("lVal30"),
                "GregorianDate": requested,
                "JalaliDate": _jalali(requested),
                "TradeCount": _integer(item.get("zTotTran"), 0),
                "Volume": _integer(item.get("qTotTran5J"), 0),
                "Value": _integer(item.get("qTotCap"), 0),
                "Open": _number(item.get("priceFirst")),
                "High": _number(item.get("priceMax")),
                "Low": _number(item.get("priceMin")),
                "Close": close,
                "Last": _number(item.get("pDrCotVal")),
                "PreviousClose": previous,
                "Change": change,
                "ChangePct": change_pct,
                "Source": "tsetmc_instruments_history_in_day",
            }
        )
    frame = pd.DataFrame(rows, columns=MARKET_TRADE_COLUMNS)
    if not frame.empty:
        for column in ("TradeCount", "Volume", "Value"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "Int64"
            )
        for column in ("InsCode", "ISIN", "Symbol", "Name", "Market", "AssetType"):
            frame[column] = frame[column].astype("string")
        frame = frame.sort_values(
            ["Market", "Value", "InsCode"],
            ascending=[True, False, True],
            ignore_index=True,
        )
    unknown = int((frame["Market"] == "unknown").sum()) if not frame.empty else 0
    frame.attrs.update(
        {
            "source": "tsetmc_instruments_history_in_day",
            "row_semantics": "one daily summary per instrument identity",
            "transaction_level": False,
            "market_classification": "official ISIN prefix",
            "unknown_market_rows": unknown,
            "trade_date": requested.isoformat(),
        }
    )
    if progress:
        print("Done. {} daily instrument rows found.".format(len(frame)))
    return frame


def get_market_activity(
    start=None,
    end=None,
    market="all",
    max_requests=30,
    progress=True,
):
    """Aggregate daily market activity from the public bulk daily endpoint."""
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    budget = _positive_int(max_requests, "max_requests", 366)
    if start is None and end is None:
        latest = get_market_value_history(market="tse", limit=1)
        dates = [] if latest.empty else [latest["GregorianDate"].max()]
    else:
        first = _date(start if start is not None else end, "start")
        last = _date(end if end is not None else start, "end")
        if first > last:
            raise InvalidParameterError("start must be less than or equal to end")
        calendar = get_trading_calendar(
            start=first, end=last, market=market, include_closed=False, limit=5000
        )
        dates = sorted(set(calendar.loc[calendar["IsTradingDay"], "GregorianDate"]))
    if len(dates) > budget:
        raise InvalidParameterError(
            "activity range requires {} requests, exceeding max_requests={}".format(
                len(dates), budget
            )
        )
    rows = []
    for position, value_date in enumerate(dates, start=1):
        if progress:
            print("[{}/{}] {}".format(position, len(dates), value_date.isoformat()))
        daily = get_market_trades(value_date, market=market, progress=False)
        traded = daily[daily["TradeCount"].fillna(0) > 0]
        total_value = int(daily["Value"].fillna(0).sum()) if not daily.empty else 0
        total_trades = (
            int(daily["TradeCount"].fillna(0).sum()) if not daily.empty else 0
        )
        rows.append(
            {
                "Market": (
                    "all"
                    if market.strip().lower() in {"all", "همه"}
                    else _market_specs(market)[0][1]
                ),
                "GregorianDate": value_date,
                "JalaliDate": _jalali(value_date),
                "InstrumentCount": len(daily),
                "TradedInstrumentCount": len(traded),
                "TradeCount": total_trades,
                "Volume": (
                    int(daily["Volume"].fillna(0).sum()) if not daily.empty else 0
                ),
                "Value": total_value,
                "AverageTradeValue": (
                    total_value / total_trades if total_trades else float("nan")
                ),
                "Source": "derived_from_tsetmc_bulk_daily",
            }
        )
    frame = pd.DataFrame(rows, columns=MARKET_ACTIVITY_COLUMNS)
    if not frame.empty:
        for column in (
            "InstrumentCount",
            "TradedInstrumentCount",
            "TradeCount",
            "Volume",
            "Value",
        ):
            frame[column] = frame[column].astype("Int64")
    frame.attrs.update(
        {
            "source": "derived_from_tsetmc_bulk_daily",
            "request_count": len(dates),
            "max_requests": budget,
            "market_classification": "official ISIN prefix",
        }
    )
    return frame


def _tuple_value(series):
    return series.str[0] if hasattr(series, "str") else series


def _clean_fa(value):
    if value is None or (not isinstance(value, (tuple, list)) and pd.isna(value)):
        return pd.NA
    return characters.ar_to_fa(str(value)).replace("\u200c", " ").strip()


def _market_group(value):
    text = _clean_fa(value)
    if pd.isna(text) or text in {"", "-"}:
        return "unknown"
    if "فرابورس" in text or "نوآفرین" in text:
        return "ifb"
    if "کالا" in text or "آتی" in text:
        return "commodity"
    if "انرژی" in text or "برق" in text:
        return "energy"
    if "بورس" in text:
        return "tse"
    return "other"


def _instrument_name_parts(value):
    """Split the public table label at its final ``(symbol)`` segment."""
    text = str(value or "").strip()
    match = re.search(r"\(([^()]*)\)\s*$", text)
    if match is None:
        return _clean_fa(text), _clean_fa(text)
    return _clean_fa(text[: match.start()].strip()), _clean_fa(match.group(1))


def get_instrument_master(active=None, market=None, asset_type=None, progress=True):
    """Return the complete public TSETMC instrument reference table."""
    if active is not None and not isinstance(active, bool):
        raise InvalidParameterError("active must be True, False, or None")
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    response = safe_get(settings.url_stock_list)
    try:
        raw = pd.read_html(StringIO(response.text), extract_links="body")[0]
    except Exception as exc:
        raise DataParsingError("cannot parse TSETMC instrument table") from exc
    names = raw["نماد [Name]"]
    frame = pd.DataFrame(
        {
            "InsCode": names.str[-1].str.extract(r"i=(\d+)", expand=False),
            "ISIN": _tuple_value(raw["کد 12 رقمی نماد [Instrument ISIN]"]),
            "RawName": names.str[0],
            "EnglishName": _tuple_value(raw["نام انگلیسی [English Name]"]),
            "CompanyCode": _tuple_value(raw["کد 4 رقمی شرکت [Company Code]"]),
            "CompanyISIN": _tuple_value(raw["کد 12 رقمی شرکت [Company ISIN]"]),
            "Market": _tuple_value(raw["بازار"]),
            "Industry": _tuple_value(raw["گروه صنعت"]),
            "InstrumentStatus": _tuple_value(raw["نوع [Type]"]),
        }
    )
    frame = frame.loc[frame["InsCode"].notna()].copy()
    parts = frame["RawName"].map(_instrument_name_parts)
    frame["Name"] = parts.str[0]
    frame["Symbol"] = parts.str[1]
    for column in ("Market", "Industry"):
        frame[column] = frame[column].map(_clean_fa)
    frame["MarketGroup"] = frame["Market"].map(_market_group)
    frame["AssetType"] = frame["ISIN"].map(_asset_type_from_isin)
    frame["Active"] = pd.NA
    if active is not None:
        from .market_data import market_watch

        snapshot = market_watch()
        live = snapshot["stocks"] if isinstance(snapshot, Mapping) else snapshot
        live_codes = set(live["InsCode"].astype(str))
        frame["Active"] = frame["InsCode"].astype(str).isin(live_codes)
        frame = frame.loc[frame["Active"] == active].copy()
    if market is not None:
        wanted = {_market_specs(market, allow_all=False)[0][1]}
        frame = frame.loc[frame["MarketGroup"].isin(wanted)].copy()
    if asset_type is not None:
        try:
            values = [asset_type] if isinstance(asset_type, str) else list(asset_type)
        except TypeError as exc:
            raise InvalidParameterError(
                "asset_type must be a string or iterable of strings"
            ) from exc
        if any(not isinstance(value, str) for value in values):
            raise InvalidParameterError("asset_type values must be strings")
        values = [value.strip().lower() for value in values]
        allowed = {
            "stock",
            "right",
            "fund",
            "bond",
            "option",
            "future",
            "mortgage",
            "commodity",
            "energy",
            "unknown",
        }
        invalid = sorted(set(values) - allowed)
        if invalid:
            raise InvalidParameterError(
                "unknown asset_type: {}".format(", ".join(invalid))
            )
        frame = frame.loc[frame["AssetType"].isin(values)].copy()
    frame["Source"] = "tsetmc_public_instrument_table"
    frame = frame.drop(columns=["RawName"])
    frame = frame.drop_duplicates("InsCode", keep="last")
    frame = frame.reindex(columns=INSTRUMENT_MASTER_COLUMNS)
    frame["InsCode"] = frame["InsCode"].astype("string")
    frame["Active"] = frame["Active"].astype("boolean")
    frame = frame.sort_values(
        ["MarketGroup", "AssetType", "Symbol", "InsCode"], ignore_index=True
    )
    frame.attrs.update(
        {
            "source": "tsetmc_public_instrument_table",
            "active_snapshot_joined": active is not None,
            "identity_key": "InsCode",
        }
    )
    if progress:
        print("Done. {} instrument identities found.".format(len(frame)))
    return frame


def _load_master(value, name):
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
    elif isinstance(value, (str, Path)):
        path = Path(value)
        if not path.exists():
            raise InvalidParameterError("{} path does not exist".format(name))
        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path, dtype={"InsCode": "string"})
        elif suffix in {".parquet", ".pq"}:
            frame = pd.read_parquet(path)
        elif suffix in {".json", ".jsonl"}:
            frame = pd.read_json(path, lines=suffix == ".jsonl")
        else:
            raise InvalidParameterError(
                "{} must be DataFrame, CSV, Parquet, or JSON".format(name)
            )
    else:
        raise InvalidParameterError(
            "{} must be a DataFrame or supported path".format(name)
        )
    if "InsCode" not in frame:
        raise InvalidParameterError("{} must contain InsCode".format(name))
    frame["InsCode"] = (
        frame["InsCode"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    valid = frame["InsCode"].str.fullmatch(r"[0-9]{1,20}", na=False)
    if not bool(valid.all()):
        raise InvalidParameterError("{} contains invalid InsCode values".format(name))
    if bool(frame["InsCode"].duplicated().any()):
        raise InvalidParameterError("{} contains duplicate InsCode values".format(name))
    return frame.set_index("InsCode", drop=False)


def get_instrument_changes(previous, current=None, progress=True):
    """Compare two exact instrument-master snapshots by ``InsCode``."""
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    old = _load_master(previous, "previous")
    new = (
        get_instrument_master(progress=False).set_index("InsCode", drop=False)
        if current is None
        else _load_master(current, "current")
    )
    rows = []
    old_codes, new_codes = set(old.index), set(new.index)
    for code in sorted(new_codes - old_codes):
        rows.append(
            {
                "ChangeType": "added",
                "InsCode": code,
                "Field": "*",
                "OldValue": pd.NA,
                "NewValue": "present",
                "Symbol": new.at[code, "Symbol"] if "Symbol" in new else pd.NA,
                "Source": "instrument_master_diff",
            }
        )
    for code in sorted(old_codes - new_codes):
        rows.append(
            {
                "ChangeType": "removed",
                "InsCode": code,
                "Field": "*",
                "OldValue": "present",
                "NewValue": pd.NA,
                "Symbol": old.at[code, "Symbol"] if "Symbol" in old else pd.NA,
                "Source": "instrument_master_diff",
            }
        )
    fields = [
        field
        for field in (
            "ISIN",
            "Symbol",
            "Name",
            "Market",
            "Industry",
            "AssetType",
            "InstrumentStatus",
        )
        if field in old and field in new
    ]
    for code in sorted(old_codes & new_codes):
        for field in fields:
            left, right = old.at[code, field], new.at[code, field]
            same = (pd.isna(left) and pd.isna(right)) or str(left) == str(right)
            if not same:
                rows.append(
                    {
                        "ChangeType": "changed",
                        "InsCode": code,
                        "Field": field,
                        "OldValue": left,
                        "NewValue": right,
                        "Symbol": new.at[code, "Symbol"] if "Symbol" in new else pd.NA,
                        "Source": "instrument_master_diff",
                    }
                )
    frame = pd.DataFrame(rows, columns=INSTRUMENT_CHANGE_COLUMNS)
    if not frame.empty:
        for column in ("ChangeType", "InsCode", "Field", "Symbol", "Source"):
            frame[column] = frame[column].astype("string")
        frame = frame.sort_values(["ChangeType", "InsCode", "Field"], ignore_index=True)
    frame.attrs.update(
        {
            "source": "instrument_master_diff",
            "identity_key": "InsCode",
            "previous_count": len(old),
            "current_count": len(new),
        }
    )
    if progress:
        print("Done. {} instrument changes found.".format(len(frame)))
    return frame


def _soap_rows(operation, parameters, timeout=None):
    envelope = ET.Element(
        "{http://schemas.xmlsoap.org/soap/envelope/}Envelope",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
        },
    )
    body = ET.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
    action = ET.SubElement(body, "{{http://tsetmc.com/}}{}".format(operation))
    for name, value in parameters.items():
        child = ET.SubElement(action, "{{http://tsetmc.com/}}{}".format(name))
        child.text = str(value)
    payload = ET.tostring(envelope, encoding="utf-8", xml_declaration=True)
    try:
        response = requests.post(
            settings.url_tsetmc_public_soap,
            data=payload,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "http://tsetmc.com/{}".format(operation),
                **settings.headers,
            },
            timeout=settings.timeout if timeout is None else timeout,
            verify=settings.ssl_verify,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ConnectionError("TSETMC subscriber web service failed") from exc
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise DataParsingError(
            "TSETMC subscriber service returned invalid XML"
        ) from exc
    fault = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Fault")
    if fault is not None:
        message = (
            fault.findtext("faultstring")
            or "TSETMC subscriber service rejected the request"
        )
        raise DataParsingError(message)
    diffgram = root.find(".//{urn:schemas-microsoft-com:xml-diffgram-v1}diffgram")
    if diffgram is None:
        return []
    rows = []
    for element in diffgram.iter():
        children = list(element)
        if children and all(not list(child) for child in children):
            record = {child.tag.split("}")[-1]: child.text for child in children}
            if record:
                rows.append(record)
    return rows


def _subscriber_credentials(username, password):
    if not isinstance(username, str) or not username.strip():
        raise InvalidParameterError("username is required for the official TOP service")
    if not isinstance(password, str) or not password:
        raise InvalidParameterError("password is required for the official TOP service")
    return username.strip(), password


def get_theoretical_opening_price(
    *,
    username=None,
    password=None,
    market="all",
    timeout=None,
    progress=True,
):
    """Return official TSETMC TOP data for licensed web-service subscribers.

    The official service requires subscriber credentials.  They are sent only
    to TSETMC over HTTPS for this call and are never stored by the package.
    """
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    if timeout is not None:
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("timeout must be a positive number") from exc
        if not math.isfinite(timeout_value) or timeout_value <= 0:
            raise InvalidParameterError("timeout must be a positive number")
        timeout = timeout_value
    username, password = _subscriber_credentials(username, password)
    rows = []
    for flow, label, _ in _market_specs(market):
        records = _soap_rows(
            "TOP",
            {"UserName": username, "Password": password, "Flow": flow},
            timeout=timeout,
        )
        for item in records:
            value_date = _provider_date(item.get("DEven"))
            raw_time = str(_integer(item.get("HEven"), 0)).zfill(6)
            rows.append(
                {
                    "Market": label,
                    "Flow": flow,
                    "InsCode": str(item.get("NInsCode") or ""),
                    "Symbol": item.get("LVal18AFC"),
                    "Name": item.get("LVal30"),
                    "GregorianDate": value_date,
                    "JalaliDate": _jalali(value_date),
                    "Time": "{}:{}:{}".format(
                        raw_time[:2], raw_time[2:4], raw_time[4:]
                    ),
                    "TheoreticalOpeningPrice": _number(item.get("PTeoOvJ")),
                    "TheoreticalVolume": _integer(item.get("QXtePTeoOvj")),
                    "RemainderSide": item.get("CSensQNrepOv"),
                    "RemainderVolume": _integer(item.get("QNrepOv")),
                    "TheoreticalBuyVolume": _integer(item.get("QTitMeLimSimAc")),
                    "TheoreticalBuyPrice": _number(item.get("PMeLimSimAcVal")),
                    "TheoreticalSellPrice": _number(item.get("PMeLimSimVtVal")),
                    "TheoreticalSellVolume": _integer(item.get("QTitMeLimSimVt")),
                    "ChangePct": _number(item.get("XQVarPJDrPRf")),
                    "Source": "tsetmc_subscriber_top",
                }
            )
    frame = pd.DataFrame(rows, columns=TOP_COLUMNS)
    if not frame.empty:
        for column in (
            "Flow",
            "TheoreticalVolume",
            "RemainderVolume",
            "TheoreticalBuyVolume",
            "TheoreticalSellVolume",
        ):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "Int64"
            )
        frame["InsCode"] = frame["InsCode"].astype("string")
    frame.attrs.update(
        {
            "source": "tsetmc_subscriber_top",
            "official": True,
            "credentials_stored": False,
            "subscriber_service": True,
        }
    )
    if progress:
        print("Done. {} official TOP rows found.".format(len(frame)))
    return frame


def get_preopen_imbalance(
    top_data=None,
    *,
    username=None,
    password=None,
    market="all",
    timeout=None,
    progress=True,
):
    """Add transparent buy/sell imbalance metrics to official TOP rows."""
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    if top_data is None:
        top_data = get_theoretical_opening_price(
            username=username,
            password=password,
            market=market,
            timeout=timeout,
            progress=progress,
        )
    if not isinstance(top_data, pd.DataFrame):
        raise InvalidParameterError("top_data must be a pandas DataFrame")
    required = {"TheoreticalBuyVolume", "TheoreticalSellVolume"}
    missing = sorted(required - set(top_data.columns))
    if missing:
        raise InvalidParameterError("top_data lacks: {}".format(", ".join(missing)))
    frame = top_data.copy()
    buy = pd.to_numeric(frame["TheoreticalBuyVolume"], errors="coerce")
    sell = pd.to_numeric(frame["TheoreticalSellVolume"], errors="coerce")
    total = buy + sell
    frame["ImbalanceVolume"] = buy - sell
    frame["ImbalanceRatio"] = (buy - sell).div(total.where(total != 0))
    frame["ImbalanceSide"] = "balanced"
    frame.loc[frame["ImbalanceVolume"] > 0, "ImbalanceSide"] = "buy"
    frame.loc[frame["ImbalanceVolume"] < 0, "ImbalanceSide"] = "sell"
    frame.loc[total.isna() | total.eq(0), "ImbalanceSide"] = "unavailable"
    frame.attrs.update(getattr(top_data, "attrs", {}))
    frame.attrs.update(
        {
            "analysis": "theoretical_buy_sell_volume_imbalance",
            "formula": "(buy_volume-sell_volume)/(buy_volume+sell_volume)",
        }
    )
    return frame


__all__ = [
    "get_trading_calendar",
    "get_market_activity",
    "get_market_value_history",
    "get_index_impact",
    "get_market_trades",
    "get_instrument_master",
    "get_instrument_changes",
    "get_theoretical_opening_price",
    "get_preopen_imbalance",
]
