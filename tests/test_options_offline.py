import datetime as dt
import inspect
import math

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import instruments
from algotik_tse.core import options as opt


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def paired_payload(crossed_put=False):
    return {
        "instrumentOptMarketWatch": [
            {
                "insCode_C": "111",
                "insCode_P": "222",
                "instrumentID_C": "IROC1",
                "instrumentID_P": "IROP1",
                "symbol_C": "ضتست1",
                "symbol_P": "طتست1",
                "name_C": "اختیار خرید تست",
                "name_P": "اختیار فروش تست",
                "uaInsCode": "999",
                # Captured official schema semantics: lval30_UA is the
                # underlying ticker (real values include اخابر/شستا/وبملت).
                "lval30_UA": "تست",
                "contractSize": "1000",
                "strikePrice": "۱۰۰",
                "beginDate": 20250101,
                "endDate": 20270101,
                "pDrCotVal_C": 10,
                "pClosing_C": 9,
                "pDrCotVal_P": 5,
                "pClosing_P": 6,
                "qTotTran5J_C": 100,
                "qTotTran5J_P": 0,
                "qTotCap_C": 1000,
                "qTotCap_P": 0,
                "zTotTran_C": 2,
                "zTotTran_P": 0,
                "oP_C": 50,
                "oP_P": 25,
                "pMeDem_C": 9,
                "pMeOf_C": 11,
                "qTitMeDem_C": 20,
                "qTitMeOf_C": 30,
                "pMeDem_P": 7 if crossed_put else 4,
                "pMeOf_P": 6,
                "qTitMeDem_P": 10,
                "qTitMeOf_P": 10,
                "pClosing_UA": 100,
            }
        ]
    }


def market(monkeypatch, payload=None):
    monkeypatch.setattr(
        opt, "safe_get", lambda url: Response(payload or paired_payload())
    )
    return opt.get_option_market(progress=False)


def at_date(frame, value):
    frame = frame.copy()
    frame["AsOf"] = pd.Timestamp(value, tz="Asia/Tehran")
    return frame


def test_black_scholes_reference_and_scales():
    call = att.black_scholes_price(100, 100, 1, 0.05, 0.2, "call")
    put = att.black_scholes_price(100, 100, 1, 0.05, 0.2, "put")
    assert call == pytest.approx(10.4505835722)
    assert put == pytest.approx(5.5735260223)
    greeks = att.black_scholes_greeks(100, 100, 1, 0.05, 0.2, "call")
    assert greeks["Delta"] == pytest.approx(0.6368306512)
    assert greeks["Gamma"] == pytest.approx(0.01876201735)
    assert greeks["Vega"] == pytest.approx(37.52403469)
    assert greeks["Vega1Pct"] == pytest.approx(greeks["Vega"] * 0.01)
    assert greeks["ThetaPerYear"] == pytest.approx(-6.414027546)
    assert greeks["ThetaPerDay"] == pytest.approx(greeks["ThetaPerYear"] / 365)
    assert greeks["Rho"] == pytest.approx(53.23248155)
    assert greeks["Rho100bp"] == pytest.approx(greeks["Rho"] * 0.01)


def test_math_boundaries_negative_rates_dividend_and_expiry():
    assert att.black_scholes_price(90, 100, 0, -0.1, 0.2, "call", 0.03) == 0
    assert att.black_scholes_price(90, 100, 0, -0.1, 0.2, "put", 0.03) == 10
    expected = max(100 * math.exp(-0.02) - 100 * math.exp(0.01), 0)
    assert att.black_scholes_price(
        100, 100, 1, -0.01, 0, "call", 0.02
    ) == pytest.approx(expected)
    with pytest.raises(ValueError):
        att.black_scholes_price(math.nan, 100, 1, 0.1, 0.2)
    with pytest.raises(ValueError):
        att.black_scholes_price(100, 100, 1, 0.1, 0.2, exercise_style="american")
    with pytest.raises(ValueError, match="stable"):
        att.black_scholes_price(100, 100, 10, -100, 0.2)


def test_iv_roundtrip_statuses_and_validation():
    price = att.black_scholes_price(100, 100, 1, 0.05, 0.2)
    assert att.implied_volatility(price, 100, 100, 1, 0.05)[
        "ImpliedVolatility"
    ] == pytest.approx(0.2, abs=1e-7)
    assert att.implied_volatility(None, 100, 100, 1, 0.05)["Status"] == "missing"
    assert att.implied_volatility(1, 100, 100, 0, 0.05)["Status"] == "expiry"
    assert att.implied_volatility(200, 100, 100, 1, 0.05)["Status"] == "out_of_bounds"
    assert (
        att.implied_volatility(price, 100, 100, 1, 0.05, upper_volatility=0.1)["Status"]
        == "no_bracket"
    )
    exhausted = att.implied_volatility(
        price, 100, 100, 1, 0.05, tolerance=1e-30, max_iterations=1
    )
    assert exhausted["Status"] == "non_converged"
    assert math.isnan(exhausted["ImpliedVolatility"])
    for tolerance in (0, -1, math.nan, math.inf):
        with pytest.raises(ValueError):
            att.implied_volatility(price, 100, 100, 1, 0.05, tolerance=tolerance)
    for iterations in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            att.implied_volatility(price, 100, 100, 1, 0.05, max_iterations=iterations)


def test_bulk_endpoint_parser_atomic_exact_filter_and_provenance(monkeypatch):
    frame = market(monkeypatch)
    assert list(frame["InsCode"]) == ["111", "222"]
    assert list(frame["OptionType"]) == ["call", "put"]
    assert frame.loc[0, "Strike"] == 100
    assert frame.loc[0, "Price"] == 10
    assert frame.loc[0, "PriceSource"] == "mid"
    assert frame.loc[1, "PriceSource"] == "mid"
    assert frame.loc[1, "NoTrade"]
    assert frame.loc[0, "UnderlyingClose"] == 100
    assert pd.isna(frame.loc[0, "UnderlyingName"])
    assert frame.loc[0, "UnderlyingSymbol"] == "تست"
    assert frame["AsOf"].dt.tz is not None
    assert frame["Stale"].isna().all()
    assert frame.attrs["atomic_snapshot"] is True
    assert frame.attrs["exchange_event_freshness_known"] is False
    assert (
        frame.dtypes.astype(str).to_dict()
        == opt._empty_options().dtypes.astype(str).to_dict()
    )
    exact = opt.get_option_market(underlying="999", progress=False)
    assert len(exact) == 2
    absent = opt.get_option_market(underlying="99", progress=False)
    assert absent.empty


def test_bulk_parser_canonical_pair_dedupe_and_strict_root(monkeypatch):
    payload = paired_payload()
    duplicate = dict(payload["instrumentOptMarketWatch"][0])
    duplicate["strikePrice"] = "100.0"
    duplicate["endDate"] = "۲۰۲۷۰۱۰۱"
    duplicate["pClosing_C"] = 12
    payload["instrumentOptMarketWatch"].append(duplicate)
    frame = market(monkeypatch, payload)
    assert len(frame) == 2
    assert frame.loc[frame["OptionType"].eq("call"), "Close"].iloc[0] == 12
    assert frame.attrs["duplicate_pairs_dropped"] == 1
    monkeypatch.setattr(
        opt,
        "safe_get",
        lambda url: Response({"nested": {"instrumentOptMarketWatch": []}}),
    )
    with pytest.raises(Exception, match="instrumentOptMarketWatch"):
        opt.get_option_market(progress=False)


def test_pricing_fallback_rejects_crossed_and_requires_trade_evidence(monkeypatch):
    frame = market(monkeypatch, paired_payload(crossed_put=True))
    put = frame.loc[frame["OptionType"].eq("put")].iloc[0]
    assert put["Price"] == 6
    assert put["PriceSource"] == "close"
    call = frame.loc[frame["OptionType"].eq("call")].iloc[0]
    assert call["PriceSource"] == "mid"


class FlatCurve:
    def __init__(self, rate, settlement_date):
        self.rate = rate
        self.settlement_date = settlement_date
        self.calls = []

    def zero_rate(self, tenor, compounding="continuous"):
        self.calls.append((tenor, compounding))
        return self.rate

    def discount_factor(self, tenor):
        self.calls.append((tenor, "discount_factor"))
        years = (tenor - self.settlement_date).days / 365
        return math.exp(-self.rate * years)


def test_analysis_curve_iv_greeks_contract_and_liquidity(monkeypatch):
    frame = market(monkeypatch)
    valuation = dt.date(2026, 1, 1)
    frame = at_date(frame, valuation)
    curve = FlatCurve(0.05, valuation)
    result = opt.analyze_option_chain(
        frame,
        yield_curve=curve,
        valuation_date=valuation,
        liquidity_weights={},
        progress=False,
    )
    assert set(result["RiskFreeRateSource"]) == {
        "yield_curve_discount_factor_act365f_continuous"
    }
    assert all(kind == "discount_factor" for _, kind in curve.calls)
    assert result["ImpliedVolatility"].notna().all()
    assert result["ImpliedVolatilityBid"].notna().all()
    assert result["ImpliedVolatilityMid"].notna().all()
    assert result["ImpliedVolatilityAsk"].notna().all()
    assert result.loc[0, "Vega1PctContract"] == pytest.approx(
        result.loc[0, "Vega1Pct"] * 1000
    )
    assert result.loc[0, "PremiumContract"] == pytest.approx(
        result.loc[0, "Price"] * 1000
    )
    assert result["SpreadAbs"].notna().all()
    assert "LiquidityComponent_spread" in result
    assert result.attrs["parity_is_diagnostic_only"] is True
    with pytest.raises(ValueError, match="current curve"):
        opt.analyze_option_chain(
            frame,
            yield_curve=FlatCurve(0.05, dt.date(2025, 12, 31)),
            valuation_date=valuation,
            progress=False,
        )


def test_analysis_unknown_contract_size_stays_missing(monkeypatch):
    payload = paired_payload()
    payload["instrumentOptMarketWatch"][0]["contractSize"] = None
    frame = market(monkeypatch, payload)
    frame = at_date(frame, dt.date(2026, 1, 1))
    result = opt.analyze_option_chain(
        frame, risk_free_rate=0.05, valuation_date=dt.date(2026, 1, 1), progress=False
    )
    assert result["ContractSize"].isna().all()
    assert result["PremiumContract"].isna().all()


def test_parity_pair_is_exact_and_includes_contract_size(monkeypatch):
    frame = market(monkeypatch)
    frame = at_date(frame, dt.date(2026, 1, 1))
    result = opt.analyze_option_chain(
        frame, risk_free_rate=0.05, valuation_date=dt.date(2026, 1, 1), progress=False
    )
    assert result["ParityResidual"].notna().all()
    assert result["ImpliedForward"].notna().all()
    mismatched = frame.copy()
    mismatched.loc[mismatched["OptionType"].eq("put"), "ContractSize"] = 500
    result = opt.analyze_option_chain(
        mismatched,
        risk_free_rate=0.05,
        valuation_date=dt.date(2026, 1, 1),
        progress=False,
    )
    assert result["ParityResidual"].isna().all()


def test_put_call_ratios_and_zero_denominator(monkeypatch):
    frame = market(monkeypatch)
    ratios = opt.option_put_call_ratios(frame)
    assert ratios.loc[0, "PCRVolume"] == 0
    assert ratios.loc[0, "PCROpenInterest"] == pytest.approx(0.5)
    frame.loc[frame["OptionType"].eq("call"), "Value"] = 0
    ratios = opt.option_put_call_ratios(frame)
    assert pd.isna(ratios.loc[0, "PCRValue"])
    assert ratios.loc[0, "PCRValueStatus"] == "zero_denominator"
    second = frame.copy()
    second["AsOf"] = second["AsOf"] + pd.Timedelta(seconds=1)
    multiple = pd.concat([frame, second], ignore_index=True)
    with pytest.raises(ValueError, match="one non-null atomic AsOf"):
        opt.option_put_call_ratios(multiple)
    missing_asof = frame.drop(columns="AsOf")
    with pytest.raises(ValueError, match="one non-null atomic AsOf"):
        opt.option_put_call_ratios(missing_asof)
    null_asof = frame.copy()
    null_asof["AsOf"] = pd.NaT
    with pytest.raises(ValueError, match="one non-null atomic AsOf"):
        opt.option_put_call_ratios(null_asof)
    with pytest.raises(ValueError, match="one atomic AsOf"):
        opt.analyze_option_chain(
            multiple,
            risk_free_rate=0.05,
            valuation_date=dt.date(2026, 1, 1),
            progress=False,
        )


def test_snapshot_atomic_write_and_dedupe(monkeypatch, tmp_path):
    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))
    path = tmp_path / "options.json"
    saved = opt.save_option_snapshot(path, frame, progress=False)
    assert path.exists()
    assert len(saved) == 2
    saved_again = opt.save_option_snapshot(path, frame, progress=False)
    assert len(saved_again) == 2
    loaded = opt.load_option_snapshots(path)
    assert len(loaded) == 2
    assert loaded.attrs["schema_version"] == 1
    assert loaded.loc[0, "EndDate"] == dt.date(2027, 1, 1)
    analyzed = opt.analyze_option_chain(
        loaded, risk_free_rate=0.05, valuation_date=dt.date(2026, 1, 1), progress=False
    )
    assert analyzed["ImpliedVolatility"].notna().all()
    assert not list(tmp_path.glob("*.tmp"))
    incomplete_new_pair = frame.copy()
    newer_call = frame.loc[frame["OptionType"].eq("call")].copy()
    newer_call["PairSequence"] = 1
    incomplete_new_pair = pd.concat(
        [incomplete_new_pair, newer_call], ignore_index=True
    )
    with pytest.raises(ValueError, match="one call and one put"):
        opt.save_option_snapshot(
            tmp_path / "invalid.json", incomplete_new_pair, progress=False
        )


def test_history_coverage_snapshot_and_include_today(monkeypatch, tmp_path):
    index = pd.DatetimeIndex(["2025-12-30", "2025-12-31"])
    daily = pd.DataFrame(
        {
            "Open": [8, 9],
            "High": [10, 11],
            "Low": [7, 8],
            "Close": [9, 10],
            "Final": [8.5, 9.5],
            "Volume": [20, 30],
        },
        index=index,
    )
    monkeypatch.setattr(opt, "_stock_history", lambda **kwargs: daily)
    live = market(monkeypatch)
    path = tmp_path / "options.json"
    opt.save_option_snapshot(path, live, progress=False)
    result = opt.get_option_history(
        "ضتست1", snapshot_path=path, include_today=True, progress=False
    )
    assert len(result) == 4
    assert set(result["Source"]) == {
        "tsetmc_price_history",
        "local_user_saved_option_snapshot",
        opt.OPTION_SOURCE,
    }
    assert result.attrs["prices_no_lookahead"] is True
    assert pd.isna(result.attrs["rates_no_lookahead"])
    assert result.attrs["curve_applied"] is False
    assert (
        "local snapshots"
        in result.attrs["source_coverage"]["bid_ask_open_interest_adjustments"]
    )
    historical = result.loc[result["Source"].eq("tsetmc_price_history")]
    assert list(historical["Last"]) == [9, 10]
    assert list(historical["Close"]) == [8.5, 9.5]
    empty_dtypes = opt._empty_history().dtypes.astype(str).to_dict()
    assert result.dtypes.astype(str).to_dict() == empty_dtypes


def test_historical_snapshot_derives_valuation_and_rejects_current_curve(monkeypatch):
    historical_date = dt.date(2025, 1, 1)
    frame = at_date(market(monkeypatch), historical_date)
    result = opt.analyze_option_chain(frame, risk_free_rate=0.05, progress=False)
    assert result.attrs["valuation_date"] == historical_date
    assert result.attrs["valuation_date_source"] == "atomic_snapshot_as_of_date"
    with pytest.raises(ValueError, match="current curve"):
        opt.analyze_option_chain(
            frame,
            yield_curve=FlatCurve(0.05, dt.date(2026, 1, 1)),
            progress=False,
        )
    matched = opt.analyze_option_chain(
        frame, yield_curve=FlatCurve(0.05, historical_date), progress=False
    )
    assert list(matched["RiskFreeRate"]) == pytest.approx([0.05, 0.05])
    with pytest.raises(ValueError, match="AsOf date"):
        opt.analyze_option_chain(
            frame,
            risk_free_rate=0.05,
            valuation_date=dt.date(2025, 1, 2),
            progress=False,
        )


def test_history_request_preflight_and_no_implicit_snapshot_write(
    monkeypatch, tmp_path
):
    called = {"history": False}

    def history(**kwargs):
        called["history"] = True
        return pd.DataFrame()

    monkeypatch.setattr(opt, "_stock_history", history)
    with pytest.raises(ValueError, match="preflight"):
        opt.get_option_history(
            "ضتست1", include_today=True, max_requests=2, progress=False
        )
    assert called["history"] is False
    missing = tmp_path / "never-created.json"
    monkeypatch.setattr(opt, "safe_get", lambda url: Response(paired_payload()))
    opt.get_option_history("ضتست1", snapshot_path=missing, progress=False)
    assert not missing.exists()


def test_empty_schema_and_unavailable_endpoint(monkeypatch):
    monkeypatch.setattr(
        opt, "safe_get", lambda url: Response({"instrumentOptMarketWatch": []})
    )
    frame = opt.get_option_market(progress=False)
    assert list(frame.columns) == opt.OPTION_COLUMNS
    assert str(frame["Stale"].dtype) == "boolean"
    analyzed = opt.analyze_option_chain(frame, risk_free_rate=0.1, progress=False)
    assert analyzed.empty
    assert "ImpliedVolatility" in analyzed


def test_legacy_option_signatures_and_functions_untouched():
    assert (
        str(inspect.signature(instruments.list_options))
        == "(underlying=None, progress=True)"
    )
    assert (
        str(inspect.signature(instruments.get_options_chain))
        == "(underlying, fetch_oi=False, progress=True)"
    )
    assert att.list_options is instruments.list_options
    assert att.get_options_chain is instruments.get_options_chain


def test_official_underlying_ticker_exact_normalized_filter(monkeypatch):
    payload = paired_payload()
    row = payload["instrumentOptMarketWatch"][0]
    row["lval30_UA"] = "كيف"
    row["underlyingName"] = None
    monkeypatch.setattr(opt, "safe_get", lambda url: Response(payload))
    exact = opt.get_option_market(underlying="کیف", progress=False)
    assert len(exact) == 2
    assert exact["UnderlyingSymbol"].eq("كيف").all()
    assert exact["UnderlyingName"].isna().all()
    assert opt.get_option_market(underlying="وبمل", progress=False).empty


def test_quote_iv_gates_and_nullable_inputs(monkeypatch):
    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))
    frame.loc[0, ["BidPrice", "BidVolume"]] = [None, None]
    result = opt.analyze_option_chain(
        frame, risk_free_rate=0.05, valuation_date=dt.date(2026, 1, 1), progress=False
    )
    assert pd.isna(result.loc[0, "ImpliedVolatilityBid"])
    assert result.loc[0, "IVStatusBid"] == "missing_quote"
    assert pd.isna(result.loc[0, "ImpliedVolatilityMid"])
    assert result.loc[0, "IVStatusMid"] == "missing_quote"
    assert result.loc[0, "IVStatusAsk"] == "ok_unverified_freshness"

    strict = opt.analyze_option_chain(
        frame,
        risk_free_rate=0.05,
        valuation_date=dt.date(2026, 1, 1),
        allow_unverified_freshness=False,
        progress=False,
    )
    assert strict["ImpliedVolatility"].isna().all()
    assert strict["AnalyticsComputed"].eq(False).all()


def test_liquidity_all_none_quotes_and_depth_do_not_crash(monkeypatch):
    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))
    frame[["BidPrice", "AskPrice", "BidVolume", "AskVolume"]] = None
    result = opt.analyze_option_chain(
        frame,
        risk_free_rate=0.05,
        valuation_date=dt.date(2026, 1, 1),
        progress=False,
    )
    assert result["SpreadAbs"].isna().all()
    assert result["QuotedDepth"].isna().all()
    assert result["IVStatusBid"].eq("missing_quote").all()
    assert result["IVStatusAsk"].eq("missing_quote").all()


def test_daily_history_missing_volume_keeps_no_trade_unknown():
    daily = pd.DataFrame(
        {"Close": [10], "Final": [9.5], "Volume": [None]},
        index=pd.DatetimeIndex(["2025-12-31"]),
    )
    result = opt._daily_history_rows(daily, "ضتست1", "111")
    assert pd.isna(result.loc[0, "NoTrade"])


def test_missing_asof_requires_explicit_valuation_and_marks_guard(monkeypatch):
    frame = market(monkeypatch)
    frame["AsOf"] = pd.NaT
    with pytest.raises(ValueError, match="valuation_date is required"):
        opt.analyze_option_chain(frame, risk_free_rate=0.05, progress=False)
    result = opt.analyze_option_chain(
        frame,
        risk_free_rate=0.05,
        valuation_date=dt.date(2026, 1, 1),
        progress=False,
    )
    assert result.attrs["observation_date_verified"] is False
    assert result["AnalyticsWarning"].str.contains("observation_as_of_unverified").all()


def test_unknown_no_trade_and_incomplete_pair_diagnostics(monkeypatch):
    payload = paired_payload()
    row = payload["instrumentOptMarketWatch"][0]
    row["qTotTran5J_C"] = None
    row["zTotTran_C"] = None
    frame = market(monkeypatch, payload)
    assert pd.isna(frame.loc[frame["OptionType"].eq("call"), "NoTrade"].iloc[0])
    assert frame["SnapshotFreshnessKnown"].isna().all()

    row.pop("insCode_P")
    malformed = market(monkeypatch, payload)
    assert malformed.empty
    assert malformed.attrs["atomic_snapshot"] is False
    assert malformed.attrs["incomplete_pairs_quarantined"] == 1
    assert malformed.attrs["malformed_pair_status"] == "quarantined"


def test_parity_missing_spread_and_inconsistent_spot_are_unknown(monkeypatch):
    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))
    frame.loc[frame["OptionType"].eq("put"), ["BidPrice", "AskPrice"]] = pd.NA
    result = opt.analyze_option_chain(
        frame, risk_free_rate=0.05, valuation_date=dt.date(2026, 1, 1), progress=False
    )
    assert result["ParityToleranceBand"].isna().all()
    assert result["ParityWithinBand"].isna().all()

    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))
    frame.loc[frame["OptionType"].eq("put"), "UnderlyingClose"] = 101
    frame.loc[frame["OptionType"].eq("put"), "UnderlyingLast"] = 101
    result = opt.analyze_option_chain(
        frame, risk_free_rate=0.05, valuation_date=dt.date(2026, 1, 1), progress=False
    )
    assert result["ParityResidual"].isna().all()
    assert result["ParityStatus"].eq("inconsistent_or_missing_spot").all()


def test_snapshot_writer_lock_timeout_and_cleanup(monkeypatch, tmp_path):
    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))
    path = tmp_path / "locked.json"
    lock = tmp_path / "locked.json.lock"
    lock.write_text("active", encoding="ascii")
    with pytest.raises(TimeoutError, match="writer lock"):
        opt.save_option_snapshot(
            path, frame, progress=False, lock_timeout=0.01, stale_lock_seconds=60
        )
    lock.unlink()
    first = opt.save_option_snapshot(path, frame, progress=False)
    second = opt.save_option_snapshot(path, frame, progress=False)
    assert len(first) == len(second) == 2
    assert not lock.exists()


def test_curve_discount_factor_converted_on_bsm_act365(monkeypatch):
    frame = at_date(market(monkeypatch), dt.date(2026, 1, 1))

    class KnownDiscountCurve:
        settlement_date = dt.date(2026, 1, 1)

        def discount_factor(self, expiry):
            assert expiry == dt.date(2027, 1, 1)
            return 0.9

    result = opt.analyze_option_chain(
        frame,
        yield_curve=KnownDiscountCurve(),
        valuation_date=dt.date(2026, 1, 1),
        progress=False,
    )
    assert result["RiskFreeRate"].eq(-math.log(0.9)).all()
    assert (
        result["RiskFreeRateSource"]
        .eq("yield_curve_discount_factor_act365f_continuous")
        .all()
    )


def test_option_history_exact_resolution_and_underlying_date_join(monkeypatch):
    option_index = pd.DatetimeIndex(["2025-12-30", "2025-12-31"])
    option_daily = pd.DataFrame(
        {"Close": [9, 10], "Final": [8.5, 9.5], "Volume": [20, 30]},
        index=option_index,
    )
    underlying_daily = pd.DataFrame(
        {"Close": [100, 102], "Final": [99, 101], "Volume": [200, 300]},
        index=option_index,
    )
    calls = []

    def history(**kwargs):
        calls.append(kwargs.copy())
        return (
            option_daily if kwargs["_resolved_inscode"] == "111" else underlying_daily
        )

    monkeypatch.setattr(opt, "_stock_history", history)
    monkeypatch.setattr(opt, "safe_get", lambda url: Response(paired_payload()))
    result = opt.get_option_history("ضتست1", progress=False)
    assert [(call["symbol"], call["_resolved_inscode"]) for call in calls] == [
        ("ضتست1", "111"),
        ("تست", "999"),
    ]
    assert list(result["UnderlyingLast"]) == [100, 102]
    assert list(result["UnderlyingClose"]) == [99, 101]
    assert result.attrs["underlying_prices_no_lookahead"] is True
    calls.clear()
    limited = opt.get_option_history("ضتست1", limit=1, progress=False)
    assert [call["limit"] for call in calls] == [1, 0]
    assert list(limited["UnderlyingLast"]) == [102]
    with pytest.raises(ValueError, match="exact option"):
        opt.get_option_history("ضتست", progress=False)
