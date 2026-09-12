"""AlgoTik TSE — Tehran Stock Exchange data library for Python.

A comprehensive Python library for fetching market data from the Tehran Stock
Exchange (TSETMC) and currency, precious-metal and coin prices from TGJU. Most outputs are returned
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

    # Currency / precious-metal / coin prices
    att.get_currency('dollar')
    att.get_currency(['ربع سکه', 'euro'])

    # Intraday candles
    att.get_intraday('شتران', interval='5min')

    # Live market snapshot
    att.get_market_snapshot()

    # Trading calendar, market value and index impact
    att.get_trading_calendar(market='tse')
    att.get_market_value_history(market='all')
    att.get_index_impact(top=10)

    # Options chain
    att.list_options(underlying='اهرم')
    att.get_options_chain('اهرم')

    # ETFs with NAV
    att.list_etfs()

    # Bonds & treasury bills
    att.list_bonds()

    # Iran Energy Exchange auctions and power contracts
    att.get_energy_auctions(top=10)
    att.list_power_instruments(market='green')

    # Iran Mercantile Exchange live and physical markets
    att.get_commodity_market(kind='certificate')
    att.get_commodity_physical_history('1405-01-01')

    # Manager analytics — comparison, liquidity, regime and market map
    att.compare_symbols(['فولاد', 'فملی'], benchmark='شاخص کل')
    att.get_liquidity_metrics(['فولاد', 'فملی'])
    att.get_market_regime()
    att.plot_market_map(att.get_market_map(top=50))

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
__version__ = "1.8.0"

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
from algotik_tse.core.shareholders import shareholders, get_shareholder_history
from algotik_tse.core.ownership import (
    get_major_shareholder_snapshots,
    get_major_shareholder_changes,
    get_active_shareholders,
    rank_shareholder_accumulation,
    get_shareholder_network,
    get_ownership_concentration,
)
from algotik_tse.core.symbol_events import get_symbol_events
from algotik_tse.core.currency import currency_coin
from algotik_tse.core.tgju import get_tgju_history, list_tgju_assets
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
    FUND_TAXONOMY_VERSION,
    list_options,
    get_options_chain,
    list_etfs,
    list_bonds,
    list_debt_instruments,
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
    get_industry_membership_overlap,
    get_industry_intraday,
    get_industry_membership_churn,
    get_industry_concentration,
    get_industry_momentum_profile,
    get_industry_correlation_neighborhood,
    get_industry_health_score,
    rank_industries,
    get_industry_membership_events,
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
    get_debt_yields,
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
from algotik_tse.core.market_reference import (
    get_trading_calendar,
    get_market_activity,
    get_market_value_history,
    get_index_impact,
    get_market_trades,
    get_instrument_master,
    get_instrument_changes,
    get_theoretical_opening_price,
    get_preopen_imbalance,
)
from algotik_tse.core.energy_commodity import (
    get_energy_auctions,
    get_energy_auction,
    get_energy_market_overview,
    list_power_instruments,
    list_energy_securities,
    get_energy_future_contract,
    get_commodity_market,
    get_commodity_physical_history,
    get_commodity_physical_summary,
    get_commodity_market_activity,
    get_futures_curve,
    get_calendar_spreads,
    analyze_cash_and_carry,
)
from algotik_tse.core.manager_analytics import (
    compare_symbols,
    get_liquidity_metrics,
    get_market_regime,
    get_market_map,
    plot_market_map,
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
    """Get TGJU currency, precious-metal or coin price history."""
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
    "get_shareholder_history",
    "get_major_shareholder_snapshots",
    "get_major_shareholder_changes",
    "get_active_shareholders",
    "rank_shareholder_accumulation",
    "get_shareholder_network",
    "get_ownership_concentration",
    "get_symbol_events",
    "get_currency",
    "get_market_snapshot",
    "get_market_client_type",
    "get_market_fundamentals",
    "get_market_fundamentals_history",
    "get_price_adjustments",
    "get_latest_price_adjustment",
    "get_trading_calendar",
    "get_market_activity",
    "get_market_value_history",
    "get_index_impact",
    "get_market_trades",
    "get_instrument_master",
    "get_instrument_changes",
    "get_theoretical_opening_price",
    "get_preopen_imbalance",
    # ── Manager analytics ──
    "compare_symbols",
    "get_liquidity_metrics",
    "get_market_regime",
    "get_market_map",
    "plot_market_map",
    # ── Energy and commodity markets ──
    "get_energy_auctions",
    "get_energy_auction",
    "get_energy_market_overview",
    "list_power_instruments",
    "list_energy_securities",
    "get_energy_future_contract",
    "get_commodity_market",
    "get_commodity_physical_history",
    "get_commodity_physical_summary",
    "get_commodity_market_activity",
    "get_futures_curve",
    "get_calendar_spreads",
    "analyze_cash_and_carry",
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
    "get_debt_yields",
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
    "FUND_TAXONOMY_VERSION",
    "list_bonds",
    "list_debt_instruments",
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
    "get_industry_membership_overlap",
    "get_industry_intraday",
    "get_industry_membership_churn",
    "get_industry_membership_events",
    "get_industry_concentration",
    "get_industry_momentum_profile",
    "get_industry_correlation_neighborhood",
    "get_industry_health_score",
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
    "get_tgju_history",
    "list_tgju_assets",
    "market_watch",
    "market_client_type",
    "market_data",
]
