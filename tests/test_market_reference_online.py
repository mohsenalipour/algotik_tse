import pandas as pd
import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


def test_public_market_reference_endpoints_have_live_rows():
    calendar = att.get_trading_calendar(market="tse", limit=2)
    values = att.get_market_value_history(market="tse", limit=2)
    assert len(calendar) == 2
    assert len(values) == 2
    assert calendar["IsTradingDay"].all()
    assert pd.to_numeric(values["MarketValue"], errors="coerce").gt(0).all()


def test_index_impact_and_bulk_daily_contracts_are_live():
    calendar = att.get_trading_calendar(market="tse", limit=1)
    trade_date = calendar.iloc[-1]["GregorianDate"]
    impact = att.get_index_impact(trade_date, market="tse", top=3)
    daily = att.get_market_trades(trade_date, market="tse", progress=False)
    assert 0 < len(impact) <= 3
    assert not daily.empty
    assert daily.attrs["transaction_level"] is False
    assert {"InsCode", "ISIN", "TradeCount", "Volume", "Value"}.issubset(daily)


def test_instrument_master_public_table_is_parseable():
    frame = att.get_instrument_master(asset_type="fund", progress=False)
    assert not frame.empty
    assert frame["InsCode"].notna().all()
    assert frame["Symbol"].notna().all()
    assert frame["AssetType"].eq("fund").all()
