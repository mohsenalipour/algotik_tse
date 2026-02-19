#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Comprehensive integration tests for algotik_tse v1.0.0.

Usage:
    1. Turn off VPN
    2. Run:  python tests/test_algotik_tse.py
    3. Results saved to:  tests/test_results.txt
    4. Share test_results.txt for debugging
"""

import sys
import time
import traceback
import os
from datetime import datetime
from io import StringIO

import pandas as pd

# Ensure the package is importable from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import algotik_tse as att
from algotik_tse.settings import settings

# ──────────────────────────────────────────────────────────────
# Output buffer — everything is written here and saved to TXT
# ──────────────────────────────────────────────────────────────
output = StringIO()


def log(msg=""):
    """Write to both console and output buffer."""
    print(msg)
    output.write(msg + "\n")


# ──────────────────────────────────────────────────────────────
# Test runner
# ──────────────────────────────────────────────────────────────
results = []  # list of (id, description, status, duration, error)


def run_test(test_id, description, func, *args, **kwargs):
    """Run a test function, capture results."""
    log("")
    log("=" * 70)
    log("[TEST {:02d}] {}".format(test_id, description))
    log("=" * 70)

    t0 = time.time()
    status = "ERROR"
    error_msg = ""

    try:
        result = func(*args, **kwargs)
        elapsed = round(time.time() - t0, 2)

        if isinstance(result, pd.DataFrame):
            status = "PASS"
            log("  PASS | shape={} | time={}s".format(result.shape, elapsed))
            log("  columns: {}".format(list(result.columns)[:15]))
            log("  index name: {}".format(result.index.name))
            # Print head safely
            try:
                head_str = result.head(3).to_string()
                log(head_str)
            except Exception as e:
                log("  (head display error: {})".format(e))
        elif result is None:
            status = "FAIL"
            error_msg = "Function returned None"
            log("  FAIL | returned None | time={}s".format(elapsed))
        else:
            status = "PASS"
            log("  PASS | type={} | time={}s".format(type(result).__name__, elapsed))
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        status = "ERROR"
        error_msg = "{}: {}".format(type(e).__name__, e)
        tb = traceback.format_exc()
        log("  ERROR | {} | time={}s".format(error_msg, elapsed))
        log(tb)

    results.append((test_id, description, status, elapsed, error_msg))


# ══════════════════════════════════════════════════════════════
#  TEST FUNCTIONS
# ══════════════════════════════════════════════════════════════


# ─── 0. Version & Settings ───────────────────────────────────
def test_version():
    assert att.__version__ == "1.0.0", "Expected 1.0.0, got {}".format(att.__version__)
    return pd.DataFrame(
        {
            "version": [att.__version__],
            "ssl_verify": [settings.ssl_verify],
            "timeout": [settings.timeout],
            "max_retries": [settings.max_retries],
            "rate_limit_delay": [settings.rate_limit_delay],
        }
    )


# ─── 1-4. stock() — Index ────────────────────────────────────
def test_stock_index_values():
    return att.stock(stock="شاخص کل", values=100)


def test_stock_index_start():
    return att.stock(stock="شاخص کل", start="1401-01-01")


def test_stock_index_end():
    return att.stock(stock="شاخص کل", end="1400-01-01")


def test_stock_index_start_end():
    return att.stock(stock="شاخص کل", start="1400-01-01", end="1401-01-01")


# ─── 5-8. stock() — Regular stock ────────────────────────────
def test_stock_sahm_values():
    return att.stock(stock="مدیریت", values=100)


def test_stock_sahm_start():
    return att.stock(stock="مدیریت", start="1401-01-01")


def test_stock_sahm_end():
    return att.stock(stock="مدیریت", end="1401-01-01")


def test_stock_sahm_start_end():
    return att.stock(stock="مدیریت", start="1400-01-01", end="1401-01-01")


# ─── 9. stock() — Industry Index ─────────────────────────────
def test_stock_industry_index():
    return att.stock(stock="شاخص صنعت فلزات اساسی", values=50)


# ─── 10-11. stock() — output_type & date_format ──────────────
def test_stock_complete_gregorian_returns():
    return att.stock(
        stock="شتران",
        output_type="complete",
        auto_adjust=False,
        return_type="simple",
        date_format="gregorian",
        values=50,
    )


def test_stock_date_format_both():
    return att.stock(stock="شتران", date_format="both", values=30)


# ─── 12-14. stock() — return_type (simple/log/both) ──────────
def test_stock_return_simple():
    return att.stock(stock="فولاد", return_type="simple", values=50)


def test_stock_return_log():
    return att.stock(stock="فولاد", return_type="log", values=50)


def test_stock_return_both():
    return att.stock(stock="فولاد", return_type="both", values=50)


def test_stock_return_list():
    """Custom return_type: ['simple', 'Close', 5] — 5-day simple return on Close."""
    return att.stock(stock="فولاد", return_type=["simple", "Close", 5], values=50)


# ─── 15-16. stock() — Multi-stock ────────────────────────────
def test_stock_multi():
    return att.stock(stock=["شتران", "فملی"], values=30)


def test_stock_multi_3():
    return att.stock(stock=["شتران", "فملی", "فولاد"], values=20)


# ─── 17-19. stock_RL() / stock_RI() ──────────────────────────
def test_stock_rl_values():
    return att.stock_RL(stock="مدیریت", values=100)


def test_stock_rl_start_end():
    return att.stock_RL(stock="مدیریت", start="1400-01-01", end="1401-01-01")


def test_stock_ri_values():
    return att.stock_RI(stock="شتران", values=50)


# ─── 20-21. stock_RI() — date formats & output ───────────────
def test_stock_ri_gregorian():
    return att.stock_RI(stock="شتران", values=50, date_format="gregorian")


def test_stock_ri_complete():
    return att.stock_RI(stock="شتران", values=30, output_type="complete")


# ─── 22-23. stock_capital_increase() ─────────────────────────
def test_capital_increase():
    return att.stock_capital_increase(stock="شپنا")


def test_capital_increase_2():
    return att.stock_capital_increase(stock="شتران")


# ─── 24-28. stockdetail / stock_information / stock_statistics
def test_stockdetail():
    return att.stockdetail(stock="شتران")


def test_stock_information():
    return att.stock_information(stock="ضهرم2016")


def test_stock_information_2():
    return att.stock_information(stock="شتران")


def test_stock_statistics():
    return att.stock_statistics(stock="نوری")


def test_stock_statistics_2():
    return att.stock_statistics(stock="شتران")


# ─── 29-31. shareholders() ───────────────────────────────────
def test_shareholders_latest():
    return att.shareholders(stock="شتران")


def test_shareholders_date():
    return att.shareholders(stock="داتام", date="14021006", shh_id=True)


def test_shareholders_date_2():
    return att.shareholders(stock="شصدف", date="14011103", shh_id=True)


# ─── 32-36. currency_coin() ──────────────────────────────────
def test_currency_dollar():
    return att.currency_coin(currency_coin_name="dollar", values=100)


def test_currency_dollar_persian():
    return att.currency_coin(currency_coin_name="دلار", values=100)


def test_currency_multi():
    return att.currency_coin(["ربع سکه", "euro"], values=100)


def test_currency_return_log():
    return att.currency_coin(
        "dollar", return_type="log", date_format="gregorian", values=50
    )


def test_currency_seke():
    return att.currency_coin(currency_coin_name="سکه", values=50)


# ─── 37-39. stocklist() ──────────────────────────────────────
def test_stocklist_all():
    return att.stocklist()


def test_stocklist_payeh():
    return att.stocklist(bourse=False, farabourse=False, payeh=True)


def test_stocklist_payeh_color():
    return att.stocklist(bourse=False, farabourse=False, payeh=True, payeh_color="زرد")


# ─── 40. Settings — timeout change ───────────────────────────
def test_settings_change_timeout():
    old_timeout = settings.timeout
    settings.timeout = 20
    result = att.stock(stock="شتران", values=5)
    settings.timeout = old_timeout
    return result


# ─── 41. Settings — rate limit ────────────────────────────────
def test_settings_rate_limit():
    old_rl = settings.rate_limit_delay
    settings.rate_limit_delay = 1.0
    t0 = time.time()
    r1 = att.currency_coin("dollar", values=5)
    r2 = att.currency_coin("euro", values=5)
    elapsed = time.time() - t0
    settings.rate_limit_delay = old_rl
    if r1 is not None and r2 is not None:
        return pd.DataFrame(
            {
                "rate_limit_test": [
                    "2 requests in {:.1f}s (expected >=1s delay)".format(elapsed)
                ]
            }
        )
    return None


# ─── 42. stock() — adjust_volume ─────────────────────────────
def test_stock_adjust_volume():
    return att.stock(stock="شپنا", values=50, adjust_volume=True)


# ─── 43. stock() — tse_format ────────────────────────────────
def test_stock_tse_format():
    return att.stock(stock="شتران", values=30, tse_format=True)


# ─── 44. stock() — save_to_file ──────────────────────────────
def test_stock_save_to_file():
    result = att.stock(stock="شتران", values=10, save_to_file=True)
    csv_file = "شتران.csv"
    if os.path.exists(csv_file):
        log(
            "  CSV file created: {} ({} bytes)".format(
                csv_file, os.path.getsize(csv_file)
            )
        )
        os.remove(csv_file)
    else:
        log("  WARNING: CSV file was NOT created")
    return result


# ─── 45. stock() — auto_adjust=False (shows Adj Close col) ──
def test_stock_no_auto_adjust():
    return att.stock(stock="شتران", auto_adjust=False, values=30)


# ─── 47. stock_intraday() — 1-minute candles ─────────────────
def test_intraday_1min():
    return att.stock_intraday("شتران", interval="1min")


# ─── 48. stock_intraday() — 5-minute candles ─────────────────
def test_intraday_5min():
    return att.stock_intraday("شتران", interval="5min")


# ─── 49. stock_intraday() — tick data ────────────────────────
def test_intraday_tick():
    return att.stock_intraday("شتران", interval="tick")


# ─── 50. stock_intraday() — 1-hour candles ───────────────────
def test_intraday_1h():
    return att.stock_intraday("شتران", interval="1h")


# ─── 51. stock_intraday() — historical single day ───────────
def test_intraday_historical_single():
    return att.stock_intraday("شتران", interval="5min", start="1404-11-06")


# ─── 52. stock_intraday() — historical multi-day ────────────
def test_intraday_historical_multi():
    return att.stock_intraday(
        "شتران", interval="1min", start="1404-11-04", end="1404-11-06"
    )


# ─── 53. stock_intraday() — historical tick data ────────────
def test_intraday_historical_tick():
    return att.stock_intraday("شتران", interval="tick", start="1404-11-06")


# ─── 54. market_watch() — live prices + symbol/name/EPS ──────
def test_market_watch():
    data = att.market_watch()
    assert isinstance(data, dict), "Expected dict, got {}".format(type(data))
    assert "stocks" in data, "Missing 'stocks' key"
    assert "market_time" in data, "Missing 'market_time' key"
    assert "index_value" in data, "Missing 'index_value' key"
    stocks_df = data["stocks"]
    assert not stocks_df.empty, "Stocks DataFrame is empty"
    # Verify MarketWatchInit enriched columns
    for col in [
        "Symbol",
        "Name",
        "ISIN",
        "EPS",
        "MaxAllowed",
        "MinAllowed",
        "SectorCode",
    ]:
        assert col in stocks_df.columns, "Missing column: {}".format(col)
    log("  market_time: {}".format(data.get("market_time", "")))
    log("  index_value: {}".format(data.get("index_value", 0)))
    log("  stocks shape: {}".format(stocks_df.shape))
    # Show a few regular stocks (InstrumentType 300/303/309)
    regular = stocks_df[stocks_df["InstrumentType"].isin([300, 303, 309])]
    log("  regular stocks: {}".format(len(regular)))
    if not regular.empty:
        sample = regular[["Symbol", "Name", "Last", "Close", "Volume", "EPS"]].head(5)
        log(sample.to_string())
    return stocks_df


# ─── 55. market_client_type() — individual vs institutional ──
def test_market_client_type():
    df = att.market_client_type()
    assert isinstance(df, pd.DataFrame), "Expected DataFrame"
    assert len(df) > 0, "Empty DataFrame"
    log("  columns: {}".format(list(df.columns)))
    log(df.head(3).to_string())
    return df


# ══════════════════════════════════════════════════════════════
#  NEW PARAMETER NAMES & FEATURES (v2 standardization)
# ══════════════════════════════════════════════════════════════


# ─── 56. New param names: symbol= & limit= ──────────────────
def test_new_param_symbol_limit():
    """Test new standard parameter names: symbol instead of stock, limit instead of values."""
    return att.stock(symbol="شتران", limit=30)


# ─── 57. New param: raw= (was tse_format=) ───────────────────
def test_new_param_raw():
    """Test raw=True (replaces tse_format=True)."""
    df = att.stock(symbol="شتران", limit=10, raw=True)
    # raw mode should have TSETMC column names like <TICKER>, <HIGH>
    assert (
        "<TICKER>" in df.columns or "<HIGH>" in df.columns
    ), "raw=True should produce TSETMC columns, got: {}".format(list(df.columns))
    return df


# ─── 58. New param: output_type='full' (was 'complete') ──────
def test_new_param_output_type_full():
    """Test output_type='full' (replaces 'complete')."""
    df = att.stock(symbol="شتران", limit=10, output_type="full")
    assert "Final" in df.columns, "output_type='full' should have 'Final' column"
    assert "Ticker" in df.columns, "output_type='full' should have 'Ticker' column"
    return df


# ─── 59. New param: dropna= (was multi_stock_drop=) ──────────
def test_new_param_dropna():
    """Test dropna= for multi-stock mode."""
    return att.stock(symbol=["شتران", "فملی"], limit=20, dropna=True)


# ─── 60. New param: ascending=False ──────────────────────────
def test_new_param_ascending_false():
    """Test ascending=False — data should be sorted newest first."""
    df = att.stock(symbol="شتران", limit=10, ascending=False)
    dates = list(df.index)
    assert (
        dates[0] >= dates[-1]
    ), "ascending=False should sort newest first, got first={} last={}".format(
        dates[0], dates[-1]
    )
    return df


# ─── 61. New param: ascending=True (default) ─────────────────
def test_new_param_ascending_true():
    """Test ascending=True — data should be sorted oldest first (default)."""
    df = att.stock(symbol="شتران", limit=10, ascending=True)
    dates = list(df.index)
    assert (
        dates[0] <= dates[-1]
    ), "ascending=True should sort oldest first, got first={} last={}".format(
        dates[0], dates[-1]
    )
    return df


# ─── 62. New param: save_path= ──────────────────────────────
def test_new_param_save_path():
    """Test save_path — should save CSV to specified path."""
    csv_path = "test_save_path_output.csv"
    df = att.stock(symbol="شتران", limit=5, save_path=csv_path)
    if os.path.exists(csv_path):
        size = os.path.getsize(csv_path)
        log("  CSV saved: {} ({} bytes)".format(csv_path, size))
        os.remove(csv_path)
        assert size > 0, "CSV file is empty"
    else:
        log("  WARNING: save_path did NOT create file")
    return df


# ─── 63. New param: include_id= (was shh_id=) ───────────────
def test_new_param_include_id():
    """Test include_id=True (replaces shh_id=True)."""
    df = att.shareholders(symbol="شتران", include_id=True)
    assert (
        "share_holder_id" in df.columns
    ), "include_id=True should add 'share_holder_id' column"
    return df


# ─── 64. New param: name= for currency (was currency_coin_name=)
def test_new_param_currency_name():
    """Test name= parameter for currency_coin."""
    return att.currency_coin(name="dollar", limit=30)


# ─── 65. Currency: output_type='full' ────────────────────────
def test_currency_output_type_full():
    """Test output_type='full' for currency."""
    return att.currency_coin(name="dollar", limit=20, output_type="full")


# ─── 66. Currency: ascending=False ───────────────────────────
def test_currency_ascending_false():
    """Test ascending=False for currency."""
    df = att.currency_coin(name="dollar", limit=10, ascending=False)
    dates = list(df.index)
    assert dates[0] >= dates[-1], "ascending=False should sort newest first"
    return df


# ─── 67. Currency: dropna= (was multi_currencies_drop=) ─────
def test_currency_new_param_dropna():
    """Test dropna= for multi-currency mode."""
    return att.currency_coin(name=["dollar", "euro"], limit=20, dropna=True)


# ─── 68. stock_RI: new param names ──────────────────────────
def test_stock_ri_new_params():
    """Test stock_RI with new param names: symbol, limit, raw."""
    return att.stock_RI(symbol="شتران", limit=30, output_type="full")


# ─── 69. stocklist: English alias main_market ─────────────────
def test_stocklist_english_alias_main_market():
    """Test English alias: main_market instead of bourse."""
    return att.stocklist(main_market=True, otc=False, base_market=False)


# ─── 70. stocklist: English alias funds ──────────────────────
def test_stocklist_english_alias_funds():
    """Test English alias: funds instead of sandogh."""
    return att.stocklist(funds=True)


# ─── 71. stocklist: English alias base_market_tier ────────────
def test_stocklist_english_alias_tier():
    """Test English alias: base_market_tier instead of payeh_color."""
    return att.stocklist(
        main_market=False, otc=False, base_market=True, base_market_tier="زرد"
    )


# ─── 72. get_* aliases with new params ───────────────────────
def test_get_history_alias():
    """Test get_history() alias with new param names."""
    return att.get_history(symbol="شتران", limit=10, ascending=False)


def test_get_client_type_alias():
    """Test get_client_type() alias with new param names."""
    return att.get_client_type(symbol="شتران", limit=10)


def test_get_shareholders_alias():
    """Test get_shareholders() alias with new param names."""
    return att.get_shareholders(symbol="شتران", include_id=True)


def test_get_currency_alias():
    """Test get_currency() alias with new param names."""
    return att.get_currency(name="dollar", limit=10)


def test_get_symbols_alias():
    """Test get_symbols() alias with English param names."""
    return att.get_symbols(main_market=True, otc=False, base_market=False)


# ─── 77. get_symbols: bonds ──────────────────────────────────
def test_get_symbols_bonds():
    """Test get_symbols(bonds=True) returns bond instruments."""
    df = att.get_symbols(bourse=False, farabourse=False, payeh=False, bonds=True)
    assert df is not None, "bonds returned None"
    assert len(df) > 0, "bonds returned empty"
    assert "asset_type" in df.columns, "missing asset_type column"
    assert (df["asset_type"] == "bond").all(), "not all rows are bonds"
    # Bonds have ISIN starting with IRB
    assert (
        df["instrument_isin"].str[:3].eq("IRB").all()
    ), "bond ISINs should start with IRB"
    return df


# ─── 78. get_symbols: options ────────────────────────────────
def test_get_symbols_options():
    """Test get_symbols(options=True) returns option instruments."""
    df = att.get_symbols(bourse=False, farabourse=False, payeh=False, options=True)
    assert df is not None, "options returned None"
    assert len(df) > 0, "options returned empty"
    assert (df["asset_type"] == "option").all(), "not all rows are options"
    # Options: IRO9, IROF, IROA, IROB
    valid = df["instrument_isin"].str[:4].isin(["IRO9", "IROF", "IROA", "IROB"])
    assert valid.all(), "unexpected ISIN prefix in options"
    return df


# ─── 79. get_symbols: mortgage ───────────────────────────────
def test_get_symbols_mortgage():
    """Test get_symbols(mortgage=True) returns housing certificates."""
    df = att.get_symbols(bourse=False, farabourse=False, payeh=False, mortgage=True)
    assert df is not None, "mortgage returned None"
    assert len(df) > 0, "mortgage returned empty"
    assert (df["asset_type"] == "mortgage").all()
    assert df["instrument_isin"].str[:4].eq("IRO6").all()
    return df


# ─── 80. get_symbols: commodity ──────────────────────────────
def test_get_symbols_commodity():
    """Test get_symbols(commodity=True) returns commodity instruments."""
    df = att.get_symbols(bourse=False, farabourse=False, payeh=False, commodity=True)
    assert df is not None, "commodity returned None"
    assert len(df) > 0, "commodity returned empty"
    assert (df["asset_type"] == "commodity").all()
    valid = df["instrument_isin"].str[:4].isin(["IRBK", "IRK1"])
    assert valid.all(), "unexpected ISIN prefix in commodity"
    return df


# ─── 81. get_symbols: energy ─────────────────────────────────
def test_get_symbols_energy():
    """Test get_symbols(energy=True) returns energy certificates."""
    df = att.get_symbols(bourse=False, farabourse=False, payeh=False, energy=True)
    assert df is not None, "energy returned None"
    assert len(df) > 0, "energy returned empty"
    assert (df["asset_type"] == "energy").all()
    assert df["instrument_isin"].str[:4].eq("IRBE").all()
    return df


# ─── 82. get_symbols: asset_type column in default call ──────
def test_get_symbols_asset_type_column():
    """Test that default get_symbols() has asset_type='stock' column."""
    df = att.get_symbols()
    assert "asset_type" in df.columns, "missing asset_type column"
    assert (df["asset_type"] == "stock").all(), "default should all be stocks"
    return df


# ─── 83. get_symbols: mixed types ────────────────────────────
def test_get_symbols_mixed():
    """Test get_symbols with multiple types selected."""
    df = att.get_symbols(
        bourse=True, farabourse=False, payeh=False, sandogh=True, bonds=True
    )
    assert df is not None
    types = set(df["asset_type"].unique())
    assert "stock" in types, "should contain stocks"
    assert "fund" in types, "should contain funds"
    assert "bond" in types, "should contain bonds"
    return df


# ─── 84. get_symbols: backward compat (no asset_type param) ──
def test_get_symbols_backward_compat():
    """Existing code that ignores asset_type column should still work."""
    df = att.stocklist(bourse=True, farabourse=False, payeh=False)
    assert df is not None
    assert "name" in df.columns
    assert "instrument_isin" in df.columns
    assert "market" in df.columns
    assert df.index.name == "symbol"
    return df


# ─── 85. list_funds: all types ───────────────────────────────
def test_list_funds_all():
    """Test list_funds() returns all fund types."""
    df = att.list_funds()
    assert df is not None
    assert len(df) > 0, "no funds returned"
    required_cols = [
        "fund_name",
        "fund_type",
        "reg_no",
        "nav_redemption",
        "nav_subscription",
        "nav_statistical",
        "net_asset",
        "return_1d",
        "return_365d",
        "pct_stock",
        "pct_bond",
        "manager",
        "inception_date",
    ]
    for col in required_cols:
        assert col in df.columns, "missing column: {}".format(col)
    # Should have multiple fund types
    assert len(df["fund_type"].unique()) >= 3, "expected multiple fund types"
    return df


# ─── 86. list_funds: equity only ─────────────────────────────
def test_list_funds_equity():
    """Test list_funds(fund_type='equity')."""
    df = att.list_funds(fund_type="equity")
    assert df is not None
    assert len(df) > 0
    assert (df["fund_type"] == "equity").all(), "all should be equity"
    # Equity funds should have meaningful stock allocation
    assert df["pct_stock"].mean() > 20, "equity funds should have stock allocation"
    return df


# ─── 87. list_funds: fixed_income only ───────────────────────
def test_list_funds_fixed_income():
    """Test list_funds(fund_type='fixed_income')."""
    df = att.list_funds(fund_type="fixed_income")
    assert df is not None
    assert len(df) > 0
    assert (df["fund_type"] == "fixed_income").all()
    return df


# ─── 88. list_funds: multiple types ──────────────────────────
def test_list_funds_multi():
    """Test list_funds with list of types."""
    df = att.list_funds(fund_type=["equity", "mixed", "commodity"])
    assert df is not None
    assert len(df) > 0
    types = set(df["fund_type"].unique())
    assert "equity" in types
    assert "mixed" in types
    return df


# ─── 89. list_funds: nav & return columns ────────────────────
def test_list_funds_nav_data():
    """Test that NAV and return data is populated."""
    df = att.list_funds(fund_type="equity")
    assert df is not None
    assert len(df) > 0
    # NAV should be positive for most funds
    has_nav = (df["nav_redemption"] > 0).sum()
    assert has_nav > 0, "at least some funds should have NAV > 0"
    # Returns should be numbers (not all None)
    assert df["return_365d"].notna().any(), "annual return should have data"
    return df


# ─── 90. list_funds: invalid type ────────────────────────────
def test_list_funds_invalid():
    """Test list_funds with invalid fund_type returns None."""
    result = att.list_funds(fund_type="invalid_type")
    assert result is None, "invalid type should return None"
    return pd.DataFrame({"status": ["PASS - returned None as expected"]})


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log("=" * 70)
    log("  AlgoTik TSE v{} - Integration Test Suite".format(att.__version__))
    log("  Python: {}".format(sys.version.split()[0]))
    log("  Started: {}".format(datetime.now().isoformat()))
    log("=" * 70)

    all_tests = [
        (0, "Version & Settings check", test_version),
        (1, "stock(شاخص کل, values=100)", test_stock_index_values),
        (2, "stock(شاخص کل, start=1401-01-01)", test_stock_index_start),
        (3, "stock(شاخص کل, end=1400-01-01)", test_stock_index_end),
        (4, "stock(شاخص کل, start+end)", test_stock_index_start_end),
        (5, "stock(مدیریت, values=100)", test_stock_sahm_values),
        (6, "stock(مدیریت, start=1401-01-01)", test_stock_sahm_start),
        (7, "stock(مدیریت, end=1401-01-01)", test_stock_sahm_end),
        (8, "stock(مدیریت, start+end)", test_stock_sahm_start_end),
        (9, "stock(شاخص صنعت فلزات اساسی, values=50)", test_stock_industry_index),
        (
            10,
            "stock(complete+gregorian+return_type=simple)",
            test_stock_complete_gregorian_returns,
        ),
        (11, "stock(date_format=both)", test_stock_date_format_both),
        (12, "stock(return_type=simple)", test_stock_return_simple),
        (13, "stock(return_type=log)", test_stock_return_log),
        (14, "stock(return_type=both)", test_stock_return_both),
        (15, "stock(return_type=[simple,Close,5])", test_stock_return_list),
        (16, "stock(multi: [شتران, فملی])", test_stock_multi),
        (17, "stock(multi: [شتران, فملی, فولاد])", test_stock_multi_3),
        (18, "stock_RL(مدیریت, values=100)", test_stock_rl_values),
        (19, "stock_RL(مدیریت, start+end)", test_stock_rl_start_end),
        (20, "stock_RI(شتران, values=50)", test_stock_ri_values),
        (21, "stock_RI(شتران, gregorian)", test_stock_ri_gregorian),
        (22, "stock_RI(شتران, complete)", test_stock_ri_complete),
        (23, "stock_capital_increase(شپنا)", test_capital_increase),
        (24, "stock_capital_increase(شتران)", test_capital_increase_2),
        (25, "stockdetail(شتران)", test_stockdetail),
        (26, "stock_information(ضهرم2016)", test_stock_information),
        (27, "stock_information(شتران)", test_stock_information_2),
        (28, "stock_statistics(نوری)", test_stock_statistics),
        (29, "stock_statistics(شتران)", test_stock_statistics_2),
        (30, "shareholders(شتران, latest)", test_shareholders_latest),
        (31, "shareholders(داتام, date=14021006, shh_id)", test_shareholders_date),
        (32, "shareholders(شصدف, date=14011103, shh_id)", test_shareholders_date_2),
        (33, "currency_coin(dollar, values=100)", test_currency_dollar),
        (34, "currency_coin(دلار, values=100)", test_currency_dollar_persian),
        (35, "currency_coin([ربع سکه, euro], values=100)", test_currency_multi),
        (36, "currency_coin(dollar, log+gregorian)", test_currency_return_log),
        (37, "currency_coin(سکه, values=50)", test_currency_seke),
        (38, "stocklist(all defaults)", test_stocklist_all),
        (39, "stocklist(payeh only)", test_stocklist_payeh),
        (40, "stocklist(payeh, color=زرد)", test_stocklist_payeh_color),
        (41, "settings: change timeout", test_settings_change_timeout),
        (42, "settings: rate_limit_delay=1.0", test_settings_rate_limit),
        (43, "stock(شپنا, adjust_volume=True)", test_stock_adjust_volume),
        (44, "stock(شتران, tse_format=True)", test_stock_tse_format),
        (45, "stock(شتران, save_to_file=True)", test_stock_save_to_file),
        (46, "stock(شتران, auto_adjust=False)", test_stock_no_auto_adjust),
        (47, "stock_intraday(شتران, 1min)", test_intraday_1min),
        (48, "stock_intraday(شتران, 5min)", test_intraday_5min),
        (49, "stock_intraday(شتران, tick)", test_intraday_tick),
        (50, "stock_intraday(شتران, 1h)", test_intraday_1h),
        (
            51,
            "stock_intraday(شتران, 5min, historical)",
            test_intraday_historical_single,
        ),
        (52, "stock_intraday(شتران, 1min, multi-day)", test_intraday_historical_multi),
        (53, "stock_intraday(شتران, tick, historical)", test_intraday_historical_tick),
        (54, "market_watch()", test_market_watch),
        (55, "market_client_type()", test_market_client_type),
        # ── New parameter names & features ──
        (56, "NEW: symbol= & limit=", test_new_param_symbol_limit),
        (57, "NEW: raw=True (was tse_format)", test_new_param_raw),
        (58, "NEW: output_type='full' (was complete)", test_new_param_output_type_full),
        (59, "NEW: dropna= multi-stock", test_new_param_dropna),
        (60, "NEW: ascending=False", test_new_param_ascending_false),
        (61, "NEW: ascending=True", test_new_param_ascending_true),
        (62, "NEW: save_path=", test_new_param_save_path),
        (63, "NEW: include_id= (was shh_id)", test_new_param_include_id),
        (64, "NEW: currency name=", test_new_param_currency_name),
        (65, "NEW: currency output_type='full'", test_currency_output_type_full),
        (66, "NEW: currency ascending=False", test_currency_ascending_false),
        (67, "NEW: currency dropna=", test_currency_new_param_dropna),
        (68, "NEW: stock_RI new params", test_stock_ri_new_params),
        (
            69,
            "NEW: stocklist main_market alias",
            test_stocklist_english_alias_main_market,
        ),
        (70, "NEW: stocklist funds alias", test_stocklist_english_alias_funds),
        (
            71,
            "NEW: stocklist base_market_tier alias",
            test_stocklist_english_alias_tier,
        ),
        (72, "NEW: get_history() alias", test_get_history_alias),
        (73, "NEW: get_client_type() alias", test_get_client_type_alias),
        (74, "NEW: get_shareholders() alias", test_get_shareholders_alias),
        (75, "NEW: get_currency() alias", test_get_currency_alias),
        (76, "NEW: get_symbols() alias", test_get_symbols_alias),
        # ── New asset types (bonds, options, etc.) ──
        (77, "NEW: get_symbols(bonds=True)", test_get_symbols_bonds),
        (78, "NEW: get_symbols(options=True)", test_get_symbols_options),
        (79, "NEW: get_symbols(mortgage=True)", test_get_symbols_mortgage),
        (80, "NEW: get_symbols(commodity=True)", test_get_symbols_commodity),
        (81, "NEW: get_symbols(energy=True)", test_get_symbols_energy),
        (82, "NEW: get_symbols() asset_type col", test_get_symbols_asset_type_column),
        (83, "NEW: get_symbols(mixed types)", test_get_symbols_mixed),
        (84, "NEW: stocklist() backward compat", test_get_symbols_backward_compat),
        # ── Fund API (list_funds) ──
        (85, "NEW: list_funds() all types", test_list_funds_all),
        (86, "NEW: list_funds(equity)", test_list_funds_equity),
        (87, "NEW: list_funds(fixed_income)", test_list_funds_fixed_income),
        (88, "NEW: list_funds(multi types)", test_list_funds_multi),
        (89, "NEW: list_funds nav & returns", test_list_funds_nav_data),
        (90, "NEW: list_funds invalid type", test_list_funds_invalid),
    ]

    total_start = time.time()

    for test_id, desc, func in all_tests:
        run_test(test_id, desc, func)

    total_elapsed = round(time.time() - total_start, 1)

    # ── Summary ──
    passed = sum(1 for r in results if r[2] == "PASS")
    failed = sum(1 for r in results if r[2] == "FAIL")
    errors = sum(1 for r in results if r[2] == "ERROR")
    total = len(results)

    log("")
    log("")
    log("=" * 70)
    log("  TEST SUMMARY")
    log("=" * 70)
    log("  Version:  {}".format(att.__version__))
    log("  Python:   {}".format(sys.version.split()[0]))
    log("  Date:     {}".format(datetime.now().isoformat()))
    log("  Duration: {}s".format(total_elapsed))
    log("")
    log(
        "  Total: {}  |  PASS: {}  |  FAIL: {}  |  ERROR: {}".format(
            total, passed, failed, errors
        )
    )
    log("")

    # Per-test summary table
    log("  {:<4s}  {:<6s}  {:<6s}  {}".format("ID", "STATUS", "TIME", "DESCRIPTION"))
    log("  " + "-" * 66)
    for tid, desc, status, dur, err in results:
        marker = "  "
        if status == "FAIL":
            marker = "X "
        elif status == "ERROR":
            marker = "! "
        line = "  {:02d}    {:<6s}  {:<6.2f}  {}".format(tid, status, dur, desc)
        if err:
            line += "  -> {}".format(err)
        log(marker + line)

    log("")
    log("=" * 70)

    # ── Save to TXT ──
    output_path = os.path.join(os.path.dirname(__file__), "test_results.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output.getvalue())

    print("")
    print("  Results saved to: {}".format(output_path))
    print("  Share this file for debugging.")
    print("")

    sys.exit(1 if (failed + errors) > 0 else 0)
