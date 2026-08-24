import importlib
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import market_data
from algotik_tse.exceptions import AmbiguousSymbolError, ConnectionError

stock_module = importlib.import_module("algotik_tse.core.stock")
FIXTURE = Path(__file__).parent / "fixtures" / "market_watch_init.txt"
FETCHED_AT = pd.Timestamp("2026-08-23 10:16:00", tz="Asia/Tehran")


@pytest.fixture()
def parsed_snapshot():
    return market_data._parse_market_watch_response(
        FIXTURE.read_text(encoding="utf-8"), fetched_at=FETCHED_AT
    )


def _current(snapshot):
    result = snapshot.copy()
    today = stock_module._tehran_today()
    result.update(
        {
            "trade_date": today,
            "exchange_time": pd.Timestamp.now(tz="Asia/Tehran"),
            "fetched_at": pd.Timestamp.now(tz="Asia/Tehran"),
            "snapshot_age_seconds": 0.0,
            "is_today_trade_date": True,
            "is_history_eligible": True,
            "is_realtime_fresh": True,
            "is_previous_trade_date": False,
            "is_stale": False,
            "is_partial": pd.NA,
        }
    )
    return result


def _client_frame():
    return pd.DataFrame(
        [
            {
                "InsCode": "111",
                "Buy_I_Count": 2,
                "Buy_N_Count": 1,
                "Buy_I_Volume": 600,
                "Buy_N_Volume": 400,
                "Sell_I_Count": 4,
                "Sell_N_Count": 1,
                "Sell_I_Volume": 800,
                "Sell_N_Volume": 200,
                "Net_I_Volume": -200,
                "Net_N_Volume": 200,
            },
            {
                "InsCode": "222",
                "Buy_I_Count": 0,
                "Buy_N_Count": 0,
                "Buy_I_Volume": 0,
                "Buy_N_Volume": 0,
                "Sell_I_Count": 0,
                "Sell_N_Count": 0,
                "Sell_I_Volume": 0,
                "Sell_N_Volume": 0,
                "Net_I_Volume": 0,
                "Net_N_Volume": 0,
            },
        ]
    )


class _Response:
    def __init__(self, text="", json_data=None):
        self.text = text
        self.content = text.encode("utf-8")
        self._json_data = json_data

    def json(self):
        return self._json_data


PRICE_CSV = (
    "<TICKER>,<DTYYYYMMDD>,<FIRST>,<HIGH>,<LOW>,<CLOSE>,<VALUE>,"
    "<VOL>,<OPENINT>,<PER>,<OPEN>,<LAST>\n"
    "تست,20260822,100,110,90,105,10000,100,5,D,100,104\n"
)
RI_HISTORY = "20260822,1,1,1,1,100,100,100,100,10000,10000,10000,10000"


def test_market_watch_header_and_wire_contract(parsed_snapshot):
    row = parsed_snapshot["stocks"].set_index("InsCode").loc["111"]
    assert list(parsed_snapshot["stocks"].columns) == market_data.STOCK_COLUMNS
    assert list(parsed_snapshot["stocks"].columns[:25]) == [
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
    ]
    assert parsed_snapshot["trade_date"] == pd.Timestamp("2026-08-23").date()
    assert parsed_snapshot["exchange_time"].tz is not None
    assert parsed_snapshot["fetched_at"] == FETCHED_AT
    assert parsed_snapshot["is_stale"] is False
    assert parsed_snapshot["is_today_trade_date"] is True
    assert parsed_snapshot["is_history_eligible"] is True
    assert parsed_snapshot["is_realtime_fresh"] is True
    assert pd.isna(parsed_snapshot["is_partial"])
    assert row["FirstPrice"] == row["Open"] == row["LegacyYesterday"] == 100
    assert row["Yesterday"] == 100
    assert row["PreviousClose"] == row["PriceYesterday"] == 105
    assert row["BaseVolume"] == 1_000_000
    assert row["ActualBaseVolume"] == 500
    assert row["VisitCount"] == 42
    assert row["SharesOutstanding"] == row["LegacyBaseVolume"] == 1_000_000
    assert row["Change"] == 10
    assert row["ChangePct"] == pytest.approx(10.0)
    assert row["PreviousCloseChange"] == 5
    assert row["PreviousCloseChangePct"] == pytest.approx(4.76)
    assert parsed_snapshot["migration"]["schema_version"] == "1.1"


def test_market_watch_preserves_contract_without_deprecation_warning(monkeypatch):
    raw = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(market_data, "safe_get", lambda *_: _Response(raw))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = market_data.market_watch()
    first["migration"]["schema_version"] = "mutated"
    with warnings.catch_warnings(record=True) as caught_again:
        warnings.simplefilter("always")
        result = market_data.market_watch()
    with warnings.catch_warnings(record=True) as caught_alias:
        warnings.simplefilter("always")
        alias_result = att.get_market_snapshot()
    assert not caught and not caught_again and not caught_alias
    assert "LegacyYesterday" in result["stocks"].columns
    assert result["migration"]["schema_version"] == "1.1"
    assert alias_result["stocks"].loc[0, "Yesterday"] == 100
    assert alias_result["stocks"].loc[0, "BaseVolume"] == 1_000_000


def test_stale_header_is_not_current(parsed_snapshot):
    stale = market_data._parse_market_watch_response(
        FIXTURE.read_text(encoding="utf-8"),
        fetched_at=pd.Timestamp("2026-08-24 10:00", tz="Asia/Tehran"),
    )
    assert stale["trade_date"] == pd.Timestamp("2026-08-23").date()
    assert stale["is_stale"] is True
    assert pd.isna(stale["is_partial"])
    assert stale["is_previous_trade_date"] is True
    assert market_data._is_current_snapshot(stale) is False
    final = market_data._snapshot_metadata(
        "05/06/01 12:30:00", market_state="F", fetched_at=FETCHED_AT
    )
    assert final["is_stale"] is True
    assert final["is_history_eligible"] is True
    assert final["is_realtime_fresh"] is False
    assert pd.isna(final["is_partial"])
    aged = market_data._snapshot_metadata(
        "05/06/01 10:15:30",
        market_state="unknown",
        fetched_at=pd.Timestamp("2026-08-23 10:20:00", tz="Asia/Tehran"),
    )
    assert aged["is_previous_trade_date"] is False
    assert aged["snapshot_age_seconds"] == 270
    assert aged["is_stale"] is True
    assert aged["is_history_eligible"] is True
    aged_snapshot = dict(parsed_snapshot, **aged)
    assert market_data._is_current_snapshot(aged_snapshot, now=FETCHED_AT) is True


def test_realtime_freshness_has_configurable_symmetric_clock_skew():
    fetched = pd.Timestamp("2026-08-23 10:00:00", tz="Asia/Tehran")
    within_skew = market_data._snapshot_metadata(
        "05/06/01 10:00:04",
        fetched_at=fetched,
        freshness_threshold_seconds=120,
        clock_skew_tolerance_seconds=5,
    )
    beyond_skew = market_data._snapshot_metadata(
        "05/06/01 10:00:06",
        fetched_at=fetched,
        freshness_threshold_seconds=120,
        clock_skew_tolerance_seconds=5,
    )
    upper_with_skew = market_data._snapshot_metadata(
        "05/06/01 09:57:56",
        fetched_at=fetched,
        freshness_threshold_seconds=120,
        clock_skew_tolerance_seconds=5,
    )
    assert within_skew["snapshot_age_seconds"] == -4
    assert within_skew["is_realtime_fresh"] is True
    assert beyond_skew["is_realtime_fresh"] is False
    assert upper_with_skew["snapshot_age_seconds"] == 124
    assert upper_with_skew["is_realtime_fresh"] is True


def test_order_book_part_three_is_parsed_as_five_levels(parsed_snapshot):
    book = parsed_snapshot["order_book"]
    first = book[(book["InsCode"] == "111") & (book["Level"] == 1)].iloc[0]
    assert list(book.columns) == market_data.ORDER_COLUMNS
    assert len(book[book["InsCode"] == "111"]) == 5
    assert first.to_dict() == {
        "InsCode": "111",
        "Level": 1,
        "AskOrderCount": 2,
        "BidOrderCount": 3,
        "BidPrice": 109,
        "AskPrice": 111,
        "BidVolume": 600,
        "AskVolume": 400,
    }


def test_live_metrics_safe_canonical_aliases_and_no_input_mutation(parsed_snapshot):
    stocks = parsed_snapshot["stocks"].copy(deep=True)
    client = _client_frame()
    orders = parsed_snapshot["order_book"].copy(deep=True)
    stocks_before, client_before, orders_before = (
        stocks.copy(deep=True),
        client.copy(deep=True),
        orders.copy(deep=True),
    )
    live = market_data._enrich_live_market(
        stocks,
        client,
        orders,
        as_of=FETCHED_AT,
        snapshot_metadata=parsed_snapshot,
    ).set_index("InsCode")
    pd.testing.assert_frame_equal(stocks, stocks_before)
    pd.testing.assert_frame_equal(client, client_before)
    pd.testing.assert_frame_equal(orders, orders_before)
    test = live.loc["111"]
    assert test["Yesterday"] == test["PreviousClose"] == 105
    assert test["BaseVolume"] == test["ActualBaseVolume"] == 500
    assert test["Change"] == test["PreviousCloseChange"] == 5
    assert test["VWAP"] == 110
    assert test["IndividualPower"] == test["Power_retail"] == pytest.approx(1.5)
    assert test["LegalPower"] == test["Power_institutional"]
    assert test["EstimatedNetIndividualFlow"] == -22_000
    assert test["Spread"] == 2
    assert test["L1Imbalance"] == pytest.approx(0.2)
    assert test["L5Imbalance"] == pytest.approx(475 / 2025)
    assert test["MarketCap"] == 112_000_000
    assert test["VolumeToBaseVolume"] == pytest.approx(2.0)
    assert test["QueueValueSource"] == "market_watch_5_level_estimate"
    assert test["QueueIsFresh"]
    assert test["client_value_source"] == "estimated_from_market_vwap"
    assert test["client_values_estimated"]
    assert test["power_method"] == "volume_per_participant_ratio"
    assert test["client_snapshot_consistent"]
    assert test["client_buy_volume_difference"] == 0
    assert test["client_sell_volume_ratio"] == 1
    zero = live.loc["222"]
    for column in [
        "VWAP",
        "IndividualPower",
        "LegalPower",
        "Spread",
        "SpreadBps",
        "L1Imbalance",
        "VolumeToBaseVolume",
    ]:
        assert np.isnan(zero[column]), column
    stale_metadata = dict(
        parsed_snapshot,
        is_stale=True,
        is_realtime_fresh=False,
        snapshot_age_seconds=300,
    )
    stale_live = market_data._enrich_live_market(
        stocks,
        client,
        orders,
        as_of=FETCHED_AT,
        snapshot_metadata=stale_metadata,
    ).set_index("InsCode")
    assert not stale_live.loc["111", "QueueIsFresh"]
    assert np.isnan(stale_live.loc["111", "EstimatedBuyQueueVolume"])


def test_list_filters_empty_schema_and_ambiguity(monkeypatch, parsed_snapshot):
    assert att.AmbiguousSymbolError is AmbiguousSymbolError
    snapshot = _current(parsed_snapshot)
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(market_data, "market_client_type", _client_frame)
    live = market_data.get_live_market(["تست", "222"])
    book = market_data.get_order_book(["111", "صفر"])
    assert live["InsCode"].tolist() == ["111", "222"]
    assert set(book["InsCode"]) == {"111", "222"}
    ambiguous = snapshot.copy()
    ambiguous["stocks"] = snapshot["stocks"].copy()
    ambiguous["stocks"].loc[1, "Symbol"] = "تست"
    monkeypatch.setattr(market_data, "market_watch", lambda: ambiguous)
    with pytest.raises(AmbiguousSymbolError):
        market_data.get_live_symbol("تست")
    monkeypatch.setattr(
        market_data,
        "market_watch",
        lambda: market_data._parse_market_watch_response(
            "x@05/06/01 10:00:00,P,1@@@x", fetched_at=FETCHED_AT
        ),
    )
    empty_live = market_data.get_live_market()
    empty_book = market_data.get_order_book()
    assert list(empty_book.columns) == market_data.PUBLIC_ORDER_COLUMNS
    for column in [
        "InsCode",
        "IndividualPower",
        "BidPrice1",
        "trade_date",
        "is_stale",
        "QueueValueSource",
    ]:
        assert column in empty_live.columns


def test_stale_snapshot_never_stamped_as_today(monkeypatch, parsed_snapshot):
    stale = parsed_snapshot.copy()
    stale.update(
        {
            "is_stale": True,
            "is_partial": False,
            "is_today_trade_date": False,
            "is_history_eligible": False,
            "is_realtime_fresh": False,
            "is_previous_trade_date": True,
            "trade_date": pd.Timestamp("2026-08-22").date(),
        }
    )
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(PRICE_CSV))
    monkeypatch.setattr(market_data, "market_watch", lambda: stale)
    with pytest.warns(RuntimeWarning, match="stale"):
        result = stock_module.stock(
            "تست", include_today=True, date_format="gregorian", progress=False
        )
    assert result.index[-1].date() == pd.Timestamp("2026-08-22").date()
    assert result.attrs["include_today_appended"] == []


def test_same_day_aged_snapshot_still_augments_history(monkeypatch, parsed_snapshot):
    aged = _current(parsed_snapshot)
    aged.update(
        {
            "snapshot_age_seconds": 3_600.0,
            "is_realtime_fresh": False,
            "is_stale": True,
        }
    )
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(PRICE_CSV))
    monkeypatch.setattr(market_data, "market_watch", lambda: aged)
    result = stock_module.stock(
        "تست", include_today=True, date_format="gregorian", progress=False
    )
    assert result.index[-1].date() == stock_module._tehran_today()
    assert result.attrs["include_today_appended"] == ["تست"]
    assert result.attrs["live_is_realtime_fresh"] is False


def test_no_trade_instrument_and_final_filter_do_not_claim_append(
    monkeypatch, parsed_snapshot
):
    snapshot = _current(parsed_snapshot)
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(PRICE_CSV))
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "222")
    with pytest.warns(RuntimeWarning, match="canonical InsCode"):
        stopped = stock_module.stock(
            "صفر", include_today=True, date_format="gregorian", progress=False
        )
    assert stopped.index[-1].date() == pd.Timestamp("2026-08-22").date()
    assert stopped.attrs["include_today_appended"] == []

    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    filtered = stock_module.stock(
        "تست",
        include_today=True,
        end="2026-08-22",
        date_format="gregorian",
        progress=False,
    )
    assert filtered.attrs["include_today_appended"] == []


def test_live_failure_falls_back_to_successful_history(monkeypatch):
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(PRICE_CSV))

    def fail():
        raise ConnectionError("x")

    monkeypatch.setattr(market_data, "market_watch", fail)
    with pytest.warns(RuntimeWarning, match="unavailable"):
        result = stock_module.stock(
            "تست", include_today=True, date_format="gregorian", progress=False
        )
    assert result is not None and len(result) == 1
    assert "unavailable" in result.attrs["include_today_warning"]


def test_live_schema_failure_falls_back_without_hiding_ambiguity(
    monkeypatch, parsed_snapshot
):
    malformed = _current(parsed_snapshot)
    malformed["stocks"] = malformed["stocks"].drop(columns=["PreviousClose"])
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(PRICE_CSV))
    monkeypatch.setattr(market_data, "market_watch", lambda: malformed)
    with pytest.warns(RuntimeWarning, match="invalid live schema"):
        result = stock_module.stock(
            "تست", include_today=True, date_format="gregorian", progress=False
        )
    assert result is not None and len(result) == 1
    ambiguous = _current(parsed_snapshot)
    duplicate = ambiguous["stocks"].loc[ambiguous["stocks"]["InsCode"] == "111"]
    ambiguous["stocks"] = pd.concat([ambiguous["stocks"], duplicate], ignore_index=True)
    monkeypatch.setattr(market_data, "market_watch", lambda: ambiguous)
    with pytest.raises(AmbiguousSymbolError):
        stock_module.stock("تست", include_today=True, progress=False)


def test_client_raw_stale_fallback_builds_safe_provenance_defaults(
    monkeypatch, parsed_snapshot
):
    stale = dict(
        parsed_snapshot,
        trade_date=pd.Timestamp("2026-08-22").date(),
        is_today_trade_date=False,
        is_history_eligible=False,
        is_realtime_fresh=False,
        is_stale=True,
        is_previous_trade_date=True,
        snapshot_age_seconds=86_400,
    )
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(RI_HISTORY))
    monkeypatch.setattr(market_data, "market_watch", lambda: stale)
    with pytest.warns(RuntimeWarning, match="stale"):
        result = stock_module.stock_RI(
            "تست", include_today=True, raw=True, progress=False
        )
    assert len(result) == 1
    assert result.iloc[0]["<VALUE_SOURCE>"] == "tsetmc_actual"
    assert not bool(result.iloc[0]["<IS_ESTIMATED>"])


def test_price_multi_symbol_fetches_market_once_and_never_client(
    monkeypatch, parsed_snapshot
):
    snapshot = _current(parsed_snapshot)
    snapshot["stocks"] = snapshot["stocks"].copy()
    row = snapshot["stocks"].index[snapshot["stocks"]["InsCode"] == "222"][0]
    snapshot["stocks"].loc[row, ["TradeCount", "Volume", "Value"]] = [1, 10, 2000]
    calls = {"market": 0, "client": 0}
    ids = {"تست": "111", "صفر": "222"}
    monkeypatch.setattr(
        stock_module, "search_stock", lambda search_txt: ids[search_txt]
    )
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(PRICE_CSV))

    def market_once():
        calls["market"] += 1
        return snapshot

    def forbidden_client():
        calls["client"] += 1
        raise AssertionError("price history must not fetch client type")

    monkeypatch.setattr(market_data, "market_watch", market_once)
    monkeypatch.setattr(market_data, "market_client_type", forbidden_client)
    result = stock_module.stock(
        ["تست", "صفر"],
        include_today=True,
        date_format="gregorian",
        progress=False,
        dropna=False,
    )
    assert result is not None
    assert calls == {"market": 1, "client": 0}


def test_client_multi_fetches_each_bulk_feed_once(monkeypatch, parsed_snapshot):
    snapshot = _current(parsed_snapshot)
    snapshot["stocks"] = snapshot["stocks"].copy()
    row = snapshot["stocks"].index[snapshot["stocks"]["InsCode"] == "222"][0]
    snapshot["stocks"].loc[row, ["TradeCount", "Volume", "Value"]] = [1, 10, 2000]
    calls = {"market": 0, "client": 0}
    ids = {"تست": "111", "صفر": "222"}
    monkeypatch.setattr(
        stock_module, "search_stock", lambda search_txt: ids[search_txt]
    )
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(RI_HISTORY))

    def market_once():
        calls["market"] += 1
        return snapshot

    def client_once():
        calls["client"] += 1
        client = _client_frame()
        row = client["InsCode"].eq("222")
        client.loc[
            row,
            [
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
            ],
        ] = [1, 1, 6, 4, 1, 1, 8, 2, -2, 2]
        return client

    monkeypatch.setattr(market_data, "market_watch", market_once)
    monkeypatch.setattr(market_data, "market_client_type", client_once)
    result = stock_module.stock_RI(
        ["تست", "صفر"],
        include_today=True,
        date_format="gregorian",
        progress=False,
    )
    assert result is not None
    assert calls == {"market": 1, "client": 1}
    assert result.index[-1].date() == stock_module._tehran_today()


def test_client_raw_contract_keeps_estimates_out_of_actual_values(
    monkeypatch, parsed_snapshot
):
    snapshot = _current(parsed_snapshot)
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(RI_HISTORY))
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(market_data, "market_client_type", _client_frame)
    result = stock_module.stock_RI("تست", include_today=True, raw=True, progress=False)
    today = result.iloc[-1]
    assert pd.isna(today["<VAL_BUY_RETAIL>"])
    assert today["<EST_VAL_BUY_RETAIL>"] == 66_000
    assert today["<VALUE_SOURCE>"] == "estimated_from_market_vwap"
    assert bool(today["<IS_ESTIMATED>"])
    assert str(result["<VAL_BUY_RETAIL>"].dtype) == "Int64"
    assert str(result["<IS_PARTIAL>"].dtype) == "boolean"
    assert not bool(result.iloc[0]["<IS_PARTIAL>"])
    assert pd.isna(today["<IS_PARTIAL>"])
    assert bool(today["<CLIENT_SNAPSHOT_CONSISTENT>"])


def test_client_type_default_and_opt_in_column_contracts(monkeypatch, parsed_snapshot):
    snapshot = _current(parsed_snapshot)
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(RI_HISTORY))
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(market_data, "market_client_type", _client_frame)
    standard_columns = [
        "N_buy_retail",
        "N_buy_institutional",
        "N_sell_retail",
        "N_sell_institutional",
        "Vol_buy_retail",
        "Vol_buy_institutional",
        "Vol_sell_retail",
        "Vol_sell_institutional",
        "Val_buy_retail",
        "Val_buy_institutional",
        "Val_sell_retail",
        "Val_sell_institutional",
    ]
    default_standard = stock_module.stock_RI(
        "تست", progress=False, date_format="gregorian"
    )
    opt_in_standard = stock_module.stock_RI(
        "تست", include_today=True, progress=False, date_format="gregorian"
    )
    default_full = stock_module.stock_RI(
        "تست", output_type="full", progress=False, date_format="gregorian"
    )
    opt_in_full = stock_module.stock_RI(
        "تست",
        include_today=True,
        output_type="full",
        progress=False,
        date_format="gregorian",
    )
    default_raw = stock_module.stock_RI("تست", raw=True, progress=False)
    assert list(default_standard.columns) == standard_columns
    assert list(opt_in_standard.columns) == standard_columns
    assert "Value_source" not in default_full.columns
    assert "Estimated_val_buy_retail" not in default_full.columns
    assert str(opt_in_full["Estimated_val_buy_retail"].dtype) == "Float64"
    assert str(opt_in_full["Is_estimated"].dtype) == "boolean"
    assert str(opt_in_full["Is_partial"].dtype) == "boolean"
    assert not bool(opt_in_full.iloc[0]["Is_partial"])
    assert pd.isna(opt_in_full.iloc[-1]["Is_partial"])
    assert "<VALUE_SOURCE>" not in default_raw.columns
    assert str(opt_in_standard["N_buy_retail"].dtype) == "Int64"
    assert str(opt_in_standard["Val_buy_retail"].dtype) == "Int64"


def test_full_client_type_zero_counts_preserve_default_and_opt_in_safety(
    monkeypatch, parsed_snapshot
):
    zero = "20260822,0,0,0,0,0,0,0,0,0,0,0,0"
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(zero))
    default = stock_module.stock_RI(
        "تست", output_type="full", date_format="gregorian", progress=False
    )
    monkeypatch.setattr(market_data, "market_watch", lambda: _current(parsed_snapshot))
    monkeypatch.setattr(market_data, "market_client_type", _client_frame)
    opt_in = stock_module.stock_RI(
        "تست",
        include_today=True,
        output_type="full",
        date_format="gregorian",
        progress=False,
    )
    for column in [
        "Per_capita_buy_retail",
        "Per_capita_sell_retail",
        "Power_retail",
        "Power_institutional",
    ]:
        assert default.iloc[0][column] == 0
        assert np.isnan(opt_in.iloc[0][column])
    numeric = opt_in.select_dtypes(include=[np.number]).to_numpy(
        dtype=float, na_value=np.nan
    )
    assert not np.isinf(numeric).any()


def test_include_today_auto_adjust_handles_corporate_action(
    monkeypatch, parsed_snapshot
):
    csv = (
        "<TICKER>,<DTYYYYMMDD>,<FIRST>,<HIGH>,<LOW>,<CLOSE>,<VALUE>,"
        "<VOL>,<OPENINT>,<PER>,<OPEN>,<LAST>\n"
        "تست,20260822,100,110,90,100,10000,100,5,D,100,100\n"
    )
    snapshot = _current(parsed_snapshot)
    snapshot["stocks"] = snapshot["stocks"].copy()
    row = snapshot["stocks"].index[snapshot["stocks"]["InsCode"] == "111"][0]
    columns = [
        "FirstPrice",
        "Open",
        "High",
        "Low",
        "Close",
        "Last",
        "PreviousClose",
        "Yesterday",
        "PriceYesterday",
    ]
    snapshot["stocks"].loc[row, columns] = [50, 50, 55, 48, 52, 53, 50, 50, 50]
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(csv))
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    result = stock_module.stock(
        "تست",
        include_today=True,
        auto_adjust=True,
        date_format="gregorian",
        progress=False,
    )
    assert result.iloc[0]["Close"] == 50
    assert result.iloc[-1]["Close"] == 53


@pytest.mark.parametrize("industry", [False, True])
def test_index_and_industry_include_today(monkeypatch, parsed_snapshot, industry):
    snapshot = _current(parsed_snapshot)
    inscode = "34408080767216529" if industry else "32097828799138957"
    suffix = "industry" if industry else "index"
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: inscode + suffix)
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    live_index = {
        "insCode": inscode,
        "xDrNivJIdx004": 120.0,
        "xPhNivJIdx004": 125.0,
        "xPbNivJIdx004": 95.0,
        "indexChange": 20.0,
        "dEven": int(stock_module._tehran_today().strftime("%Y%m%d")),
        "hEven": 101500,
    }

    def safe_get(url):
        if url == stock_module.settings.url_all_indices:
            return _Response(json_data={"indexB1": [live_index]})
        if industry:
            return _Response(
                json_data={
                    "indexB2": [
                        {
                            "dEven": 20260822,
                            "xNivInuClMresIbs": 100,
                            "xNivInuPhMresIbs": 110,
                            "xNivInuPbMresIbs": 90,
                        }
                    ]
                }
            )
        return _Response("20260822,110,90,100,100,0,100")

    monkeypatch.setattr(stock_module, "safe_get", safe_get)
    result = stock_module.stock(
        "شاخص", include_today=True, date_format="gregorian", progress=False
    )
    assert result.index[-1].date() == stock_module._tehran_today()
    assert result.iloc[-1]["Close"] == 120
    if not industry:
        raw = stock_module.stock("شاخص", include_today=True, raw=True, progress=False)
        assert pd.isna(raw.iloc[-1]["<FIRST>"])
        assert pd.isna(raw.iloc[-1]["<OPEN>"])
        assert raw.iloc[-1]["<PREVIOUS_CLOSE>"] == 100


def test_stale_index_snapshot_does_not_fetch_live_index_feed(
    monkeypatch, parsed_snapshot
):
    inscode = "32097828799138957"
    stale = dict(
        parsed_snapshot,
        trade_date=pd.Timestamp("2026-08-22").date(),
        is_today_trade_date=False,
        is_history_eligible=False,
        is_realtime_fresh=False,
        is_previous_trade_date=True,
        is_stale=True,
        snapshot_age_seconds=86_400,
    )
    calls = {"live_index": 0}
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: inscode + "index")
    monkeypatch.setattr(market_data, "market_watch", lambda: stale)

    def safe_get(url):
        if url == stock_module.settings.url_all_indices:
            calls["live_index"] += 1
        return _Response("20260822,110,90,100,100,0,100")

    monkeypatch.setattr(stock_module, "safe_get", safe_get)
    with pytest.warns(RuntimeWarning, match="stale"):
        result = stock_module.stock(
            "شاخص", include_today=True, date_format="gregorian", progress=False
        )
    assert result is not None
    assert calls["live_index"] == 0


def test_invalid_live_index_ohlc_falls_back_to_history(monkeypatch, parsed_snapshot):
    inscode = "32097828799138957"
    snapshot = _current(parsed_snapshot)
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: inscode + "index")
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)

    def safe_get(url):
        if url == stock_module.settings.url_all_indices:
            return _Response(
                json_data={
                    "indexB1": [
                        {
                            "insCode": inscode,
                            "xDrNivJIdx004": 120,
                            "xPhNivJIdx004": np.nan,
                            "xPbNivJIdx004": 95,
                            "indexChange": 20,
                            "dEven": int(
                                stock_module._tehran_today().strftime("%Y%m%d")
                            ),
                            "hEven": 101500,
                        }
                    ]
                }
            )
        return _Response("20260822,110,90,100,100,0,100")

    monkeypatch.setattr(stock_module, "safe_get", safe_get)
    with pytest.warns(RuntimeWarning, match="invalid live index OHLC"):
        result = stock_module.stock(
            "شاخص", include_today=True, date_format="gregorian", progress=False
        )
    assert result.index[-1].date() == pd.Timestamp("2026-08-22").date()
    assert result.attrs["include_today_appended"] == []


def test_inconsistent_client_snapshot_is_audited_and_not_appended(
    monkeypatch, parsed_snapshot
):
    snapshot = _current(parsed_snapshot)
    inconsistent = _client_frame()
    inconsistent.loc[inconsistent["InsCode"].eq("111"), "Buy_I_Volume"] = 60
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(stock_module, "safe_get", lambda *_: _Response(RI_HISTORY))
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(market_data, "market_client_type", lambda: inconsistent)
    live = market_data._enrich_live_market(
        snapshot["stocks"],
        inconsistent,
        snapshot["order_book"],
        snapshot_metadata=snapshot,
    ).set_index("InsCode")
    assert not live.loc["111", "client_snapshot_consistent"]
    assert live.loc["111", "client_buy_volume_ratio"] == pytest.approx(0.46)
    assert live.loc["111", "client_value_source"] == "inconsistent"
    assert not live.loc["111", "client_values_estimated"]
    assert np.isnan(live.loc["111", "IndividualPower"])
    assert np.isnan(live.loc["111", "EstimatedIndividualBuyValue"])
    with pytest.warns(RuntimeWarning, match="inconsistent live client volumes"):
        result = stock_module.stock_RI(
            "تست", include_today=True, raw=True, progress=False
        )
    assert len(result) == 1
    assert result.attrs["include_today_appended"] == []


@pytest.mark.parametrize(
    ("client_total", "expected"),
    [(950, True), (1050, True), (949, False), (1051, False)],
)
def test_client_volume_consistency_tolerance_is_inclusive(client_total, expected):
    audit = market_data._client_volume_audit(
        pd.Series([client_total]),
        pd.Series([0]),
        pd.Series([client_total]),
        pd.Series([0]),
        pd.Series([1000]),
        tolerance=0.05,
    )
    assert bool(audit["client_snapshot_consistent"].iloc[0]) is expected


def test_overlap_today_coalesces_actual_ri_and_non_null_index_fields():
    today = pd.Timestamp(stock_module._tehran_today())
    historical_ri = pd.DataFrame(
        [
            {
                "<TICKER>": "تست",
                "<N_BUY_RETAIL>": 1,
                "<N_BUY_INSTITUTIONAL>": 2,
                "<N_SELL_RETAIL>": 3,
                "<N_SELL_INSTITUTIONAL>": 4,
                "<VOL_BUY_RETAIL>": 11,
                "<VOL_BUY_INSTITUTIONAL>": 12,
                "<VOL_SELL_RETAIL>": 13,
                "<VOL_SELL_INSTITUTIONAL>": 14,
                "<VAL_BUY_RETAIL>": 101,
                "<VAL_BUY_INSTITUTIONAL>": 102,
                "<VAL_SELL_RETAIL>": 103,
                "<VAL_SELL_INSTITUTIONAL>": 104,
                "<PER>": "D",
            }
        ],
        index=pd.DatetimeIndex([today], name="<DTYYYYMMDD>"),
    )
    live_ri = pd.DataFrame(
        [
            {
                "<TICKER>": "تست",
                "<N_BUY_RETAIL>": 9,
                "<VAL_BUY_RETAIL>": pd.NA,
                "<VAL_BUY_INSTITUTIONAL>": pd.NA,
                "<VAL_SELL_RETAIL>": pd.NA,
                "<VAL_SELL_INSTITUTIONAL>": pd.NA,
                "<EST_VAL_BUY_RETAIL>": 999.0,
                "<VALUE_SOURCE>": "estimated_from_market_vwap",
                "<IS_ESTIMATED>": True,
                "<IS_PARTIAL>": pd.NA,
                "<PER>": "D",
            }
        ],
        index=pd.DatetimeIndex([today], name="<DTYYYYMMDD>"),
    )
    merged_ri = stock_module._append_partial_today(historical_ri, live_ri).iloc[0]
    assert merged_ri["<N_BUY_RETAIL>"] == 1
    assert merged_ri["<VOL_BUY_RETAIL>"] == 11
    assert merged_ri["<VAL_BUY_RETAIL>"] == 101
    assert merged_ri["<VALUE_SOURCE>"] == "tsetmc_actual"
    assert not bool(merged_ri["<IS_ESTIMATED>"])
    assert pd.isna(merged_ri["<IS_PARTIAL>"])
    assert pd.isna(merged_ri["<EST_VAL_BUY_RETAIL>"])

    historical_index = pd.DataFrame(
        [
            {
                "<FIRST>": 90.0,
                "<HIGH>": 110.0,
                "<LOW>": 85.0,
                "<CLOSE>": 100.0,
                "<VOL>": 123.0,
                "<OPEN>": 91.0,
            }
        ],
        index=pd.DatetimeIndex([today], name="<DTYYYYMMDD>"),
    )
    live_index = pd.DataFrame(
        [
            {
                "<FIRST>": np.nan,
                "<HIGH>": 120.0,
                "<LOW>": 86.0,
                "<CLOSE>": 115.0,
                "<VOL>": np.nan,
                "<OPEN>": np.nan,
            }
        ],
        index=pd.DatetimeIndex([today], name="<DTYYYYMMDD>"),
    )
    merged_index = stock_module._append_partial_today(
        historical_index, live_index
    ).iloc[0]
    assert merged_index["<FIRST>"] == 90
    assert merged_index["<VOL>"] == 123
    assert merged_index["<OPEN>"] == 91
    assert merged_index["<CLOSE>"] == 115


def test_index_date_provenance_must_match_marketwatch(monkeypatch, parsed_snapshot):
    inscode = "32097828799138957"
    snapshot = _current(parsed_snapshot)
    stale_date = stock_module._tehran_today() - pd.Timedelta(days=1)
    row = {
        "insCode": inscode,
        "xDrNivJIdx004": 120,
        "xPhNivJIdx004": 125,
        "xPbNivJIdx004": 95,
        "indexChange": 20,
        "dEven": int(stale_date.strftime("%Y%m%d")),
        "hEven": 101500,
    }
    with pytest.raises(ValueError, match="does not match"):
        stock_module._live_index_history_row(
            "شاخص", inscode, snapshot, [row], industry=False
        )
    without_date = dict(row)
    without_date.pop("dEven")
    with pytest.raises(ValueError, match="date provenance unavailable"):
        stock_module._live_index_history_row(
            "شاخص", inscode, snapshot, [without_date], industry=False
        )


def test_default_history_calls_do_not_add_live_attrs(monkeypatch):
    monkeypatch.setattr(stock_module, "search_stock", lambda **_: "111")
    monkeypatch.setattr(
        stock_module,
        "safe_get",
        lambda url: _Response(RI_HISTORY if "clienttype" in url else PRICE_CSV),
    )
    price = stock_module.stock(
        "تست", include_today=False, date_format="gregorian", progress=False
    )
    ri = stock_module.stock_RI(
        "تست", include_today=False, date_format="gregorian", progress=False
    )
    assert price.attrs == {}
    assert ri.attrs == {}
