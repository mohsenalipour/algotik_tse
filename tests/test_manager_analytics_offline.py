import sys
import types

import numpy as np
import pandas as pd
import pytest

from algotik_tse import InvalidParameterError
from algotik_tse.core import manager_analytics as ma


def price_history(symbol="الف", multiplier=1.0, periods=30):
    dates = pd.date_range("2026-07-01", periods=periods, freq="D")
    close = np.linspace(100, 130, periods) * multiplier
    return pd.DataFrame(
        {
            "Close": close,
            "Open": close - 1,
            "High": close + 2,
            "Low": close - 2,
            "Volume": np.linspace(1_000, 2_000, periods),
            "Value": close * np.linspace(1_000, 2_000, periods),
            "No.": np.linspace(10, 20, periods),
            "Ticker": symbol,
        },
        index=dates,
    )


def client_history(periods=30):
    dates = pd.date_range("2026-07-01", periods=periods, freq="D")
    return pd.DataFrame(
        {
            "Val_buy_retail": np.full(periods, 120_000),
            "Val_sell_retail": np.full(periods, 100_000),
            "Power_retail": np.full(periods, 1.2),
        },
        index=dates,
    )


def live_market():
    as_of = pd.Timestamp("2026-08-01 12:00", tz="Asia/Tehran")
    rows = []
    for index, (symbol, sector, last, flow) in enumerate(
        [
            ("الف", "10", 110, 200_000),
            ("ب", "10", 105, 100_000),
            ("ج", "20", 95, -20_000),
        ]
    ):
        row = {
            "InsCode": str(index + 1),
            "Symbol": symbol,
            "SectorCode": sector,
            "Flow": 1,
            "InstrumentType": 300,
            "PreviousClose": 100,
            "Close": last,
            "Last": last,
            "ChangePct": (last / 100 - 1) * 100,
            "Volume": 10_000 * (index + 1),
            "Value": 1_000_000_000 * (index + 1),
            "MarketCap": 10_000_000_000 * (index + 1),
            "SharesOutstanding": 100_000_000,
            "Turnover": 0.001 * (index + 1),
            "VolumeToBaseVolume": 1.0 + index,
            "SpreadBps": 20.0 + index,
            "L1Imbalance": 0.1 * (index + 1),
            "L5Imbalance": 0.05 * (index + 1),
            "EstimatedNetIndividualFlow": flow,
            "IndividualPower": 1.1 + index * 0.1,
            "client_snapshot_consistent": True,
            "EstimatedBuyQueueValue": 300_000_000 * (index + 1),
            "EstimatedSellQueueValue": 50_000_000 * (index + 1),
            "QueueIsFresh": True,
            "as_of": as_of,
            "trade_date": as_of.date(),
            "is_realtime_fresh": True,
            "is_stale": False,
            "is_partial": False,
        }
        for level in range(1, 6):
            row.update(
                {
                    f"BidPrice{level}": last - level,
                    f"BidVolume{level}": 1_000 * level,
                    f"AskPrice{level}": last + level,
                    f"AskVolume{level}": 900 * level,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def activity_history():
    return pd.DataFrame(
        {
            "GregorianDate": pd.date_range("2026-07-10", periods=20, freq="D"),
            "Value": np.linspace(2_000_000_000, 4_000_000_000, 20),
        }
    )


def test_compare_symbols_returns_explainable_metrics_without_mutating_inputs():
    histories = {"الف": price_history("الف"), "ب": price_history("ب", 1.02)}
    clients = {"الف": client_history(), "ب": client_history()}
    before = histories["الف"].copy(deep=True)
    result = ma.compare_symbols(
        ["الف", "ب"],
        benchmark="الف",
        min_observations=10,
        progress=False,
        history_data=histories,
        client_data=clients,
    )
    assert list(result["Symbol"]) == ["الف", "ب"]
    assert result.loc[1, "Beta"] == pytest.approx(1.0)
    assert result.loc[0, "NetIndividualFlow"] == 600_000
    assert result.loc[0, "AverageIndividualPower"] == pytest.approx(1.2)
    assert result.loc[0, "ValueUnit"] == "rial"
    assert result.attrs["alignment"] == "inner"
    assert result.attrs["is_partial"] is False
    pd.testing.assert_frame_equal(histories["الف"], before)


def test_compare_symbols_inner_alignment_and_insufficient_quality():
    first = price_history(periods=5)
    second = price_history(periods=5)
    second.index = pd.date_range("2026-07-03", periods=5, freq="D")
    result = ma.compare_symbols(
        ["الف", "ب"],
        align="inner",
        min_observations=4,
        include_client_type=False,
        progress=False,
        history_data={"الف": first, "ب": second},
    )
    assert result.attrs["common_observations"] == 3
    assert result["QualityFlags"].str.contains("insufficient_observations").all()


def test_compare_symbols_missing_history_and_strict_mode():
    result = ma.compare_symbols(
        ["الف", "مفقود"],
        include_client_type=False,
        progress=False,
        history_data={"الف": price_history()},
    )
    assert result.attrs["missing_symbols"] == ("مفقود",)
    assert result.attrs["is_partial"] is True
    assert "history_unavailable" in result.loc[1, "QualityFlags"]
    with pytest.raises(ma.DataParsingError):
        ma.compare_symbols(["مفقود"], progress=False, history_data={}, strict=True)


@pytest.mark.parametrize("align", ["bad", "INNER "])
def test_compare_symbols_alignment_validation(align):
    if align.strip().lower() == "inner":
        assert not ma.compare_symbols(
            ["الف"],
            align=align,
            include_client_type=False,
            progress=False,
            history_data={"الف": price_history()},
        ).empty
    else:
        with pytest.raises(InvalidParameterError):
            ma.compare_symbols(["الف"], align=align, history_data={})


def test_liquidity_metrics_historical_and_live_values():
    result = ma.get_liquidity_metrics(
        ["الف"],
        window=20,
        progress=False,
        history_data={"الف": price_history()},
        live_data=live_market(),
    )
    row = result.iloc[0]
    assert row["Observations"] == 20
    assert row["TradingDays"] == 20
    assert row["ZeroTradeRatio"] == 0
    assert row["Amihud1B"] > 0
    assert row["SpreadBps"] == 20
    assert row["L5DepthValue"] > 0
    assert row["SharesOutstandingSource"] == "current_live_snapshot"
    assert result.attrs["value_unit"] == "rial"


def test_liquidity_metrics_live_only_universe_is_explicitly_partial():
    result = ma.get_liquidity_metrics(
        symbols=None, live_data=live_market(), progress=False
    )
    assert len(result) == 3
    assert result["Observations"].eq(0).all()
    assert result["QualityFlags"].str.contains("history_unavailable").all()


def test_liquidity_metrics_rejects_incompatible_inputs():
    with pytest.raises(InvalidParameterError):
        ma.get_liquidity_metrics([], progress=False)
    with pytest.raises(InvalidParameterError):
        ma.get_liquidity_metrics(
            ["الف"], include_live=False, live_data=live_market(), progress=False
        )
    with pytest.raises(InvalidParameterError):
        ma.get_liquidity_metrics(["الف"], window=0, progress=False)


def test_market_regime_exposes_all_components_and_weights():
    result = ma.get_market_regime(
        benchmark="شاخص کل",
        lookback=20,
        liquidity_window=10,
        progress=False,
        benchmark_history=price_history("شاخص کل"),
        live_data=live_market(),
        activity_history=activity_history(),
    )
    row = result.iloc[0]
    assert row["Regime"] == "risk_on"
    assert row["AvailableComponents"] == 5
    assert row["MissingComponents"] == 0
    assert row["Confidence"] == pytest.approx(1.0)
    assert row["TrendScore"] > 0
    assert row["BreadthScore"] > 0
    assert row["FlowScore"] > 0
    assert row["LiquidityScore"] > 0
    assert row["QueueScore"] > 0
    assert result.attrs["method"] == "weighted_mean_of_available_components"


def test_market_regime_renormalizes_available_components():
    live = live_market().drop(
        columns=[
            "EstimatedNetIndividualFlow",
            "client_snapshot_consistent",
            "EstimatedBuyQueueValue",
            "EstimatedSellQueueValue",
            "QueueIsFresh",
        ]
    )
    result = ma.get_market_regime(
        progress=False,
        benchmark_history=price_history("شاخص کل"),
        live_data=live,
        activity_history=pd.DataFrame(),
    )
    row = result.iloc[0]
    assert row["AvailableComponents"] == 2
    assert row["MissingComponents"] == 3
    assert row["Confidence"] == pytest.approx(0.55)
    assert result.attrs["is_partial"] is True
    assert "missing_components" in row["QualityFlags"]


def test_market_regime_validation_is_fail_fast(monkeypatch):
    monkeypatch.setattr(ma, "_fetch_price_history", lambda *args: pytest.fail())
    with pytest.raises(InvalidParameterError):
        ma.get_market_regime(benchmark_history="bad")
    with pytest.raises(InvalidParameterError):
        ma.get_market_regime(weights={"mystery": 1})
    with pytest.raises(InvalidParameterError):
        ma.get_market_regime(weights={"trend": -1})


def test_market_map_symbol_and_sector_aggregations():
    live = live_market()
    symbol_map = ma.get_market_map(
        group_by="symbol", size="value", color="return", top=2, data=live
    )
    assert len(symbol_map) == 2
    assert symbol_map.iloc[0]["Label"] == "ج"
    assert symbol_map["DisplayedWeightPct"].sum() == pytest.approx(100)
    assert symbol_map.attrs["is_partial"] is True

    sector_map = ma.get_market_map(
        group_by="sector",
        size="market_cap",
        color="net_individual_flow",
        top=None,
        data=live,
    )
    sector10 = sector_map.loc[sector_map["GroupKey"] == "10"].iloc[0]
    assert sector10["InstrumentCount"] == 2
    assert sector10["EstimatedNetIndividualFlow"] == 300_000
    assert sector10["ColorValue"] == 300_000
    assert sector_map.attrs["is_partial"] is False


def test_market_map_filters_and_validates_schema():
    live = live_market()
    filtered = ma.get_market_map(flow=1, instrument_types=[300], data=live)
    assert len(filtered) == 3
    with pytest.raises(InvalidParameterError):
        ma.get_market_map(group_by="unknown", data=live)
    with pytest.raises(ma.DataParsingError):
        ma.get_market_map(data=pd.DataFrame({"Symbol": ["الف"]}))
    with pytest.raises(ma.DataParsingError):
        ma.get_market_map(data=live.drop(columns="Flow"), flow=1)


class FakeFigure:
    def __init__(self):
        self.layout = None
        self.written = None
        self.shown = False

    def update_layout(self, **kwargs):
        self.layout = kwargs

    def write_html(self, path, **kwargs):
        self.written = (path, kwargs)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("<html>market map</html>")

    def show(self):
        self.shown = True


def test_plot_market_map_uses_optional_plotly_and_writes_html(monkeypatch, tmp_path):
    figure = FakeFigure()
    package = types.ModuleType("plotly")
    package.__path__ = []
    express = types.ModuleType("plotly.express")
    express.treemap = lambda *args, **kwargs: figure
    monkeypatch.setitem(sys.modules, "plotly", package)
    monkeypatch.setitem(sys.modules, "plotly.express", express)
    map_data = ma.get_market_map(top=2, data=live_market())
    output = tmp_path / "map.html"
    returned = ma.plot_market_map(map_data, output_path=output, show=True)
    assert returned is figure
    assert output.read_text(encoding="utf-8") == "<html>market map</html>"
    assert figure.shown is True
    with pytest.raises(InvalidParameterError):
        ma.plot_market_map(map_data, output_path=tmp_path / "map.png")


def test_public_schema_constants_are_stable():
    assert len(ma.COMPARISON_COLUMNS) == 31
    assert len(ma.LIQUIDITY_COLUMNS) == 32
    assert len(ma.REGIME_COLUMNS) == 30
    assert len(ma.MARKET_MAP_COLUMNS) == 23
