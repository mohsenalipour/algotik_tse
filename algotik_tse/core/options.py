"""Live Iranian option market data, analytics and honest local history.

The bulk TSETMC option endpoint is the authoritative source for live contract
metadata.  Historical bid/ask, open interest, contract adjustments and rates
are not reliably exposed by the public feeds, so this module never backfills
them.  Callers may explicitly persist snapshots from this release onward.
"""

import datetime
import json
import math
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from algotik_tse.core.options_math import (
    black_scholes_greeks,
    implied_volatility,
)
from algotik_tse.core.stock import stock as _stock_history
from algotik_tse.core.conventions import coerce_financial_date
from algotik_tse.http_client import safe_get
from algotik_tse.settings import settings
from algotik_tse.exceptions import DataParsingError

OPTION_SNAPSHOT_SCHEMA_VERSION = 1
OPTION_SOURCE = "tsetmc_option_market_watch"

OPTION_COLUMNS = [
    "InsCode",
    "PairID",
    "PairSequence",
    "ISIN",
    "Symbol",
    "Name",
    "OptionType",
    "UnderlyingInsCode",
    "UnderlyingSymbol",
    "UnderlyingName",
    "ContractSize",
    "Strike",
    "BeginDate",
    "EndDate",
    "DaysToExpiry",
    "Last",
    "Close",
    "Yesterday",
    "Volume",
    "Value",
    "TradeCount",
    "NotionalValue",
    "OpenInterest",
    "YesterdayOpenInterest",
    "BidPrice",
    "AskPrice",
    "BidVolume",
    "AskVolume",
    "UnderlyingLast",
    "UnderlyingClose",
    "Price",
    "PriceSource",
    "AsOf",
    "AsOfSource",
    "SnapshotFreshnessKnown",
    "PriceFreshnessKnown",
    "Stale",
    "NoTrade",
    "AnalyticsEligible",
    "AnalyticsEligibilityReason",
    "MetadataConflict",
    "Source",
]

HISTORY_COLUMNS = [
    "Timestamp",
    "InsCode",
    "Symbol",
    "Open",
    "High",
    "Low",
    "Close",
    "Last",
    "Volume",
    "Value",
    "TradeCount",
    "OpenInterest",
    "BidPrice",
    "AskPrice",
    "BidVolume",
    "AskVolume",
    "UnderlyingLast",
    "UnderlyingClose",
    "ContractSize",
    "Strike",
    "EndDate",
    "Price",
    "PriceSource",
    "Source",
    "AsOf",
    "Stale",
    "NoTrade",
    "AnalyticsEligible",
]

OPTION_NUMERIC_COLUMNS = {
    "ContractSize",
    "Strike",
    "DaysToExpiry",
    "Last",
    "Close",
    "Yesterday",
    "Volume",
    "Value",
    "TradeCount",
    "NotionalValue",
    "OpenInterest",
    "YesterdayOpenInterest",
    "BidPrice",
    "AskPrice",
    "BidVolume",
    "AskVolume",
    "UnderlyingLast",
    "UnderlyingClose",
    "Price",
}
OPTION_BOOLEAN_COLUMNS = {
    "SnapshotFreshnessKnown",
    "PriceFreshnessKnown",
    "Stale",
    "NoTrade",
    "AnalyticsEligible",
    "MetadataConflict",
}
ANALYTICS_NUMERIC_COLUMNS = [
    "TimeToExpiry",
    "Spot",
    "RiskFreeRate",
    "DividendYield",
    "ImpliedVolatility",
    "ImpliedVolatilityBid",
    "ImpliedVolatilityMid",
    "ImpliedVolatilityAsk",
    "Delta",
    "Gamma",
    "Vega",
    "Vega1Pct",
    "ThetaPerYear",
    "ThetaPerDay",
    "Rho",
    "Rho100bp",
    "PremiumContract",
    "DeltaContract",
    "GammaContract",
    "VegaContract",
    "Vega1PctContract",
    "ThetaPerYearContract",
    "ThetaPerDayContract",
    "RhoContract",
    "Rho100bpContract",
    "SpreadAbs",
    "SpreadPct",
    "QuotedDepth",
    "LiquidityScore",
    "ParityResidual",
    "ParityToleranceBand",
    "ImpliedForward",
]
ANALYTICS_OBJECT_COLUMNS = [
    "SpotSource",
    "RiskFreeRateSource",
    "DividendYieldSource",
    "IVStatus",
    "IVStatusBid",
    "IVStatusMid",
    "IVStatusAsk",
    "GreeksStatus",
    "AnalyticsWarning",
    "ParityStatus",
    "AnalyticsReliability",
]
ANALYTICS_BOOLEAN_COLUMNS = ["AnalyticsComputed"]
OPTION_TEXT_COLUMNS = {
    "InsCode",
    "PairID",
    "ISIN",
    "Symbol",
    "Name",
    "OptionType",
    "UnderlyingInsCode",
    "UnderlyingSymbol",
    "UnderlyingName",
    "PriceSource",
    "AsOfSource",
    "AnalyticsEligibilityReason",
    "Source",
}.union(ANALYTICS_OBJECT_COLUMNS)


def _cast_options(frame):
    """Apply one nullable dtype contract to empty and populated frames."""
    frame = frame.copy()
    for column in OPTION_NUMERIC_COLUMNS.intersection(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Float64")
    if "PairSequence" in frame:
        numeric_sequence = pd.to_numeric(frame["PairSequence"], errors="coerce")
        invalid = numeric_sequence.notna() & numeric_sequence.mod(1).ne(0)
        if invalid.any():
            raise DataParsingError("PairSequence must be an integer")
        frame["PairSequence"] = numeric_sequence.astype("Int64")
    for column in OPTION_BOOLEAN_COLUMNS.intersection(frame.columns):
        frame[column] = frame[column].astype("boolean")
    for column in OPTION_TEXT_COLUMNS:
        if column in frame:
            frame[column] = frame[column].astype("string")
    if "AsOf" in frame:
        frame["AsOf"] = (
            pd.to_datetime(frame["AsOf"], errors="coerce", utc=True)
            .dt.tz_convert("Asia/Tehran")
            .astype("datetime64[ns, Asia/Tehran]")
        )
    for column in ("BeginDate", "EndDate"):
        if column in frame:
            frame[column] = frame[column].map(_date)
    for column in ANALYTICS_NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "Float64"
            )
    if "ParityWithinBand" in frame:
        frame["ParityWithinBand"] = frame["ParityWithinBand"].astype("boolean")
    for column in ANALYTICS_BOOLEAN_COLUMNS:
        if column in frame:
            frame[column] = frame[column].astype("boolean")
    return frame


def _cast_history(frame):
    frame = frame.copy()
    numeric = set(HISTORY_COLUMNS).intersection(
        {
            "Open",
            "High",
            "Low",
            "Close",
            "Last",
            "Volume",
            "Value",
            "TradeCount",
            "OpenInterest",
            "BidPrice",
            "AskPrice",
            "BidVolume",
            "AskVolume",
            "UnderlyingLast",
            "UnderlyingClose",
            "ContractSize",
            "Strike",
            "Price",
        }
    )
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Float64")
    for column in ("Stale", "NoTrade", "AnalyticsEligible"):
        if column in frame:
            frame[column] = frame[column].astype("boolean")
    for column in ("InsCode", "Symbol", "PriceSource", "Source"):
        if column in frame:
            frame[column] = frame[column].astype("string")
    for column in ("Timestamp", "AsOf"):
        if column in frame:
            frame[column] = (
                pd.to_datetime(frame[column], errors="coerce", utc=True)
                .dt.tz_convert("Asia/Tehran")
                .astype("datetime64[ns, Asia/Tehran]")
            )
    return frame


def _empty_options():
    frame = pd.DataFrame(
        {column: pd.Series(dtype="object") for column in OPTION_COLUMNS}
    )
    for column in (
        "PairSequence",
        "ContractSize",
        "Strike",
        "DaysToExpiry",
        "Last",
        "Close",
        "Yesterday",
        "Volume",
        "Value",
        "TradeCount",
        "NotionalValue",
        "OpenInterest",
        "YesterdayOpenInterest",
        "BidPrice",
        "AskPrice",
        "BidVolume",
        "AskVolume",
        "UnderlyingLast",
        "UnderlyingClose",
        "Price",
    ):
        frame[column] = pd.Series(dtype="Float64")
    frame["PairSequence"] = pd.Series(dtype="Int64")
    for column in OPTION_BOOLEAN_COLUMNS:
        frame[column] = pd.Series(dtype="boolean")
    frame["AsOf"] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    return _cast_options(frame)


def _empty_history():
    frame = pd.DataFrame(
        {column: pd.Series(dtype="object") for column in HISTORY_COLUMNS}
    )
    for column in (
        "Open",
        "High",
        "Low",
        "Close",
        "Last",
        "Volume",
        "Value",
        "TradeCount",
        "OpenInterest",
        "BidPrice",
        "AskPrice",
        "BidVolume",
        "AskVolume",
        "UnderlyingLast",
        "UnderlyingClose",
        "ContractSize",
        "Strike",
        "Price",
    ):
        frame[column] = pd.Series(dtype="Float64")
    for column in ("Stale", "NoTrade", "AnalyticsEligible"):
        frame[column] = pd.Series(dtype="boolean")
    frame["Timestamp"] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    frame["AsOf"] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    return _cast_history(frame)


def _key(value):
    return "".join(
        character for character in str(value).casefold() if character.isalnum()
    )


def _lookup(record, *names, default=None):
    normalized = {_key(key): value for key, value in record.items()}
    for name in names:
        if _key(name) in normalized:
            value = normalized[_key(name)]
            if value is not None and value != "":
                return value
    return default


def _side_value(record, side, *bases, default=None):
    suffixes = ("C", "Call", "c") if side == "call" else ("P", "Put", "p")
    names = []
    for base in bases:
        names.extend(f"{base}_{suffix}" for suffix in suffixes)
        names.extend(f"{base}{suffix}" for suffix in suffixes)
    return _lookup(record, *names, default=default)


def _number(value):
    try:
        if isinstance(value, str):
            value = value.translate(
                str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
            )
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _true(value):
    return False if pd.isna(value) else bool(value)


def _identifier(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _normalize_exact_identifier(value):
    """Normalize Persian/Arabic glyph variants without enabling fuzzy match."""
    if value is None:
        return ""
    return (
        str(value)
        .strip()
        .translate(
            str.maketrans(
                "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك",
                "01234567890123456789یک",
            )
        )
    )


def _date(value):
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = (
        str(value)
        .strip()
        .translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    )
    try:
        return datetime.date.fromisoformat(text[:10])
    except (TypeError, ValueError):
        pass
    text = "".join(character for character in text if character.isdigit())
    if len(text) != 8:
        return None
    try:
        return datetime.datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _find_paired_records(payload):
    """Read the documented top-level collection, tolerating key casing only."""
    if not isinstance(payload, dict):
        raise DataParsingError("option market response root must be an object")
    root = next(
        (
            value
            for key, value in payload.items()
            if _key(key) == "instrumentoptmarketwatch"
        ),
        None,
    )
    if root is None or not isinstance(root, list):
        raise DataParsingError("option market response lacks instrumentOptMarketWatch")
    if any(not isinstance(item, dict) for item in root):
        raise DataParsingError("instrumentOptMarketWatch must contain objects")
    return root


def _select_price(row):
    bid, ask = _number(row.get("BidPrice")), _number(row.get("AskPrice"))
    bid_size, ask_size = _number(row.get("BidVolume")), _number(row.get("AskVolume"))
    stale = _true(row.get("Stale", pd.NA))
    quote_valid = (
        not stale
        and bid > 0
        and ask > 0
        and bid <= ask
        and bid_size > 0
        and ask_size > 0
    )
    if quote_valid:
        return (bid + ask) / 2.0, "mid"
    last = _number(row.get("Last"))
    volume = _number(row.get("Volume"))
    trades = _number(row.get("TradeCount"))
    if not stale and last > 0 and (volume > 0 or trades > 0):
        return last, "last"
    close = _number(row.get("Close"))
    if close > 0:
        return close, "close"
    return math.nan, "missing"


def _paired_to_rows(records, as_of):
    rows = []
    today = as_of.date()
    deduped = {}
    duplicate_pairs = 0
    incomplete_pairs_quarantined = 0
    for sequence, record in enumerate(records):
        strike_key = _number(_lookup(record, "strikePrice", "strike"))
        size_key = _number(_lookup(record, "contractSize"))
        end_key = _date(_lookup(record, "endDate", "expiryDate"))
        identity = (
            _identifier(
                _lookup(record, "uaInsCode", "underlyingInsCode", "underlyingCode")
            ),
            None if math.isnan(strike_key) else strike_key,
            end_key,
            None if math.isnan(size_key) else size_key,
            _identifier(_side_value(record, "call", "insCode")),
            _identifier(_side_value(record, "put", "insCode")),
        )
        if identity in deduped:
            duplicate_pairs += 1
        deduped[identity] = (sequence, record)
    for sequence, record in deduped.values():
        call_inscode = _identifier(_side_value(record, "call", "insCode"))
        put_inscode = _identifier(_side_value(record, "put", "insCode"))
        if not call_inscode or not put_inscode:
            incomplete_pairs_quarantined += 1
            continue
        underlying_code = _identifier(
            _lookup(record, "uaInsCode", "underlyingInsCode", "underlyingCode")
        )
        # The official feed currently puts the underlying *ticker* (for
        # example ``اخابر``/``شستا``) in lval30_UA.  It is not a long name.
        underlying_symbol = _lookup(
            record,
            "uaSymbol",
            "underlyingSymbol",
            "lVal18AFC_UA",
            "lval30_UA",
        )
        underlying_name = _lookup(record, "underlyingName", "uaName")
        strike = _number(_lookup(record, "strikePrice", "strike"))
        contract_size = _number(_lookup(record, "contractSize"))
        begin = _date(_lookup(record, "beginDate"))
        end = _date(_lookup(record, "endDate", "expiryDate"))
        remained = _number(_lookup(record, "remainedDay", "daysToExpiry"))
        if math.isnan(remained) and end is not None:
            remained = float((end - today).days)
        pair_id = "|".join(
            (
                underlying_code or "",
                end.isoformat() if end else "",
                "" if math.isnan(strike) else format(strike, ".15g"),
                "" if math.isnan(contract_size) else format(contract_size, ".15g"),
            )
        )
        underlying_last = _number(
            _lookup(record, "underlyingLast", "pDrCotVal_UA", "uaLastPrice", "last_UA")
        )
        underlying_close = _number(
            _lookup(
                record, "underlyingClose", "pClosing_UA", "uaClosingPrice", "close_UA"
            )
        )
        for side, suffix in (("call", "C"), ("put", "P")):
            inscode = _identifier(_side_value(record, side, "insCode"))
            if not inscode:
                continue
            side_strike = _number(_side_value(record, side, "strikePrice"))
            side_end = _date(_side_value(record, side, "endDate", "expiryDate"))
            metadata_conflict = bool(
                (
                    not math.isnan(side_strike)
                    and not math.isnan(strike)
                    and side_strike != strike
                )
                or (side_end is not None and end is not None and side_end != end)
            )
            authoritative_strike = (
                side_strike if not math.isnan(side_strike) else strike
            )
            authoritative_end = side_end or end
            row = {
                "InsCode": inscode,
                "PairID": pair_id,
                "PairSequence": sequence,
                "ISIN": _identifier(_side_value(record, side, "instrumentID", "isin")),
                "Symbol": _side_value(record, side, "symbol", "lVal18AFC"),
                "Name": _side_value(record, side, "name", "lVal30"),
                "OptionType": side,
                "UnderlyingInsCode": underlying_code,
                "UnderlyingSymbol": underlying_symbol,
                "UnderlyingName": underlying_name,
                "ContractSize": contract_size,
                "Strike": authoritative_strike,
                "BeginDate": begin,
                "EndDate": authoritative_end,
                "DaysToExpiry": (
                    float((authoritative_end - today).days)
                    if authoritative_end is not None
                    else remained
                ),
                "Last": _number(_side_value(record, side, "last", "pDrCotVal")),
                "Close": _number(_side_value(record, side, "close", "pClosing")),
                "Yesterday": _number(
                    _side_value(record, side, "yesterday", "priceYesterday")
                ),
                "Volume": _number(_side_value(record, side, "volume", "qTotTran5J")),
                "Value": _number(_side_value(record, side, "value", "qTotCap")),
                "TradeCount": _number(
                    _side_value(record, side, "tradeCount", "zTotTran")
                ),
                "NotionalValue": _number(_side_value(record, side, "notionalValue")),
                "OpenInterest": _number(
                    _side_value(record, side, "oP", "openInterest")
                ),
                "YesterdayOpenInterest": _number(
                    _side_value(record, side, "yesterdayOP", "yesterdayOpenInterest")
                ),
                "BidPrice": _number(_side_value(record, side, "bidPrice", "pMeDem")),
                "AskPrice": _number(_side_value(record, side, "askPrice", "pMeOf")),
                "BidVolume": _number(
                    _side_value(record, side, "bidVolume", "qTitMeDem")
                ),
                "AskVolume": _number(
                    _side_value(record, side, "askVolume", "qTitMeOf")
                ),
                "UnderlyingLast": underlying_last,
                "UnderlyingClose": underlying_close,
                "AsOf": as_of,
                "AsOfSource": "http_response_fetched_at_not_exchange_event_time",
                "SnapshotFreshnessKnown": pd.NA,
                "PriceFreshnessKnown": pd.NA,
                "Stale": pd.NA,
                "MetadataConflict": metadata_conflict,
                "Source": OPTION_SOURCE,
            }
            trade_count = _number(row["TradeCount"])
            volume = _number(row["Volume"])
            row["NoTrade"] = (
                pd.NA
                if not math.isfinite(trade_count) and not math.isfinite(volume)
                else not (trade_count > 0 or volume > 0)
            )
            row["Price"], row["PriceSource"] = _select_price(row)
            structurally_eligible = bool(
                math.isfinite(row["Price"])
                and row["Price"] > 0
                and math.isfinite(row["Strike"])
                and row["Strike"] > 0
                and row["EndDate"] is not None
                and not metadata_conflict
                and (
                    (math.isfinite(row["UnderlyingLast"]) and row["UnderlyingLast"] > 0)
                    or (
                        math.isfinite(row["UnderlyingClose"])
                        and row["UnderlyingClose"] > 0
                    )
                )
            )
            row["AnalyticsEligible"] = pd.NA if structurally_eligible else False
            bid = _number(row["BidPrice"])
            ask = _number(row["AskPrice"])
            bid_depth = _number(row["BidVolume"])
            ask_depth = _number(row["AskVolume"])
            valid_book = (
                bid > 0 and ask > 0 and bid <= ask and bid_depth > 0 and ask_depth > 0
            )
            if not structurally_eligible:
                reason = "invalid_or_conflicting_inputs"
            elif not valid_book:
                # The selected price ladder may still have a traded last or
                # close.  Side/mid IVs are gated separately by quote depth.
                reason = "freshness_unverified;side_quotes_unavailable_or_invalid"
            elif row["NoTrade"] is True:
                reason = "freshness_unverified;no_trade_but_valid_book"
            else:
                reason = "freshness_unverified"
            row["AnalyticsEligibilityReason"] = reason
            rows.append(row)
    if not rows:
        frame = _empty_options()
        frame.attrs.update(
            {
                "duplicate_pairs_dropped": duplicate_pairs,
                "incomplete_pairs_quarantined": incomplete_pairs_quarantined,
            }
        )
        return frame
    frame = pd.DataFrame(rows).reindex(columns=OPTION_COLUMNS)
    frame = _cast_options(frame)
    frame.attrs["duplicate_pairs_dropped"] = duplicate_pairs
    frame.attrs["incomplete_pairs_quarantined"] = incomplete_pairs_quarantined
    return frame


def get_option_market(exchange=0, underlying=None, progress=True, max_requests=1):
    """Fetch one atomic bulk snapshot of active options.

    ``exchange`` accepts 0/``'all'``, 1/``'tse'`` or 2/``'ifb'``.  Filtering
    is exact on official ``UnderlyingInsCode`` or the endpoint's underlying
    symbol when the endpoint actually supplies it; partial/name matching is
    intentionally unsupported. ``UnderlyingInsCode`` is the guaranteed key.
    """
    exchange_map = {0: 0, 1: 1, 2: 2, "all": 0, "tse": 1, "ifb": 2}
    key = exchange.casefold() if isinstance(exchange, str) else exchange
    if key not in exchange_map:
        raise ValueError("exchange must be 0/'all', 1/'tse', or 2/'ifb'")
    if (
        isinstance(max_requests, bool)
        or int(max_requests) != max_requests
        or max_requests < 1
    ):
        raise ValueError("max_requests must allow the one required bulk request")
    url = settings.url_option_market_watch.format(exchange_map[key])
    if progress:
        print("Fetching atomic option market snapshot...")
    response = safe_get(url)
    if response is None or response.status_code != 200:
        frame = _empty_options()
        frame.attrs.update(
            {"source": OPTION_SOURCE, "status": "unavailable", "request_count": 1}
        )
        return frame
    try:
        payload = response.json()
    except Exception as exc:
        raise DataParsingError("option market response is not valid JSON") from exc
    records = _find_paired_records(payload)
    as_of = pd.Timestamp.now(tz="Asia/Tehran")
    frame = _paired_to_rows(records, as_of)
    duplicate_pairs_dropped = frame.attrs.get("duplicate_pairs_dropped", 0)
    incomplete_pairs_quarantined = frame.attrs.get("incomplete_pairs_quarantined", 0)
    if underlying is not None and not frame.empty:
        target = _normalize_exact_identifier(underlying)
        frame = frame.loc[
            frame["UnderlyingInsCode"].map(_normalize_exact_identifier).eq(target)
            | frame["UnderlyingSymbol"].map(_normalize_exact_identifier).eq(target)
        ].copy()
    frame = frame.reset_index(drop=True)
    frame.attrs.update(
        {
            "source": OPTION_SOURCE,
            "as_of": as_of,
            "atomic_snapshot": incomplete_pairs_quarantined == 0,
            "as_of_source": "http_response_fetched_at_not_exchange_event_time",
            "exchange_event_freshness_known": False,
            "request_count": 1,
            "max_requests": int(max_requests),
            "premium_unit": "per_underlying_unit",
            "contract_size_source": "tsetmc_or_missing",
            "duplicate_pairs_dropped": duplicate_pairs_dropped,
            "incomplete_pairs_quarantined": incomplete_pairs_quarantined,
            "malformed_pair_status": (
                "quarantined" if incomplete_pairs_quarantined else "none"
            ),
        }
    )
    return frame


def _spot(row, override):
    if override is not None:
        value = _number(override)
        return value, "user_supplied"
    for column, source in (
        ("UnderlyingLast", "tsetmc_underlying_last"),
        ("UnderlyingClose", "tsetmc_underlying_close"),
    ):
        value = _number(row.get(column))
        if value > 0:
            return value, source
    return math.nan, "missing"


def _rate(time, scalar, curve, expiry_date, valuation_date):
    if scalar is not None:
        value = _number(scalar)
        if not math.isfinite(value):
            raise ValueError("risk_free_rate must be finite")
        return value, "user_supplied_continuous"
    if curve is not None:
        curve_settlement = getattr(curve, "settlement_date", None)
        if isinstance(curve_settlement, datetime.datetime):
            curve_settlement = curve_settlement.date()
        if curve_settlement != valuation_date:
            raise ValueError(
                "yield_curve.settlement_date must equal valuation_date; a current "
                "curve cannot be applied to historical observations"
            )
        discount_factor = _number(curve.discount_factor(expiry_date))
        if not math.isfinite(discount_factor) or discount_factor <= 0:
            raise ValueError("yield_curve discount factor must be finite and positive")
        # Derive the continuous rate on exactly the same ACT/365F horizon
        # consumed by BSM, irrespective of the curve's quoted day-count basis.
        return (
            -math.log(discount_factor) / time,
            "yield_curve_discount_factor_act365f_continuous",
        )
    return math.nan, "missing"


def _expiry_time(value, valuation_date):
    expiry = value if isinstance(value, datetime.date) else _date(value)
    if expiry is None:
        return math.nan
    return max((expiry - valuation_date).days, 0) / 365.0


def _liquidity(frame, weights):
    # User-supplied frames are not guaranteed to have passed through our
    # nullable dtype caster.  Coerce before vector arithmetic so complete
    # pairs with absent quotes (Python None/object dtype) remain analyzable.
    for column in (
        "BidPrice",
        "AskPrice",
        "BidVolume",
        "AskVolume",
        "Volume",
        "Value",
        "TradeCount",
        "OpenInterest",
    ):
        frame[column] = pd.to_numeric(
            frame[column] if column in frame else np.nan, errors="coerce"
        )
    frame["SpreadAbs"] = frame["AskPrice"] - frame["BidPrice"]
    valid = (
        frame["BidPrice"].gt(0)
        & frame["AskPrice"].gt(0)
        & frame["BidPrice"].le(frame["AskPrice"])
        & frame["BidVolume"].gt(0)
        & frame["AskVolume"].gt(0)
    )
    mid = (frame["BidPrice"] + frame["AskPrice"]) / 2.0
    frame["SpreadPct"] = (frame["SpreadAbs"] / mid).where(valid)
    frame["QuotedDepth"] = (frame["BidVolume"] + frame["AskVolume"]).where(valid)
    if weights is None:
        frame["LiquidityScore"] = np.nan
        return frame
    default = {
        "spread": 0.30,
        "depth": 0.20,
        "volume": 0.15,
        "value": 0.10,
        "trades": 0.10,
        "open_interest": 0.15,
    }
    supplied = dict(weights)
    unknown = set(supplied).difference(default)
    if unknown:
        raise ValueError(f"unknown liquidity weight keys: {sorted(unknown)}")
    default.update(supplied)
    numeric_weights = [_number(value) for value in default.values()]
    if (
        any(not math.isfinite(value) or value < 0 for value in numeric_weights)
        or sum(numeric_weights) <= 0
    ):
        raise ValueError("liquidity_weights must be non-negative with positive sum")
    components = {
        "spread": 1.0 - frame["SpreadPct"].rank(pct=True),
        "depth": frame["QuotedDepth"].rank(pct=True),
        "volume": frame["Volume"].rank(pct=True),
        "value": frame["Value"].rank(pct=True),
        "trades": frame["TradeCount"].rank(pct=True),
        "open_interest": frame["OpenInterest"].rank(pct=True),
    }
    numerator = pd.Series(0.0, index=frame.index)
    denominator = pd.Series(0.0, index=frame.index)
    for name, values in components.items():
        weight = float(default[name])
        available = values.notna()
        numerator = numerator.add(values.fillna(0) * weight)
        denominator = denominator.add(available.astype(float) * weight)
        frame[f"LiquidityComponent_{name}"] = values
    frame["LiquidityScore"] = numerator.div(denominator.where(denominator > 0))
    return frame


def _add_parity(frame, q, tolerance):
    if tolerance is not None:
        tolerance = _number(tolerance)
        if not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("parity_tolerance must be finite and non-negative")
    frame["ParityResidual"] = np.nan
    frame["ParityToleranceBand"] = np.nan
    frame["ParityWithinBand"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame["ImpliedForward"] = np.nan
    frame["ParityStatus"] = "unpaired_or_incomplete"
    keys = ["UnderlyingInsCode", "Strike", "EndDate", "ContractSize"]
    if "AsOf" in frame:
        keys.append("AsOf")
    for _, pair in frame.groupby(keys, dropna=False, sort=False):
        if (
            pair[["UnderlyingInsCode", "Strike", "EndDate", "ContractSize"]]
            .isna()
            .any()
            .any()
        ):
            frame.loc[pair.index, "ParityStatus"] = "missing_exact_pair_key"
            continue
        calls = pair.loc[pair["OptionType"].eq("call")]
        puts = pair.loc[pair["OptionType"].eq("put")]
        if len(calls) != 1 or len(puts) != 1:
            continue
        call, put = calls.iloc[0], puts.iloc[0]
        if _true(call.get("Stale")) or _true(put.get("Stale")):
            frame.loc[pair.index, "ParityStatus"] = "stale"
            continue
        if _true(call.get("MetadataConflict")) or _true(put.get("MetadataConflict")):
            frame.loc[pair.index, "ParityStatus"] = "metadata_conflict"
            continue
        if not (
            _true(call.get("AnalyticsComputed")) and _true(put.get("AnalyticsComputed"))
        ):
            frame.loc[pair.index, "ParityStatus"] = "analytics_ineligible_or_suppressed"
            continue
        call_spot, put_spot = _number(call.get("Spot")), _number(put.get("Spot"))
        if not (
            math.isfinite(call_spot)
            and math.isfinite(put_spot)
            and math.isclose(call_spot, put_spot, rel_tol=1e-12, abs_tol=0.0)
        ):
            frame.loc[pair.index, "ParityStatus"] = "inconsistent_or_missing_spot"
            continue
        values = [
            call["Price"],
            put["Price"],
            call["Spot"],
            call["Strike"],
            call["TimeToExpiry"],
            call["RiskFreeRate"],
        ]
        if not all(math.isfinite(_number(value)) for value in values):
            frame.loc[pair.index, "ParityStatus"] = "missing_analytics_input"
            continue
        discount = math.exp(-call["RiskFreeRate"] * call["TimeToExpiry"])
        dividend_discount = math.exp(-q * call["TimeToExpiry"])
        residual = (
            call["Price"]
            - put["Price"]
            - (call["Spot"] * dividend_discount - call["Strike"] * discount)
        )
        call_spread = _number(call.get("SpreadAbs"))
        put_spread = _number(put.get("SpreadAbs"))
        call_depth = _number(call.get("QuotedDepth"))
        put_depth = _number(put.get("QuotedDepth"))
        band = float(tolerance) if tolerance is not None else math.nan
        if (
            tolerance is None
            and math.isfinite(call_spread)
            and math.isfinite(put_spread)
            and call_spread >= 0
            and put_spread >= 0
            and call_depth > 0
            and put_depth > 0
        ):
            band = max(call_spread, put_spread)
        implied_forward = (
            call["Price"] - put["Price"] + call["Strike"] * discount
        ) / discount
        indices = [call.name, put.name]
        frame.loc[indices, "ParityResidual"] = residual
        frame.loc[indices, "ImpliedForward"] = implied_forward
        if math.isfinite(band):
            frame.loc[indices, "ParityToleranceBand"] = band
            frame.loc[indices, "ParityWithinBand"] = abs(residual) <= band
            frame.loc[indices, "ParityStatus"] = "ok"
        else:
            frame.loc[indices, "ParityStatus"] = (
                "crossed_quote"
                if call_spread < 0 or put_spread < 0
                else "missing_spread"
            )
    return frame


def analyze_option_chain(
    options=None,
    underlying=None,
    spot=None,
    risk_free_rate=None,
    yield_curve=None,
    dividend_yield=0.0,
    valuation_date=None,
    exercise_style="european",
    parity_tolerance=None,
    liquidity_weights=None,
    progress=True,
    *,
    allow_unverified_freshness=True,
):
    """Enrich an atomic option snapshot with IV, Greeks, parity and liquidity.

    BSM analytics are European and per underlying unit. Rates and dividend
    yield are continuous annual rates. Contract-scaled columns remain missing
    when TSETMC does not publish a valid ``ContractSize``. Put-call parity is a
    diagnostic residual, not an executable-arbitrage claim.
    """
    exercise_style = str(exercise_style).strip().lower()
    if exercise_style != "european":
        raise ValueError("only exercise_style='european' is supported")
    if risk_free_rate is not None and yield_curve is not None:
        raise ValueError("provide either risk_free_rate or yield_curve, not both")
    q = _number(dividend_yield)
    if not math.isfinite(q):
        raise ValueError("dividend_yield must be finite")
    if options is None:
        options = get_option_market(underlying=underlying, progress=progress)
    if not isinstance(options, pd.DataFrame):
        raise TypeError("options must be a pandas DataFrame")
    frame = options.copy()
    if frame.empty:
        result = _empty_options()
        for column in ANALYTICS_NUMERIC_COLUMNS:
            result[column] = pd.Series(dtype="Float64")
        for column in ANALYTICS_OBJECT_COLUMNS:
            result[column] = pd.Series(dtype="string")
        for column in ANALYTICS_BOOLEAN_COLUMNS:
            result[column] = pd.Series(dtype="boolean")
        result["ParityWithinBand"] = pd.Series(dtype="boolean")
        result.attrs.update(getattr(options, "attrs", {}))
        result.attrs["analytics"] = "black_scholes_european"
        return result
    required = {"OptionType", "Strike", "EndDate", "Price"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"options is missing required columns: {sorted(missing)}")
    parsed_as_of = None
    if "AsOf" in frame:
        parsed_as_of = pd.to_datetime(frame["AsOf"], errors="coerce", utc=True)
        if parsed_as_of.nunique(dropna=False) > 1:
            raise ValueError("analyze_option_chain requires one atomic AsOf snapshot")
    observation_date = None
    if parsed_as_of is not None:
        observed = parsed_as_of.dropna()
        if not observed.empty:
            dates = observed.dt.tz_convert("Asia/Tehran").dt.date.unique().tolist()
            if len(dates) == 1:
                observation_date = dates[0]
    if valuation_date is None:
        if observation_date is not None:
            valuation_date = observation_date
            valuation_source = "atomic_snapshot_as_of_date"
        else:
            raise ValueError(
                "valuation_date is required when atomic AsOf is missing or invalid"
            )
    elif isinstance(valuation_date, datetime.datetime):
        valuation_date = valuation_date.date()
        valuation_source = "user_supplied"
    elif isinstance(valuation_date, datetime.date):
        valuation_source = "user_supplied"
    else:
        valuation_date = datetime.date.fromisoformat(str(valuation_date))
        valuation_source = "user_supplied"
    if observation_date is not None and valuation_date != observation_date:
        raise ValueError("valuation_date must equal the atomic snapshot AsOf date")
    observation_verified = observation_date is not None and (
        parsed_as_of is None or not parsed_as_of.isna().any()
    )
    records = []
    for _, source_row in frame.iterrows():
        row = source_row.to_dict()
        time = _expiry_time(row.get("EndDate"), valuation_date)
        row_spot, spot_source = _spot(row, spot)
        expiry_date = (
            row.get("EndDate")
            if isinstance(row.get("EndDate"), datetime.date)
            else _date(row.get("EndDate"))
        )
        rate, rate_source = (
            _rate(time, risk_free_rate, yield_curve, expiry_date, valuation_date)
            if math.isfinite(time) and time > 0
            else (math.nan, "missing_at_expiry")
        )
        row.update(
            {
                "TimeToExpiry": time,
                "Spot": row_spot,
                "SpotSource": spot_source,
                "RiskFreeRate": rate,
                "RiskFreeRateSource": rate_source,
                "DividendYield": q,
                "DividendYieldSource": (
                    "user_supplied"
                    if dividend_yield != 0.0
                    else "explicit_default_zero"
                ),
                "AnalyticsWarning": None,
            }
        )
        bid, ask = _number(row.get("BidPrice")), _number(row.get("AskPrice"))
        bid_depth = _number(row.get("BidVolume"))
        ask_depth = _number(row.get("AskVolume"))
        crossed = (
            math.isfinite(bid)
            and math.isfinite(ask)
            and bid > 0
            and ask > 0
            and bid > ask
        )
        side_quotes = {
            "Bid": (bid, bid_depth),
            "Ask": (ask, ask_depth),
        }
        mid_valid = (
            bid > 0 and ask > 0 and bid <= ask and bid_depth > 0 and ask_depth > 0
        )
        iv_prices = {
            "": row.get("Price"),
            "Bid": bid if bid > 0 and bid_depth > 0 else math.nan,
            "Mid": (bid + ask) / 2.0 if mid_valid else math.nan,
            "Ask": ask if ask > 0 and ask_depth > 0 else math.nan,
        }
        stale_value = row.get("Stale", pd.NA)
        stale = False if pd.isna(stale_value) else bool(stale_value)
        conflict = _true(row.get("MetadataConflict"))
        eligibility_value = row.get("AnalyticsEligible", pd.NA)
        eligibility_known = not pd.isna(eligibility_value)
        eligible = (
            bool(eligibility_value)
            if eligibility_known
            else bool(allow_unverified_freshness)
        )
        freshness_values = (
            row.get("SnapshotFreshnessKnown", pd.NA),
            row.get("PriceFreshnessKnown", pd.NA),
        )
        freshness_verified = all(
            not pd.isna(value) and bool(value) for value in freshness_values
        )
        if not freshness_verified and not allow_unverified_freshness:
            eligible = False
            row["AnalyticsWarning"] = "freshness_unverified_analytics_suppressed"
        elif not freshness_verified:
            row["AnalyticsWarning"] = "freshness_unverified_analytics_computed"
        if not observation_verified:
            extra = "observation_as_of_unverified_user_valuation_date"
            row["AnalyticsWarning"] = (
                extra
                if not row["AnalyticsWarning"]
                else row["AnalyticsWarning"] + ";" + extra
            )
        source_invalid = stale or conflict or not eligible
        for label, premium in iv_prices.items():
            status = None
            if stale:
                status = "stale"
            elif conflict:
                status = "metadata_conflict"
            elif not eligible:
                status = (
                    "freshness_unverified"
                    if not freshness_verified
                    else "analytics_ineligible"
                )
            elif label in side_quotes and crossed:
                status = "crossed_quote"
            elif label in side_quotes:
                side_price, side_depth = side_quotes[label]
                if (
                    not math.isfinite(side_price)
                    or side_price <= 0
                    or not math.isfinite(side_depth)
                    or side_depth <= 0
                ):
                    status = "missing_quote"
            elif label == "Mid" and not mid_valid:
                status = "crossed_quote" if crossed else "missing_quote"
            if (
                status is not None
                or source_invalid
                or not all(
                    math.isfinite(_number(value))
                    for value in (row_spot, row.get("Strike"), time, rate)
                )
            ):
                solved = {
                    "ImpliedVolatility": math.nan,
                    "Status": status or "missing_input",
                }
            else:
                solved = implied_volatility(
                    premium,
                    row_spot,
                    row["Strike"],
                    time,
                    rate,
                    row["OptionType"],
                    q,
                    exercise_style,
                )
                if solved["Status"] == "ok" and not freshness_verified:
                    solved["Status"] = "ok_unverified_freshness"
            row[f"ImpliedVolatility{label}"] = solved["ImpliedVolatility"]
            row[f"IVStatus{label}"] = solved["Status"]
        iv = row["ImpliedVolatility"]
        if math.isfinite(_number(iv)) and iv > 0 and time > 0:
            greeks = black_scholes_greeks(
                row_spot,
                row["Strike"],
                time,
                rate,
                iv,
                row["OptionType"],
                q,
                exercise_style,
            )
        else:
            greeks = {
                name: math.nan
                for name in (
                    "Delta",
                    "Gamma",
                    "Vega",
                    "Vega1Pct",
                    "ThetaPerYear",
                    "ThetaPerDay",
                    "Rho",
                    "Rho100bp",
                )
            }
            greeks["Status"] = "unavailable"
        row.update(greeks)
        row["GreeksStatus"] = row.pop("Status")
        row["AnalyticsComputed"] = bool(
            math.isfinite(_number(row.get("ImpliedVolatility")))
        )
        row["AnalyticsReliability"] = (
            "unverified_freshness"
            if row["AnalyticsComputed"] and not freshness_verified
            else "verified" if row["AnalyticsComputed"] else "not_computed"
        )
        contract_size = _number(row.get("ContractSize"))
        row["PremiumContract"] = (
            row["Price"] * contract_size
            if contract_size > 0 and math.isfinite(_number(row["Price"]))
            else math.nan
        )
        for name in (
            "Delta",
            "Gamma",
            "Vega",
            "Vega1Pct",
            "ThetaPerYear",
            "ThetaPerDay",
            "Rho",
            "Rho100bp",
        ):
            row[f"{name}Contract"] = (
                row[name] * contract_size
                if contract_size > 0 and math.isfinite(_number(row[name]))
                else math.nan
            )
        records.append(row)
    result = pd.DataFrame(records)
    result = _liquidity(result, liquidity_weights)
    result = _add_parity(result, q, parity_tolerance)
    result = _cast_options(result)
    result.attrs.update(getattr(options, "attrs", {}))
    result.attrs.update(
        {
            "analytics": "black_scholes_european",
            "premium_unit": "per_underlying_unit",
            "rate_compounding": "continuous",
            "time_basis": "ACT/365F",
            "valuation_date": valuation_date,
            "valuation_date_source": valuation_source,
            "observation_date_verified": observation_verified,
            "allow_unverified_freshness": bool(allow_unverified_freshness),
            "parity_is_diagnostic_only": True,
            "greek_scaling": {
                "Delta": "per_unit",
                "Gamma": "per_unit",
                "Vega": "per_1.0_volatility",
                "Vega1Pct": "per_1_percentage_point",
                "ThetaPerYear": "per_year",
                "ThetaPerDay": "per_calendar_day",
                "Rho": "per_1.0_rate",
                "Rho100bp": "per_100_basis_points",
            },
        }
    )
    return result


def option_put_call_ratios(options, group_by="market"):
    """Calculate put/call Volume, Value and OpenInterest ratios."""
    if not isinstance(options, pd.DataFrame):
        raise TypeError("options must be a pandas DataFrame")
    required = {"InsCode", "OptionType", "Volume", "Value", "OpenInterest"}
    missing = required.difference(options.columns)
    if missing:
        raise ValueError(f"options is missing required columns: {sorted(missing)}")
    if "AsOf" not in options.columns:
        raise ValueError(
            "option_put_call_ratios requires one non-null atomic AsOf snapshot"
        )
    if not options.empty:
        as_of = pd.to_datetime(options["AsOf"], errors="coerce", utc=True)
        if as_of.isna().any() or as_of.nunique() != 1:
            raise ValueError(
                "option_put_call_ratios requires one non-null atomic AsOf snapshot"
            )
    if options.duplicated(["AsOf", "InsCode"], keep=False).any():
        raise ValueError("options contains duplicate contract observations")
    group_map = {
        "market": [],
        "underlying": ["UnderlyingInsCode"],
        "expiry": ["EndDate"],
        "underlying_expiry": ["UnderlyingInsCode", "EndDate"],
    }
    if group_by not in group_map:
        raise ValueError(f"group_by must be one of {sorted(group_map)}")
    fields = ["Volume", "Value", "OpenInterest"]
    invalid_sides = set(options["OptionType"].dropna().astype(str)).difference(
        {"call", "put"}
    )
    if invalid_sides:
        raise ValueError(f"unknown OptionType values: {sorted(invalid_sides)}")
    output_columns = list(group_map[group_by])
    for field in fields:
        output_columns.extend(
            (f"Call{field}", f"Put{field}", f"PCR{field}", f"PCR{field}Status")
        )
    if options.empty:
        result = pd.DataFrame(
            {column: pd.Series(dtype="object") for column in output_columns}
        )
        for field in fields:
            for prefix in ("Call", "Put", "PCR"):
                result[f"{prefix}{field}"] = pd.Series(dtype="Float64")
            result[f"PCR{field}Status"] = pd.Series(dtype="string")
        result.attrs.update(getattr(options, "attrs", {}))
        result.attrs["coverage"] = (
            "only non-missing values present in the supplied snapshot"
        )
        return result
    result_rows = []
    grouper = group_map[group_by]
    groups = (
        [((), options)]
        if not grouper
        else options.groupby(grouper, dropna=False, sort=False)
    )
    for key, group in groups:
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(grouper, key))
        for field in fields:
            values = pd.to_numeric(group.get(field), errors="coerce")
            calls = values.loc[group["OptionType"].eq("call")].sum(min_count=1)
            puts = values.loc[group["OptionType"].eq("put")].sum(min_count=1)
            row[f"Call{field}"] = calls
            row[f"Put{field}"] = puts
            if pd.isna(calls) or calls == 0:
                row[f"PCR{field}"] = math.nan
                row[f"PCR{field}Status"] = (
                    "missing_denominator" if pd.isna(calls) else "zero_denominator"
                )
            else:
                row[f"PCR{field}"] = puts / calls
                row[f"PCR{field}Status"] = "ok"
        result_rows.append(row)
    result = pd.DataFrame(result_rows).reindex(columns=output_columns)
    for field in fields:
        for prefix in ("Call", "Put", "PCR"):
            result[f"{prefix}{field}"] = pd.to_numeric(
                result[f"{prefix}{field}"], errors="coerce"
            ).astype("Float64")
        result[f"PCR{field}Status"] = result[f"PCR{field}Status"].astype("string")
    result.attrs.update(getattr(options, "attrs", {}))
    result.attrs["coverage"] = (
        "only non-missing values present in the supplied snapshot"
    )
    return result


def _atomic_snapshot_pairs(frame):
    """Select/validate whole call-put pairs without row-wise hybridization."""
    if frame.empty:
        return frame.copy()
    required = {"AsOf", "PairID", "PairSequence", "OptionType", "InsCode"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"snapshot is missing atomic pair columns: {sorted(missing)}")
    work = _cast_options(frame)
    if (
        work[["AsOf", "PairID", "PairSequence", "OptionType", "InsCode"]]
        .isna()
        .any()
        .any()
    ):
        raise ValueError("snapshot atomic pair identity cannot be missing")
    selected = []
    for _, group in work.groupby(["AsOf", "PairID"], dropna=False, sort=False):
        latest_sequence = group["PairSequence"].max()
        latest = group.loc[group["PairSequence"].eq(latest_sequence)]
        sides = set(latest["OptionType"])
        if sides != {"call", "put"}:
            raise ValueError(
                "each saved atomic PairID/as-of must contain one call and one put"
            )
        latest = latest.drop_duplicates("OptionType", keep="last")
        if len(latest) != 2:
            raise ValueError("duplicate option sides remain in an atomic pair")
        selected.append(latest)
    return (
        pd.concat(selected, ignore_index=True, sort=False)
        if selected
        else work.iloc[0:0]
    )


def _acquire_snapshot_lock(lock_path, timeout, stale_after):
    """Acquire a bounded, cross-process exclusive writer lock."""
    timeout = _number(timeout)
    stale_after = _number(stale_after)
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("lock_timeout must be finite and non-negative")
    if not math.isfinite(stale_after) or stale_after <= 0:
        raise ValueError("stale_lock_seconds must be finite and positive")
    deadline = time.monotonic() + timeout
    while True:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(f"pid={os.getpid()} created={time.time():.6f}\n")
                stream.flush()
                os.fsync(stream.fileno())
            return
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > stale_after:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out acquiring option snapshot writer lock: {lock_path}"
                )
            time.sleep(min(0.05, max(deadline - time.monotonic(), 0)))


def save_option_snapshot(
    path,
    options=None,
    exchange=0,
    progress=True,
    *,
    lock_timeout=10.0,
    stale_lock_seconds=300.0,
):
    """Persist/dedupe under a bounded cross-process read-modify-write lock."""
    target = Path(path).expanduser()
    if not target.parent.exists():
        raise FileNotFoundError("snapshot parent directory must already exist")
    if options is None:
        options = get_option_market(exchange=exchange, progress=progress)
    if not isinstance(options, pd.DataFrame):
        raise TypeError("options must be a pandas DataFrame")
    options = _atomic_snapshot_pairs(options)
    lock_path = target.with_name(f"{target.name}.lock")
    _acquire_snapshot_lock(lock_path, lock_timeout, stale_lock_seconds)
    temporary_name = None
    try:
        existing = (
            load_option_snapshots(target) if target.exists() else _empty_options()
        )
        combined = (
            options.copy()
            if existing.empty
            else pd.concat([existing, options], ignore_index=True, sort=False)
        )
        if not combined.empty:
            combined["AsOf"] = pd.to_datetime(
                combined["AsOf"], errors="coerce", utc=True
            )
            # JSON storage is millisecond precision; normalize before dedupe so
            # saving the exact same in-memory snapshot is idempotent.
            combined["AsOf"] = combined["AsOf"].dt.floor("ms")
            combined = _atomic_snapshot_pairs(combined).sort_values(
                ["AsOf", "PairID", "OptionType"]
            )
        records = json.loads(combined.to_json(orient="records", date_format="iso"))
        document = {
            "schema_version": OPTION_SNAPSHOT_SCHEMA_VERSION,
            "source": OPTION_SOURCE,
            "coverage": (
                "snapshots explicitly saved by the user from this package "
                "version onward"
            ),
            "records": records,
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    document,
                    stream,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
            temporary_name = None
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
    combined.attrs.update(
        {
            "schema_version": OPTION_SNAPSHOT_SCHEMA_VERSION,
            "source": OPTION_SOURCE,
            "path": str(target),
        }
    )
    return combined.reset_index(drop=True)


def load_option_snapshots(path):
    """Load a snapshot store and reject incompatible schema versions."""
    target = Path(path).expanduser()
    if not target.exists():
        result = _empty_options()
        result.attrs.update(
            {
                "schema_version": OPTION_SNAPSHOT_SCHEMA_VERSION,
                "path": str(target),
                "status": "missing",
            }
        )
        return result
    with target.open("r", encoding="utf-8") as stream:
        document = json.load(stream)
    if document.get("schema_version") != OPTION_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported option snapshot schema_version")
    result = pd.DataFrame(document.get("records", []))
    if result.empty:
        result = _empty_options()
    else:
        result["AsOf"] = pd.to_datetime(
            result["AsOf"], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Tehran")
        for column in OPTION_COLUMNS:
            if column not in result:
                result[column] = pd.NA
        result = result.reindex(columns=OPTION_COLUMNS)
        result = _cast_options(result)
    result.attrs.update(
        {
            "schema_version": OPTION_SNAPSHOT_SCHEMA_VERSION,
            "source": document.get("source"),
            "coverage": document.get("coverage"),
            "path": str(target),
        }
    )
    return result


def _daily_history_rows(frame, symbol, inscode=None):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _empty_history()
    result = pd.DataFrame(index=frame.index)
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.tz is None:
        timestamps = timestamps.tz_localize("Asia/Tehran")
    else:
        timestamps = timestamps.tz_convert("Asia/Tehran")
    result["Timestamp"] = timestamps
    result["Symbol"] = str(symbol)
    result["InsCode"] = _identifier(inscode)
    aliases = {
        "Open": ("Open", "<OPEN>"),
        "High": ("High", "<HIGH>"),
        "Low": ("Low", "<LOW>"),
        # Existing stock history calls raw last trade ``Close`` and weighted
        # closing price ``Final``.  Canonical option/live symmetry uses Last
        # for the former and Close for the latter.
        "Close": ("Final", "<FINAL>", "Adj Close"),
        "Last": ("Close", "Last", "<LAST>"),
        "Volume": ("Volume", "<VOL>"),
        "Value": ("Value", "<VALUE>"),
        "TradeCount": ("No.", "TradeCount", "<OPENINT>"),
    }
    for output, candidates in aliases.items():
        source = next(
            (candidate for candidate in candidates if candidate in frame.columns), None
        )
        result[output] = (
            pd.to_numeric(frame[source], errors="coerce").to_numpy()
            if source
            else np.nan
        )
    result["Price"] = result["Close"].where(result["Close"].gt(0), result["Last"])
    result["PriceSource"] = np.where(
        result["Close"].gt(0), "historical_weighted_close", "historical_last"
    )
    result["Source"] = "tsetmc_price_history"
    result["AsOf"] = pd.NaT
    result["Stale"] = False
    result["NoTrade"] = result["Volume"].le(0).where(result["Volume"].notna(), pd.NA)
    result["AnalyticsEligible"] = result["Price"].gt(0)
    for column in HISTORY_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    return _cast_history(result.reindex(columns=HISTORY_COLUMNS).reset_index(drop=True))


def _underlying_daily_prices(frame):
    """Return historical underlying last/close keyed only by observation date."""
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["_Date", "UnderlyingLast", "UnderlyingClose"])
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    values = pd.DataFrame({"_Date": timestamps.date})
    last_column = next(
        (name for name in ("Close", "Last", "<LAST>") if name in frame), None
    )
    close_column = next(
        (name for name in ("Final", "<FINAL>", "Adj Close") if name in frame), None
    )
    values["UnderlyingLast"] = (
        pd.to_numeric(frame[last_column], errors="coerce").to_numpy()
        if last_column
        else np.nan
    )
    values["UnderlyingClose"] = (
        pd.to_numeric(frame[close_column], errors="coerce").to_numpy()
        if close_column
        else np.nan
    )
    return values.dropna(subset=["_Date"]).drop_duplicates("_Date", keep="last")


def _exact_option_metadata(symbol, stored, live):
    target = _normalize_exact_identifier(symbol)
    candidates = []
    for source, frame in (
        ("local_user_saved_option_snapshot", stored),
        (OPTION_SOURCE, live),
    ):
        if frame is None or frame.empty:
            continue
        exact = frame.loc[
            frame["Symbol"].map(_normalize_exact_identifier).eq(target)
            | frame["InsCode"].map(_normalize_exact_identifier).eq(target)
        ]
        for _, row in exact.iterrows():
            candidates.append((source, row))
    identities = {
        _identifier(row.get("InsCode"))
        for _, row in candidates
        if _identifier(row.get("InsCode"))
    }
    if not identities:
        raise ValueError(
            "exact option symbol/InsCode was not found in authoritative option metadata"
        )
    if len(identities) != 1:
        raise ValueError(
            "exact option identifier is ambiguous in authoritative metadata"
        )
    inscode = next(iter(identities))
    matching = [
        (source, row)
        for source, row in candidates
        if _identifier(row.get("InsCode")) == inscode
    ]
    source, row = matching[-1]
    underlying_code = _identifier(row.get("UnderlyingInsCode"))
    if not underlying_code:
        raise ValueError("authoritative option metadata lacks UnderlyingInsCode")
    return {
        "InsCode": inscode,
        "Symbol": str(row.get("Symbol")),
        "UnderlyingInsCode": underlying_code,
        "UnderlyingSymbol": row.get("UnderlyingSymbol"),
        "source": source,
    }


def _snapshot_history_rows(frame, symbol, source="local_user_saved_option_snapshot"):
    if frame.empty:
        return _empty_history()
    selected = frame.loc[frame["Symbol"].astype("string").eq(str(symbol))].copy()
    if selected.empty:
        return _empty_history()
    result = pd.DataFrame()
    result["Timestamp"] = pd.to_datetime(
        selected["AsOf"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Tehran")
    for column in HISTORY_COLUMNS:
        if column in selected:
            result[column] = selected[column].to_numpy()
    result["Source"] = source
    for column in HISTORY_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    return _cast_history(result.reindex(columns=HISTORY_COLUMNS))


def get_option_history(
    symbol,
    start=None,
    end=None,
    limit=0,
    include_today=False,
    snapshot_path=None,
    progress=True,
    max_requests=3,
):
    """Return price history plus explicitly saved option snapshots.

    Daily OHLCV is sourced from existing TSETMC history. Historical OI,
    quotes, contract adjustments and rates remain nullable unless captured in
    the opt-in local snapshot store. No current yield curve is applied to past
    rows; callers must join an observation-as-of curve themselves.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty exact option symbol")
    if isinstance(limit, bool) or int(limit) != limit or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    # The private resolved-InsCode path avoids fuzzy search, so this is one
    # history request each for option and underlying, plus at most one bulk
    # option metadata request.
    stored_options = (
        load_option_snapshots(snapshot_path)
        if snapshot_path is not None
        else _empty_options()
    )
    stored_target = (
        stored_options["Symbol"]
        .map(_normalize_exact_identifier)
        .eq(_normalize_exact_identifier(symbol))
        | stored_options["InsCode"]
        .map(_normalize_exact_identifier)
        .eq(_normalize_exact_identifier(symbol))
        if not stored_options.empty
        else pd.Series(dtype=bool)
    )
    need_live_metadata = bool(include_today) or not bool(stored_target.any())
    estimated = 2 + int(need_live_metadata)
    if (
        isinstance(max_requests, bool)
        or int(max_requests) != max_requests
        or max_requests < estimated
    ):
        raise ValueError(
            f"max_requests={max_requests!r} is below the preflight "
            f"requirement {estimated}"
        )
    live = (
        get_option_market(progress=progress, max_requests=1)
        if need_live_metadata
        else _empty_options()
    )
    metadata = _exact_option_metadata(symbol, stored_options, live)
    historical = _stock_history(
        symbol=metadata["Symbol"],
        start=start,
        end=end,
        limit=limit,
        auto_adjust=False,
        output_type="complete",
        date_format="gregorian",
        progress=progress,
        include_today=False,
        _resolved_inscode=metadata["InsCode"],
    )
    underlying_history = _stock_history(
        symbol=(
            metadata["UnderlyingSymbol"]
            if pd.notna(metadata["UnderlyingSymbol"])
            else metadata["UnderlyingInsCode"]
        ),
        start=start,
        end=end,
        # Underlyings trade more densely than options; applying the option's
        # row limit here can under-cover sparse option observation dates.
        limit=0,
        auto_adjust=False,
        output_type="complete",
        date_format="gregorian",
        progress=progress,
        include_today=False,
        _resolved_inscode=metadata["UnderlyingInsCode"],
    )
    result = _daily_history_rows(historical, metadata["Symbol"], metadata["InsCode"])
    underlying_prices = _underlying_daily_prices(underlying_history)
    if not result.empty and not underlying_prices.empty:
        result["_Date"] = result["Timestamp"].dt.date
        result = result.merge(
            underlying_prices,
            on="_Date",
            how="left",
            suffixes=("", "_joined"),
        )
        for column in ("UnderlyingLast", "UnderlyingClose"):
            joined = f"{column}_joined"
            if joined in result:
                result[column] = result[joined]
                result = result.drop(columns=joined)
        result = result.drop(columns="_Date")
    if snapshot_path is not None:
        stored = _snapshot_history_rows(stored_options, metadata["Symbol"])
        result = (
            stored.copy()
            if result.empty
            else pd.concat([result, stored], ignore_index=True, sort=False)
        )
    include_warning = None
    if include_today:
        matches = live.loc[live["InsCode"].astype("string").eq(metadata["InsCode"])]
        if len(matches) == 1:
            result = pd.concat(
                [
                    result,
                    _snapshot_history_rows(
                        matches, metadata["Symbol"], source=OPTION_SOURCE
                    ),
                ],
                ignore_index=True,
                sort=False,
            )
        elif matches.empty:
            include_warning = (
                "exact option symbol was absent from the live bulk snapshot"
            )
        else:
            include_warning = (
                "exact option symbol was ambiguous in the live bulk snapshot"
            )
    if not result.empty:
        result["Timestamp"] = pd.to_datetime(
            result["Timestamp"], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Tehran")
        start_ts = (
            pd.Timestamp(coerce_financial_date(start, "start"))
            if start is not None
            else None
        )
        end_ts = (
            pd.Timestamp(coerce_financial_date(end, "end")) if end is not None else None
        )
        if start_ts is not None:
            start_ts = (
                start_ts.tz_localize("Asia/Tehran")
                if start_ts.tzinfo is None
                else start_ts.tz_convert("Asia/Tehran")
            )
            result = result.loc[result["Timestamp"].ge(start_ts)]
        if end_ts is not None:
            end_ts = (
                end_ts.tz_localize("Asia/Tehran")
                if end_ts.tzinfo is None
                else end_ts.tz_convert("Asia/Tehran")
            )
            end_boundary = (
                end_ts + pd.Timedelta(days=1)
                if end_ts.time() == datetime.time()
                else end_ts
            )
            result = result.loc[result["Timestamp"].lt(end_boundary)]
        result = result.sort_values("Timestamp").drop_duplicates(
            ["Timestamp", "Symbol"], keep="last"
        )
        if limit:
            result = result.tail(int(limit))
        result = result.reset_index(drop=True).reindex(columns=HISTORY_COLUMNS)
    result = _cast_history(result.reindex(columns=HISTORY_COLUMNS))
    result.attrs.update(
        {
            "source_coverage": {
                "daily_price_volume": "tsetmc_history",
                "historical_underlying_prices": (
                    "exact UnderlyingInsCode history joined by observation date"
                ),
                "bid_ask_open_interest_adjustments": (
                    "local snapshots only when explicitly saved"
                ),
                "historical_rates": "not supplied; join observation-as-of curve",
            },
            "limitations": (
                "TSETMC public history does not reliably provide historical OI, "
                "quotes, adjustments or rates"
            ),
            "prices_no_lookahead": True,
            "option_prices_no_lookahead": True,
            "underlying_prices_no_lookahead": True,
            "metadata_no_lookahead": False,
            "universe_no_lookahead": False,
            "metadata_source": metadata["source"],
            "metadata_limitation": (
                "contract identity comes from a current live universe or a "
                "user-saved post-1.1 snapshot; "
                "expired pre-1.1 contracts require authoritative saved metadata"
            ),
            "rates_no_lookahead": pd.NA,
            "curve_applied": False,
            "include_today_requested": bool(include_today),
            "include_today_warning": include_warning,
            "request_count_upper_bound": estimated,
            "max_requests": int(max_requests),
            "option_identity": metadata,
            "symbol_resolution": (
                "exact normalized Persian/Arabic glyph match or exact InsCode; "
                "no partial matching"
            ),
        }
    )
    return result


__all__ = [
    "OPTION_SNAPSHOT_SCHEMA_VERSION",
    "get_option_market",
    "analyze_option_chain",
    "option_put_call_ratios",
    "get_option_history",
    "save_option_snapshot",
    "load_option_snapshots",
]
