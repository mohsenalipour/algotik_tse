"""Industry-index data and analytics for the Tehran market.

The public API in this module deliberately separates exact TSETMC index
membership from ``SectorCode`` grouping.  Membership is fetched from
``GetIndexCompany`` and joined by ``InsCode`` to one bulk MarketWatch
snapshot.  No official constituent weights or historical membership are
invented.
"""

import copy
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from algotik_tse.exceptions import (
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)
from algotik_tse.http_client import safe_get
from algotik_tse.settings import settings

from .helper import date_fix
from .market_data import (
    CLIENT_COLUMNS,
    ORDER_COLUMNS,
    _canonical_live_stocks,
    _enrich_live_market,
    market_client_type,
    market_watch,
)
from .search import INDUSTRY_NAMES, _INDUSTRY_DICT, _INDUSTRY_RAW, _normalize_fa


INDUSTRY_INDEX_COLUMNS = [
    "IndustryName",
    "IndustryNameEn",
    "IndustryGroupCode",
    "IndexInsCode",
    "IndexValue",
    "IndexPreviousValue",
    "DayHigh",
    "DayLow",
    "IndexChange",
    "IndexChangePct",
    "MemberCount",
    "HasMembers",
    "ExchangeTime",
]

INDUSTRY_MEMBER_COLUMNS = [
    "IndustryName",
    "IndustryIndexCode",
    "InsCode",
    "Symbol",
    "Name",
    "SectorCode",
    "Flow",
    "MarketCode",
    "InstrumentType",
    "PreviousClose",
    "Open",
    "High",
    "Low",
    "Close",
    "Last",
    "Change",
    "ChangePct",
    "TradeCount",
    "Volume",
    "Value",
    "SharesOutstanding",
    "EstimatedMarketCap",
    "IndividualPower",
    "NetIndividualVolume",
    "EstimatedNetIndividualFlow",
    "ClientDataAvailable",
    "BidPrice1",
    "AskPrice1",
    "SpreadBps",
    "L1Imbalance",
    "L5Imbalance",
    "EstimatedBuyQueueVolume",
    "EstimatedBuyQueueValue",
    "EstimatedSellQueueVolume",
    "EstimatedSellQueueValue",
    "TradeDate",
    "ExchangeTime",
    "FetchedAt",
    "IsRealtimeFresh",
    "IsStale",
]

INDUSTRY_SNAPSHOT_COLUMNS = [
    "IndustryName",
    "IndustryNameEn",
    "IndustryGroupCode",
    "IndustryIndexCode",
    "IndexValue",
    "IndexPreviousValue",
    "IndexChange",
    "IndexChangePct",
    "IndexDayHigh",
    "IndexDayLow",
    "MemberCount",
    "TradedCount",
    "Advances",
    "Declines",
    "Unchanged",
    "NoTrade",
    "AdvanceDeclineDifference",
    "AdvanceDeclineRatio",
    "AdvancePct",
    "DeclinePct",
    "EqualWeightReturn",
    "MedianReturn",
    "ReturnDispersion",
    "TotalTradeCount",
    "TotalVolume",
    "TotalValue",
    "MarketValueSharePct",
    "UpperLimitCount",
    "LowerLimitCount",
    "ClientCoveredCount",
    "ClientCoverage",
    "NetIndividualVolume",
    "EstimatedNetIndividualValue",
    "IndividualPower",
    "FlowValueMethod",
    "OrderBookCoveredCount",
    "OrderBookCoverage",
    "BuyQueueCount",
    "BuyQueueValue",
    "SellQueueCount",
    "SellQueueValue",
    "TradeDate",
    "ExchangeTime",
    "FetchedAt",
    "IsRealtimeFresh",
    "IsStale",
]

INDUSTRY_HISTORY_COLUMNS = [
    "IndustryName",
    "IndustryIndexCode",
    "TradeDate",
    "JalaliDate",
    "High",
    "Low",
    "Close",
    "Change",
    "ChangePct",
]

INDUSTRY_MEMBER_HISTORY_COLUMNS = [
    "IndustryName",
    "IndustryIndexCode",
    "TradeDate",
    "JalaliDate",
    "InsCode",
    "Symbol",
    "Name",
    "Close",
    "Last",
    "Change",
    "ChangePct",
    "TradeCount",
    "Volume",
    "Value",
]

INDUSTRY_INTRADAY_COLUMNS = [
    "IndustryName",
    "IndustryIndexCode",
    "Timestamp",
    "JalaliDate",
    "Interval",
    "Open",
    "High",
    "Low",
    "Close",
    "Change",
    "ChangePct",
]


_MEMBERSHIP_CACHE = {}
_MEMBERSHIP_CACHE_LOCK = threading.RLock()
_INDUSTRY_API_ALIASES = {_normalize_fa("فلزات"): "32453344048876642"}


def _canonical_name(code):
    names = _INDUSTRY_RAW.get(str(code), [])
    return names[0] if names else ""


def _clean_text(value):
    return _normalize_fa(str(value)) if value is not None and str(value).strip() else ""


def _resolve_industry(industry):
    if isinstance(industry, bool) or industry is None:
        raise InvalidParameterError("industry must be a Persian name or IndexInsCode")
    if isinstance(industry, (int, np.integer)):
        candidate = str(int(industry))
    elif isinstance(industry, str):
        candidate = industry.strip()
    else:
        raise InvalidParameterError("industry must be a Persian name or IndexInsCode")
    if not candidate:
        raise InvalidParameterError("industry cannot be empty")
    if candidate.isascii() and candidate.isdigit():
        code = candidate
    else:
        normalized = _normalize_fa(candidate)
        code = _INDUSTRY_DICT.get(normalized) or _INDUSTRY_API_ALIASES.get(normalized)
    if code not in _INDUSTRY_RAW:
        raise StockNotFoundError("industry index {!r} was not found".format(industry))
    return str(code), _canonical_name(code), INDUSTRY_NAMES.get(str(code), "")


def _resolve_industries(industries):
    if industries is None:
        return [
            (str(code), _canonical_name(code), INDUSTRY_NAMES.get(str(code), ""))
            for code in _INDUSTRY_RAW
        ]
    values = (
        list(industries)
        if isinstance(industries, (list, tuple, set, pd.Index, np.ndarray))
        else [industries]
    )
    if not values:
        raise InvalidParameterError("industries cannot be empty")
    resolved = []
    seen = set()
    for value in values:
        item = _resolve_industry(value)
        if item[0] not in seen:
            resolved.append(item)
            seen.add(item[0])
    return resolved


def _fetch_json(url, context):
    try:
        response = safe_get(url)
    except requests.exceptions.RequestException as exc:
        raise ConnectionError("{} request failed: {}".format(context, exc)) from exc
    status = getattr(response, "status_code", 200)
    if status is not None and int(status) >= 400:
        raise ConnectionError("{} returned HTTP {}".format(context, status))
    try:
        payload = response.json()
    except (AttributeError, TypeError, ValueError) as exc:
        raise DataParsingError("{} returned invalid JSON".format(context)) from exc
    if not isinstance(payload, dict):
        raise DataParsingError("{} returned a non-object JSON payload".format(context))
    return payload


def _fetch_index_rows():
    payload = _fetch_json(settings.url_all_indices, "industry-index list")
    rows = payload.get("indexB1")
    if not isinstance(rows, list):
        raise DataParsingError("industry-index list is missing indexB1")
    return rows


def _cache_ttl():
    value = getattr(settings, "industry_membership_cache_ttl", 3600.0)
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(
            "settings.industry_membership_cache_ttl must be a non-negative number"
        ) from exc
    if value < 0:
        raise InvalidParameterError(
            "settings.industry_membership_cache_ttl must be a non-negative number"
        )
    return value


def _get_membership_payload(code, refresh=False):
    ttl = _cache_ttl()
    now = time.monotonic()
    if not refresh and ttl > 0:
        with _MEMBERSHIP_CACHE_LOCK:
            cached = _MEMBERSHIP_CACHE.get(str(code))
            if cached is not None and now - cached[0] <= ttl:
                return copy.deepcopy(cached[1]), True
    payload = _fetch_json(
        settings.url_index_companies.format(code),
        "industry membership {}".format(code),
    )
    members = payload.get("indexCompany")
    history = payload.get("relatedCompanyThirtyDayHistory")
    if not isinstance(members, list) or not isinstance(history, list):
        raise DataParsingError(
            "industry membership {} has an invalid schema".format(code)
        )
    with _MEMBERSHIP_CACHE_LOCK:
        _MEMBERSHIP_CACHE[str(code)] = (now, copy.deepcopy(payload))
    return payload, False


def _get_membership_batch(resolved, refresh=False, max_workers=6):
    if isinstance(max_workers, bool) or not isinstance(max_workers, (int, np.integer)):
        raise InvalidParameterError("max_workers must be an integer between 1 and 16")
    max_workers = int(max_workers)
    if max_workers < 1 or max_workers > 16:
        raise InvalidParameterError("max_workers must be an integer between 1 and 16")
    payloads = {}
    cache_hits = 0
    if len(resolved) == 1:
        code = resolved[0][0]
        payload, hit = _get_membership_payload(code, refresh=refresh)
        return {code: payload}, int(hit)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(resolved))) as executor:
        futures = {
            executor.submit(_get_membership_payload, code, refresh): code
            for code, _, _ in resolved
        }
        for future in as_completed(futures):
            code = futures[future]
            payload, hit = future.result()
            payloads[code] = payload
            cache_hits += int(hit)
    return payloads, cache_hits


def _time_text(value):
    try:
        digits = str(int(value)).zfill(6)
    except (TypeError, ValueError):
        return pd.NA
    return "{}:{}:{}".format(digits[:2], digits[2:4], digits[4:6])


def _group_code(name):
    text = str(name or "").strip()
    match = re.match(r"^(\d{2})", text) or re.search(r"(\d{2})$", text)
    return match.group(1) if match else pd.NA


def _jalali(value):
    if pd.isna(value):
        return pd.NA
    date = pd.Timestamp(value).date()
    return JalaliDate.to_jalali(date).isoformat()


def _numeric(value):
    try:
        if value is None:
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _safe_divide(numerator, denominator):
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return np.nan
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def _typed_frame(rows, columns):
    frame = pd.DataFrame(rows).reindex(columns=columns)
    count_columns = {
        "MemberCount",
        "TradedCount",
        "Advances",
        "Declines",
        "Unchanged",
        "NoTrade",
        "AdvanceDeclineDifference",
        "TotalTradeCount",
        "UpperLimitCount",
        "LowerLimitCount",
        "ClientCoveredCount",
        "OrderBookCoveredCount",
        "BuyQueueCount",
        "SellQueueCount",
        "TradeCount",
        "Rank",
    }
    boolean_columns = {
        "HasMembers",
        "ClientDataAvailable",
        "IsRealtimeFresh",
        "IsStale",
    }
    for column in count_columns.intersection(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    for column in boolean_columns.intersection(frame.columns):
        frame[column] = frame[column].astype("boolean")
    return frame


def _members_from_payload(payload, industry_name, code):
    rows = []
    for item in payload.get("indexCompany", []):
        if not isinstance(item, dict):
            continue
        instrument = item.get("instrument") or {}
        ins_code = str(item.get("insCode") or instrument.get("insCode") or "").strip()
        if not ins_code:
            continue
        previous = _numeric(item.get("priceYesterday"))
        close = _numeric(item.get("pClosing"))
        change = close - previous if previous > 0 and np.isfinite(close) else np.nan
        rows.append(
            {
                "IndustryName": industry_name,
                "IndustryIndexCode": str(code),
                "InsCode": ins_code,
                "Symbol": _clean_text(instrument.get("lVal18AFC")),
                "Name": _clean_text(instrument.get("lVal30")),
                "PreviousClose": previous,
                "Open": _numeric(item.get("priceFirst")),
                "High": _numeric(item.get("priceMax")),
                "Low": _numeric(item.get("priceMin")),
                "Close": close,
                "Last": _numeric(item.get("pDrCotVal")),
                "Change": change,
                "ChangePct": _safe_divide(change, previous) * 100,
                "TradeCount": _numeric(item.get("zTotTran")),
                "Volume": _numeric(item.get("qTotTran5J")),
                "Value": _numeric(item.get("qTotCap")),
            }
        )
    return pd.DataFrame(rows)


def _live_frame(snapshot, include_client_type, include_orderbook):
    if not isinstance(snapshot, dict):
        raise DataParsingError("MarketWatch snapshot must be a mapping")
    stocks = snapshot.get("stocks")
    if not isinstance(stocks, pd.DataFrame):
        raise DataParsingError("MarketWatch snapshot is missing stocks")
    if not include_client_type and not include_orderbook:
        return _canonical_live_stocks(stocks)
    client = market_client_type() if include_client_type else pd.DataFrame(columns=CLIENT_COLUMNS)
    if not isinstance(client, pd.DataFrame):
        raise DataParsingError("client-type feed must return a DataFrame")
    order_book = snapshot.get("order_book", pd.DataFrame(columns=ORDER_COLUMNS))
    if not include_orderbook:
        order_book = pd.DataFrame(columns=ORDER_COLUMNS)
    if not isinstance(order_book, pd.DataFrame):
        raise DataParsingError("order-book feed must be a DataFrame")
    return _enrich_live_market(
        stocks,
        client,
        order_book,
        as_of=snapshot.get("fetched_at"),
        snapshot_metadata=snapshot,
    )


def _combine_members_live(base, live, snapshot):
    if base.empty:
        return base.copy()
    live = live.copy()
    live["InsCode"] = live["InsCode"].astype(str).str.strip()
    result = base.copy()
    result["InsCode"] = result["InsCode"].astype(str).str.strip()
    live = live.loc[live["InsCode"].isin(set(result["InsCode"]))]
    result = result.set_index("InsCode", drop=False)
    live = live.set_index("InsCode", drop=False)
    new_columns = [
        column for column in live.columns if column not in result and column != "InsCode"
    ]
    if new_columns:
        result = pd.concat([result, live[new_columns].reindex(result.index)], axis=1)
    for column in set(live.columns).intersection(result.columns) - {"InsCode"}:
        aligned = live[column].reindex(result.index)
        if column in {"Symbol", "Name"}:
            valid = aligned.notna() & aligned.astype(str).str.strip().ne("")
        else:
            valid = aligned.notna()
        result.loc[valid, column] = aligned.loc[valid]
    result = result.reset_index(drop=True).copy()
    result["EstimatedMarketCap"] = pd.to_numeric(
        result.get("SharesOutstanding"), errors="coerce"
    ) * pd.to_numeric(result.get("Close"), errors="coerce")
    result["ClientDataAvailable"] = result.get(
        "client_snapshot_consistent", pd.Series(False, index=result.index)
    ).fillna(False)
    metadata = snapshot or {}
    result["TradeDate"] = metadata.get("trade_date")
    result["ExchangeTime"] = metadata.get("exchange_time")
    result["FetchedAt"] = metadata.get("fetched_at")
    result["IsRealtimeFresh"] = metadata.get("is_realtime_fresh", False)
    result["IsStale"] = metadata.get("is_stale", True)
    return result


def _public_member_frame(frame):
    result = frame.copy()
    aliases = {
        "NetIndividualVolume": "NetIndividualVolume",
        "EstimatedNetIndividualFlow": "EstimatedNetIndividualFlow",
        "IndividualPower": "IndividualPower",
    }
    for target, source in aliases.items():
        if source not in result:
            result[target] = np.nan
    for column in INDUSTRY_MEMBER_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    return _typed_frame(result, INDUSTRY_MEMBER_COLUMNS)


def list_industry_indices(
    progress=True,
    include_member_count=False,
    refresh=False,
    max_workers=6,
):
    """List the 45 TSETMC industry indices with corrected change semantics.

    ``include_member_count=False`` keeps this a single-request operation.
    Enabling it fetches and caches exact current membership for every industry.
    ``refresh=True`` bypasses the membership cache.
    """
    if not isinstance(progress, bool) or not isinstance(include_member_count, bool):
        raise InvalidParameterError("progress and include_member_count must be bool")
    if not isinstance(refresh, bool):
        raise InvalidParameterError("refresh must be bool")
    if progress:
        print("Fetching industry indices...")
    index_rows = _fetch_index_rows()
    live_by_code = {str(row.get("insCode")): row for row in index_rows if isinstance(row, dict)}
    resolved = _resolve_industries(None)
    counts = {}
    cache_hits = 0
    if include_member_count:
        payloads, cache_hits = _get_membership_batch(
            resolved, refresh=refresh, max_workers=max_workers
        )
        counts = {code: len(payload.get("indexCompany", [])) for code, payload in payloads.items()}
    output = []
    for code, name, name_en in resolved:
        item = live_by_code.get(code, {})
        value = _numeric(item.get("xDrNivJIdx004"))
        change = _numeric(item.get("indexChange"))
        member_count = counts.get(code, pd.NA)
        output.append(
            {
                "IndustryName": name,
                "IndustryNameEn": name_en,
                "IndustryGroupCode": _group_code(item.get("lVal30")),
                "IndexInsCode": code,
                "IndexValue": value,
                "IndexPreviousValue": value - change if np.isfinite(value) and np.isfinite(change) else np.nan,
                "DayHigh": _numeric(item.get("xPhNivJIdx004")),
                "DayLow": _numeric(item.get("xPbNivJIdx004")),
                "IndexChange": change,
                "IndexChangePct": _numeric(item.get("xVarIdxJRfV")),
                "MemberCount": member_count,
                "HasMembers": (member_count > 0) if member_count is not pd.NA else pd.NA,
                "ExchangeTime": _time_text(item.get("hEven")),
            }
        )
    result = _typed_frame(output, INDUSTRY_INDEX_COLUMNS)
    result.attrs.update(
        {
            "source": "TSETMC",
            "membership_source": "GetIndexCompany" if include_member_count else "not_requested",
            "member_count_requested": include_member_count,
            "cache_hits": cache_hits,
            "industry_count": len(result),
        }
    )
    if progress:
        print("Done. {} industry indices returned.".format(len(result)))
    return result


def get_industry_members(
    industry,
    include_live=True,
    include_client_type=False,
    include_orderbook=False,
    progress=True,
    refresh=False,
):
    """Return exact current members of one TSETMC industry index.

    Identity always comes from ``GetIndexCompany``.  With ``include_live`` the
    exact members are joined by ``InsCode`` to one MarketWatch snapshot.
    Client-type and order-book analytics are opt-in.
    """
    for name, value in (
        ("include_live", include_live),
        ("include_client_type", include_client_type),
        ("include_orderbook", include_orderbook),
        ("progress", progress),
        ("refresh", refresh),
    ):
        if not isinstance(value, bool):
            raise InvalidParameterError("{} must be bool".format(name))
    if (include_client_type or include_orderbook) and not include_live:
        raise InvalidParameterError(
            "include_client_type/include_orderbook require include_live=True"
        )
    code, industry_name, _ = _resolve_industry(industry)
    if progress:
        print("Fetching members of {}...".format(industry_name))
    payload, cache_hit = _get_membership_payload(code, refresh=refresh)
    base = _members_from_payload(payload, industry_name, code)
    snapshot = None
    if include_live and not base.empty:
        snapshot = market_watch()
        live = _live_frame(snapshot, include_client_type, include_orderbook)
        frame = _combine_members_live(base, live, snapshot)
    else:
        frame = base.copy()
        frame["ClientDataAvailable"] = False
        frame["IsRealtimeFresh"] = False
        frame["IsStale"] = True
    result = _public_member_frame(frame)
    result.attrs.update(
        {
            "source": "TSETMC",
            "universe": "exact_index_members",
            "industry_name": industry_name,
            "industry_index_code": code,
            "membership_is_current": True,
            "historical_membership_available": False,
            "cache_hit": cache_hit,
            "client_type_requested": include_client_type,
            "orderbook_requested": include_orderbook,
            "membership_count": len(result),
        }
    )
    if progress:
        print("Done. {} members returned.".format(len(result)))
    return result


def _snapshot_record(
    code,
    name,
    name_en,
    index_item,
    members,
    live,
    snapshot,
    market_total_value,
    include_client_type,
    include_orderbook,
):
    base = _members_from_payload(members, name, code)
    frame = _combine_members_live(base, live, snapshot) if not base.empty else base
    member_count = len(base)
    if frame.empty:
        price = previous = traded = pd.Series(dtype="float64")
    else:
        last = pd.to_numeric(frame.get("Last"), errors="coerce")
        close = pd.to_numeric(frame.get("Close"), errors="coerce")
        price = last.where(last.gt(0), close)
        previous = pd.to_numeric(frame.get("PreviousClose"), errors="coerce")
        traded = pd.to_numeric(frame.get("TradeCount"), errors="coerce").gt(0) & pd.to_numeric(
            frame.get("Volume"), errors="coerce"
        ).gt(0)
    valid = price.gt(0) & previous.gt(0)
    returns = (price.loc[valid] / previous.loc[valid] - 1.0) * 100 if len(frame) else pd.Series(dtype="float64")
    advances = int((valid & price.gt(previous)).sum()) if len(frame) else 0
    declines = int((valid & price.lt(previous)).sum()) if len(frame) else 0
    unchanged = int((valid & price.eq(previous)).sum()) if len(frame) else 0
    total_value = pd.to_numeric(frame.get("Value"), errors="coerce").sum(min_count=1) if len(frame) else np.nan
    upper = pd.to_numeric(frame.get("MaxAllowed"), errors="coerce") if len(frame) else pd.Series(dtype="float64")
    lower = pd.to_numeric(frame.get("MinAllowed"), errors="coerce") if len(frame) else pd.Series(dtype="float64")

    client_covered = pd.Series(False, index=frame.index)
    if include_client_type and len(frame):
        client_covered = frame.get(
            "client_snapshot_consistent", pd.Series(False, index=frame.index)
        ).fillna(False).astype(bool)
    covered = frame.loc[client_covered] if len(frame) else frame
    net_volume = pd.to_numeric(covered.get("NetIndividualVolume"), errors="coerce").sum(min_count=1) if len(covered) else np.nan
    net_value = pd.to_numeric(covered.get("EstimatedNetIndividualFlow"), errors="coerce").sum(min_count=1) if len(covered) else np.nan
    buy_volume = pd.to_numeric(covered.get("IndividualBuyVolume"), errors="coerce").sum(min_count=1) if len(covered) else np.nan
    sell_volume = pd.to_numeric(covered.get("IndividualSellVolume"), errors="coerce").sum(min_count=1) if len(covered) else np.nan
    buy_count = pd.to_numeric(covered.get("IndividualBuyCount"), errors="coerce").sum(min_count=1) if len(covered) else np.nan
    sell_count = pd.to_numeric(covered.get("IndividualSellCount"), errors="coerce").sum(min_count=1) if len(covered) else np.nan
    industry_power = _safe_divide(
        _safe_divide(buy_volume, buy_count), _safe_divide(sell_volume, sell_count)
    )

    order_covered = pd.Series(False, index=frame.index)
    if include_orderbook and len(frame):
        bid = pd.to_numeric(frame.get("BidPrice1"), errors="coerce")
        ask = pd.to_numeric(frame.get("AskPrice1"), errors="coerce")
        order_covered = bid.gt(0) | ask.gt(0)
    buy_queue = pd.to_numeric(frame.get("EstimatedBuyQueueValue"), errors="coerce") if len(frame) else pd.Series(dtype="float64")
    sell_queue = pd.to_numeric(frame.get("EstimatedSellQueueValue"), errors="coerce") if len(frame) else pd.Series(dtype="float64")

    index_value = _numeric(index_item.get("xDrNivJIdx004"))
    index_change = _numeric(index_item.get("indexChange"))
    return {
        "IndustryName": name,
        "IndustryNameEn": name_en,
        "IndustryGroupCode": _group_code(index_item.get("lVal30")),
        "IndustryIndexCode": code,
        "IndexValue": index_value,
        "IndexPreviousValue": index_value - index_change if np.isfinite(index_value) and np.isfinite(index_change) else np.nan,
        "IndexChange": index_change,
        "IndexChangePct": _numeric(index_item.get("xVarIdxJRfV")),
        "IndexDayHigh": _numeric(index_item.get("xPhNivJIdx004")),
        "IndexDayLow": _numeric(index_item.get("xPbNivJIdx004")),
        "MemberCount": member_count,
        "TradedCount": int(traded.sum()) if len(frame) else 0,
        "Advances": advances,
        "Declines": declines,
        "Unchanged": unchanged,
        "NoTrade": int((~traded).sum()) if len(frame) else member_count,
        "AdvanceDeclineDifference": advances - declines,
        "AdvanceDeclineRatio": advances / declines if declines else (np.inf if advances else np.nan),
        "AdvancePct": advances / member_count * 100 if member_count else np.nan,
        "DeclinePct": declines / member_count * 100 if member_count else np.nan,
        "EqualWeightReturn": returns.mean() if len(returns) else np.nan,
        "MedianReturn": returns.median() if len(returns) else np.nan,
        "ReturnDispersion": returns.std(ddof=0) if len(returns) else np.nan,
        "TotalTradeCount": pd.to_numeric(frame.get("TradeCount"), errors="coerce").sum(min_count=1) if len(frame) else np.nan,
        "TotalVolume": pd.to_numeric(frame.get("Volume"), errors="coerce").sum(min_count=1) if len(frame) else np.nan,
        "TotalValue": total_value,
        "MarketValueSharePct": _safe_divide(total_value, market_total_value) * 100,
        "UpperLimitCount": int((traded & price.eq(upper) & upper.gt(0)).sum()) if len(frame) else 0,
        "LowerLimitCount": int((traded & price.eq(lower) & lower.gt(0)).sum()) if len(frame) else 0,
        "ClientCoveredCount": int(client_covered.sum()) if include_client_type else pd.NA,
        "ClientCoverage": float(client_covered.mean()) if include_client_type and member_count else np.nan,
        "NetIndividualVolume": net_volume,
        "EstimatedNetIndividualValue": net_value,
        "IndividualPower": industry_power,
        "FlowValueMethod": "market_vwap_estimate" if np.isfinite(_numeric(net_value)) else "unavailable",
        "OrderBookCoveredCount": int(order_covered.sum()) if include_orderbook else pd.NA,
        "OrderBookCoverage": float(order_covered.mean()) if include_orderbook and member_count else np.nan,
        "BuyQueueCount": int(buy_queue.gt(0).sum()) if include_orderbook else pd.NA,
        "BuyQueueValue": buy_queue.sum(min_count=1) if include_orderbook else np.nan,
        "SellQueueCount": int(sell_queue.gt(0).sum()) if include_orderbook else pd.NA,
        "SellQueueValue": sell_queue.sum(min_count=1) if include_orderbook else np.nan,
        "TradeDate": snapshot.get("trade_date"),
        "ExchangeTime": snapshot.get("exchange_time"),
        "FetchedAt": snapshot.get("fetched_at"),
        "IsRealtimeFresh": snapshot.get("is_realtime_fresh", False),
        "IsStale": snapshot.get("is_stale", True),
    }


def get_industry_snapshot(
    industries=None,
    include_client_type=True,
    include_orderbook=False,
    include_empty=False,
    progress=True,
    refresh=False,
    max_workers=6,
):
    """Build one exact-membership live analytics row per requested industry.

    The function performs one bulk MarketWatch request, at most one bulk
    client-type request, and cached membership requests.  Industry memberships
    may overlap; rows must not be summed to derive a market total.
    """
    for name, value in (
        ("include_client_type", include_client_type),
        ("include_orderbook", include_orderbook),
        ("include_empty", include_empty),
        ("progress", progress),
        ("refresh", refresh),
    ):
        if not isinstance(value, bool):
            raise InvalidParameterError("{} must be bool".format(name))
    resolved = _resolve_industries(industries)
    if progress:
        print("Fetching industry snapshot for {} industries...".format(len(resolved)))
    index_rows = _fetch_index_rows()
    index_by_code = {str(row.get("insCode")): row for row in index_rows if isinstance(row, dict)}
    payloads, cache_hits = _get_membership_batch(
        resolved, refresh=refresh, max_workers=max_workers
    )
    snapshot = market_watch()
    live = _live_frame(snapshot, include_client_type, include_orderbook)
    market_total_value = pd.to_numeric(live.get("Value"), errors="coerce").sum(min_count=1)
    rows = []
    empty = []
    for code, name, name_en in resolved:
        payload = payloads[code]
        if not payload.get("indexCompany"):
            empty.append(name)
            if not include_empty:
                continue
        rows.append(
            _snapshot_record(
                code,
                name,
                name_en,
                index_by_code.get(code, {}),
                payload,
                live,
                snapshot,
                market_total_value,
                include_client_type,
                include_orderbook,
            )
        )
    result = _typed_frame(rows, INDUSTRY_SNAPSHOT_COLUMNS)
    result.attrs.update(
        {
            "source": "TSETMC",
            "universe": "exact_index_members",
            "membership_is_current": True,
            "historical_membership_available": False,
            "memberships_may_overlap": True,
            "client_type_requested": include_client_type,
            "orderbook_requested": include_orderbook,
            "empty_industries": empty,
            "cache_hits": cache_hits,
            "membership_requests": len(resolved) - cache_hits,
            "flow_value_method": "market_vwap_estimate",
        }
    )
    if progress:
        print("Done. {} industry rows returned.".format(len(result)))
    return result


def _validate_limit(limit, name="limit", maximum=None):
    if isinstance(limit, bool) or not isinstance(limit, (int, np.integer)):
        raise InvalidParameterError("{} must be a non-negative integer".format(name))
    limit = int(limit)
    if limit < 0 or (maximum is not None and limit > maximum):
        suffix = " no greater than {}".format(maximum) if maximum is not None else ""
        raise InvalidParameterError("{} must be a non-negative integer{}".format(name, suffix))
    return limit


def _date_bounds(start, end):
    if start is not None and not isinstance(start, str):
        raise InvalidParameterError("start must be a Jalali/Gregorian date string")
    if end is not None and not isinstance(end, str):
        raise InvalidParameterError("end must be a Jalali/Gregorian date string")
    try:
        fixed_start, fixed_end = date_fix(start=start, end=end)
        start_date = pd.Timestamp(fixed_start).normalize() if fixed_start else None
        end_date = pd.Timestamp(fixed_end).normalize() if fixed_end else None
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidParameterError("start/end must be valid Jalali/Gregorian dates") from exc
    if start_date is not None and end_date is not None and start_date > end_date:
        raise InvalidParameterError("start cannot be after end")
    return start_date, end_date


def get_industry_history(
    industry,
    start=None,
    end=None,
    limit=0,
    ascending=True,
    progress=True,
):
    """Return completed daily history for one industry index.

    The provider has no volume for index history, so this function does not
    create a synthetic volume column.  ``start`` and ``end`` accept either
    Jalali or Gregorian dates.
    """
    limit = _validate_limit(limit)
    if not isinstance(ascending, bool) or not isinstance(progress, bool):
        raise InvalidParameterError("ascending and progress must be bool")
    start_date, end_date = _date_bounds(start, end)
    code, industry_name, _ = _resolve_industry(industry)
    if progress:
        print("Fetching history of {}...".format(industry_name))
    payload = _fetch_json(
        settings.url_industry_history.format(code),
        "industry history {}".format(code),
    )
    values = payload.get("indexB2")
    if not isinstance(values, list):
        raise DataParsingError("industry history {} is missing indexB2".format(code))
    rows = []
    for item in values:
        if not isinstance(item, dict):
            continue
        try:
            trade_date = pd.to_datetime(str(int(item.get("dEven"))), format="%Y%m%d")
        except (TypeError, ValueError, OverflowError):
            continue
        rows.append(
            {
                "IndustryName": industry_name,
                "IndustryIndexCode": code,
                "TradeDate": trade_date,
                "JalaliDate": _jalali(trade_date),
                "High": _numeric(item.get("xNivInuPhMresIbs")),
                "Low": _numeric(item.get("xNivInuPbMresIbs")),
                "Close": _numeric(item.get("xNivInuClMresIbs")),
            }
        )
    result = pd.DataFrame(rows).sort_values("TradeDate").reset_index(drop=True) if rows else pd.DataFrame()
    if not result.empty:
        result["Change"] = result["Close"].diff()
        result["ChangePct"] = result["Close"].pct_change(fill_method=None) * 100
        if start_date is not None:
            result = result.loc[result["TradeDate"] >= start_date]
        if end_date is not None:
            result = result.loc[result["TradeDate"] <= end_date]
        if limit:
            result = result.tail(limit)
        result = result.sort_values("TradeDate", ascending=ascending).reset_index(drop=True)
    result = _typed_frame(result, INDUSTRY_HISTORY_COLUMNS)
    result.attrs.update(
        {
            "source": "TSETMC:GetIndexB2History",
            "volume_available": False,
            "completed_sessions_only": True,
            "industry_name": industry_name,
            "industry_index_code": code,
        }
    )
    if progress:
        print("Done. {} sessions returned.".format(len(result)))
    return result


def get_industry_members_history(
    industry,
    days=30,
    ascending=True,
    progress=True,
    refresh=False,
):
    """Return the provider's short daily history for all current members.

    ``days`` is the number of latest trading dates and must be between 1 and
    30.  The universe is today's membership, not point-in-time membership.
    """
    days = _validate_limit(days, name="days", maximum=30)
    if days == 0:
        raise InvalidParameterError("days must be between 1 and 30")
    for name, value in (("ascending", ascending), ("progress", progress), ("refresh", refresh)):
        if not isinstance(value, bool):
            raise InvalidParameterError("{} must be bool".format(name))
    code, industry_name, _ = _resolve_industry(industry)
    if progress:
        print("Fetching member history of {}...".format(industry_name))
    payload, cache_hit = _get_membership_payload(code, refresh=refresh)
    identity = {
        str(item.get("insCode") or ""): (
            _clean_text((item.get("instrument") or {}).get("lVal18AFC")),
            _clean_text((item.get("instrument") or {}).get("lVal30")),
        )
        for item in payload.get("indexCompany", [])
        if isinstance(item, dict)
    }
    rows = []
    for item in payload.get("relatedCompanyThirtyDayHistory", []):
        if not isinstance(item, dict):
            continue
        try:
            trade_date = pd.to_datetime(str(int(item.get("dEven"))), format="%Y%m%d")
        except (TypeError, ValueError, OverflowError):
            continue
        ins_code = str(item.get("insCode") or "").strip()
        symbol, name = identity.get(ins_code, ("", ""))
        rows.append(
            {
                "IndustryName": industry_name,
                "IndustryIndexCode": code,
                "TradeDate": trade_date,
                "JalaliDate": _jalali(trade_date),
                "InsCode": ins_code,
                "Symbol": symbol,
                "Name": name,
                "Close": _numeric(item.get("pClosing")),
                "Last": _numeric(item.get("pDrCotVal")),
                "TradeCount": _numeric(item.get("zTotTran")),
                "Volume": _numeric(item.get("qTotTran5J")),
                "Value": _numeric(item.get("qTotCap")),
            }
        )
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["InsCode", "TradeDate"]).reset_index(drop=True)
        result["Change"] = result.groupby("InsCode", sort=False)["Close"].diff()
        result["ChangePct"] = result.groupby("InsCode", sort=False)["Close"].pct_change(fill_method=None) * 100
        dates = sorted(result["TradeDate"].dropna().unique())[-days:]
        result = result.loc[result["TradeDate"].isin(dates)]
        result = result.sort_values(
            ["TradeDate", "Symbol"], ascending=[ascending, True]
        ).reset_index(drop=True)
    result = _typed_frame(result, INDUSTRY_MEMBER_HISTORY_COLUMNS)
    result.attrs.update(
        {
            "source": "TSETMC:GetIndexCompany.relatedCompanyThirtyDayHistory",
            "universe": "current_index_members",
            "point_in_time_membership": False,
            "survivorship_bias_possible": True,
            "maximum_provider_sessions": 30,
            "cache_hit": cache_hit,
            "industry_name": industry_name,
            "industry_index_code": code,
        }
    )
    if progress:
        print("Done. {} member-session rows returned.".format(len(result)))
    return result


_INTERVALS = {
    "raw": None,
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "60min": "60min",
    "1h": "60min",
}


def get_industry_intraday(industry, interval="1min", progress=True):
    """Return latest-day industry-index candles without synthetic volume.

    Supported intervals are ``raw``, ``1min``, ``5min``, ``15min``,
    ``30min``, ``60min`` and ``1h``.  ``raw`` preserves provider observations;
    other values resample the index level into OHLC candles.
    """
    if not isinstance(interval, str) or interval.lower().strip() not in _INTERVALS:
        raise InvalidParameterError(
            "interval must be one of raw, 1min, 5min, 15min, 30min, 60min, 1h"
        )
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    requested = interval.lower().strip()
    code, industry_name, _ = _resolve_industry(industry)
    if progress:
        print("Fetching intraday data of {}...".format(industry_name))
    payload = _fetch_json(
        settings.url_industry_intra.format(code),
        "industry intraday {}".format(code),
    )
    values = payload.get("indexB1")
    if not isinstance(values, list):
        raise DataParsingError("industry intraday {} is missing indexB1".format(code))
    raw_rows = []
    for item in values:
        if not isinstance(item, dict):
            continue
        try:
            date_text = str(int(item.get("dEven")))
            time_text = str(int(item.get("hEven"))).zfill(6)
            timestamp = pd.to_datetime(date_text + time_text, format="%Y%m%d%H%M%S")
            timestamp = timestamp.tz_localize("Asia/Tehran")
        except (TypeError, ValueError, OverflowError):
            continue
        raw_rows.append(
            {
                "Timestamp": timestamp,
                "Value": _numeric(item.get("xDrNivJIdx004")),
                "Change": _numeric(item.get("indexChange")),
                "ChangePct": _numeric(item.get("xVarIdxJRfV")),
            }
        )
    raw = pd.DataFrame(raw_rows).dropna(subset=["Value"]).sort_values("Timestamp") if raw_rows else pd.DataFrame()
    output = []
    if not raw.empty:
        if _INTERVALS[requested] is None:
            grouped = [
                (row.Timestamp, row.Value, row.Value, row.Value, row.Value, row.Change, row.ChangePct)
                for row in raw.itertuples(index=False)
            ]
        else:
            indexed = raw.set_index("Timestamp")
            ohlc = indexed["Value"].resample(_INTERVALS[requested]).ohlc()
            changes = indexed[["Change", "ChangePct"]].resample(_INTERVALS[requested]).last()
            merged = ohlc.join(changes).dropna(subset=["close"])
            grouped = [
                (idx, row.open, row.high, row.low, row.close, row.Change, row.ChangePct)
                for idx, row in merged.iterrows()
            ]
        for timestamp, open_, high, low, close, change, change_pct in grouped:
            output.append(
                {
                    "IndustryName": industry_name,
                    "IndustryIndexCode": code,
                    "Timestamp": timestamp,
                    "JalaliDate": _jalali(timestamp),
                    "Interval": requested,
                    "Open": open_,
                    "High": high,
                    "Low": low,
                    "Close": close,
                    "Change": change,
                    "ChangePct": change_pct,
                }
            )
    result = _typed_frame(output, INDUSTRY_INTRADAY_COLUMNS)
    result.attrs.update(
        {
            "source": "TSETMC:GetIndexB1LastDay",
            "volume_available": False,
            "synthetic_volume": False,
            "interval": requested,
            "latest_provider_day_only": True,
            "industry_name": industry_name,
            "industry_index_code": code,
        }
    )
    if progress:
        print("Done. {} intraday rows returned.".format(len(result)))
    return result


_RANK_METRICS = {
    "indexchangepct": "IndexChangePct",
    "change_pct": "IndexChangePct",
    "return": "IndexChangePct",
    "equalweightreturn": "EqualWeightReturn",
    "equal_weight_return": "EqualWeightReturn",
    "medianreturn": "MedianReturn",
    "median_return": "MedianReturn",
    "advancepct": "AdvancePct",
    "advance_pct": "AdvancePct",
    "breadth": "AdvancePct",
    "totalvalue": "TotalValue",
    "total_value": "TotalValue",
    "turnover": "TotalValue",
    "estimatednetindividualvalue": "EstimatedNetIndividualValue",
    "estimated_net_individual_value": "EstimatedNetIndividualValue",
    "money_flow": "EstimatedNetIndividualValue",
    "individualpower": "IndividualPower",
    "individual_power": "IndividualPower",
    "buyer_power": "IndividualPower",
}


def rank_industries(
    metric="IndexChangePct",
    top=None,
    ascending=False,
    include_client_type=True,
    include_orderbook=False,
    progress=True,
    refresh=False,
    max_workers=6,
):
    """Rank all non-empty industries by a supported snapshot metric."""
    if not isinstance(metric, str) or not metric.strip():
        raise InvalidParameterError("metric must be a supported metric name")
    key = metric.strip().replace(" ", "").lower()
    column = _RANK_METRICS.get(key)
    if column is None:
        raise InvalidParameterError(
            "metric must be one of IndexChangePct, EqualWeightReturn, "
            "MedianReturn, AdvancePct, TotalValue, "
            "EstimatedNetIndividualValue, IndividualPower"
        )
    if top is not None:
        top = _validate_limit(top, name="top")
        if top == 0:
            raise InvalidParameterError("top must be a positive integer or None")
    for name, value in (
        ("ascending", ascending),
        ("include_client_type", include_client_type),
        ("include_orderbook", include_orderbook),
        ("progress", progress),
        ("refresh", refresh),
    ):
        if not isinstance(value, bool):
            raise InvalidParameterError("{} must be bool".format(name))
    snapshot = get_industry_snapshot(
        include_client_type=include_client_type,
        include_orderbook=include_orderbook,
        include_empty=False,
        progress=progress,
        refresh=refresh,
        max_workers=max_workers,
    )
    result = snapshot.loc[pd.to_numeric(snapshot[column], errors="coerce").notna()].copy()
    result = result.sort_values(column, ascending=ascending, kind="mergesort")
    if top is not None:
        result = result.head(top)
    result = result.reset_index(drop=True)
    result.insert(0, "Rank", pd.Series(range(1, len(result) + 1), dtype="Int64"))
    result.attrs.update(copy.deepcopy(snapshot.attrs))
    result.attrs.update({"ranking_metric": column, "ranking_ascending": ascending})
    return result


__all__ = [
    "list_industry_indices",
    "get_industry_members",
    "get_industry_snapshot",
    "get_industry_history",
    "get_industry_members_history",
    "get_industry_intraday",
    "rank_industries",
]
