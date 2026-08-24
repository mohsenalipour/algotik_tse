import datetime as dt
import math

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import fixed_income as fi


@pytest.fixture(autouse=True)
def _fixed_tehran_clock(monkeypatch):
    """Keep date-sensitive live fixtures deterministic across calendar days."""
    fixed_now = dt.datetime(
        2026, 8, 24, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=3, minutes=30))
    )
    monkeypatch.setattr(fi, "tehran_today", lambda: fixed_now.date())
    monkeypatch.setattr(fi, "tehran_now", lambda: fixed_now)
    current_snapshot = fi._is_current_snapshot
    monkeypatch.setattr(
        fi,
        "_is_current_snapshot",
        lambda snapshot: current_snapshot(snapshot, now=pd.Timestamp(fixed_now)),
    )


def test_treasury_symbol_maturity_is_authoritative_and_validated():
    parsed = att.parse_treasury_maturity("اخزا020322")
    assert parsed["maturity_jalali"] == "1402/03/22"
    assert parsed["maturity_gregorian"] == dt.date(2023, 6, 12)
    assert parsed["maturity_source"] == "user_confirmed_symbol_jalali_yymmdd"
    old = att.parse_treasury_maturity("اخزا۹۹۱۱۱۷")
    assert old["maturity_jalali"] == "1399/11/17"
    assert old["maturity_gregorian"] == dt.date(2021, 2, 5)
    assert att.parse_treasury_maturity("اخزا021322") is None
    assert att.parse_treasury_maturity("اخزا020332") is None
    assert att.parse_treasury_maturity("نماد020322") is None
    assert att.parse_treasury_maturity("اخزا0203227") is None
    assert att.parse_treasury_maturity("Xاخزا020322") is None
    assert att.parse_treasury_maturity("اخزا020322X") is None
    assert att.parse_treasury_maturity("اخزا-020322") is None
    assert att.parse_treasury_maturity("اخزا202") is None
    assert att.parse_treasury_maturity("اخزا4024") is None


def test_day_counts_cover_leap_and_30e():
    assert att.day_count_fraction(
        "2024-01-01", "2025-01-01", "ACT/365F"
    ) == pytest.approx(366 / 365)
    assert att.day_count_fraction(
        "2024-01-01", "2025-01-01", "ACT/ACT-ISDA"
    ) == pytest.approx(1.0)
    assert att.day_count_fraction(
        "2024-02-29", "2024-03-30", "30E/360"
    ) == pytest.approx(31 / 360)
    assert att.day_count_fraction("1402-03-22", "1403-03-22") > 0
    with pytest.raises(ValueError):
        att.day_count_fraction("2025-01-01", "2025-01-01")


def test_zero_coupon_expected_yield_duration_convexity():
    settlement = dt.date(2025, 1, 1)
    maturity = dt.date(2027, 1, 1)
    result = att.treasury_yield(800_000, maturity, settlement)
    assert result["EffectiveAnnualYield"] == pytest.approx(0.11803398875)
    assert result["DiscountFactor"] == pytest.approx(0.8)
    assert result["MacaulayDuration"] == pytest.approx(2.0)
    assert result["ModifiedDuration"] == pytest.approx(1.788854382, rel=1e-9)
    assert result["Convexity"] == pytest.approx(4.8)
    analytics = att.bond_analytics(
        800_000,
        [(maturity, 1_000_000)],
        settlement_date=settlement,
        annual_yield=result["EffectiveAnnualYield"],
        compounding="effective",
    )
    assert analytics["MacaulayDuration"] == pytest.approx(2.0)
    assert analytics["ModifiedDuration"] == pytest.approx(1.788854382, rel=1e-9)
    assert analytics["Convexity"] == pytest.approx(4.8)


def test_coupon_price_yield_duration_convexity_round_trip():
    settlement = dt.date(2025, 1, 1)
    cashflows = [
        (dt.date(2026, 1, 1), 100),
        (dt.date(2027, 1, 1), 100),
        (dt.date(2028, 1, 1), 1_100),
    ]
    price = att.bond_price(0.08, cashflows, settlement)
    assert price == pytest.approx(1051.541939745)
    solved = att.yield_to_maturity(price, cashflows, settlement)
    assert solved == pytest.approx(0.08, abs=1e-10)
    result = att.bond_analytics(price, cashflows, settlement, annual_yield=0.08)
    assert result["MacaulayDuration"] == pytest.approx(2.742360188)
    assert result["ModifiedDuration"] == pytest.approx(2.539222397)
    assert result["Convexity"] == pytest.approx(9.113742589)


def test_coupon_metadata_generation_and_compounding_conversions():
    settlement = dt.date(2025, 1, 1)
    maturity = dt.date(2028, 1, 1)
    generated = att.bond_price(
        0.08,
        settlement_date=settlement,
        maturity_date=maturity,
        face_value=1_000,
        coupon_rate=0.10,
        frequency=1,
    )
    assert generated == pytest.approx(1051.541939745)
    effective = 0.12
    continuous = math.log1p(effective)
    cashflow = [(dt.date(2026, 1, 1), 1_000)]
    assert att.bond_price(
        effective, cashflow, settlement, compounding="effective"
    ) == pytest.approx(
        att.bond_price(continuous, cashflow, settlement, compounding="continuous")
    )


def test_coupon_schedule_eom_anchor_and_stub_rejection():
    cashflows, previous, _, _ = fi._generated_coupon_cashflows(
        dt.date(2027, 1, 1), dt.date(2028, 8, 31), 1_000, 0.10, 2
    )
    assert [value for value, _ in cashflows] == [
        dt.date(2027, 2, 28),
        dt.date(2027, 8, 31),
        dt.date(2028, 2, 29),
        dt.date(2028, 8, 31),
    ]
    assert previous == dt.date(2026, 8, 31)
    with pytest.raises(ValueError, match="stub"):
        att.bond_price(
            0.08,
            settlement_date=dt.date(2026, 1, 1),
            maturity_date=dt.date(2028, 8, 31),
            issue_date=dt.date(2025, 7, 15),
            face_value=1_000,
            coupon_rate=0.10,
            frequency=2,
        )
    with pytest.raises(ValueError, match="precede issue_date"):
        att.bond_price(
            0.08,
            settlement_date=dt.date(2024, 1, 1),
            maturity_date=dt.date(2028, 8, 31),
            issue_date=dt.date(2025, 8, 31),
            face_value=1_000,
            coupon_rate=0.10,
            frequency=2,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_public_math_rejects_nonfinite_numbers(bad):
    settlement = dt.date(2025, 1, 1)
    maturity = dt.date(2026, 1, 1)
    with pytest.raises(ValueError):
        att.treasury_yield(bad, maturity, settlement)
    with pytest.raises(ValueError):
        att.bond_price(bad, [(maturity, 1_000)], settlement)
    with pytest.raises(ValueError):
        att.bond_analytics(900, [(maturity, 1_000)], settlement, annual_yield=bad)
    with pytest.raises(ValueError):
        fi.discount_factor_from_rate(bad, 1.0)


def test_frequency_is_not_silently_truncated_and_dv01_matches_finite_difference():
    settlement = dt.date(2025, 1, 1)
    cashflows = [(dt.date(2026, 1, 1), 100), (dt.date(2027, 1, 1), 1_100)]
    with pytest.raises(ValueError, match="positive integer"):
        att.bond_price(0.08, cashflows, settlement, frequency=2.5)
    price = att.bond_price(0.08, cashflows, settlement)
    analytics = att.bond_analytics(price, cashflows, settlement, annual_yield=0.08)
    finite_difference = (
        att.bond_price(0.08 - 0.0001, cashflows, settlement)
        - att.bond_price(0.08 + 0.0001, cashflows, settlement)
    ) / 2
    assert analytics["DV01"] == pytest.approx(finite_difference, rel=1e-7)


def test_cashflow_safety_and_invalid_zero_coupon_inputs():
    settlement = dt.date(2025, 1, 1)
    with pytest.raises(ValueError, match="sign-changing"):
        att.yield_to_maturity(100, [(dt.date(2026, 1, 1), -100)], settlement)
    with pytest.raises(ValueError, match="maturity_date"):
        att.treasury_yield(800_000, settlement, settlement)
    with pytest.raises(ValueError, match="price"):
        att.treasury_yield(0, dt.date(2026, 1, 1), settlement)


def test_curve_exact_nodes_log_discount_forward_and_no_extrapolation():
    settlement = dt.date(2025, 1, 1)
    nodes = pd.DataFrame(
        {
            "Maturity": [dt.date(2026, 1, 1), dt.date(2027, 1, 1)],
            "DiscountFactor": [0.9, 0.8],
            "Symbol": ["A", "B"],
        }
    )
    curve = att.build_yield_curve(nodes, settlement)
    assert isinstance(curve, att.YieldCurve)
    assert curve.discount_factor(1.0) == pytest.approx(0.9)
    assert curve.discount_factor(2.0) == pytest.approx(0.8)
    expected_mid = math.exp((math.log(0.9) + math.log(0.8)) / 2)
    assert curve.discount_factor(1.5) == pytest.approx(expected_mid)
    assert curve.forward_rate(1.0, 2.0) == pytest.approx(-math.log(0.8 / 0.9))
    with pytest.raises(ValueError, match="beyond"):
        curve.discount_factor(3.0)
    assert list(curve.nodes["Symbol"]) == ["A", "B"]


def test_curve_duplicates_and_monotonic_validation():
    settlement = dt.date(2025, 1, 1)
    duplicate = pd.DataFrame(
        {
            "Maturity": [dt.date(2026, 1, 1)] * 2,
            "DiscountFactor": [0.9, 0.8],
            "Volume": [1, 3],
        }
    )
    with pytest.raises(ValueError, match="duplicate"):
        att.build_yield_curve(duplicate, settlement)
    curve = att.build_yield_curve(
        duplicate, settlement, duplicate_policy="volume_weighted"
    )
    assert curve.discount_factors[0] == pytest.approx(0.825)
    with pytest.raises(ValueError, match="non-increasing"):
        att.build_yield_curve(
            [
                {"Maturity": dt.date(2026, 1, 1), "DiscountFactor": 0.8},
                {"Maturity": dt.date(2027, 1, 1), "DiscountFactor": 0.9},
            ],
            settlement,
        )
    with pytest.raises(ValueError, match="settlement anchor"):
        att.build_yield_curve(
            [{"Maturity": dt.date(2026, 1, 1), "DiscountFactor": 1.1}],
            settlement,
        )
    negative_rate_curve = att.build_yield_curve(
        [{"Maturity": dt.date(2026, 1, 1), "DiscountFactor": 1.1}],
        settlement,
        enforce_monotonic_discount=False,
    )
    assert negative_rate_curve.discount_factors == (1.1,)


def test_yield_curve_direct_constructor_freezes_input_sequences():
    curve = att.YieldCurve(
        settlement_date=dt.date(2025, 1, 1),
        maturities=[dt.date(2026, 1, 1)],
        times=[1.0],
        discount_factors=[0.9],
        continuous_zero_rates=[-math.log(0.9)],
        node_metadata=[{"Symbol": "A"}],
    )
    assert isinstance(curve.times, tuple)
    assert isinstance(curve.discount_factors, tuple)
    assert isinstance(curve.node_metadata, tuple)


def _snapshot(fresh=True, trade_date=dt.date(2026, 8, 24)):
    stocks = pd.DataFrame(
        [
            {
                "InsCode": "1",
                "ISIN": "IRB1",
                "Symbol": "اخزا070101",
                "Name": "اسناد خزانه اسلامی",
                "Last": 800_000,
                "Close": 799_000,
                "Volume": 100,
                "Value": 80_000_000,
                "TradeCount": 5,
                "Time": "10:00:00",
            },
            {
                "InsCode": "2",
                "ISIN": "IRB2",
                "Symbol": "اخزا080101",
                "Name": "اسناد خزانه اسلامی",
                "Last": 700_000,
                "Close": 699_000,
                "Volume": 200,
                "Value": 140_000_000,
                "TradeCount": 6,
                "Time": "10:00:00",
            },
            {
                "InsCode": "3",
                "ISIN": "IRB3",
                "Symbol": "اخزا090101",
                "Name": "اسناد خزانه اسلامی",
                "Last": 600_000,
                "Close": 599_000,
                "Volume": 300,
                "Value": 180_000_000,
                "TradeCount": 7,
                "Time": "10:00:00",
            },
            {
                "InsCode": "4",
                "ISIN": "IRO1",
                "Symbol": "فولاد",
                "Name": "فولاد مبارکه",
                "Last": 100,
                "Close": 100,
                "Volume": 1,
                "Value": 100,
                "TradeCount": 1,
                "Time": "10:00:00",
            },
        ]
    )
    orders = pd.DataFrame(
        [
            {"InsCode": "1", "Level": 1, "BidPrice": 799_000, "AskPrice": 801_000},
            {"InsCode": "2", "Level": 1, "BidPrice": 710_000, "AskPrice": 700_000},
            {"InsCode": "3", "Level": 1, "BidPrice": 0, "AskPrice": 0},
        ]
    )
    return {
        "stocks": stocks,
        "order_book": orders,
        "trade_date": trade_date,
        "is_realtime_fresh": fresh,
        "is_history_eligible": True,
        "fetched_at": pd.Timestamp("2026-08-24 10:00", tz="Asia/Tehran"),
        "snapshot_age_seconds": 1.0 if fresh else 1000.0,
        "is_partial": pd.NA,
    }


def test_live_treasury_yields_one_snapshot_quote_fallback_and_provenance(monkeypatch):
    calls = []
    monkeypatch.setattr(fi, "market_watch", lambda: calls.append(1) or _snapshot())
    result = att.get_treasury_yields(include_stale=False)
    assert calls == [1]
    assert list(result["PriceSource"]) == ["bid_ask_mid", "last", "last"]
    assert result["MaturitySource"].eq("user_confirmed_symbol_jalali_yymmdd").all()
    assert (
        result["FaceValueSource"]
        .eq("iran_treasury_market_convention_ifb_validated")
        .all()
    )
    assert str(result["Volume"].dtype) == "Int64"
    assert result.attrs["diagnostics"]["excluded"] == []


def test_live_stale_filter_and_typed_empty(monkeypatch):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot(fresh=False))
    result = att.get_treasury_yields()
    assert result.empty
    assert str(result["Tenor"].dtype) == "Float64"
    included = att.get_treasury_yields(include_stale=True, symbol="اخزا070101")
    assert len(included) == 1
    assert bool(included["IsStale"].iloc[0]) is True


def test_live_locked_quote_sizes_no_trade_and_nullable_fields(monkeypatch):
    snapshot = _snapshot()
    snapshot["order_book"].loc[
        snapshot["order_book"]["InsCode"].eq("1"), ["BidPrice", "AskPrice"]
    ] = 800_000
    for column in ("BidVolume", "AskVolume", "BidOrderCount", "AskOrderCount"):
        snapshot["order_book"][column] = 1
    snapshot["stocks"].loc[
        snapshot["stocks"]["InsCode"].eq("2"),
        ["Volume", "TradeCount", "Last", "Close", "Value"],
    ] = pd.NA
    monkeypatch.setattr(fi, "market_watch", lambda: snapshot)
    locked = att.get_treasury_yields(symbol="اخزا070101")
    assert locked["PriceSource"].iloc[0] == "bid_ask_mid"
    assert locked["Price"].iloc[0] == 800_000
    missing = att.get_treasury_yields(symbol="اخزا080101")
    assert missing.empty

    no_trade = _snapshot()
    row_mask = no_trade["stocks"]["InsCode"].eq("3")
    no_trade["stocks"].loc[row_mask, ["Volume", "TradeCount"]] = 0
    monkeypatch.setattr(fi, "market_watch", lambda: no_trade)
    assert att.get_treasury_yields(symbol="اخزا090101", price_source="close").empty
    explicit = att.get_treasury_yields(
        symbol="اخزا090101", price_source="close", allow_no_trade=True
    )
    assert bool(explicit["NoTrade"].iloc[0]) is True
    assert bool(explicit["IsInstrumentStale"].iloc[0]) is True
    assert explicit["InstrumentValueSource"].iloc[0] == "close_no_trade_explicit"


def test_live_auto_falls_back_from_nullable_last_to_valid_close(monkeypatch):
    snapshot = _snapshot()
    stock_mask = snapshot["stocks"]["InsCode"].eq("1")
    snapshot["stocks"].loc[
        stock_mask, ["Last", "Close", "Volume", "TradeCount", "Time"]
    ] = [pd.NA, 799_000, 1, 1, "10:00:00"]
    book_mask = snapshot["order_book"]["InsCode"].eq("1")
    snapshot["order_book"].loc[book_mask, ["BidPrice", "AskPrice"]] = [0, pd.NA]
    monkeypatch.setattr(fi, "market_watch", lambda: snapshot)

    result = att.get_treasury_yields(symbol="اخزا070101", price_source="auto")

    assert len(result) == 1
    assert result["Price"].iloc[0] == 799_000
    assert result["PriceSource"].iloc[0] == "close"
    assert bool(result["NoTrade"].iloc[0]) is False


@pytest.mark.parametrize(
    "history_source, expected_live_source, expected_price",
    [
        ("auto", "close", 799_000),
        ("final", "close", 799_000),
        ("close", "last", 800_000),
    ],
)
def test_include_today_price_source_is_symmetric(
    monkeypatch, history_source, expected_live_source, expected_price
):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())
    monkeypatch.setattr(
        fi,
        "stock",
        lambda **kwargs: pd.DataFrame(
            {
                "Open": [780_000],
                "High": [810_000],
                "Low": [770_000],
                "Close": [795_000],
                "Final": [798_000],
                "Adj Close": [1],
                "Volume": [10],
                "No.": [1],
                "Value": [7_980_000],
            },
            index=pd.to_datetime(["2026-08-23"]),
        ),
    )
    result = att.get_treasury_yield_history(
        "اخزا070101",
        include_today=True,
        price_source=history_source,
        date_format="gregorian",
        progress=False,
    )
    live = result.loc[result["Status"].eq("live_snapshot")].iloc[0]
    assert live["PriceSource"] == expected_live_source
    assert live["Price"] == expected_price


def test_maturity_priority_ifb_then_explicit_and_conflicts(monkeypatch):
    snapshot = _snapshot()
    symbol_date = att.parse_treasury_maturity("اخزا070101")["maturity_gregorian"]
    ifb_date = dt.date(2029, 3, 20)
    reference = pd.DataFrame(
        {
            "Symbol": ["اخزا\u200c070101"],
            "Price": [800_000],
            "LastTradeJalali": ["1405/06/02"],
            "LastTradeDate": [dt.date(2026, 8, 24)],
            "MaturityJalali": ["1408/12/30"],
            "Maturity": [ifb_date],
            "ReferenceYTM": [0.2],
            "ReferenceSimpleYield": [0.18],
            "ReferenceSource": ["ifb_ytm_page"],
        }
    )
    monkeypatch.setattr(fi, "market_watch", lambda: snapshot)
    monkeypatch.setattr(fi, "get_ifb_yield_table", lambda category: reference)
    official = att.get_treasury_yields(symbol="اخزا070101", source="hybrid")
    assert official["Maturity"].iloc[0].date() == ifb_date
    assert official["MaturitySource"].iloc[0] == "ifb_ytm_page"
    assert bool(official["MaturityConflict"].iloc[0]) is True
    assert bool(official["MaturityMatchesReference"].iloc[0]) is True
    explicit_date = dt.date(2030, 3, 20)
    explicit = att.get_treasury_yields(
        symbol="اخزا070101", source="hybrid", maturity_date=explicit_date
    )
    assert explicit["Maturity"].iloc[0].date() == explicit_date
    assert explicit["MaturitySource"].iloc[0] == "user_supplied_maturity"
    assert bool(explicit["MaturityMatchesReference"].iloc[0]) is False
    assert pd.isna(explicit["YieldDifferenceBps"].iloc[0])
    assert symbol_date != ifb_date


def test_history_is_unadjusted_per_trade_settlement_limit_and_today(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(fi, "market_watch", lambda: snapshot)
    captured = []

    def fake_stock(**kwargs):
        captured.append(kwargs)
        symbol_offset = 0 if kwargs["symbol"] == "اخزا070101" else 10_000
        return pd.DataFrame(
            {
                "Open": [780_000 + symbol_offset, 790_000 + symbol_offset],
                "High": [810_000 + symbol_offset, 820_000 + symbol_offset],
                "Low": [770_000 + symbol_offset, 780_000 + symbol_offset],
                "Close": [795_000 + symbol_offset, 805_000 + symbol_offset],
                "Final": [800_000 + symbol_offset, 810_000 + symbol_offset],
                "Adj Close": [1, 1],
                "Volume": [10, 20],
                "No.": [1, 2],
                "Value": [8_000_000, 16_200_000],
            },
            index=pd.to_datetime(["2026-08-22", "2026-08-23"]),
        )

    monkeypatch.setattr(fi, "stock", fake_stock)
    result = att.get_treasury_yield_history(
        ["اخزا070101", "اخزا080101"],
        limit=2,
        include_today=True,
        date_format="gregorian",
        progress=False,
    )
    assert len(captured) == 2
    assert all(call["auto_adjust"] is False for call in captured)
    assert all(call["include_today"] is False for call in captured)
    assert len(result) == 4
    assert result.groupby("Symbol").size().eq(2).all()
    assert set(result["TradeDate"].dt.date) == {
        dt.date(2026, 8, 23),
        dt.date(2026, 8, 24),
    }
    assert result.loc[result["Status"].eq("historical"), "SettlementDate"].equals(
        result.loc[result["Status"].eq("historical"), "TradeDate"]
    )
    assert result.attrs["diagnostics"]["auto_adjust"] is False


def test_delisted_treasury_history_resolves_from_authoritative_symbol(monkeypatch):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())

    def historical_stock(**kwargs):
        assert kwargs["symbol"] == "اخزا991117"
        return pd.DataFrame(
            {
                "Open": [800_000],
                "High": [810_000],
                "Low": [790_000],
                "Close": [805_000],
                "Final": [802_000],
                "Adj Close": [1],
                "Volume": [10],
                "No.": [1],
                "Value": [8_020_000],
            },
            index=pd.to_datetime(["2021-01-01"]),
        )

    monkeypatch.setattr(fi, "stock", historical_stock)
    result = att.get_treasury_yield_history(
        "اخزا991117", date_format="gregorian", progress=False
    )
    assert len(result) == 1
    assert result["Maturity"].iloc[0].date() == dt.date(2021, 2, 5)
    assert result["MaturitySource"].iloc[0] == "user_confirmed_symbol_jalali_yymmdd"
    assert pd.isna(result["InsCode"].iloc[0])


def test_history_unresolved_issue_id_is_reported_without_stock_request(monkeypatch):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())
    calls = []
    monkeypatch.setattr(fi, "stock", lambda **kwargs: calls.append(kwargs))
    result = att.get_treasury_yield_history("اخزا202", progress=False)
    assert result.empty
    assert calls == []
    assert result.attrs["diagnostics"]["failures"] == [
        {"Symbol": "اخزا202", "reason": "unresolved_maturity_or_symbol"}
    ]


def test_history_issue_id_resolves_from_explicit_and_ifb_metadata(monkeypatch):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())
    monkeypatch.setattr(
        fi,
        "stock",
        lambda **kwargs: pd.DataFrame(
            {
                "Open": [800_000],
                "High": [810_000],
                "Low": [790_000],
                "Close": [805_000],
                "Final": [802_000],
                "Adj Close": [1],
                "Volume": [10],
                "No.": [1],
                "Value": [8_020_000],
            },
            index=pd.to_datetime(["2026-08-23"]),
        ),
    )
    explicit = att.get_treasury_yield_history(
        "اخزا202",
        maturity_date=dt.date(2027, 1, 1),
        progress=False,
        max_requests=3,
    )
    assert explicit["MaturitySource"].iloc[0] == "user_supplied_maturity"
    reference = pd.DataFrame({"Symbol": ["اخزا202"], "Maturity": [dt.date(2027, 2, 1)]})
    monkeypatch.setattr(fi, "get_ifb_yield_table", lambda category: reference)
    official = att.get_treasury_yield_history(
        "اخزا202", use_ifb_reference=True, progress=False, max_requests=4
    )
    assert official["MaturitySource"].iloc[0] == "ifb_ytm_page"
    assert (
        official.attrs["diagnostics"]["request_budget"]["estimated_requests_used"] == 4
    )


def test_history_request_budget_guards_before_symbol_calls(monkeypatch):
    market_calls = []
    stock_calls = []
    monkeypatch.setattr(
        fi, "market_watch", lambda: market_calls.append(1) or _snapshot()
    )
    monkeypatch.setattr(fi, "stock", lambda **kwargs: stock_calls.append(kwargs))
    with pytest.raises(ValueError, match="needs 3 requests"):
        att.get_treasury_yield_history("اخزا070101", max_requests=2, progress=False)
    assert market_calls == [1]
    assert stock_calls == []


def test_history_symbol_none_uses_current_universe_with_honest_provenance(
    monkeypatch,
):
    stock_calls = []
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())
    monkeypatch.setattr(
        fi,
        "stock",
        lambda **kwargs: stock_calls.append(kwargs) or pd.DataFrame(),
    )
    with pytest.raises(ValueError, match="needs 7 requests"):
        att.get_treasury_yield_history(max_requests=6, progress=False)
    assert stock_calls == []

    result = att.get_treasury_yields_history(max_requests=7, progress=False)
    assert result.empty
    assert len(stock_calls) == 3
    diagnostics = result.attrs["diagnostics"]
    assert diagnostics["universe_source"] == "current_tsetmc_market_watch"
    assert diagnostics["prices_no_lookahead"] is True
    assert diagnostics["universe_no_lookahead"] is False
    assert diagnostics["no_lookahead"] is False
    assert diagnostics["request_budget"]["estimated_requests_used"] == 7
    assert att.get_treasury_yields_history is att.get_treasury_yield_history


def test_current_curve_min_nodes_is_after_duplicate_maturity(monkeypatch):
    settlement = dt.date(2025, 1, 1)
    nodes = pd.DataFrame(
        {
            "Maturity": [dt.date(2026, 1, 1), dt.date(2026, 1, 1), dt.date(2027, 1, 1)],
            "DiscountFactor": [0.9, 0.9, 0.8],
            "SettlementDate": [settlement] * 3,
            "Volume": pd.Series([1, 2, 3], dtype="Int64"),
        }
    )
    monkeypatch.setattr(fi, "get_treasury_yields", lambda **kwargs: nodes)
    with pytest.raises(ValueError, match="distinct maturities"):
        att.get_yield_curve(min_nodes=3)


def test_yield_curve_history_marks_no_lookahead(monkeypatch):
    trade_date = dt.date(2026, 8, 23)
    history = pd.DataFrame(
        {
            "TradeDate": [trade_date] * 3,
            "Maturity": [
                dt.date(2028, 3, 20),
                dt.date(2029, 3, 20),
                dt.date(2030, 3, 20),
            ],
            "DiscountFactor": [0.8, 0.7, 0.6],
            "Symbol": ["a", "b", "c"],
            "Volume": pd.Series([1, 2, 3], dtype="Int64"),
        }
    )
    history = history.reindex(columns=fi.TREASURY_HISTORY_COLUMNS)
    history.attrs["diagnostics"] = {"auto_adjust": False}
    monkeypatch.setattr(
        fi, "get_treasury_yield_history", lambda *args, **kwargs: history
    )
    result = att.get_yield_curve_history(symbol=["a", "b", "c"], progress=False)
    assert result["CurveStatus"].eq("valid").all()
    assert result["CurvePricesNoLookahead"].all()
    assert not result["CurveUniverseNoLookahead"].any()
    assert not result["CurveNoLookahead"].any()
    assert result["CurveID"].nunique() == 1
    assert result.attrs["diagnostics"]["no_lookahead"] is False


def test_curve_history_duplicate_count_and_ifb_universe_provenance(monkeypatch):
    trade_date = dt.date(2026, 8, 23)
    history = pd.DataFrame(
        {
            "TradeDate": [trade_date] * 3,
            "Maturity": [
                dt.date(2028, 3, 20),
                dt.date(2028, 3, 20),
                dt.date(2029, 3, 20),
            ],
            "DiscountFactor": [0.8, 0.8, 0.7],
            "Symbol": ["a", "b", "c"],
            "Volume": pd.Series([1, 2, 3], dtype="Int64"),
        }
    ).reindex(columns=fi.TREASURY_HISTORY_COLUMNS)
    history.attrs["diagnostics"] = {"auto_adjust": False}
    monkeypatch.setattr(
        fi, "get_treasury_yield_history", lambda *args, **kwargs: history
    )
    result = att.get_yield_curve_history(
        symbol=["a", "b", "c"], min_nodes=3, progress=False
    )
    assert result["CurveStatus"].eq("insufficient_nodes").all()
    assert result["InputNodeCount"].eq(3).all()
    assert result["CalibratedNodeCount"].eq(2).all()

    captured = {}
    catalog = pd.DataFrame(
        {
            "Symbol": ["اخزا202", "اخزا210"],
            "Maturity": [dt.date(2027, 1, 1), dt.date(2028, 1, 1)],
        }
    )
    monkeypatch.setattr(fi, "get_ifb_yield_table", lambda category: catalog)

    def empty_history(symbol, **kwargs):
        captured["symbol"] = symbol
        captured.update(kwargs)
        return fi._typed_empty(fi.TREASURY_HISTORY_COLUMNS)

    monkeypatch.setattr(fi, "get_treasury_yield_history", empty_history)
    empty = att.get_yield_curve_history(symbol=None, max_requests=10, progress=False)
    assert captured["symbol"] == ["اخزا202", "اخزا210"]
    assert captured["maturity_map"] == dict(zip(catalog["Symbol"], catalog["Maturity"]))
    assert captured["max_requests"] == 9
    assert empty.attrs["diagnostics"]["universe_source"] == "ifb_latest_history_initial"
    assert empty.attrs["diagnostics"]["universe_no_lookahead"] is False


def test_existing_list_bonds_signature_is_unchanged():
    import inspect

    assert str(inspect.signature(att.list_bonds)) == "(progress=True)"


IFB_HTML = """
<html><body>
<table id="ContentPlaceHolder1_grdytmforkhazaneh" class="KhazanehGrid">
<thead><tr><th>ردیف</th><th>نماد</th><th>قیمت معامله شده هر ورقه</th>
<th>تاریخ آخرین روز معاملاتی</th><th>تاریخ سررسید</th><th>YTM</th>
<th>بازده ساده</th></tr></thead>
<tbody>
<tr><td>1</td><td>اخزا202</td><td>904,550</td><td>1405-06-02</td>
<td>1405-09-23</td><td>38/67%</td><td>34/39%</td></tr>
<tr><td>2</td><td>گام020</td><td>900,000</td><td>1405-06-02</td>
<td>1405-10-01</td><td>40/00%</td><td>35/00%</td></tr>
</tbody></table>
</body></html>
"""


def test_ifb_table_parser_and_official_golden_sample():
    result = fi._parse_ifb_yield_html(IFB_HTML, "treasury")
    assert list(result["Symbol"]) == ["اخزا202"]
    row = result.iloc[0]
    assert row["Price"] == 904_550
    assert row["ReferenceYTM"] == pytest.approx(0.3867)
    assert row["ReferenceSimpleYield"] == pytest.approx(0.3439)
    calculated = att.treasury_yield(row["Price"], row["Maturity"], row["LastTradeDate"])
    assert calculated["DaysToMaturity"] == 112
    assert calculated["EffectiveAnnualYield"] == pytest.approx(
        row["ReferenceYTM"], abs=0.0001
    )
    assert result.attrs["reference_url"] == "https://ifb.ir/ytm.aspx"


def test_ifb_conflicting_duplicates_are_rejected():
    duplicate = IFB_HTML.replace(
        "</tbody>",
        "<tr><td>3</td><td>اخزا202</td><td>900,000</td><td>1405-06-02</td>"
        "<td>1405-09-23</td><td>39/00%</td><td>35/00%</td></tr></tbody>",
    )
    with pytest.raises(att.DataParsingError, match="conflicting"):
        fi._parse_ifb_yield_html(duplicate, "treasury")


def test_hybrid_ifb_failure_falls_back_without_losing_tsetmc(monkeypatch):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())

    def unavailable(*args, **kwargs):
        raise att.ConnectionError("timeout")

    monkeypatch.setattr(fi, "get_ifb_yield_table", unavailable)
    with pytest.warns(RuntimeWarning, match="IFB reference unavailable"):
        result = att.get_treasury_yields(source="hybrid")
    assert len(result) == 3
    assert "ifb_reference_warning" in result.attrs["diagnostics"]


def test_hybrid_adds_reference_and_difference_bps(monkeypatch):
    monkeypatch.setattr(fi, "market_watch", lambda: _snapshot())
    reference = pd.DataFrame(
        {
            "Symbol": ["اخزا070101"],
            "Price": [801_000.0],
            "LastTradeJalali": ["1405/06/02"],
            "LastTradeDate": [dt.date(2026, 8, 24)],
            "MaturityJalali": ["1407/01/01"],
            "Maturity": [
                att.parse_treasury_maturity("اخزا070101")["maturity_gregorian"]
            ],
            "ReferenceYTM": [0.20],
            "ReferenceSimpleYield": [0.18],
            "ReferenceSource": ["ifb_ytm_page"],
        }
    )
    monkeypatch.setattr(fi, "get_ifb_yield_table", lambda category: reference)
    result = att.get_treasury_yields(symbol="اخزا070101", source="hybrid")
    assert result["ReferenceYTM"].iloc[0] == pytest.approx(0.20)
    assert result["YieldDifferenceBps"].iloc[0] == pytest.approx(
        (result["EffectiveAnnualYield"].iloc[0] - 0.20) * 10_000
    )
    assert bool(result["MaturityMatchesReference"].iloc[0]) is True
    all_rows = att.get_treasury_yields(source="hybrid")
    missing = all_rows.loc[all_rows["Symbol"].ne("اخزا070101")]
    assert missing["MaturityMatchesReference"].isna().all()
    assert missing["YieldDifferenceBps"].isna().all()
