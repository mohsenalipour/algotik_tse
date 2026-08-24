"""Market data module — live market watchlist and client type data.

Provides bulk market data from TSETMC in a single API call:

- ``market_watch()``  — Real-time prices, volumes, and comprehensive
  instrument data (symbol, name, EPS, price limits, etc.) for all
  instruments.
- ``market_client_type()``  — Individual (حقیقی) vs institutional (حقوقی)
  trade breakdown for all instruments.
"""

import datetime
import copy
import re
import warnings
from collections.abc import Iterable

import numpy as np
import pandas as pd
from persiantools import characters
from persiantools.jdatetime import JalaliDate

from ..http_client import safe_get
from ..settings import settings
from ..exceptions import (
    AmbiguousSymbolError,
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)
from .resolver import normalize_instrument_text, resolve_instrument, validate_ins_code

STOCK_COLUMNS = [
    # Exact legacy public order; values and semantics remain unchanged.
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "Time",
    "Yesterday",
    "Close",
    "Last",
    "TradeCount",
    "Volume",
    "Value",
    "Low",
    "High",
    "EPS",
    "PriceYesterday",
    "Flow",
    "SectorCode",
    "MaxAllowed",
    "MinAllowed",
    "BaseVolume",
    "InstrumentType",
    "NAV",
    "MarketCode",
    "Change",
    "ChangePct",
    # Additive canonical schema.
    "FirstPrice",
    "Open",
    "PreviousClose",
    "ActualBaseVolume",
    "VisitCount",
    "SharesOutstanding",
    "PreviousCloseChange",
    "PreviousCloseChangePct",
    "LegacyYesterday",
    "LegacyBaseVolume",
]
ORDER_COLUMNS = [
    "InsCode",
    "Level",
    "AskOrderCount",
    "BidOrderCount",
    "BidPrice",
    "AskPrice",
    "BidVolume",
    "AskVolume",
]
PUBLIC_ORDER_COLUMNS = [
    "InsCode",
    "Symbol",
    "Name",
    "Level",
    "BidOrderCount",
    "BidVolume",
    "BidPrice",
    "AskPrice",
    "AskVolume",
    "AskOrderCount",
    "trade_date",
    "market_state",
    "exchange_time",
    "fetched_at",
    "snapshot_age_seconds",
    "is_today_trade_date",
    "is_history_eligible",
    "is_realtime_fresh",
    "is_previous_trade_date",
    "is_stale",
    "is_partial",
]
CLIENT_COLUMNS = [
    "InsCode",
    "Buy_I_Count",
    "Buy_N_Count",
    "Buy_I_Volume",
    "Buy_N_Volume",
    "Sell_I_Count",
    "Sell_N_Count",
    "Sell_I_Volume",
    "Sell_N_Volume",
    "Net_I_Volume",
    "Net_N_Volume",
]

MARKET_WATCH_MIGRATION = {
    "schema_version": "1.1",
    "corrected_fields": {
        "Yesterday": "legacy field 5; use PreviousClose for field 13",
        "BaseVolume": "legacy field 21; use ActualBaseVolume for field 15",
    },
    "new_aliases": {
        "FirstPrice": "field 5",
        "Open": "field 5",
        "PreviousClose": "field 13",
        "SharesOutstanding": "field 21",
    },
}


# ── helpers ───────────────────────────────────────────────────


def _heven_to_time_str(heven):
    """Convert hEven integer (e.g. 125205) to 'HH:MM:SS' string."""
    try:
        val = int(heven)
        h = val // 10000
        m = (val % 10000) // 100
        s = val % 100
        return f"{h:02d}:{m:02d}:{s:02d}"
    except (ValueError, TypeError):
        return str(heven)


def _safe_int(val, default=0):
    """Convert to int, return *default* on failure.

    Handles float-strings like ``'22964.00'`` by trying
    ``int(float(val))`` as a fallback.
    """
    try:
        return int(val)
    except (ValueError, TypeError):
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default


def _wire_integer_is_valid(value):
    """Whether a wire field contains a finite, integral numeric value."""
    if value is None or isinstance(value, bool) or not str(value).strip():
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(numeric) and numeric.is_integer())


def _safe_float(val, default=0.0):
    """Convert to float, return *default* on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_divide(numerator, denominator):
    """Vectorised division where an undefined ratio is always ``NaN``."""
    numerator = pd.to_numeric(numerator, errors="coerce").astype(float)
    denominator = pd.to_numeric(denominator, errors="coerce").astype(float)
    return numerator.div(denominator.where(denominator.ne(0))).replace(
        [np.inf, -np.inf], np.nan
    )


def _client_volume_audit(
    individual_buy,
    legal_buy,
    individual_sell,
    legal_sell,
    market_volume,
    tolerance=None,
):
    """Return client-feed volume reconciliation metrics.

    A live client row is considered consistent only when both buy and sell
    totals are positive and independently reconcile to traded market volume.
    """
    tolerance = float(
        tolerance
        if tolerance is not None
        else getattr(settings, "client_volume_consistency_tolerance", 0.05)
    )
    buy_total = pd.to_numeric(individual_buy, errors="coerce") + pd.to_numeric(
        legal_buy, errors="coerce"
    )
    sell_total = pd.to_numeric(individual_sell, errors="coerce") + pd.to_numeric(
        legal_sell, errors="coerce"
    )
    volume = pd.to_numeric(market_volume, errors="coerce")
    buy_ratio = _safe_divide(buy_total, volume)
    sell_ratio = _safe_divide(sell_total, volume)
    allowed_delta = volume.abs() * tolerance
    numeric_slack = volume.abs().clip(lower=1) * np.finfo(float).eps * 4
    consistent = (
        buy_total.gt(0)
        & sell_total.gt(0)
        & volume.gt(0)
        & buy_total.sub(volume).abs().le(allowed_delta + numeric_slack)
        & sell_total.sub(volume).abs().le(allowed_delta + numeric_slack)
    ).fillna(False)
    return {
        "client_buy_volume_total": buy_total,
        "client_sell_volume_total": sell_total,
        "client_buy_volume_difference": buy_total - volume,
        "client_sell_volume_difference": sell_total - volume,
        "client_buy_volume_ratio": buy_ratio,
        "client_sell_volume_ratio": sell_ratio,
        "client_snapshot_consistent": consistent.astype(bool),
    }


def _normalise_symbol(value):
    """Normalise Arabic/Persian character variants used by TSETMC."""
    if value is None:
        return ""
    return characters.ar_to_fa(str(value)).replace("\u200c", "").strip()


def _parse_market_timestamp(value):
    """Convert the Jalali MarketWatch header timestamp to Tehran time."""
    match = re.search(
        r"(?P<year>\d{2,4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})\s+"
        r"(?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})",
        str(value or ""),
    )
    if not match:
        return None
    values = {key: int(item) for key, item in match.groupdict().items()}
    year = values["year"]
    if year < 100:
        year = 1400 + year if year < 80 else 1300 + year
    try:
        gregorian = JalaliDate(year, values["month"], values["day"]).to_gregorian()
        naive = datetime.datetime.combine(
            gregorian,
            datetime.time(values["hour"], values["minute"], values["second"]),
        )
        return pd.Timestamp(naive, tz="Asia/Tehran")
    except (TypeError, ValueError, OverflowError):
        return None


FRESHNESS_THRESHOLD_SECONDS = 120.0


def _snapshot_metadata(
    market_time,
    market_state="",
    fetched_at=None,
    freshness_threshold_seconds=None,
    clock_skew_tolerance_seconds=None,
):
    """Build date-level and real-time freshness metadata independently.

    ``is_history_eligible`` is intentionally date-level here; the parser adds
    the requirement that at least one instrument row was parsed. Real-time
    freshness uses a configurable age threshold and symmetric clock-skew
    allowance and must not decide whether a valid same-day close may be added
    to daily history.
    """
    fetched_at = fetched_at or pd.Timestamp.now(tz="Asia/Tehran")
    exchange_time = _parse_market_timestamp(market_time)
    trade_date = exchange_time.date() if exchange_time is not None else None
    is_today_trade_date = trade_date is not None and trade_date == fetched_at.date()
    is_previous_trade_date = trade_date is not None and not is_today_trade_date
    snapshot_age_seconds = (
        (fetched_at - exchange_time).total_seconds()
        if exchange_time is not None
        else np.nan
    )
    threshold = float(
        freshness_threshold_seconds
        if freshness_threshold_seconds is not None
        else getattr(
            settings,
            "market_snapshot_freshness_seconds",
            FRESHNESS_THRESHOLD_SECONDS,
        )
    )
    skew_tolerance = abs(
        float(
            clock_skew_tolerance_seconds
            if clock_skew_tolerance_seconds is not None
            else getattr(settings, "market_clock_skew_tolerance_seconds", 5.0)
        )
    )
    is_realtime_fresh = bool(
        exchange_time is not None
        and is_today_trade_date
        and -skew_tolerance <= snapshot_age_seconds <= threshold + skew_tolerance
    )
    return {
        "trade_date": trade_date,
        "market_state": market_state,
        "exchange_time": exchange_time,
        "fetched_at": fetched_at,
        "snapshot_age_seconds": snapshot_age_seconds,
        "is_today_trade_date": bool(is_today_trade_date),
        "is_history_eligible": bool(is_today_trade_date),
        "is_realtime_fresh": is_realtime_fresh,
        "is_previous_trade_date": bool(is_previous_trade_date),
        # Backward-compatible freshness alias. It no longer controls daily
        # history augmentation; use is_history_eligible for that purpose.
        "is_stale": not is_realtime_fresh,
        # TSETMC exposes provider status text here. There is no documented,
        # stable P/F/C code mapping, so partial/final must remain unknown.
        "is_partial": pd.NA,
    }


def _is_current_snapshot(snapshot, now=None):
    """Whether a snapshot can be considered for today's daily history.

    Instrument-level trade/OHLC validation is performed by the caller. This
    deliberately does not require ``is_realtime_fresh``: a same-day final
    snapshot remains valid daily history after the real-time freshness window.
    """
    if not snapshot:
        return False
    stocks = snapshot.get("stocks")
    reference_time = now or pd.Timestamp.now(tz="Asia/Tehran")
    reference_time = pd.Timestamp(reference_time)
    if reference_time.tzinfo is None:
        reference_time = reference_time.tz_localize("Asia/Tehran")
    else:
        reference_time = reference_time.tz_convert("Asia/Tehran")
    same_tehran_date = snapshot.get("trade_date") == reference_time.date()
    eligible = snapshot.get("is_history_eligible")
    if eligible is None:
        eligible = same_tehran_date
    return (
        bool(eligible)
        and same_tehran_date
        and isinstance(stocks, pd.DataFrame)
        and not stocks.empty
    )


def _empty_order_book():
    return pd.DataFrame(columns=ORDER_COLUMNS)


def _parse_market_watch_response(text, fetched_at=None):
    """Parse one raw ``MarketWatchInit`` response.

    This internal parser is intentionally network-free so the wire contract can
    be protected by fixture-based tests.  The field map follows the actual
    response returned by ``MarketWatchInit.aspx``.
    """
    text = (text or "").strip()
    if not text:
        raise DataParsingError("Empty response from market watch endpoint")

    parts = text.split("@")
    if len(parts) < 3:
        raise DataParsingError(
            f"Unexpected market watch format: expected at least 3 "
            f"'@'-separated parts, got {len(parts)}"
        )

    market_time = ""
    market_state = ""
    index_value = 0.0
    try:
        header_fields = parts[1].replace("\n", ",").replace("\r", "").split(",")
        if header_fields:
            market_time = header_fields[0].strip()
        if len(header_fields) >= 2:
            market_state = header_fields[1].strip()
        if len(header_fields) >= 3:
            index_value = _safe_float(header_fields[2])
    except (ValueError, TypeError, IndexError):
        pass
    metadata = _snapshot_metadata(
        market_time, market_state=market_state, fetched_at=fetched_at
    )

    # Wire fields used below:
    # 5=PDrCotVal/first price, 13=previous close, 15=base volume,
    # 16=visit count, 21=shares outstanding.
    stock_records = []
    eps_validity = {}
    for item in parts[2].strip().split(";") if parts[2].strip() else []:
        fields = item.split(",")
        if len(fields) < 22:
            continue
        try:
            first_price = _safe_int(fields[5])
            previous_close = _safe_int(fields[13]) if len(fields) > 13 else 0
            ins_code = fields[0].strip()
            eps_validity[ins_code] = bool(
                len(fields) > 14 and _wire_integer_is_valid(fields[14])
            )
            stock_records.append(
                {
                    "InsCode": ins_code,
                    "ISIN": fields[1].strip(),
                    "Symbol": fields[2].strip(),
                    "Name": fields[3].strip(),
                    "Time": _heven_to_time_str(fields[4]),
                    "FirstPrice": first_price,
                    "Open": first_price,
                    # Existing public columns intentionally retain the exact
                    # pre-1.1 wire semantics for backward compatibility.
                    "Yesterday": first_price,
                    "PreviousClose": previous_close,
                    "PriceYesterday": previous_close,
                    "LegacyYesterday": first_price,
                    "Close": _safe_int(fields[6]),
                    "Last": _safe_int(fields[7]),
                    "TradeCount": _safe_int(fields[8]),
                    "Volume": _safe_int(fields[9]),
                    "Value": _safe_int(fields[10]),
                    "Low": _safe_int(fields[11]),
                    "High": _safe_int(fields[12]),
                    "EPS": _safe_int(fields[14]) if len(fields) > 14 else 0,
                    "ActualBaseVolume": (
                        _safe_int(fields[15]) if len(fields) > 15 else 0
                    ),
                    "BaseVolume": _safe_int(fields[21]) if len(fields) > 21 else 0,
                    "LegacyBaseVolume": (
                        _safe_int(fields[21]) if len(fields) > 21 else 0
                    ),
                    "VisitCount": _safe_int(fields[16]) if len(fields) > 16 else 0,
                    "Flow": _safe_int(fields[17]) if len(fields) > 17 else 0,
                    "SectorCode": fields[18].strip() if len(fields) > 18 else "",
                    "MaxAllowed": _safe_int(fields[19]) if len(fields) > 19 else 0,
                    "MinAllowed": _safe_int(fields[20]) if len(fields) > 20 else 0,
                    "SharesOutstanding": (
                        _safe_int(fields[21]) if len(fields) > 21 else 0
                    ),
                    "InstrumentType": (
                        _safe_int(fields[22]) if len(fields) > 22 else 0
                    ),
                    "NAV": _safe_int(fields[23]) if len(fields) > 23 else 0,
                    "MarketCode": fields[25].strip() if len(fields) > 25 else "",
                }
            )
        except (ValueError, TypeError, IndexError):
            continue

    stocks_df = pd.DataFrame(stock_records)
    if not stocks_df.empty:
        stocks_df["Change"] = stocks_df["Close"] - stocks_df["Yesterday"]
        stocks_df["ChangePct"] = (
            _safe_divide(stocks_df["Change"], stocks_df["Yesterday"]) * 100
        ).round(2)
        stocks_df["Change"] = stocks_df["Change"].astype(int)
        stocks_df["PreviousCloseChange"] = (
            stocks_df["Close"] - stocks_df["PreviousClose"]
        ).astype(int)
        stocks_df["PreviousCloseChangePct"] = (
            _safe_divide(stocks_df["PreviousCloseChange"], stocks_df["PreviousClose"])
            * 100
        ).round(2)
    source_schema_presence = {
        column: column in stocks_df.columns for column in STOCK_COLUMNS
    }
    stocks_df = stocks_df.reindex(columns=STOCK_COLUMNS)
    # Preserve the exact legacy EPS value/column while exposing whether the
    # wire value was actually present. DataFrame attrs are additive metadata
    # and do not change MarketWatch's public shape or values.
    stocks_df.attrs["field_validity"] = {"EPS": eps_validity}
    stocks_df.attrs["source_schema_presence"] = source_schema_presence
    metadata["is_history_eligible"] = bool(
        metadata["is_today_trade_date"] and not stocks_df.empty
    )

    order_records = []
    # Part 3 wire order:
    # InsCode, depth, ask count, bid count, bid price, ask price,
    # bid quantity, ask quantity.
    if len(parts) > 3 and parts[3].strip():
        for item in parts[3].strip().split(";"):
            fields = item.split(",")
            if len(fields) < 8:
                continue
            try:
                level = _safe_int(fields[1])
                if level < 1 or level > 5:
                    continue
                order_records.append(
                    {
                        "InsCode": fields[0].strip(),
                        "Level": level,
                        "AskOrderCount": _safe_int(fields[2]),
                        "BidOrderCount": _safe_int(fields[3]),
                        "BidPrice": _safe_int(fields[4]),
                        "AskPrice": _safe_int(fields[5]),
                        "BidVolume": _safe_int(fields[6]),
                        "AskVolume": _safe_int(fields[7]),
                    }
                )
            except (ValueError, TypeError, IndexError):
                continue

    order_book = pd.DataFrame(order_records)
    if order_book.empty:
        order_book = _empty_order_book()
    else:
        order_book.sort_values(["InsCode", "Level"], inplace=True)
        order_book.reset_index(drop=True, inplace=True)

    result = {
        "stocks": stocks_df,
        "order_book": order_book,
        "market_time": market_time,
        "index_value": index_value,
        "migration": copy.deepcopy(MARKET_WATCH_MIGRATION),
    }
    result.update(metadata)
    return result


# ── backward-compat shim ─────────────────────────────────────


def market_data():
    """Deprecated — use :func:`market_watch` instead.

    .. deprecated:: 1.0.0
        ``market_data()`` was a placeholder. It now redirects to
        :func:`market_watch`.
    """
    warnings.warn(
        "market_data() is deprecated. Use market_watch() instead.",
        FutureWarning,
        stacklevel=2,
    )
    return market_watch()


# ══════════════════════════════════════════════════════════════
#  market_watch()
# ══════════════════════════════════════════════════════════════


def market_watch():
    """Get live market data for all instruments in one API call.

    Fetches comprehensive market data from the TSETMC MarketWatchInit
    endpoint, including symbol names, ISIN codes, EPS, price limits,
    and much more.

    Compatibility note
    ------------------
    Existing columns intentionally keep their pre-1.1 semantics:
    ``Yesterday`` is wire field 5, ``BaseVolume`` is wire field 21, and
    ``Change`` is relative to legacy ``Yesterday``. Prefer the additive
    canonical names ``FirstPrice``, ``PreviousClose``, ``ActualBaseVolume``,
    ``SharesOutstanding`` and ``PreviousCloseChange`` for new code. The
    unified :func:`get_live_market` API exposes corrected aliases by default.

    Returns
    -------
    dict
        A dictionary with the following keys:

        - ``'stocks'`` : pd.DataFrame — Comprehensive data for every
          instrument on TSETMC.

          Columns include ``InsCode``, ``ISIN``, ``Symbol``, ``Name``,
          ``Time``, ``FirstPrice``, ``Open``, ``PreviousClose``,
          ``Yesterday``, ``Close``, ``Last``, ``TradeCount``,
          ``Volume``, ``Value``, ``Low``, ``High``, ``EPS``,
          ``PriceYesterday``, ``BaseVolume``, ``VisitCount``,
          ``SharesOutstanding``, ``Flow``,
          ``SectorCode``, ``MaxAllowed``, ``MinAllowed``,
          ``InstrumentType``, ``NAV``, ``MarketCode``,
          ``Change``, ``ChangePct``

        - ``'order_book'`` : pd.DataFrame — Five bid/ask levels in long form.

        - ``'market_time'`` : str — Jalali date/time string.

        - ``'index_value'`` : float — Total market index (شاخص کل).

    Raises
    ------
    ConnectionError
        If the HTTP request fails.
    DataParsingError
        If the response format is unexpected.

    Examples
    --------
    >>> import algotik_tse as att
    >>> data = att.market_watch()
    >>> print(data['stocks'].head())
    >>> # Filter regular stocks only
    >>> regular = data['stocks'][data['stocks']['InstrumentType'].isin([300, 303, 309])]
    """
    url = settings.url_market_watch_init
    response = safe_get(url)
    if response is None:
        raise ConnectionError(f"Failed to fetch market watch data from {url}")
    return _parse_market_watch_response(response.text)


# ══════════════════════════════════════════════════════════════
#  market_client_type()
# ══════════════════════════════════════════════════════════════


def market_client_type():
    """Get individual vs institutional trade data for all instruments.

    Fetches the ClientTypeAll endpoint in a single API call, returning
    today's breakdown of trade counts and volumes between individual
    (حقیقی) and institutional (حقوقی) participants for every instrument.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code (str)
        - ``Buy_I_Count`` — Number of individual (حقیقی) buyers
        - ``Buy_N_Count`` — Number of institutional (حقوقی) buyers
        - ``Buy_I_Volume`` — Volume bought by individuals
        - ``Buy_N_Volume`` — Volume bought by institutions
        - ``Sell_I_Count`` — Number of individual sellers
        - ``Sell_N_Count`` — Number of institutional sellers
        - ``Sell_I_Volume`` — Volume sold by individuals
        - ``Sell_N_Volume`` — Volume sold by institutions
        - ``Net_I_Volume`` — Net individual volume (buy - sell)
        - ``Net_N_Volume`` — Net institutional volume (buy - sell)

    Raises
    ------
    ConnectionError
        If the HTTP request fails.
    DataParsingError
        If the response format is unexpected.

    Examples
    --------
    >>> import algotik_tse as att
    >>> df = att.market_client_type()
    >>> print(df.head())
    >>> # Filter for net institutional buyers
    >>> buyers = df[df['Net_N_Volume'] > 0]
    """
    url = settings.url_client_type_all
    response = safe_get(url)
    if response is None:
        raise ConnectionError(f"Failed to fetch client type data from {url}")

    text = response.text.strip()
    if not text:
        raise DataParsingError("Empty response from client type endpoint")

    records = []
    for item in text.split(";"):
        fields = item.split(",")
        if len(fields) < 9:
            continue
        try:
            records.append(
                {
                    "InsCode": fields[0],
                    "Buy_I_Count": _safe_int(fields[1]),
                    "Buy_N_Count": _safe_int(fields[2]),
                    "Buy_I_Volume": _safe_int(fields[3]),
                    "Buy_N_Volume": _safe_int(fields[4]),
                    "Sell_I_Count": _safe_int(fields[5]),
                    "Sell_N_Count": _safe_int(fields[6]),
                    "Sell_I_Volume": _safe_int(fields[7]),
                    "Sell_N_Volume": _safe_int(fields[8]),
                }
            )
        except (ValueError, TypeError, IndexError):
            continue

    df = pd.DataFrame(records)

    if not df.empty:
        df["Net_I_Volume"] = df["Buy_I_Volume"] - df["Sell_I_Volume"]
        df["Net_N_Volume"] = df["Buy_N_Volume"] - df["Sell_N_Volume"]

    return df.reindex(columns=CLIENT_COLUMNS)


def _selector_list(selector):
    if selector is None:
        return None
    if isinstance(selector, str) or not isinstance(selector, Iterable):
        return [selector]
    return list(selector)


def _instrument_mask(df, selector):
    selectors = _selector_list(selector)
    if selectors is None:
        return pd.Series(True, index=df.index)
    if not selectors:
        return pd.Series(False, index=df.index)
    normalized = [(value, str(value).strip()) for value in selectors]
    inscodes = {text for _, text in normalized if text.isdigit()}
    symbols = {
        _normalise_symbol(value) for value, text in normalized if not text.isdigit()
    }
    return df["InsCode"].astype(str).isin(inscodes) | df["Symbol"].map(
        _normalise_symbol
    ).isin(symbols)


def _resolve_live_selection(frame, selector, snapshot, strict=False):
    """Select live rows through canonical exact identity resolution."""
    selectors = _selector_list(selector)
    if selectors is None:
        result = frame
        missing = []
    else:
        codes = []
        missing = []
        memo = {}
        for value in selectors:
            normalized = normalize_instrument_text(value)
            key = (
                f"inscode:{normalized}"
                if normalized.isascii() and normalized.isdigit()
                else f"selector:{normalized}"
            )
            if key not in memo:
                try:
                    memo[key] = resolve_instrument(value, snapshot=snapshot)
                except StockNotFoundError:
                    memo[key] = None
            ref = memo[key]
            if ref is None:
                if value not in missing:
                    missing.append(value)
                continue
            codes.append(ref.ins_code)
            if not frame["InsCode"].astype(str).eq(ref.ins_code).any():
                if value not in missing:
                    missing.append(value)
        wanted = set(codes)
        result = frame.loc[frame["InsCode"].astype(str).isin(wanted)]
    if strict and missing:
        raise StockNotFoundError(
            f"Selectors absent from the current MarketWatch snapshot: {missing!r}"
        )
    return result, missing


def get_order_book(symbol=None, *, selector_strict=False):
    """Get the five-level order book from the bulk market snapshot.

    Parameters
    ----------
    symbol : str, optional
        Persian symbol or ``InsCode``.  When omitted, all available market
        levels are returned in long form.

    Returns
    -------
    pandas.DataFrame
        One row per instrument/depth with bid/ask order count, price and
        volume.  A snapshot and its order book come from the same HTTP
        response, avoiding cross-request price/order-book drift.
    """
    snapshot = market_watch()
    orders = snapshot["order_book"].copy()
    stocks = snapshot["stocks"]
    if not isinstance(selector_strict, bool):
        raise InvalidParameterError("selector_strict must be bool")
    selected_stocks, missing = _resolve_live_selection(
        stocks, symbol, snapshot, strict=selector_strict
    )
    if orders.empty:
        result = pd.DataFrame(columns=PUBLIC_ORDER_COLUMNS)
        result.attrs["migration"] = copy.deepcopy(snapshot.get("migration", {}))
        result.attrs["missing_selectors"] = list(missing)
        return result

    identity = selected_stocks.loc[:, ["InsCode", "Symbol", "Name"]].drop_duplicates(
        "InsCode"
    )
    orders = orders.merge(identity, on="InsCode", how="left")
    orders = orders.loc[
        orders["InsCode"].astype(str).isin(identity["InsCode"].astype(str))
    ]
    orders = orders.loc[
        :,
        [
            "InsCode",
            "Symbol",
            "Name",
            "Level",
            "BidOrderCount",
            "BidVolume",
            "BidPrice",
            "AskPrice",
            "AskVolume",
            "AskOrderCount",
        ],
    ]
    for column in [
        "trade_date",
        "market_state",
        "exchange_time",
        "fetched_at",
        "snapshot_age_seconds",
        "is_today_trade_date",
        "is_history_eligible",
        "is_realtime_fresh",
        "is_previous_trade_date",
        "is_stale",
        "is_partial",
    ]:
        orders[column] = snapshot.get(column)
    result = orders.reindex(columns=PUBLIC_ORDER_COLUMNS).reset_index(drop=True)
    result.attrs["migration"] = copy.deepcopy(snapshot.get("migration", {}))
    result.attrs["missing_selectors"] = list(missing)
    return result


def _wide_order_book(order_book):
    """Convert the long five-level order book to one row per instrument."""
    if order_book.empty:
        return pd.DataFrame(columns=["InsCode"])
    result = pd.DataFrame({"InsCode": order_book["InsCode"].unique()})
    for level in range(1, 6):
        level_df = order_book.loc[order_book["Level"].eq(level)].copy()
        level_df = level_df.drop_duplicates("InsCode", keep="last")
        level_df = level_df.rename(
            columns={
                column: f"{column}{level}"
                for column in [
                    "BidOrderCount",
                    "BidVolume",
                    "BidPrice",
                    "AskPrice",
                    "AskVolume",
                    "AskOrderCount",
                ]
            }
        )
        result = result.merge(
            level_df.drop(columns=["Level"]), on="InsCode", how="left"
        )
    return result


def _canonical_live_stocks(stocks):
    """Return a corrected semantic copy for new live APIs.

    ``market_watch()`` remains byte-for-byte compatible in the meaning of its
    pre-1.1 columns. New APIs intentionally remap the familiar aliases while
    retaining explicit legacy columns for migration.
    """
    source_attrs = copy.deepcopy(getattr(stocks, "attrs", {}))
    source_schema_presence = source_attrs.get("source_schema_presence", {})
    if not isinstance(source_schema_presence, dict):
        source_schema_presence = {}
    else:
        source_schema_presence = dict(source_schema_presence)
    for column in STOCK_COLUMNS:
        source_schema_presence.setdefault(column, column in stocks.columns)
    source_attrs["source_schema_presence"] = source_schema_presence

    result = stocks.copy(deep=True).reindex(columns=STOCK_COLUMNS)
    result["LegacyYesterday"] = result["Yesterday"]
    result["LegacyBaseVolume"] = result["BaseVolume"]
    result["Yesterday"] = result["PreviousClose"]
    result["BaseVolume"] = result["ActualBaseVolume"]
    result["Change"] = result["PreviousCloseChange"]
    result["ChangePct"] = result["PreviousCloseChangePct"]
    result.attrs.clear()
    result.attrs.update(source_attrs)
    return result


def _enrich_live_market(
    stocks, client_type, order_book, as_of=None, snapshot_metadata=None
):
    """Merge bulk feeds and calculate safe, trading-oriented metrics."""
    live = _canonical_live_stocks(stocks)
    source_attrs = copy.deepcopy(live.attrs)

    if client_type is not None and not client_type.empty:
        live = live.merge(client_type, on="InsCode", how="left")
        live.attrs.update(copy.deepcopy(source_attrs))
    client_columns = [
        "Buy_I_Count",
        "Buy_N_Count",
        "Buy_I_Volume",
        "Buy_N_Volume",
        "Sell_I_Count",
        "Sell_N_Count",
        "Sell_I_Volume",
        "Sell_N_Volume",
        "Net_I_Volume",
        "Net_N_Volume",
    ]
    for column in client_columns:
        if column not in live:
            live[column] = np.nan

    wide_orders = _wide_order_book(order_book)
    if not wide_orders.empty:
        live = live.merge(wide_orders, on="InsCode", how="left")
        live.attrs.update(copy.deepcopy(source_attrs))
    for level in range(1, 6):
        for prefix in [
            "BidOrderCount",
            "BidVolume",
            "BidPrice",
            "AskPrice",
            "AskVolume",
            "AskOrderCount",
        ]:
            column = f"{prefix}{level}"
            if column not in live:
                live[column] = np.nan

    semantic_aliases = {
        "IndividualBuyCount": "Buy_I_Count",
        "LegalBuyCount": "Buy_N_Count",
        "IndividualSellCount": "Sell_I_Count",
        "LegalSellCount": "Sell_N_Count",
        "IndividualBuyVolume": "Buy_I_Volume",
        "LegalBuyVolume": "Buy_N_Volume",
        "IndividualSellVolume": "Sell_I_Volume",
        "LegalSellVolume": "Sell_N_Volume",
        "NetIndividualVolume": "Net_I_Volume",
        "NetLegalVolume": "Net_N_Volume",
    }
    for public_name, wire_name in semantic_aliases.items():
        live[public_name] = live[wire_name]

    historical_aliases = {
        "N_buy_retail": "Buy_I_Count",
        "N_buy_institutional": "Buy_N_Count",
        "N_sell_retail": "Sell_I_Count",
        "N_sell_institutional": "Sell_N_Count",
        "Vol_buy_retail": "Buy_I_Volume",
        "Vol_buy_institutional": "Buy_N_Volume",
        "Vol_sell_retail": "Sell_I_Volume",
        "Vol_sell_institutional": "Sell_N_Volume",
    }
    for public_name, wire_name in historical_aliases.items():
        live[public_name] = live[wire_name]

    live["VWAP"] = _safe_divide(live["Value"], live["Volume"])
    live["PerCapitaIndividualBuyVolume"] = _safe_divide(
        live["IndividualBuyVolume"], live["IndividualBuyCount"]
    )
    live["PerCapitaIndividualSellVolume"] = _safe_divide(
        live["IndividualSellVolume"], live["IndividualSellCount"]
    )
    live["PerCapitaLegalBuyVolume"] = _safe_divide(
        live["LegalBuyVolume"], live["LegalBuyCount"]
    )
    live["PerCapitaLegalSellVolume"] = _safe_divide(
        live["LegalSellVolume"], live["LegalSellCount"]
    )
    live["IndividualPower"] = _safe_divide(
        live["PerCapitaIndividualBuyVolume"],
        live["PerCapitaIndividualSellVolume"],
    )
    live["LegalPower"] = _safe_divide(
        live["PerCapitaLegalBuyVolume"], live["PerCapitaLegalSellVolume"]
    )

    for side in ["IndividualBuy", "IndividualSell", "LegalBuy", "LegalSell"]:
        live[f"Estimated{side}Value"] = live[f"{side}Volume"] * live["VWAP"]
        live[f"EstimatedPerCapita{side}Value"] = _safe_divide(
            live[f"Estimated{side}Value"], live[f"{side}Count"]
        )
    live["EstimatedNetIndividualFlow"] = live["NetIndividualVolume"] * live["VWAP"]
    live["EstimatedNetLegalFlow"] = live["NetLegalVolume"] * live["VWAP"]
    live["Per_capita_buy_retail"] = live["EstimatedPerCapitaIndividualBuyValue"]
    live["Per_capita_sell_retail"] = live["EstimatedPerCapitaIndividualSellValue"]
    live["Per_capita_buy_institutional"] = live["EstimatedPerCapitaLegalBuyValue"]
    live["Per_capita_sell_institutional"] = live["EstimatedPerCapitaLegalSellValue"]
    live["Power_retail"] = live["IndividualPower"]
    live["Power_institutional"] = live["LegalPower"]

    total_buy = live["IndividualBuyVolume"] + live["LegalBuyVolume"]
    total_sell = live["IndividualSellVolume"] + live["LegalSellVolume"]
    client_audit = _client_volume_audit(
        live["IndividualBuyVolume"],
        live["LegalBuyVolume"],
        live["IndividualSellVolume"],
        live["LegalSellVolume"],
        live["Volume"],
    )
    for column, values in client_audit.items():
        live[column] = values
    live["IndividualBuyParticipation"] = _safe_divide(
        live["IndividualBuyVolume"], total_buy
    )
    live["LegalBuyParticipation"] = _safe_divide(live["LegalBuyVolume"], total_buy)
    live["IndividualSellParticipation"] = _safe_divide(
        live["IndividualSellVolume"], total_sell
    )
    live["LegalSellParticipation"] = _safe_divide(live["LegalSellVolume"], total_sell)
    client_actionable_columns = [
        "PerCapitaIndividualBuyVolume",
        "PerCapitaIndividualSellVolume",
        "PerCapitaLegalBuyVolume",
        "PerCapitaLegalSellVolume",
        "IndividualPower",
        "LegalPower",
        "EstimatedIndividualBuyValue",
        "EstimatedIndividualSellValue",
        "EstimatedLegalBuyValue",
        "EstimatedLegalSellValue",
        "EstimatedPerCapitaIndividualBuyValue",
        "EstimatedPerCapitaIndividualSellValue",
        "EstimatedPerCapitaLegalBuyValue",
        "EstimatedPerCapitaLegalSellValue",
        "EstimatedNetIndividualFlow",
        "EstimatedNetLegalFlow",
        "Per_capita_buy_retail",
        "Per_capita_sell_retail",
        "Per_capita_buy_institutional",
        "Per_capita_sell_institutional",
        "Power_retail",
        "Power_institutional",
        "IndividualBuyParticipation",
        "LegalBuyParticipation",
        "IndividualSellParticipation",
        "LegalSellParticipation",
    ]
    client_consistent = live["client_snapshot_consistent"].fillna(False)
    live.loc[~client_consistent, client_actionable_columns] = np.nan

    best_bid = pd.to_numeric(live["BidPrice1"], errors="coerce").replace(0, np.nan)
    best_ask = pd.to_numeric(live["AskPrice1"], errors="coerce").replace(0, np.nan)
    live["Spread"] = best_ask - best_bid
    live["SpreadBps"] = _safe_divide(live["Spread"], (best_ask + best_bid) / 2) * 10000
    live["L1Imbalance"] = _safe_divide(
        live["BidVolume1"] - live["AskVolume1"],
        live["BidVolume1"] + live["AskVolume1"],
    )
    bid_volume_columns = [f"BidVolume{i}" for i in range(1, 6)]
    ask_volume_columns = [f"AskVolume{i}" for i in range(1, 6)]
    bid_l5 = live[bid_volume_columns].sum(axis=1, min_count=1)
    ask_l5 = live[ask_volume_columns].sum(axis=1, min_count=1)
    live["L5BidVolume"] = bid_l5
    live["L5AskVolume"] = ask_l5
    live["L5Imbalance"] = _safe_divide(bid_l5 - ask_l5, bid_l5 + ask_l5)

    # Consolidate blocks before adding the final metadata/provenance columns.
    live = live.copy()
    buy_queue_volume = pd.Series(0.0, index=live.index)
    sell_queue_volume = pd.Series(0.0, index=live.index)
    for level in range(1, 6):
        buy_queue_volume += (
            live[f"BidVolume{level}"]
            .fillna(0)
            .where(live[f"BidPrice{level}"].eq(live["MaxAllowed"]), 0)
        )
        sell_queue_volume += (
            live[f"AskVolume{level}"]
            .fillna(0)
            .where(live[f"AskPrice{level}"].eq(live["MinAllowed"]), 0)
        )
    metadata = snapshot_metadata or {}
    order_book_valid = (
        isinstance(order_book, pd.DataFrame)
        and not order_book.empty
        and set(ORDER_COLUMNS).issubset(order_book.columns)
    )
    queue_is_fresh = bool(
        order_book_valid
        and metadata.get("is_realtime_fresh", False)
        and metadata.get("is_today_trade_date", False)
        and not metadata.get("is_previous_trade_date", False)
        and not metadata.get("is_stale", True)
    )
    if not queue_is_fresh:
        buy_queue_volume[:] = np.nan
        sell_queue_volume[:] = np.nan
    live["EstimatedBuyQueueVolume"] = buy_queue_volume
    live["EstimatedSellQueueVolume"] = sell_queue_volume
    live["EstimatedBuyQueueValue"] = buy_queue_volume * live["MaxAllowed"]
    live["EstimatedSellQueueValue"] = sell_queue_volume * live["MinAllowed"]
    # Additive compatibility aliases. Values remain explicitly marked as
    # five-level estimates through QueueValueSource/QueueIsFresh.
    live["BuyQueueVolume"] = live["EstimatedBuyQueueVolume"]
    live["SellQueueVolume"] = live["EstimatedSellQueueVolume"]
    live["BuyQueueValue"] = live["EstimatedBuyQueueValue"]
    live["SellQueueValue"] = live["EstimatedSellQueueValue"]
    live["QueueValueSource"] = "market_watch_5_level_estimate"
    live["QueueIsFresh"] = queue_is_fresh

    market_price = live["Last"].where(live["Last"].ne(0), live["Close"])
    live["MarketCap"] = market_price * live["SharesOutstanding"]
    live["Turnover"] = _safe_divide(live["Volume"], live["SharesOutstanding"])
    live["VolumeToBaseVolume"] = _safe_divide(live["Volume"], live["BaseVolume"])
    fetched_at = as_of if as_of is not None else pd.Timestamp.now(tz="Asia/Tehran")
    live["as_of"] = fetched_at
    live["trade_date"] = metadata.get("trade_date")
    live["market_state"] = metadata.get("market_state", "")
    live["exchange_time"] = metadata.get("exchange_time")
    live["fetched_at"] = metadata.get("fetched_at", fetched_at)
    live["snapshot_age_seconds"] = metadata.get("snapshot_age_seconds", np.nan)
    live["is_today_trade_date"] = bool(metadata.get("is_today_trade_date", False))
    live["is_history_eligible"] = bool(metadata.get("is_history_eligible", False))
    live["is_realtime_fresh"] = bool(metadata.get("is_realtime_fresh", False))
    live["is_previous_trade_date"] = bool(metadata.get("is_previous_trade_date", False))
    live["is_stale"] = bool(metadata.get("is_stale", False))
    live["is_partial"] = metadata.get("is_partial", pd.NA)
    client_volume_fields_available = (
        live[
            [
                "IndividualBuyVolume",
                "IndividualSellVolume",
                "LegalBuyVolume",
                "LegalSellVolume",
            ]
        ]
        .notna()
        .all(axis=1)
    )
    client_values_available = (
        live["VWAP"].notna() & client_volume_fields_available & client_consistent
    )
    live["client_value_source"] = np.select(
        [
            client_values_available,
            client_volume_fields_available & ~client_consistent,
        ],
        ["estimated_from_market_vwap", "inconsistent"],
        default="unavailable",
    )
    live["client_values_estimated"] = client_values_available.astype(bool)
    live["value_source"] = live["client_value_source"]
    live["is_estimated"] = live["client_values_estimated"]
    live["power_method"] = "volume_per_participant_ratio"
    live.attrs.clear()
    live.attrs.update(source_attrs)
    return live


def _live_market_from_snapshot(snapshot):
    client_type = market_client_type()
    as_of = snapshot.get("fetched_at", pd.Timestamp.now(tz="Asia/Tehran"))
    return _enrich_live_market(
        snapshot["stocks"],
        client_type,
        snapshot["order_book"],
        as_of=as_of,
        snapshot_metadata=snapshot,
    )


def get_live_market(symbol=None, *, strict=False):
    """Return a unified live market DataFrame with client/order-book metrics.

    ``symbol`` may be a Persian ticker or an ``InsCode``.  Omitting it returns
    the entire market; an iterable selects multiple instruments. Unlike the
    legacy-compatible :func:`market_watch`, ``Yesterday``, ``BaseVolume`` and
    ``Change`` are remapped to their canonical corrected meanings here.
    Undefined ratios deliberately remain ``NaN``.
    """
    if not isinstance(strict, bool):
        raise InvalidParameterError("strict must be bool")
    snapshot = market_watch()
    live = _live_market_from_snapshot(snapshot)
    live, missing = _resolve_live_selection(live, symbol, snapshot, strict=strict)
    source_attrs = copy.deepcopy(live.attrs)
    result = live.reset_index(drop=True)
    result.attrs.update(source_attrs)
    result.attrs["migration"] = copy.deepcopy(snapshot.get("migration", {}))
    result.attrs["missing_selectors"] = list(missing)
    return result


def _point_value(record, *keys):
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return np.nan


def _parse_deven(value):
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return None


def _point_exchange_time(trade_date, heven):
    if trade_date is None:
        return None
    text = str(heven or "").strip().split(".", 1)[0].zfill(6)
    if len(text) != 6 or not text.isdigit():
        return None
    try:
        clock = datetime.time(int(text[:2]), int(text[2:4]), int(text[4:]))
    except ValueError:
        return None
    return pd.Timestamp(datetime.datetime.combine(trade_date, clock), tz="Asia/Tehran")


LIVE_SYMBOL_PROVENANCE_COLUMNS = [
    "SnapshotSource",
    "PresentInMarketWatch",
    "MarketStateTitle",
    "market_state_title",
    "MarketTitle",
    "has_trade_today",
    "PriceActionable",
    "FallbackReason",
    "IdentityVerified",
]

LIVE_SYMBOL_STRING_COLUMNS = {
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "Time",
    "SectorCode",
    "MarketCode",
    "QueueValueSource",
    "client_value_source",
    "value_source",
    "power_method",
    "market_state",
    "SnapshotSource",
    "MarketStateTitle",
    "market_state_title",
    "MarketTitle",
    "FallbackReason",
}
LIVE_SYMBOL_BOOLEAN_COLUMNS = {
    "client_snapshot_consistent",
    "client_values_estimated",
    "is_estimated",
    "QueueIsFresh",
    "is_today_trade_date",
    "is_history_eligible",
    "is_realtime_fresh",
    "is_previous_trade_date",
    "is_stale",
    "is_partial",
    "PresentInMarketWatch",
    "has_trade_today",
    "PriceActionable",
    "IdentityVerified",
}
LIVE_SYMBOL_DATETIME_COLUMNS = {"as_of", "exchange_time", "fetched_at"}


def _identity_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return None if text in {"", "0", "0.0", "None", "nan", "<NA>"} else text


def _finalize_live_symbol_provenance(
    live,
    *,
    snapshot_source,
    present_in_market_watch,
    identity_verified,
    fallback_reason=pd.NA,
    market_state_title=pd.NA,
):
    result = live.copy()
    trade_count = pd.to_numeric(result["TradeCount"], errors="coerce")
    volume = pd.to_numeric(result["Volume"], errors="coerce")
    close = pd.to_numeric(result["Close"], errors="coerce")
    last = pd.to_numeric(result["Last"], errors="coerce")
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    has_trade = (
        result["trade_date"].eq(today)
        & trade_count.gt(0)
        & volume.gt(0)
        & close.where(close.gt(0), last).gt(0)
    ).fillna(False)
    identity = pd.Series(bool(identity_verified), index=result.index, dtype="boolean")
    actionable = (
        identity.fillna(False)
        & has_trade
        & result["is_realtime_fresh"].fillna(False).astype(bool)
        & ~result["is_stale"].fillna(True).astype(bool)
    )
    result["SnapshotSource"] = pd.Series(
        snapshot_source, index=result.index, dtype="string"
    )
    result["PresentInMarketWatch"] = pd.Series(
        bool(present_in_market_watch), index=result.index, dtype="boolean"
    )
    title = pd.NA if _identity_value(market_state_title) is None else market_state_title
    for column in ("MarketStateTitle", "market_state_title", "MarketTitle"):
        result[column] = pd.Series(title, index=result.index, dtype="string")
    result["has_trade_today"] = has_trade.astype("boolean")
    result["PriceActionable"] = actionable.astype("boolean")
    reason = pd.NA if _identity_value(fallback_reason) is None else fallback_reason
    result["FallbackReason"] = pd.Series(reason, index=result.index, dtype="string")
    result["IdentityVerified"] = identity
    base_columns = [
        column
        for column in result.columns
        if column not in LIVE_SYMBOL_PROVENANCE_COLUMNS
    ]
    result = result.reindex(columns=base_columns + LIVE_SYMBOL_PROVENANCE_COLUMNS)
    # A single canonical type pass prevents provider sparsity from changing a
    # live-symbol schema.  In particular, fallback NA values must not turn a
    # numeric or boolean column into ``object`` while MarketWatch uses another
    # dtype for the same public column.
    for column in result.columns:
        if column in LIVE_SYMBOL_STRING_COLUMNS:
            result[column] = result[column].astype("string")
        elif column in LIVE_SYMBOL_BOOLEAN_COLUMNS:
            result[column] = result[column].astype("boolean")
        elif column in LIVE_SYMBOL_DATETIME_COLUMNS:
            result[column] = pd.to_datetime(
                result[column], errors="coerce", utc=True
            ).dt.tz_convert("Asia/Tehran")
        elif column != "trade_date":
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(
                "Float64"
            )
    return result


def _point_fallback_row(ref, snapshot, reason):
    response = safe_get(settings.url_closing_price_info.format(ref.ins_code))
    try:
        payload = response.json()
    except (ValueError, AttributeError, TypeError) as exc:
        raise DataParsingError("invalid ClosingPriceInfo response") from exc
    record = payload.get("closingPriceInfo") if isinstance(payload, dict) else None
    if not isinstance(record, dict):
        raise DataParsingError(
            "ClosingPriceInfo response has no closingPriceInfo object"
        )

    instrument = record.get("instrument")
    if not isinstance(instrument, dict):
        instrument = {}
    state = record.get("instrumentState")
    if not isinstance(state, dict):
        state = instrument.get("instrumentState")
    if not isinstance(state, dict) and isinstance(payload, dict):
        state = payload.get("instrumentState")
    if not isinstance(state, dict):
        state = {}
    has_instrument_state = bool(state)

    identity_verified = False
    for source, value in (
        ("closingPriceInfo.insCode", record.get("insCode")),
        ("instrument.insCode", instrument.get("insCode")),
    ):
        reported = _identity_value(value)
        if reported is None:
            continue
        try:
            normalized = validate_ins_code(reported)
        except InvalidParameterError as exc:
            raise DataParsingError(
                f"{source} is not a canonical provider InsCode"
            ) from exc
        if normalized != ref.ins_code:
            raise DataParsingError(
                f"{source}={reported!r} does not match requested InsCode "
                f"{ref.ins_code!r}"
            )
        identity_verified = True
    embedded_symbol = _identity_value(_point_value(instrument, "lVal18AFC", "lVal18"))
    if embedded_symbol is not None:
        if ref.symbol is None or normalize_instrument_text(
            embedded_symbol
        ) != normalize_instrument_text(ref.symbol):
            raise DataParsingError(
                "embedded instrument symbol does not match resolved identity"
            )
        identity_verified = True

    trade_date = _parse_deven(_point_value(record, "dEven", "date"))
    exchange_time = _point_exchange_time(
        trade_date, _point_value(record, "hEven", "time")
    )
    fetched_at = pd.Timestamp.now(tz="Asia/Tehran")
    age = (
        (fetched_at - exchange_time).total_seconds()
        if exchange_time is not None
        else np.nan
    )
    threshold = float(
        getattr(
            settings, "market_snapshot_freshness_seconds", FRESHNESS_THRESHOLD_SECONDS
        )
    )
    skew = abs(float(getattr(settings, "market_clock_skew_tolerance_seconds", 5.0)))
    trade_count = pd.to_numeric(
        pd.Series([_point_value(record, "zTotTran", "tradeCount")]),
        errors="coerce",
    ).iloc[0]
    volume = pd.to_numeric(
        pd.Series([_point_value(record, "qTotTran5J", "volume")]),
        errors="coerce",
    ).iloc[0]
    close = pd.to_numeric(
        pd.Series([_point_value(record, "pClosing", "close")]), errors="coerce"
    ).iloc[0]
    last = pd.to_numeric(
        pd.Series([_point_value(record, "pDrCotVal", "lastPrice")]),
        errors="coerce",
    ).iloc[0]
    has_trade_today = bool(
        trade_date == fetched_at.date()
        and pd.notna(trade_count)
        and pd.notna(volume)
        and trade_count > 0
        and volume > 0
        and max(close if pd.notna(close) else 0, last if pd.notna(last) else 0) > 0
    )
    state_code = _point_value(state, "cEtaval", "stateCode", "code")
    state_title = _point_value(state, "cEtavalTitle", "stateTitle", "title", "lVal30")
    if pd.isna(state_code):
        state_code = snapshot.get("market_state", "")
    if pd.isna(state_title):
        state_title = ""
    state_text = normalize_instrument_text(f"{state_code} {state_title}").lower()
    halted = any(
        token in state_text
        for token in ("متوقف", "ممنوع", "بسته", "halt", "suspend", "closed")
    )
    if has_instrument_state:
        state_code_text = str(state_code).strip().upper()
        halted = halted or state_code_text.startswith(("I", "O"))
    fresh = bool(
        identity_verified
        and has_trade_today
        and exchange_time is not None
        and -skew <= age <= threshold + skew
        and not halted
    )

    first = _point_value(record, "priceFirst", "pFirst", "priceOpen")
    previous = _point_value(record, "priceYesterday", "pYesterday")
    stock_row = {
        "InsCode": ref.ins_code,
        "ISIN": _point_value(instrument, "cIsin", "instrumentID"),
        "Symbol": ref.symbol or _point_value(instrument, "lVal18AFC", "lVal18"),
        "Name": ref.name or _point_value(instrument, "lVal30", "name"),
        "Time": _heven_to_time_str(_point_value(record, "hEven", "time")),
        "FirstPrice": first,
        "Open": first,
        "Yesterday": first,
        "LegacyYesterday": first,
        "PreviousClose": previous,
        "PriceYesterday": previous,
        "Close": close,
        "Last": last,
        "TradeCount": trade_count,
        "Volume": volume,
        "Value": _point_value(record, "qTotCap", "value"),
        "Low": _point_value(record, "priceMin", "low"),
        "High": _point_value(record, "priceMax", "high"),
        "EPS": _point_value(instrument, "eps"),
        "ActualBaseVolume": _point_value(instrument, "baseVol"),
        "BaseVolume": _point_value(instrument, "zTitad"),
        "LegacyBaseVolume": _point_value(instrument, "zTitad"),
        "VisitCount": np.nan,
        "Flow": _point_value(instrument, "flow"),
        "SectorCode": _point_value(instrument, "cSecVal"),
        "MaxAllowed": _point_value(record, "priceMaxAllowed", "maxAllowed"),
        "MinAllowed": _point_value(record, "priceMinAllowed", "minAllowed"),
        "SharesOutstanding": _point_value(instrument, "zTitad"),
        "InstrumentType": _point_value(instrument, "yVal"),
        "NAV": np.nan,
        "MarketCode": _point_value(instrument, "cgrValCot"),
    }
    stocks = pd.DataFrame([stock_row]).reindex(columns=STOCK_COLUMNS)
    stocks["Change"] = pd.to_numeric(stocks["Close"], errors="coerce") - pd.to_numeric(
        stocks["Yesterday"], errors="coerce"
    )
    stocks["ChangePct"] = _safe_divide(stocks["Change"], stocks["Yesterday"]) * 100
    stocks["PreviousCloseChange"] = pd.to_numeric(
        stocks["Close"], errors="coerce"
    ) - pd.to_numeric(stocks["PreviousClose"], errors="coerce")
    stocks["PreviousCloseChangePct"] = (
        _safe_divide(stocks["PreviousCloseChange"], stocks["PreviousClose"]) * 100
    )
    metadata = {
        "trade_date": trade_date,
        "market_state": str(state_code),
        "exchange_time": exchange_time,
        "fetched_at": fetched_at,
        "snapshot_age_seconds": age,
        "is_today_trade_date": trade_date == fetched_at.date(),
        "is_history_eligible": bool(identity_verified and has_trade_today),
        "is_realtime_fresh": fresh,
        "is_previous_trade_date": trade_date is not None
        and trade_date != fetched_at.date(),
        "is_stale": not fresh,
        "is_partial": pd.NA,
    }
    live = _enrich_live_market(
        stocks,
        pd.DataFrame(columns=CLIENT_COLUMNS),
        _empty_order_book(),
        as_of=fetched_at,
        snapshot_metadata=metadata,
    )
    result = _finalize_live_symbol_provenance(
        live.reset_index(drop=True),
        snapshot_source="closing_price_info_fallback",
        present_in_market_watch=False,
        identity_verified=identity_verified,
        fallback_reason=reason,
        market_state_title=state_title,
    )
    result.attrs["migration"] = copy.deepcopy(snapshot.get("migration", {}))
    result.attrs["missing_selectors"] = []
    return result


def get_live_symbol(symbol=None, *, ins_code=None, fallback="none"):
    """Return one exact live instrument row with canonical provenance.

    The default ``fallback='none'`` reads MarketWatch only and preserves the
    historical missing-symbol behavior. ``fallback='point'`` resolves a
    canonical identity and calls official ``ClosingPriceInfo`` only when the
    instrument is absent from that authoritative snapshot. A point row records
    its source, absence reason, identity verification, freshness, and
    actionability; absent/wrong identity, no trade, stale data, and halted state
    can never be price-actionable. Client and order-book fields remain NA.

    Raises ``InvalidParameterError`` for invalid/conflicting selectors,
    ``StockNotFoundError`` when neither path resolves the instrument,
    ``AmbiguousSymbolError`` for duplicate exact live identities, and
    ``DataParsingError`` for unsafe point-response identity.
    """
    fallback = str(fallback).strip().lower()
    if fallback not in {"none", "point"}:
        raise InvalidParameterError("fallback must be 'none' or 'point'")
    if symbol is None and ins_code is None:
        raise InvalidParameterError("symbol or ins_code is required")
    snapshot = market_watch()
    selector = ins_code if symbol is None else symbol
    identity_rows, _ = _resolve_live_selection(
        snapshot["stocks"], selector, snapshot, strict=False
    )
    if identity_rows.empty:
        if fallback == "none":
            raise StockNotFoundError(f"No live instrument matched {selector!r}")
        ref = resolve_instrument(symbol, ins_code=ins_code, snapshot=None)
        return _point_fallback_row(ref, snapshot, "absent_from_market_watch")

    live_all = _live_market_from_snapshot(snapshot)
    live, missing = _resolve_live_selection(live_all, selector, snapshot, strict=False)
    if live.empty:
        if fallback == "none":
            raise StockNotFoundError(f"No live instrument matched {selector!r}")
        ref = resolve_instrument(symbol, ins_code=ins_code, snapshot=None)
        return _point_fallback_row(ref, snapshot, "absent_from_market_watch")
    if len(live) != 1:
        matches = live.loc[:, ["InsCode", "Symbol", "Name"]].to_dict("records")
        raise AmbiguousSymbolError(
            f"Live selector {selector!r} matched {len(live)} instruments: {matches}"
        )
    if ins_code is not None and str(live.iloc[0]["InsCode"]) != str(ins_code):
        raise InvalidParameterError(
            "symbol and ins_code refer to different instruments"
        )
    result = _finalize_live_symbol_provenance(
        live.reset_index(drop=True),
        snapshot_source="market_watch",
        present_in_market_watch=True,
        identity_verified=True,
    )
    result.attrs["migration"] = copy.deepcopy(snapshot.get("migration", {}))
    result.attrs["missing_selectors"] = list(missing)
    return result
