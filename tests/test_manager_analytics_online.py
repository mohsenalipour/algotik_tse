"""Bounded integration checks for the manager analytics public APIs."""

import pandas as pd
import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


@pytest.fixture(scope="module")
def live_market():
    frame = att.get_live_market()
    assert not frame.empty
    return frame


@pytest.fixture(scope="module")
def benchmark_history():
    frame = att.get_history(
        "شاخص کل",
        start="1405-05-01",
        output_type="full",
        date_format="gregorian",
        progress=False,
        ascending=True,
    )
    assert not frame.empty
    return frame


def test_compare_symbols_fetches_real_tsetmc_history():
    result = att.compare_symbols(
        ["فولاد"],
        start="1405-05-01",
        include_client_type=False,
        min_observations=5,
        progress=False,
    )
    assert list(result["Symbol"]) == ["فولاد"]
    assert result.loc[0, "Observations"] >= 5
    assert result.loc[0, "ValueUnit"] == "rial"


def test_live_liquidity_and_market_map_contracts(live_market):
    liquidity = att.get_liquidity_metrics(
        symbols=None,
        include_live=True,
        progress=False,
        live_data=live_market,
    )
    market_map = att.get_market_map(top=5, data=live_market)
    assert not liquidity.empty
    assert {"CurrentTurnover", "SpreadBps", "L5DepthValue"} <= set(liquidity)
    assert 0 < len(market_map) <= 5
    assert market_map["DisplayedWeightPct"].sum() == pytest.approx(100)


def test_regime_uses_real_snapshot_and_benchmark(live_market, benchmark_history):
    activity = pd.DataFrame({"Value": [live_market["Value"].sum()]})
    result = att.get_market_regime(
        progress=False,
        live_data=live_market,
        benchmark_history=benchmark_history,
        activity_history=activity,
    )
    assert len(result) == 1
    assert result.loc[0, "Regime"] in {"risk_on", "neutral", "risk_off"}
    assert result.loc[0, "AvailableComponents"] >= 3
    assert 0 < result.loc[0, "Confidence"] <= 1
