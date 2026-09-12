"""Explainable manager analytics built on AlgoTik TSE market data.

The functions in this module keep data acquisition and calculation separate.
Every analytical API accepts explicit DataFrames for reproducible research and
can fetch the same inputs from existing package APIs when they are omitted.
Missing observations remain missing and are described by quality flags; they
are never replaced with zero.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
from persiantools.jdatetime import JalaliDate

from .._clock import tehran_now
from ..exceptions import DataParsingError, InvalidParameterError
from .conventions import coerce_financial_date
from .market_data import get_live_market
from .market_reference import get_market_activity
from .stock import stock, stock_RI

COMPARISON_COLUMNS = [
    "Symbol",
    "Benchmark",
    "StartDate",
    "EndDate",
    "JalaliStartDate",
    "JalaliEndDate",
    "Observations",
    "ReturnObservations",
    "CoveragePct",
    "TotalReturnPct",
    "AnnualizedReturnPct",
    "AnnualizedVolatilityPct",
    "MaxDrawdownPct",
    "BestDayPct",
    "WorstDayPct",
    "PositiveDayPct",
    "Beta",
    "Correlation",
    "AlphaAnnualizedPct",
    "TrackingErrorPct",
    "InformationRatio",
    "AverageDailyValue",
    "MedianDailyValue",
    "AverageDailyVolume",
    "AverageTradeValue",
    "NetIndividualFlow",
    "AverageIndividualPower",
    "ClientCoveragePct",
    "ValueUnit",
    "QualityFlags",
    "Source",
]

LIQUIDITY_COLUMNS = [
    "Symbol",
    "StartDate",
    "EndDate",
    "JalaliStartDate",
    "JalaliEndDate",
    "Window",
    "Observations",
    "TradingDays",
    "ZeroTradeRatio",
    "ZeroReturnRatio",
    "AverageDailyValue",
    "MedianDailyValue",
    "AverageDailyVolume",
    "AverageTradeValue",
    "Amihud1B",
    "AnnualizedVolatilityPct",
    "SharesOutstanding",
    "HistoricalTurnover",
    "CurrentTurnover",
    "SpreadBps",
    "L1Imbalance",
    "L5Imbalance",
    "L5DepthValue",
    "MarketCap",
    "VolumeToBaseVolume",
    "HistoryCoveragePct",
    "LiveCoveragePct",
    "ValueUnit",
    "AmihudUnit",
    "SharesOutstandingSource",
    "QualityFlags",
    "Source",
]

REGIME_COLUMNS = [
    "AsOf",
    "TradeDate",
    "JalaliDate",
    "Benchmark",
    "Regime",
    "Score",
    "Confidence",
    "TrendScore",
    "BreadthScore",
    "FlowScore",
    "LiquidityScore",
    "QueueScore",
    "TrendWeight",
    "BreadthWeight",
    "FlowWeight",
    "LiquidityWeight",
    "QueueWeight",
    "BenchmarkReturnPct",
    "AnnualizedVolatilityPct",
    "AdvancePct",
    "DeclinePct",
    "EstimatedNetIndividualFlow",
    "CurrentMarketValue",
    "HistoricalMedianValue",
    "EstimatedBuyQueueValue",
    "EstimatedSellQueueValue",
    "AvailableComponents",
    "MissingComponents",
    "QualityFlags",
    "Source",
]

MARKET_MAP_COLUMNS = [
    "GroupKey",
    "Label",
    "Parent",
    "GroupBy",
    "InstrumentCount",
    "SizeMetric",
    "SizeValue",
    "ColorMetric",
    "ColorValue",
    "UniverseWeightPct",
    "DisplayedWeightPct",
    "ReturnPct",
    "Value",
    "Volume",
    "MarketCap",
    "EstimatedNetIndividualFlow",
    "IndividualPower",
    "ColorCoveragePct",
    "AsOf",
    "IsRealtimeFresh",
    "ValueUnit",
    "QualityFlags",
    "Source",
]

_SIZE_COLUMNS = {
    "value": "Value",
    "volume": "Volume",
    "market_cap": "MarketCap",
    "queue_value": "QueueValue",
}
_COLOR_COLUMNS = {
    "return": ("ChangePct", "weighted"),
    "net_individual_flow": ("EstimatedNetIndividualFlow", "sum"),
    "individual_power": ("IndividualPower", "weighted"),
    "order_imbalance": ("L5Imbalance", "weighted"),
}
_GROUP_COLUMNS = {
    "symbol": "InsCode",
    "sector": "SectorCode",
    "flow": "Flow",
    "instrument_type": "InstrumentType",
}
_DEFAULT_REGIME_WEIGHTS = {
    "trend": 0.30,
    "breadth": 0.25,
    "flow": 0.20,
    "liquidity": 0.15,
    "queue": 0.10,
}
_EQUITY_TYPES = frozenset({300, 303, 309})
_HISTORY_BASE_COLUMNS = [
    "GregorianDate",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "Value",
    "No.",
    "Symbol",
]
_CLIENT_BASE_COLUMNS = [
    "GregorianDate",
    "Val_buy_retail",
    "Val_sell_retail",
    "Per_capita_buy_retail",
    "Per_capita_sell_retail",
    "Power_retail",
    "Symbol",
]


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return number if math.isfinite(number) else float("nan")


def _safe_divide(numerator, denominator):
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    return numerator / denominator


def _series(frame, column, default=np.nan):
    if isinstance(frame, pd.DataFrame) and column in frame:
        return frame[column]
    index = frame.index if isinstance(frame, pd.DataFrame) else pd.RangeIndex(0)
    return pd.Series(default, index=index, dtype="object")


def _date(value, name):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _date_bounds(start, end):
    first, last = _date(start, "start"), _date(end, "end")
    if first is not None and last is not None and first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    return first, last


def _positive_int(value, name, maximum=None):
    if isinstance(value, bool):
        raise InvalidParameterError("{} must be a positive integer".format(name))
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(
            "{} must be a positive integer".format(name)
        ) from exc
    if parsed <= 0 or parsed != value:
        raise InvalidParameterError("{} must be a positive integer".format(name))
    if maximum is not None and parsed > maximum:
        raise InvalidParameterError("{} must be at most {}".format(name, maximum))
    return parsed


def _symbols(value, *, allow_none=False):
    if value is None and allow_none:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError as exc:
            raise InvalidParameterError("symbols must be a symbol or iterable") from exc
    result = []
    for raw in values:
        symbol = str(raw).strip()
        if not symbol:
            raise InvalidParameterError("symbols cannot contain empty values")
        if symbol not in result:
            result.append(symbol)
    if not result and not allow_none:
        raise InvalidParameterError("symbols cannot be empty")
    return result


def _history_mapping(value, name):
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidParameterError("{} must be a mapping of DataFrames".format(name))
    result = {}
    for key, frame in value.items():
        if not isinstance(frame, pd.DataFrame):
            raise InvalidParameterError("{} values must be DataFrames".format(name))
        result[str(key).strip()] = frame.copy(deep=True)
    return result


def _fetch_price_history(symbol, start, end):
    return stock(
        symbol=symbol,
        start=start.isoformat() if start is not None else None,
        end=end.isoformat() if end is not None else None,
        auto_adjust=True,
        output_type="full",
        date_format="gregorian",
        progress=False,
        ascending=True,
    )


def _fetch_client_history(symbol, start, end):
    return stock_RI(
        symbol=symbol,
        start=start.isoformat() if start is not None else None,
        end=end.isoformat() if end is not None else None,
        output_type="full",
        date_format="gregorian",
        progress=False,
        ascending=True,
    )


def _extract_dates(frame):
    for column in ("GregorianDate", "Date", "date"):
        if column in frame:
            values = pd.to_datetime(frame[column], errors="coerce")
            if values.notna().any():
                return values
    values = pd.to_datetime(frame.index, errors="coerce")
    return pd.Series(values, index=frame.index)


def _normalise_history(frame, symbol, start=None, end=None):
    if frame is None or not isinstance(frame, pd.DataFrame):
        return pd.DataFrame(columns=_HISTORY_BASE_COLUMNS)
    if isinstance(frame.columns, pd.MultiIndex):
        raise DataParsingError(
            "history_data for each symbol must have single-level columns"
        )
    if "Close" not in frame:
        raise DataParsingError("price history must contain Close")
    result = frame.copy(deep=True)
    result["GregorianDate"] = pd.to_datetime(_extract_dates(result), errors="coerce")
    result = result.loc[result["GregorianDate"].notna()].copy()
    for column in ("Open", "High", "Low", "Close", "Volume", "Value", "No."):
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["Symbol"] = symbol
    result = result.drop_duplicates("GregorianDate", keep="last")
    result = result.sort_values("GregorianDate", kind="mergesort")
    if start is not None:
        result = result.loc[result["GregorianDate"].dt.date >= start]
    if end is not None:
        result = result.loc[result["GregorianDate"].dt.date <= end]
    return result.reset_index(drop=True)


def _normalise_client(frame, symbol, start=None, end=None):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=_CLIENT_BASE_COLUMNS)
    if isinstance(frame.columns, pd.MultiIndex):
        raise DataParsingError(
            "client_data for each symbol must have single-level columns"
        )
    result = frame.copy(deep=True)
    result["GregorianDate"] = pd.to_datetime(_extract_dates(result), errors="coerce")
    result = result.loc[result["GregorianDate"].notna()].copy()
    for column in (
        "Val_buy_retail",
        "Val_sell_retail",
        "Per_capita_buy_retail",
        "Per_capita_sell_retail",
        "Power_retail",
    ):
        if column not in result:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["Symbol"] = symbol
    result = result.drop_duplicates("GregorianDate", keep="last")
    result = result.sort_values("GregorianDate", kind="mergesort")
    if start is not None:
        result = result.loc[result["GregorianDate"].dt.date >= start]
    if end is not None:
        result = result.loc[result["GregorianDate"].dt.date <= end]
    return result.reset_index(drop=True)


def _get_histories(symbols, start, end, supplied, progress):
    output, missing = {}, []
    for position, symbol in enumerate(symbols, start=1):
        if progress:
            print("[{}/{}] {}".format(position, len(symbols), symbol))
        raw = (
            supplied.get(symbol)
            if supplied is not None
            else _fetch_price_history(symbol, start, end)
        )
        frame = _normalise_history(raw, symbol, start, end)
        if frame.empty:
            missing.append(symbol)
        output[symbol] = frame
    return output, missing


def _get_clients(symbols, start, end, supplied):
    output = {}
    for symbol in symbols:
        raw = (
            supplied.get(symbol)
            if supplied is not None
            else _fetch_client_history(symbol, start, end)
        )
        output[symbol] = _normalise_client(raw, symbol, start, end)
    return output


def _jalali(value):
    if value is None or pd.isna(value):
        return pd.NA
    return JalaliDate.to_jalali(pd.Timestamp(value).date()).isoformat()


def _annualized_return(first, last, observations, annualization):
    if observations <= 0 or first <= 0 or last <= 0:
        return float("nan")
    return ((last / first) ** (annualization / observations) - 1.0) * 100.0


def _drawdown(prices):
    values = pd.to_numeric(prices, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    peaks = values.cummax().replace(0, np.nan)
    return ((values / peaks) - 1.0).min() * 100.0


def _quality(*flags):
    values = []
    for flag in flags:
        if flag and flag not in values:
            values.append(flag)
    return ";".join(values) if values else "ok"


def _comparison_row(
    symbol,
    history,
    aligned_prices,
    benchmark,
    benchmark_returns,
    client,
    annualization,
    min_observations,
):
    prices = aligned_prices[symbol].dropna()
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    returns = returns.dropna()
    enough = len(returns) >= min_observations
    total_return = (
        (prices.iloc[-1] / prices.iloc[0] - 1.0) * 100.0
        if len(prices) >= 2 and prices.iloc[0] > 0
        else float("nan")
    )
    annual_return = (
        _annualized_return(prices.iloc[0], prices.iloc[-1], len(returns), annualization)
        if enough
        else float("nan")
    )
    volatility = (
        returns.std(ddof=1) * math.sqrt(annualization) * 100.0
        if enough
        else float("nan")
    )
    beta = correlation = alpha = tracking_error = information_ratio = float("nan")
    if benchmark is not None and symbol != benchmark:
        pair = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
        pair.columns = ["asset", "benchmark"]
        if len(pair) >= min_observations and pair["benchmark"].var(ddof=1) > 0:
            beta = pair["asset"].cov(pair["benchmark"]) / pair["benchmark"].var(ddof=1)
            correlation = pair["asset"].corr(pair["benchmark"])
            active = pair["asset"] - pair["benchmark"]
            tracking_error = active.std(ddof=1) * math.sqrt(annualization) * 100.0
            annual_asset = pair["asset"].mean() * annualization
            annual_benchmark = pair["benchmark"].mean() * annualization
            alpha = (annual_asset - beta * annual_benchmark) * 100.0
            information_ratio = (
                active.mean() / active.std(ddof=1) * math.sqrt(annualization)
                if active.std(ddof=1) > 0
                else float("nan")
            )
    history_dates = history["GregorianDate"] if not history.empty else pd.Series()
    values = pd.to_numeric(_series(history, "Value"), errors="coerce")
    volumes = pd.to_numeric(_series(history, "Volume"), errors="coerce")
    trades = pd.to_numeric(_series(history, "No."), errors="coerce")
    average_trade_value = (
        values.sum(min_count=1) / trades.sum(min_count=1)
        if trades.notna().any() and trades.sum(min_count=1) > 0
        else float("nan")
    )
    net_flow = power = client_coverage = float("nan")
    if client is not None and not client.empty:
        buy = pd.to_numeric(client["Val_buy_retail"], errors="coerce")
        sell = pd.to_numeric(client["Val_sell_retail"], errors="coerce")
        valid = buy.notna() & sell.notna()
        net_flow = (buy - sell).where(valid).sum(min_count=1)
        power_values = pd.to_numeric(client["Power_retail"], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        power = power_values.mean()
        client_coverage = valid.mean() * 100.0 if len(valid) else float("nan")
    coverage = len(prices) / max(len(history), 1) * 100.0 if len(history) else 0.0
    flags = _quality(
        "history_unavailable" if history.empty else None,
        "insufficient_observations" if not enough else None,
        (
            "benchmark_unavailable"
            if benchmark is not None and symbol != benchmark and math.isnan(beta)
            else None
        ),
        "value_unavailable" if not values.notna().any() else None,
        "client_data_unavailable" if client is None or client.empty else None,
    )
    return {
        "Symbol": symbol,
        "Benchmark": benchmark if benchmark is not None else pd.NA,
        "StartDate": history_dates.min().date() if len(history_dates) else pd.NaT,
        "EndDate": history_dates.max().date() if len(history_dates) else pd.NaT,
        "JalaliStartDate": (
            _jalali(history_dates.min()) if len(history_dates) else pd.NA
        ),
        "JalaliEndDate": _jalali(history_dates.max()) if len(history_dates) else pd.NA,
        "Observations": len(prices),
        "ReturnObservations": len(returns),
        "CoveragePct": coverage,
        "TotalReturnPct": total_return,
        "AnnualizedReturnPct": annual_return,
        "AnnualizedVolatilityPct": volatility,
        "MaxDrawdownPct": _drawdown(prices) if enough else float("nan"),
        "BestDayPct": returns.max() * 100.0 if enough else float("nan"),
        "WorstDayPct": returns.min() * 100.0 if enough else float("nan"),
        "PositiveDayPct": (returns > 0).mean() * 100.0 if enough else float("nan"),
        "Beta": beta,
        "Correlation": correlation,
        "AlphaAnnualizedPct": alpha,
        "TrackingErrorPct": tracking_error,
        "InformationRatio": information_ratio,
        "AverageDailyValue": values.mean(),
        "MedianDailyValue": values.median(),
        "AverageDailyVolume": volumes.mean(),
        "AverageTradeValue": average_trade_value,
        "NetIndividualFlow": net_flow,
        "AverageIndividualPower": power,
        "ClientCoveragePct": client_coverage,
        "ValueUnit": "rial",
        "QualityFlags": flags,
        "Source": "derived_from_tsetmc_symbol_history",
    }


def _cast(frame, columns):
    result = frame.reindex(columns=columns).copy()
    integer_columns = {
        "Observations",
        "ReturnObservations",
        "TradingDays",
        "Window",
        "InstrumentCount",
        "AvailableComponents",
        "MissingComponents",
    }
    boolean_columns = {"IsRealtimeFresh"}
    datetime_columns = {"AsOf"}
    date_columns = {"StartDate", "EndDate", "TradeDate"}
    text_columns = set(columns) - integer_columns - boolean_columns - datetime_columns
    text_columns -= date_columns
    numeric_candidates = {
        name
        for name in columns
        if name.endswith(("Pct", "Ratio", "Score", "Weight", "Value", "Volume"))
        or name
        in {
            "Beta",
            "Correlation",
            "InformationRatio",
            "Confidence",
            "NetIndividualFlow",
            "EstimatedNetIndividualFlow",
            "AverageIndividualPower",
            "IndividualPower",
            "Amihud1B",
            "SharesOutstanding",
            "HistoricalTurnover",
            "CurrentTurnover",
            "SpreadBps",
            "L1Imbalance",
            "L5Imbalance",
            "L5DepthValue",
            "MarketCap",
            "VolumeToBaseVolume",
        }
    }
    text_columns -= numeric_candidates
    for column in integer_columns.intersection(result.columns):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    for column in numeric_candidates.intersection(result.columns):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "Float64"
        )
    for column in boolean_columns.intersection(result.columns):
        result[column] = result[column].astype("boolean")
    for column in datetime_columns.intersection(result.columns):
        result[column] = pd.to_datetime(
            result[column], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Tehran")
    for column in text_columns.intersection(result.columns):
        result[column] = result[column].astype("string")
    return result


def compare_symbols(
    symbols,
    start=None,
    end=None,
    benchmark=None,
    align="inner",
    annualization=240,
    min_observations=20,
    include_client_type=True,
    progress=True,
    history_data=None,
    client_data=None,
    strict=False,
):
    """Compare return, risk, liquidity and client-flow metrics for symbols."""
    requested = _symbols(symbols)
    if benchmark is not None:
        benchmark = str(benchmark).strip()
        if not benchmark:
            raise InvalidParameterError("benchmark cannot be empty")
    alignment = str(align).strip().lower()
    if alignment not in {"inner", "outer"}:
        raise InvalidParameterError("align must be inner or outer")
    annualization = _positive_int(annualization, "annualization", 366)
    min_observations = _positive_int(min_observations, "min_observations", 10000)
    for name, value in (
        ("include_client_type", include_client_type),
        ("progress", progress),
        ("strict", strict),
    ):
        if not isinstance(value, bool):
            raise InvalidParameterError("{} must be bool".format(name))
    first, last = _date_bounds(start, end)
    supplied_history = _history_mapping(history_data, "history_data")
    supplied_client = _history_mapping(client_data, "client_data")
    fetch_symbols = requested + (
        [benchmark] if benchmark is not None and benchmark not in requested else []
    )
    histories, missing = _get_histories(
        fetch_symbols, first, last, supplied_history, progress
    )
    if strict and missing:
        raise DataParsingError(
            "price history unavailable for: {}".format(", ".join(missing))
        )
    clients = (
        _get_clients(requested, first, last, supplied_client)
        if include_client_type
        else {symbol: pd.DataFrame() for symbol in requested}
    )
    series = {
        symbol: frame.set_index("GregorianDate")["Close"].rename(symbol)
        for symbol, frame in histories.items()
        if not frame.empty
    }
    matrix = (
        pd.concat(series.values(), axis=1, join="outer") if series else pd.DataFrame()
    )
    matrix = matrix.sort_index()
    if alignment == "inner" and not matrix.empty:
        matrix = matrix.dropna(how="any")
    benchmark_returns = pd.Series(dtype=float)
    if benchmark is not None and benchmark in matrix:
        benchmark_returns = matrix[benchmark].pct_change(fill_method=None).dropna()
    rows = []
    for symbol in requested:
        aligned = (
            matrix
            if symbol in matrix
            else pd.DataFrame({symbol: pd.Series(dtype=float)})
        )
        rows.append(
            _comparison_row(
                symbol,
                histories.get(symbol, pd.DataFrame()),
                aligned,
                benchmark,
                benchmark_returns,
                clients.get(symbol),
                annualization,
                min_observations,
            )
        )
    result = _cast(pd.DataFrame(rows), COMPARISON_COLUMNS)
    result.attrs.update(
        {
            "source": "derived_from_tsetmc_symbol_history",
            "fetched_at": tehran_now().isoformat(),
            "requested_symbols": tuple(requested),
            "benchmark": benchmark,
            "alignment": alignment,
            "annualization": annualization,
            "min_observations": min_observations,
            "missing_symbols": tuple(missing),
            "common_observations": len(matrix),
            "value_unit": "rial",
            "is_partial": bool(missing),
        }
    )
    return result


def _live_selection(live, symbols):
    if live is None or not isinstance(live, pd.DataFrame):
        return pd.DataFrame()
    result = live.copy(deep=True)
    if symbols:
        symbol_values = result.get("Symbol", pd.Series(index=result.index, dtype=str))
        inscodes = result.get("InsCode", pd.Series(index=result.index, dtype=str))
        mask = symbol_values.astype(str).isin(symbols) | inscodes.astype(str).isin(
            symbols
        )
        result = result.loc[mask]
    return result.reset_index(drop=True)


def _live_row(live, symbol):
    if live.empty:
        return None
    mask = pd.Series(False, index=live.index)
    for column in ("Symbol", "InsCode"):
        if column in live:
            mask |= live[column].astype(str).eq(str(symbol))
    rows = live.loc[mask]
    return None if rows.empty else rows.iloc[0]


def _live_lookup(live):
    """Index one live snapshot once instead of scanning it per symbol."""
    lookup = {}
    if live.empty:
        return lookup
    for _, row in live.iterrows():
        for column in ("Symbol", "InsCode"):
            value = row.get(column)
            if pd.notna(value):
                key = str(value).strip()
                if key and key not in lookup:
                    lookup[key] = row
    return lookup


def _liquidity_row(symbol, history, live_row, window, annualization):
    sample = history.tail(window).copy() if window is not None else history.copy()
    values = pd.to_numeric(_series(sample, "Value"), errors="coerce")
    volumes = pd.to_numeric(_series(sample, "Volume"), errors="coerce")
    trades = pd.to_numeric(_series(sample, "No."), errors="coerce")
    prices = pd.to_numeric(_series(sample, "Close"), errors="coerce")
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    traded = volumes.gt(0) & values.gt(0)
    amihud_values = (returns.abs() / (values / 1_000_000_000)).where(traded)
    live_values = {}
    if live_row is not None:
        for column in (
            "SharesOutstanding",
            "Turnover",
            "SpreadBps",
            "L1Imbalance",
            "L5Imbalance",
            "MarketCap",
            "VolumeToBaseVolume",
        ):
            live_values[column] = _number(live_row.get(column))
        depth = 0.0
        depth_available = False
        for level in range(1, 6):
            bid_price = _number(live_row.get("BidPrice{}".format(level)))
            bid_volume = _number(live_row.get("BidVolume{}".format(level)))
            ask_price = _number(live_row.get("AskPrice{}".format(level)))
            ask_volume = _number(live_row.get("AskVolume{}".format(level)))
            for price, volume in ((bid_price, bid_volume), (ask_price, ask_volume)):
                if not math.isnan(price) and not math.isnan(volume):
                    depth += price * volume
                    depth_available = True
        live_values["L5DepthValue"] = depth if depth_available else float("nan")
    shares = live_values.get("SharesOutstanding", float("nan"))
    historical_turnover = (
        volumes.mean() / shares
        if not math.isnan(shares) and shares > 0 and volumes.notna().any()
        else float("nan")
    )
    average_trade_value = (
        values.sum(min_count=1) / trades.sum(min_count=1)
        if trades.notna().any() and trades.sum(min_count=1) > 0
        else float("nan")
    )
    history_coverage = (
        pd.concat([prices, volumes, values, trades], axis=1).notna().mean().mean()
        * 100.0
        if len(sample)
        else 0.0
    )
    live_metric_names = (
        "Turnover",
        "SpreadBps",
        "L1Imbalance",
        "L5Imbalance",
        "L5DepthValue",
        "MarketCap",
        "VolumeToBaseVolume",
    )
    live_available = sum(
        not math.isnan(live_values.get(name, float("nan")))
        for name in live_metric_names
    )
    dates = sample["GregorianDate"] if not sample.empty else pd.Series()
    flags = _quality(
        "history_unavailable" if sample.empty else None,
        "value_unavailable" if not values.notna().any() else None,
        "trade_count_unavailable" if not trades.notna().any() else None,
        "live_snapshot_unavailable" if live_row is None else None,
        (
            "spread_unavailable"
            if math.isnan(live_values.get("SpreadBps", float("nan")))
            else None
        ),
        (
            "current_shares_for_historical_turnover"
            if not math.isnan(historical_turnover)
            else None
        ),
    )
    return {
        "Symbol": symbol,
        "StartDate": dates.min().date() if len(dates) else pd.NaT,
        "EndDate": dates.max().date() if len(dates) else pd.NaT,
        "JalaliStartDate": _jalali(dates.min()) if len(dates) else pd.NA,
        "JalaliEndDate": _jalali(dates.max()) if len(dates) else pd.NA,
        "Window": window if window is not None else len(sample),
        "Observations": len(sample),
        "TradingDays": int(traded.sum()) if len(traded) else 0,
        "ZeroTradeRatio": 1.0 - traded.mean() if len(traded) else float("nan"),
        "ZeroReturnRatio": (
            returns.dropna().eq(0).mean() if returns.notna().any() else float("nan")
        ),
        "AverageDailyValue": values.mean(),
        "MedianDailyValue": values.median(),
        "AverageDailyVolume": volumes.mean(),
        "AverageTradeValue": average_trade_value,
        "Amihud1B": amihud_values.mean(),
        "AnnualizedVolatilityPct": returns.std(ddof=1)
        * math.sqrt(annualization)
        * 100.0,
        "SharesOutstanding": shares,
        "HistoricalTurnover": historical_turnover,
        "CurrentTurnover": live_values.get("Turnover", float("nan")),
        "SpreadBps": live_values.get("SpreadBps", float("nan")),
        "L1Imbalance": live_values.get("L1Imbalance", float("nan")),
        "L5Imbalance": live_values.get("L5Imbalance", float("nan")),
        "L5DepthValue": live_values.get("L5DepthValue", float("nan")),
        "MarketCap": live_values.get("MarketCap", float("nan")),
        "VolumeToBaseVolume": live_values.get("VolumeToBaseVolume", float("nan")),
        "HistoryCoveragePct": history_coverage,
        "LiveCoveragePct": live_available / len(live_metric_names) * 100.0,
        "ValueUnit": "rial",
        "AmihudUnit": "absolute_return_per_billion_rial",
        "SharesOutstandingSource": (
            "current_live_snapshot" if not math.isnan(shares) else "unavailable"
        ),
        "QualityFlags": flags,
        "Source": "derived_from_tsetmc_history_and_live_snapshot",
    }


def get_liquidity_metrics(
    symbols=None,
    start=None,
    end=None,
    window=20,
    annualization=240,
    include_live=True,
    progress=True,
    history_data=None,
    live_data=None,
    strict=False,
):
    """Calculate historical and live liquidity metrics for selected symbols."""
    requested = _symbols(symbols, allow_none=True)
    window = _positive_int(window, "window", 10000) if window is not None else None
    annualization = _positive_int(annualization, "annualization", 366)
    for name, value in (
        ("include_live", include_live),
        ("progress", progress),
        ("strict", strict),
    ):
        if not isinstance(value, bool):
            raise InvalidParameterError("{} must be bool".format(name))
    first, last = _date_bounds(start, end)
    supplied = _history_mapping(history_data, "history_data")
    if supplied is not None and not requested:
        requested = list(supplied)
    if not requested and symbols is not None:
        raise InvalidParameterError("symbols cannot be empty")
    histories, missing = (
        _get_histories(requested, first, last, supplied, progress)
        if requested
        else ({}, [])
    )
    if include_live:
        live = (
            live_data.copy(deep=True)
            if isinstance(live_data, pd.DataFrame)
            else get_live_market(requested or None)
        )
        live = _live_selection(live, requested)
    else:
        if live_data is not None:
            raise InvalidParameterError("live_data requires include_live=True")
        live = pd.DataFrame()
    if not requested and not live.empty:
        requested = [
            str(value)
            for value in live.get("Symbol", pd.Series(dtype=str)).dropna().unique()
            if str(value).strip()
        ]
    if strict and missing:
        raise DataParsingError(
            "price history unavailable for: {}".format(", ".join(missing))
        )
    live_by_symbol = _live_lookup(live)
    rows = [
        _liquidity_row(
            symbol,
            histories.get(symbol, pd.DataFrame()),
            live_by_symbol.get(str(symbol)),
            window,
            annualization,
        )
        for symbol in requested
    ]
    result = _cast(pd.DataFrame(rows), LIQUIDITY_COLUMNS)
    result.attrs.update(
        {
            "source": "derived_from_tsetmc_history_and_live_snapshot",
            "fetched_at": tehran_now().isoformat(),
            "window": window,
            "annualization": annualization,
            "requested_symbols": tuple(requested),
            "missing_symbols": tuple(missing),
            "value_unit": "rial",
            "amihud_unit": "absolute_return_per_billion_rial",
            "is_partial": bool(missing) or (include_live and live.empty),
        }
    )
    return result


def _regime_weights(weights):
    if weights is None:
        return dict(_DEFAULT_REGIME_WEIGHTS)
    if not isinstance(weights, Mapping):
        raise InvalidParameterError("weights must be a mapping")
    unknown = set(weights) - set(_DEFAULT_REGIME_WEIGHTS)
    if unknown:
        raise InvalidParameterError(
            "unknown regime weights: {}".format(", ".join(sorted(unknown)))
        )
    result = dict(_DEFAULT_REGIME_WEIGHTS)
    for key, value in weights.items():
        number = _number(value)
        if math.isnan(number) or number < 0:
            raise InvalidParameterError(
                "regime weights must be finite and non-negative"
            )
        result[key] = number
    if sum(result.values()) <= 0:
        raise InvalidParameterError("at least one regime weight must be positive")
    total = sum(result.values())
    return {key: value / total for key, value in result.items()}


def _trend_component(history, lookback, annualization):
    prices = (
        pd.to_numeric(_series(history, "Close"), errors="coerce")
        .dropna()
        .tail(lookback)
    )
    if len(prices) < 3 or prices.iloc[0] <= 0:
        return float("nan"), float("nan"), float("nan")
    returns = prices.pct_change(fill_method=None).dropna()
    cumulative = (prices.iloc[-1] / prices.iloc[0] - 1.0) * 100.0
    annual_vol = returns.std(ddof=1) * math.sqrt(annualization) * 100.0
    horizon_vol = returns.std(ddof=1) * math.sqrt(len(returns))
    if horizon_vol > 0:
        score = float(
            np.clip(
                math.log(prices.iloc[-1] / prices.iloc[0]) / (2 * horizon_vol), -1, 1
            )
        )
    else:
        score = float(np.sign(cumulative))
    return score, cumulative, annual_vol


def _breadth_component(live):
    previous = pd.to_numeric(_series(live, "PreviousClose"), errors="coerce").replace(
        0, np.nan
    )
    current = pd.to_numeric(_series(live, "Last"), errors="coerce")
    fallback = pd.to_numeric(_series(live, "Close"), errors="coerce")
    current = current.where(current.gt(0), fallback)
    valid = previous.notna() & current.notna()
    changes = current.loc[valid] - previous.loc[valid]
    advances, declines = int(changes.gt(0).sum()), int(changes.lt(0).sum())
    denominator = advances + declines
    score = (advances - declines) / denominator if denominator else float("nan")
    total = int(valid.sum())
    advance_pct = advances / total * 100.0 if total else float("nan")
    decline_pct = declines / total * 100.0 if total else float("nan")
    return score, advance_pct, decline_pct


def _flow_component(live):
    consistent = _series(live, "client_snapshot_consistent", False).fillna(False)
    flows = pd.to_numeric(_series(live, "EstimatedNetIndividualFlow"), errors="coerce")
    values = pd.to_numeric(_series(live, "Value"), errors="coerce")
    net = flows.where(consistent).sum(min_count=1)
    total = values.where(values.gt(0)).sum(min_count=1)
    if pd.isna(net) or pd.isna(total) or total <= 0:
        return float("nan"), float("nan")
    return math.tanh(5.0 * net / total), float(net)


def _liquidity_component(live, activity, window):
    current = pd.to_numeric(_series(live, "Value"), errors="coerce").sum(min_count=1)
    historical = (
        pd.to_numeric(_series(activity, "Value"), errors="coerce").dropna().tail(window)
    )
    median = historical.median() if not historical.empty else float("nan")
    if pd.isna(current) or pd.isna(median) or current <= 0 or median <= 0:
        return float("nan"), float(current), float(median)
    return math.tanh(math.log(current / median)), float(current), float(median)


def _queue_component(live):
    fresh = _series(live, "QueueIsFresh", False).fillna(False)
    buys = pd.to_numeric(
        _series(live, "EstimatedBuyQueueValue"), errors="coerce"
    ).where(fresh)
    sells = pd.to_numeric(
        _series(live, "EstimatedSellQueueValue"), errors="coerce"
    ).where(fresh)
    buy, sell = buys.sum(min_count=1), sells.sum(min_count=1)
    denominator = buy + sell
    if pd.isna(denominator) or denominator <= 0:
        return float("nan"), float(buy), float(sell)
    return float((buy - sell) / denominator), float(buy), float(sell)


def get_market_regime(
    benchmark="شاخص کل",
    start=None,
    end=None,
    lookback=60,
    liquidity_window=20,
    annualization=240,
    weights=None,
    progress=True,
    max_requests=30,
    live_data=None,
    benchmark_history=None,
    activity_history=None,
):
    """Classify an explainable current market regime from five components."""
    benchmark = str(benchmark).strip()
    if not benchmark:
        raise InvalidParameterError("benchmark cannot be empty")
    lookback = _positive_int(lookback, "lookback", 10000)
    liquidity_window = _positive_int(liquidity_window, "liquidity_window", 366)
    annualization = _positive_int(annualization, "annualization", 366)
    max_requests = _positive_int(max_requests, "max_requests", 366)
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    first, last = _date_bounds(start, end)
    regime_weights = _regime_weights(weights)
    if benchmark_history is not None and not isinstance(
        benchmark_history, pd.DataFrame
    ):
        raise InvalidParameterError("benchmark_history must be a DataFrame")
    if live_data is not None and not isinstance(live_data, pd.DataFrame):
        raise InvalidParameterError("live_data must be a DataFrame")
    if activity_history is not None and not isinstance(activity_history, pd.DataFrame):
        raise InvalidParameterError("activity_history must be a DataFrame")
    raw_history = (
        benchmark_history.copy(deep=True)
        if isinstance(benchmark_history, pd.DataFrame)
        else _fetch_price_history(benchmark, first, last)
    )
    history = _normalise_history(raw_history, benchmark, first, last).tail(lookback)
    live = (
        live_data.copy(deep=True)
        if isinstance(live_data, pd.DataFrame)
        else get_live_market()
    )
    if not isinstance(live, pd.DataFrame):
        live = pd.DataFrame()
    if activity_history is None:
        if history.empty:
            activity = pd.DataFrame()
        else:
            dates = history["GregorianDate"].tail(liquidity_window)
            activity = get_market_activity(
                start=dates.min().date(),
                end=dates.max().date(),
                market="all",
                max_requests=max_requests,
                progress=progress,
            )
    else:
        activity = activity_history.copy(deep=True)
    equity_live = live
    if "InstrumentType" in live:
        equity_live = live.loc[
            pd.to_numeric(live["InstrumentType"], errors="coerce").isin(_EQUITY_TYPES)
        ].copy()
    trend, benchmark_return, volatility = _trend_component(
        history, lookback, annualization
    )
    breadth, advance_pct, decline_pct = _breadth_component(equity_live)
    flow, net_flow = _flow_component(equity_live)
    liquidity, current_value, median_value = _liquidity_component(
        live, activity, liquidity_window
    )
    queue, buy_queue, sell_queue = _queue_component(equity_live)
    components = {
        "trend": trend,
        "breadth": breadth,
        "flow": flow,
        "liquidity": liquidity,
        "queue": queue,
    }
    available = {
        key: value for key, value in components.items() if not math.isnan(value)
    }
    missing = [key for key, value in components.items() if math.isnan(value)]
    available_weight = sum(regime_weights[key] for key in available)
    score = (
        sum(regime_weights[key] * value for key, value in available.items())
        / available_weight
        if available_weight > 0
        else float("nan")
    )
    if math.isnan(score):
        regime = "unavailable"
    elif score > 0.25:
        regime = "risk_on"
    elif score < -0.25:
        regime = "risk_off"
    else:
        regime = "neutral"
    timestamps = pd.to_datetime(_series(live, "as_of"), errors="coerce", utc=True)
    as_of = timestamps.max() if timestamps.notna().any() else pd.Timestamp(tehran_now())
    trade_dates = pd.to_datetime(_series(live, "trade_date"), errors="coerce")
    trade_date = trade_dates.max().date() if trade_dates.notna().any() else as_of.date()
    stale = bool(_series(live, "is_stale", False).fillna(False).any())
    partial = bool(_series(live, "is_partial", False).fillna(False).any())
    flags = _quality(
        "benchmark_history_unavailable" if history.empty else None,
        "live_snapshot_unavailable" if live.empty else None,
        "activity_history_unavailable" if activity.empty else None,
        "stale_snapshot" if stale else None,
        "partial_snapshot" if partial else None,
        "missing_components:{}".format(",".join(missing)) if missing else None,
    )
    row = {
        "AsOf": as_of,
        "TradeDate": trade_date,
        "JalaliDate": _jalali(trade_date),
        "Benchmark": benchmark,
        "Regime": regime,
        "Score": score,
        "Confidence": available_weight,
        "TrendScore": trend,
        "BreadthScore": breadth,
        "FlowScore": flow,
        "LiquidityScore": liquidity,
        "QueueScore": queue,
        "TrendWeight": regime_weights["trend"],
        "BreadthWeight": regime_weights["breadth"],
        "FlowWeight": regime_weights["flow"],
        "LiquidityWeight": regime_weights["liquidity"],
        "QueueWeight": regime_weights["queue"],
        "BenchmarkReturnPct": benchmark_return,
        "AnnualizedVolatilityPct": volatility,
        "AdvancePct": advance_pct,
        "DeclinePct": decline_pct,
        "EstimatedNetIndividualFlow": net_flow,
        "CurrentMarketValue": current_value,
        "HistoricalMedianValue": median_value,
        "EstimatedBuyQueueValue": buy_queue,
        "EstimatedSellQueueValue": sell_queue,
        "AvailableComponents": len(available),
        "MissingComponents": len(missing),
        "QualityFlags": flags,
        "Source": "derived_from_explainable_market_components",
    }
    result = _cast(pd.DataFrame([row]), REGIME_COLUMNS)
    result.attrs.update(
        {
            "source": "derived_from_explainable_market_components",
            "fetched_at": tehran_now().isoformat(),
            "weights": dict(regime_weights),
            "thresholds": {"risk_on": 0.25, "risk_off": -0.25},
            "available_components": tuple(available),
            "missing_components": tuple(missing),
            "value_unit": "rial",
            "is_partial": bool(missing),
            "method": "weighted_mean_of_available_components",
        }
    )
    return result


def _industry_name(code):
    try:
        from .search import _INDUSTRY_RAW

        values = _INDUSTRY_RAW.get(str(code), [])
        return values[0] if values else str(code)
    except (ImportError, AttributeError, TypeError):
        return str(code)


def _weighted_average(values, weights):
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce")
    valid = values.notna() & weights.gt(0)
    if not valid.any():
        return float("nan")
    return float(np.average(values.loc[valid], weights=weights.loc[valid]))


def _prepare_map_data(data, flow, instrument_types):
    if data is None:
        live = get_live_market()
    elif isinstance(data, pd.DataFrame):
        live = data.copy(deep=True)
    else:
        raise InvalidParameterError("data must be a DataFrame")
    required = {"InsCode", "Symbol", "Value", "Volume"}
    missing = required - set(live.columns)
    if missing:
        raise DataParsingError(
            "market map data is missing columns: {}".format(", ".join(sorted(missing)))
        )
    if flow is not None:
        if "Flow" not in live:
            raise DataParsingError("market map data must contain Flow when flow is set")
        flows = [flow] if isinstance(flow, (str, int, np.integer)) else list(flow)
        live = live.loc[live["Flow"].astype(str).isin([str(x) for x in flows])]
    if instrument_types is None:
        instrument_types = sorted(_EQUITY_TYPES)
    all_types = isinstance(instrument_types, str) and instrument_types.lower() == "all"
    if not all_types:
        if "InstrumentType" not in live:
            raise DataParsingError(
                "market map data must contain InstrumentType when filtering types"
            )
        types = (
            [instrument_types]
            if isinstance(instrument_types, (str, int, np.integer))
            else list(instrument_types)
        )
        numeric_types = pd.to_numeric(pd.Series(types), errors="raise").astype(int)
        live = live.loc[
            pd.to_numeric(live.get("InstrumentType"), errors="coerce").isin(
                numeric_types
            )
        ]
    live = live.copy()
    live["QueueValue"] = pd.to_numeric(
        _series(live, "EstimatedBuyQueueValue"), errors="coerce"
    ).fillna(0) + pd.to_numeric(
        _series(live, "EstimatedSellQueueValue"), errors="coerce"
    ).fillna(
        0
    )
    return live.reset_index(drop=True)


def get_market_map(
    group_by="symbol",
    size="value",
    color="return",
    top=100,
    flow=None,
    instrument_types=None,
    data=None,
):
    """Return renderer-independent market-map data from one live snapshot."""
    group_key = str(group_by).strip().lower()
    size_key = str(size).strip().lower()
    color_key = str(color).strip().lower()
    if group_key not in _GROUP_COLUMNS:
        raise InvalidParameterError(
            "group_by must be symbol, sector, flow, or instrument_type"
        )
    if size_key not in _SIZE_COLUMNS:
        raise InvalidParameterError(
            "size must be value, volume, market_cap, or queue_value"
        )
    if color_key not in _COLOR_COLUMNS:
        raise InvalidParameterError(
            "color must be return, net_individual_flow, individual_power, "
            "or order_imbalance"
        )
    if top is not None:
        top = _positive_int(top, "top", 5000)
    live = _prepare_map_data(data, flow, instrument_types)
    for column in (
        set(_SIZE_COLUMNS.values())
        | {spec[0] for spec in _COLOR_COLUMNS.values()}
        | {
            "Value",
            "Volume",
            "MarketCap",
            "EstimatedNetIndividualFlow",
            "IndividualPower",
            "ChangePct",
        }
    ):
        if column not in live:
            live[column] = np.nan
        live[column] = pd.to_numeric(live[column], errors="coerce")
    size_column = _SIZE_COLUMNS[size_key]
    color_column, color_aggregation = _COLOR_COLUMNS[color_key]
    live = live.loc[live[size_column].gt(0)].copy()
    total_universe_size = live[size_column].sum(min_count=1)
    group_column = _GROUP_COLUMNS[group_key]
    if group_column not in live:
        raise DataParsingError("market map data must contain {}".format(group_column))
    rows = []
    for key, group in live.groupby(group_column, dropna=False, sort=True):
        size_value = group[size_column].sum(min_count=1)
        color_values = group[color_column]
        color_value = (
            color_values.sum(min_count=1)
            if color_aggregation == "sum"
            else _weighted_average(color_values, group[size_column])
        )
        if group_key == "symbol":
            label = str(group["Symbol"].iloc[0])
            parent = _industry_name(group.get("SectorCode", pd.Series([""])).iloc[0])
        elif group_key == "sector":
            label, parent = _industry_name(key), "صنایع"
        elif group_key == "flow":
            label, parent = "Flow {}".format(key), "بازارها"
        else:
            label, parent = "InstrumentType {}".format(key), "ابزارها"
        fresh_values = group.get(
            "is_realtime_fresh", pd.Series(False, index=group.index)
        ).fillna(False)
        as_of_values = pd.to_datetime(
            _series(group, "as_of"), errors="coerce", utc=True
        )
        rows.append(
            {
                "GroupKey": str(key),
                "Label": label,
                "Parent": parent,
                "GroupBy": group_key,
                "InstrumentCount": len(group),
                "SizeMetric": size_key,
                "SizeValue": size_value,
                "ColorMetric": color_key,
                "ColorValue": color_value,
                "UniverseWeightPct": (
                    size_value / total_universe_size * 100.0
                    if total_universe_size and not pd.isna(total_universe_size)
                    else float("nan")
                ),
                "ReturnPct": _weighted_average(group["ChangePct"], group[size_column]),
                "Value": group["Value"].sum(min_count=1),
                "Volume": group["Volume"].sum(min_count=1),
                "MarketCap": group["MarketCap"].sum(min_count=1),
                "EstimatedNetIndividualFlow": group["EstimatedNetIndividualFlow"].sum(
                    min_count=1
                ),
                "IndividualPower": _weighted_average(
                    group["IndividualPower"], group[size_column]
                ),
                "ColorCoveragePct": color_values.notna().mean() * 100.0,
                "AsOf": as_of_values.max() if as_of_values.notna().any() else pd.NaT,
                "IsRealtimeFresh": bool(fresh_values.all()) if len(group) else False,
                "ValueUnit": "rial",
                "QualityFlags": _quality(
                    "color_unavailable" if not color_values.notna().any() else None,
                    "stale_snapshot" if not fresh_values.all() else None,
                    (
                        "partial_color_coverage"
                        if 0 < color_values.notna().mean() < 1
                        else None
                    ),
                ),
                "Source": "derived_from_tsetmc_live_market",
            }
        )
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(
            ["SizeValue", "GroupKey"], ascending=[False, True], kind="mergesort"
        )
        if top is not None:
            result = result.head(top)
        displayed = pd.to_numeric(result["SizeValue"], errors="coerce").sum(min_count=1)
        result["DisplayedWeightPct"] = (
            pd.to_numeric(result["SizeValue"], errors="coerce") / displayed * 100.0
            if displayed and not pd.isna(displayed)
            else np.nan
        )
        result = result.reset_index(drop=True)
    result = _cast(result, MARKET_MAP_COLUMNS)
    result.attrs.update(
        {
            "source": "derived_from_tsetmc_live_market",
            "fetched_at": tehran_now().isoformat(),
            "group_by": group_key,
            "size_metric": size_key,
            "color_metric": color_key,
            "universe_size": _number(total_universe_size),
            "displayed_size": _number(result["SizeValue"].sum(min_count=1)),
            "value_unit": "rial",
            "is_partial": bool(top is not None and len(rows) > len(result)),
        }
    )
    return result


def plot_market_map(map_data=None, output_path=None, show=False, title=None):
    """Render output of :func:`get_market_map` as an optional Plotly treemap."""
    if not isinstance(show, bool):
        raise InvalidParameterError("show must be bool")
    if map_data is None:
        frame = get_market_map()
    elif isinstance(map_data, pd.DataFrame):
        frame = map_data.copy(deep=True)
    else:
        raise InvalidParameterError("map_data must be a DataFrame")
    required = {"Label", "Parent", "SizeValue", "ColorValue", "ColorMetric"}
    missing = required - set(frame.columns)
    if missing:
        raise DataParsingError(
            "map_data is missing columns: {}".format(", ".join(sorted(missing)))
        )
    if frame.empty:
        raise InvalidParameterError("map_data cannot be empty")
    try:
        import plotly.express as px
    except ImportError as exc:
        raise ImportError(
            "plot_market_map requires plotly; install algotik-tse[visualization]"
        ) from exc
    effective_title = title or "نقشه بازار سرمایه ایران"
    figure = px.treemap(
        frame,
        path=["Parent", "Label"],
        values="SizeValue",
        color="ColorValue",
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        hover_data={
            "InstrumentCount": True,
            "UniverseWeightPct": ":.2f",
            "ReturnPct": ":.2f",
            "Value": ":,.0f",
            "EstimatedNetIndividualFlow": ":,.0f",
            "SizeValue": ":,.0f",
            "ColorValue": ":.3f",
        },
        title=effective_title,
    )
    figure.update_layout(font={"family": "Vazirmatn, Tahoma, sans-serif"})
    if output_path is not None:
        path = Path(output_path).expanduser()
        if path.suffix.lower() != ".html":
            raise InvalidParameterError("output_path must end with .html")
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(str(path), include_plotlyjs="cdn", full_html=True)
    if show:
        figure.show()
    return figure


__all__ = [
    "compare_symbols",
    "get_liquidity_metrics",
    "get_market_regime",
    "get_market_map",
    "plot_market_map",
]
