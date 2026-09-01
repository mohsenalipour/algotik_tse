"""AlgoTik TSE — Tehran Stock Exchange data library for Python.

A comprehensive Python library for fetching market data from the Tehran Stock
Exchange (TSETMC) and currency/coin prices from TGJU. All outputs are returned
as Pandas DataFrames with Jalali (Shamsi) date support.

Main module code by @Python4finance
Developed and maintained by Mohsen Alipour <alipour@algotik.ir>

Quick Start
-----------
.. code-block:: python

    import algotik_tse as att

    # Stock price history
    att.get_history('شتران', start='1402-01-01', end='1402-07-01')

    # Retail / Institutional data
    att.get_client_type('شتران', values=100)

    # All market symbols
    att.get_symbols()

    # Stock details / info / stats
    att.get_detail('شتران')
    att.get_info('شتران')
    att.get_stats('شتران')

    # Shareholders & capital increases
    att.get_shareholders('شتران')
    att.get_capital_increase('شتران')

    # Currency / Coin prices
    att.get_currency('dollar')
    att.get_currency(['ربع سکه', 'euro'])

    # Intraday candles
    att.get_intraday('شتران', interval='5min')

    # Live market snapshot
    att.get_market_snapshot()

    # Options chain
    att.list_options(underlying='اهرم')
    att.get_options_chain('اهرم')

    # ETFs with NAV
    att.list_etfs()

    # Bonds & treasury bills
    att.list_bonds()

    # Investment funds — NAV, returns, portfolio, manager
    att.list_funds()
    att.list_funds(fund_type='equity')

    # Configure settings
    att.settings.ssl_verify = True    # Enable SSL verification
    att.settings.timeout = 15         # Request timeout (seconds)
    att.settings.rate_limit_delay = 0.5  # Delay between requests (seconds)
"""

__author__ = """Mohsen Alipour"""
__email__ = "alipour@algotik.ir"
__version__ = "1.2.1"

from algotik_tse.settings import settings
from algotik_tse.exceptions import (
    AlgotikTSEError,
    AmbiguousSymbolError,
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
    UnsupportedDataSourceError,
)
from algotik_tse.core.stock_detail import (
    stockdetail,
    stock_information,
    stock_statistics,
    stock_introduction,
)
from algotik_tse.core.stock_list import stocklist
from algotik_tse.core.stock import stock, stock_RI, stock_RL, stock_capital_increase
from algotik_tse.core.shareholders import shareholders
from algotik_tse.core.currency import currency_coin
from algotik_tse.core.intraday import stock_intraday, _INTRADAY_DEFAULT_SYMBOL
from algotik_tse.core.market_data import (
    market_watch,
    market_client_type,
    market_data,
    get_order_book,
    get_live_market,
    get_live_symbol,
)
from algotik_tse.core.order_book import (
    get_queue,
    get_order_book_history,
    get_orderbook_history,
    get_queue_history,
)
from algotik_tse.core.market_stream import (
    MarketEvent,
    MarketWatcher,
    watch_market,
    get_market_messages,
    get_instrument_state_changes,
    get_market_overview,
    get_market_breadth,
    get_sector_flow,
)
from algotik_tse.core.market_history import (
    MARKET_HISTORY_SCHEMA_VERSION,
    MARKET_HISTORY_APPLICATION_ID,
    check_market_history,
    save_market_snapshot,
    load_market_snapshots,
    get_live_market_history,
    get_market_overview_history,
    get_market_snapshot_summary_history,
    get_market_breadth_history,
    get_sector_flow_history,
    record_market_event,
    get_market_event_history,
    archive_market_records,
    get_market_messages_history,
    get_instrument_state_changes_history,
)
from algotik_tse.core.instruments import (
    list_options,
    get_options_chain,
    list_etfs,
    list_bonds,
    list_funds,
    list_listed_funds,
    list_indices,
    get_index_companies,
)
from algotik_tse.core.industries import (
    list_industry_indices,
    get_industry_members,
    get_industry_snapshot,
    get_industry_history,
    get_industry_members_history,
    compare_industries,
    get_industry_relative_strength,
    get_industry_correlation,
    get_industry_intraday,
    rank_industries,
)
from algotik_tse.core.options_math import (
    black_scholes_price,
    black_scholes_greeks,
    option_price_bounds,
    implied_volatility,
)
from algotik_tse.core.options import (
    OPTION_SNAPSHOT_SCHEMA_VERSION,
    get_option_market,
    analyze_option_chain,
    option_put_call_ratios,
    get_option_history,
    save_option_snapshot,
    load_option_snapshots,
)
from algotik_tse.core.parsers import parse_treasury_maturity
from algotik_tse.core.conventions import day_count_fraction
from algotik_tse.core.fixed_income import (
    IRAN_TREASURY_FACE_VALUE,
    YieldCurve,
    treasury_yield,
    bond_price,
    yield_to_maturity,
    bond_analytics,
    build_yield_curve,
    get_ifb_yield_table,
    get_treasury_yields,
    get_treasury_yield_history,
    get_treasury_yields_history,
    get_yield_curve,
    get_yield_curve_history,
)
from algotik_tse.core.resolver import (
    InstrumentRef,
    normalize_instrument_text,
    resolve_instrument,
    validate_ins_code,
)
from algotik_tse.core.trades import get_trades, get_live_trades
from algotik_tse.core.fundamentals import (
    get_market_fundamentals,
    get_market_fundamentals_history,
)
from algotik_tse.core.price_adjustments import (
    get_price_adjustments,
    get_latest_price_adjustment,
)

# ── Standard API aliases (recommended) ────────────────────────
# These are the canonical function names following REST/finance conventions.
# The legacy names (stock, stockdetail, etc.) still work for backward compat.


def get_history(
    symbol="",
    start=None,
    end=None,
    limit=0,
    raw=False,
    auto_adjust=True,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    adjust_volume=False,
    return_type=None,
    ascending=True,
    save_path=None,
    include_today=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
):
    """Get historical OHLCV price data for one or more symbols."""
    return stock(
        symbol=symbol,
        start=start,
        end=end,
        limit=limit,
        raw=raw,
        auto_adjust=auto_adjust,
        output_type=output_type,
        date_format=date_format,
        progress=progress,
        save_to_file=save_to_file,
        dropna=dropna,
        adjust_volume=adjust_volume,
        return_type=return_type,
        ascending=ascending,
        save_path=save_path,
        include_today=include_today,
        ins_code=ins_code,
        asset_type=asset_type,
        **kwargs,
    )


def get_client_type(
    symbol="",
    start=None,
    end=None,
    limit=0,
    raw=False,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    ascending=True,
    save_path=None,
    include_today=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
):
    """Get retail/institutional (حقیقی/حقوقی) trade data per symbol."""
    return stock_RI(
        symbol=symbol,
        start=start,
        end=end,
        limit=limit,
        raw=raw,
        output_type=output_type,
        date_format=date_format,
        progress=progress,
        save_to_file=save_to_file,
        dropna=dropna,
        ascending=ascending,
        save_path=save_path,
        include_today=include_today,
        ins_code=ins_code,
        asset_type=asset_type,
        **kwargs,
    )


def get_capital_increase(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """Get capital increase history for a symbol."""
    return stock_capital_increase(
        symbol=symbol, ins_code=ins_code, asset_type=asset_type, **kwargs
    )


def get_intraday(
    symbol=_INTRADAY_DEFAULT_SYMBOL,
    interval="1min",
    start=None,
    end=None,
    progress=True,
    **kwargs,
):
    """Get intraday tick/candle data for a symbol."""
    return stock_intraday(
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        progress=progress,
        **kwargs,
    )


def get_detail(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """Get full stock detail page."""
    return stockdetail(
        symbol=symbol, ins_code=ins_code, asset_type=asset_type, **kwargs
    )


def get_info(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """Get instrument information."""
    return stock_information(
        symbol=symbol, ins_code=ins_code, asset_type=asset_type, **kwargs
    )


def get_stats(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """Get instrument statistics."""
    return stock_statistics(
        symbol=symbol, ins_code=ins_code, asset_type=asset_type, **kwargs
    )


def get_introduction(symbol="", *, ins_code=None, asset_type="auto", **kwargs):
    """Legacy API that raises because company profiles require Codal data."""
    return stock_introduction(
        symbol=symbol, ins_code=ins_code, asset_type=asset_type, **kwargs
    )


def get_symbols(
    bourse=True,
    farabourse=True,
    payeh=True,
    haghe_taqadom=False,
    sandogh=False,
    bonds=False,
    options=False,
    mortgage=False,
    commodity=False,
    energy=False,
    payeh_color=None,
    output="dataframe",
    progress=True,
    **kwargs,
):
    """Get list of all market symbols.

    In addition to stocks, rights, and funds you can now include:
      - ``bonds=True``     — sukuk, treasury bills, government bonds
      - ``options=True``   — stock & fund call/put options
      - ``mortgage=True``  — housing facility certificates
      - ``commodity=True`` — commodity-backed certificates
      - ``energy=True``    — energy certificates

    Alias for ``stocklist()``.
    """
    return stocklist(
        bourse=bourse,
        farabourse=farabourse,
        payeh=payeh,
        haghe_taqadom=haghe_taqadom,
        sandogh=sandogh,
        bonds=bonds,
        options=options,
        mortgage=mortgage,
        commodity=commodity,
        energy=energy,
        payeh_color=payeh_color,
        output=output,
        progress=progress,
        **kwargs,
    )


def get_shareholders(
    symbol="",
    date=None,
    include_id=False,
    *,
    ins_code=None,
    asset_type="auto",
    **kwargs,
):
    """Get major shareholders for a symbol."""
    return shareholders(
        symbol=symbol,
        date=date,
        include_id=include_id,
        ins_code=ins_code,
        asset_type=asset_type,
        **kwargs,
    )


def get_currency(
    name="",
    start=None,
    end=None,
    limit=0,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    return_type=None,
    ascending=True,
    save_path=None,
    **kwargs,
):
    """Get currency/coin price history."""
    return currency_coin(
        name=name,
        start=start,
        end=end,
        limit=limit,
        output_type=output_type,
        date_format=date_format,
        progress=progress,
        save_to_file=save_to_file,
        dropna=dropna,
        return_type=return_type,
        ascending=ascending,
        save_path=save_path,
        **kwargs,
    )


def get_market_snapshot(*args, **kwargs):
    """Get live market snapshot for all instruments."""
    return market_watch(*args, **kwargs)


def get_market_client_type(*args, **kwargs):
    """Get bulk individual/institutional data for all symbols."""
    return market_client_type(*args, **kwargs)


__all__ = [
    # Settings
    "settings",
    "AlgotikTSEError",
    "AmbiguousSymbolError",
    "ConnectionError",
    "DataParsingError",
    "InvalidParameterError",
    "StockNotFoundError",
    "UnsupportedDataSourceError",
    "InstrumentRef",
    "normalize_instrument_text",
    "resolve_instrument",
    "validate_ins_code",
    # ── Standard API (recommended) ──
    "get_history",
    "get_client_type",
    "get_capital_increase",
    "get_intraday",
    "get_trades",
    "get_live_trades",
    "get_detail",
    "get_info",
    "get_stats",
    "get_introduction",
    "get_symbols",
    "get_shareholders",
    "get_currency",
    "get_market_snapshot",
    "get_market_client_type",
    "get_market_fundamentals",
    "get_market_fundamentals_history",
    "get_price_adjustments",
    "get_latest_price_adjustment",
    "get_order_book",
    "get_live_market",
    "get_live_symbol",
    "get_order_book_history",
    "get_orderbook_history",
    "get_queue",
    "get_queue_history",
    "MarketEvent",
    "MarketWatcher",
    "watch_market",
    "get_market_messages",
    "get_instrument_state_changes",
    "get_market_overview",
    "get_market_breadth",
    "get_sector_flow",
    "MARKET_HISTORY_SCHEMA_VERSION",
    "MARKET_HISTORY_APPLICATION_ID",
    "check_market_history",
    "save_market_snapshot",
    "load_market_snapshots",
    "get_live_market_history",
    "get_market_overview_history",
    "get_market_snapshot_summary_history",
    "get_market_breadth_history",
    "get_sector_flow_history",
    "record_market_event",
    "get_market_event_history",
    "archive_market_records",
    "get_market_messages_history",
    "get_instrument_state_changes_history",
    # ── Fixed income / Iranian treasury bills ──
    "IRAN_TREASURY_FACE_VALUE",
    "YieldCurve",
    "parse_treasury_maturity",
    "day_count_fraction",
    "treasury_yield",
    "bond_price",
    "yield_to_maturity",
    "bond_analytics",
    "build_yield_curve",
    "get_ifb_yield_table",
    "get_treasury_yields",
    "get_treasury_yield_history",
    "get_treasury_yields_history",
    "get_yield_curve",
    "get_yield_curve_history",
    # ── Instruments ──
    "list_options",
    "get_options_chain",
    "OPTION_SNAPSHOT_SCHEMA_VERSION",
    "black_scholes_price",
    "black_scholes_greeks",
    "option_price_bounds",
    "implied_volatility",
    "get_option_market",
    "analyze_option_chain",
    "option_put_call_ratios",
    "get_option_history",
    "save_option_snapshot",
    "load_option_snapshots",
    "list_etfs",
    "list_bonds",
    "list_funds",
    "list_listed_funds",
    # ── Indices ──
    "list_indices",
    "get_index_companies",
    "list_industry_indices",
    "get_industry_members",
    "get_industry_snapshot",
    "get_industry_history",
    "get_industry_members_history",
    "compare_industries",
    "get_industry_relative_strength",
    "get_industry_correlation",
    "get_industry_intraday",
    "rank_industries",
    # ── Legacy names (backward compatible) ──
    "stock",
    "stock_RI",
    "stock_RL",
    "stock_capital_increase",
    "stock_intraday",
    "stockdetail",
    "stock_information",
    "stock_statistics",
    "stock_introduction",
    "stocklist",
    "shareholders",
    "currency_coin",
    "market_watch",
    "market_client_type",
    "market_data",
]
