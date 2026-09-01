"""Offline contract tests for the public industry-index API."""

import ast
import numpy as np
from pathlib import Path

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import industries
from algotik_tse.core import instruments
from algotik_tse.core.market_data import CLIENT_COLUMNS, ORDER_COLUMNS, STOCK_COLUMNS
from algotik_tse.core.search import _INDUSTRY_RAW


CODE = "32453344048876642"
ALT_CODE = "34408080767216529"
ALT_CODE_2 = "19219679288446732"
MEMBER = "12345678901234567"


def test_industry_module_supports_python_38_syntax():
    source = (
        Path(__file__).resolve().parents[1]
        / "algotik_tse"
        / "core"
        / "industries.py"
    ).read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 8))


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _index_rows():
    rows = []
    for number, code in enumerate(_INDUSTRY_RAW, start=1):
        rows.append(
            {
                "insCode": code,
                "dEven": 0,
                "hEven": 123456,
                "xDrNivJIdx004": 1100.0 if code == CODE else 1000.0 + number,
                "xPhNivJIdx004": 1120.0,
                "xPbNivJIdx004": 990.0,
                "xVarIdxJRfV": 10.0 if code == CODE else 1.0,
                "indexChange": 100.0 if code == CODE else 10.0,
                "lVal30": "27-فلزات اساسي" if code == CODE else "{:02d}-صنعت".format(number),
            }
        )
    return rows


def _member_payload(code=CODE, member=MEMBER):
    return {
        "indexCompany": [
            {
                "insCode": member,
                "instrument": {
                    "insCode": member,
                    "lVal18AFC": "فولاد",
                    "lVal30": "فولاد مبارکه اصفهان",
                },
                "priceYesterday": 1000,
                "priceFirst": 1010,
                "priceMin": 990,
                "priceMax": 1110,
                "pClosing": 1080,
                "pDrCotVal": 1100,
                "zTotTran": 20,
                "qTotTran5J": 1000,
                "qTotCap": 1_080_000,
            }
        ],
        "relatedCompanyThirtyDayHistory": [
            {
                "insCode": member,
                "dEven": 20260830,
                "pClosing": 1000,
                "pDrCotVal": 1000,
                "zTotTran": 10,
                "qTotTran5J": 800,
                "qTotCap": 800_000,
            },
            {
                "insCode": member,
                "dEven": 20260831,
                "pClosing": 1080,
                "pDrCotVal": 1100,
                "zTotTran": 20,
                "qTotTran5J": 1000,
                "qTotCap": 1_080_000,
            },
        ],
    }


def _stock_row():
    row = {column: pd.NA for column in STOCK_COLUMNS}
    row.update(
        {
            "InsCode": MEMBER,
            "ISIN": "IRO1FOLD0001",
            "Symbol": "فولاد",
            "Name": "فولاد مبارکه اصفهان",
            "PreviousClose": 1000,
            "Open": 1010,
            "FirstPrice": 1010,
            "Close": 1080,
            "Last": 1100,
            "Low": 990,
            "High": 1110,
            "TradeCount": 20,
            "Volume": 1000,
            "Value": 1_080_000,
            "Flow": 1,
            "SectorCode": "27",
            "MaxAllowed": 1100,
            "MinAllowed": 900,
            "InstrumentType": 300,
            "MarketCode": "NO",
            "SharesOutstanding": 10_000,
            "PreviousCloseChange": 80,
            "PreviousCloseChangePct": 8.0,
        }
    )
    return row


def _snapshot():
    orders = pd.DataFrame(
        [
            {
                "InsCode": MEMBER,
                "Level": 1,
                "AskOrderCount": 3,
                "BidOrderCount": 4,
                "BidPrice": 1100,
                "AskPrice": 1105,
                "BidVolume": 200,
                "AskVolume": 100,
            }
        ],
        columns=ORDER_COLUMNS,
    )
    return {
        "stocks": pd.DataFrame([_stock_row()], columns=STOCK_COLUMNS),
        "order_book": orders,
        "trade_date": pd.Timestamp("2026-08-31").date(),
        "exchange_time": pd.Timestamp("2026-08-31 12:30", tz="Asia/Tehran"),
        "fetched_at": pd.Timestamp("2026-08-31 12:30", tz="Asia/Tehran"),
        "is_realtime_fresh": True,
        "is_today_trade_date": True,
        "is_previous_trade_date": False,
        "is_stale": False,
    }


def _client():
    row = {column: 0 for column in CLIENT_COLUMNS}
    row.update(
        {
            "InsCode": MEMBER,
            "Buy_I_Count": 2,
            "Buy_N_Count": 1,
            "Buy_I_Volume": 700,
            "Buy_N_Volume": 300,
            "Sell_I_Count": 4,
            "Sell_N_Count": 1,
            "Sell_I_Volume": 600,
            "Sell_N_Volume": 400,
            "Net_I_Volume": 100,
            "Net_N_Volume": -100,
        }
    )
    return pd.DataFrame([row], columns=CLIENT_COLUMNS)


def _industry_history_frame(code, name, closes):
    closes = [float(value) for value in closes]
    trade_dates = [
        pd.Timestamp("2026-08-29"),
        pd.Timestamp("2026-08-30"),
        pd.Timestamp("2026-08-31"),
    ]
    changes = [pd.NA]
    change_pcts = [pd.NA]
    log_returns = [0.0]
    for previous, current in zip(closes[:-1], closes[1:]):
        delta = current - previous
        changes.append(delta)
        if previous:
            change_pcts.append((delta / previous) * 100)
        else:
            change_pcts.append(pd.NA)
        if previous:
            log_returns.append(np.log(current / previous))
        else:
            log_returns.append(pd.NA)
    return pd.DataFrame(
        {
            "IndustryName": [name, name, name],
            "IndustryIndexCode": [code, code, code],
            "TradeDate": trade_dates,
            "JalaliDate": [
                industries._jalali(trade_dates[0]),
                industries._jalali(trade_dates[1]),
                industries._jalali(trade_dates[2]),
            ],
            "High": [value * 1.01 for value in closes],
            "Low": [value * 0.99 for value in closes],
            "Close": closes,
            "Change": changes,
            "ChangePct": change_pcts,
            "LogReturn": log_returns,
        }
    )


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    industries._MEMBERSHIP_CACHE.clear()
    monkeypatch.setattr(industries.settings, "industry_membership_cache_ttl", 3600.0)


@pytest.fixture
def provider(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "GetIndexB1LastAll" in url:
            return _Response({"indexB1": _index_rows()})
        if "GetIndexCompany" in url:
            code = url.rsplit("/", 1)[-1]
            member = MEMBER if code == CODE else "9" + code[:-1]
            return _Response(_member_payload(code=code, member=member))
        if "GetIndexB2History" in url:
            return _Response(
                {
                    "indexB2": [
                        {
                            "insCode": CODE,
                            "dEven": 20260829,
                            "xNivInuClMresIbs": 900,
                            "xNivInuPbMresIbs": 880,
                            "xNivInuPhMresIbs": 920,
                        },
                        {
                            "insCode": CODE,
                            "dEven": 20260830,
                            "xNivInuClMresIbs": 1000,
                            "xNivInuPbMresIbs": 890,
                            "xNivInuPhMresIbs": 1010,
                        },
                        {
                            "insCode": CODE,
                            "dEven": 20260831,
                            "xNivInuClMresIbs": 1100,
                            "xNivInuPbMresIbs": 990,
                            "xNivInuPhMresIbs": 1120,
                        },
                    ]
                }
            )
        if "GetIndexB1LastDay" in url:
            return _Response(
                {
                    "indexB1": [
                        {
                            "dEven": 20260831,
                            "hEven": 90000,
                            "xDrNivJIdx004": 1000,
                            "indexChange": 0,
                            "xVarIdxJRfV": 0,
                        },
                        {
                            "dEven": 20260831,
                            "hEven": 90100,
                            "xDrNivJIdx004": 1100,
                            "indexChange": 100,
                            "xVarIdxJRfV": 10,
                        },
                    ]
                }
            )
        raise AssertionError("unexpected URL: " + url)

    monkeypatch.setattr(industries, "safe_get", fake_get)
    monkeypatch.setattr(industries, "market_watch", _snapshot)
    monkeypatch.setattr(industries, "market_client_type", _client)
    return calls


def test_list_industry_indices_corrects_point_and_percentage_semantics(provider):
    result = att.list_industry_indices(progress=False)
    assert list(result.columns) == industries.INDUSTRY_INDEX_COLUMNS
    assert len(result) == 45
    metals = result.loc[result["IndexInsCode"] == CODE].iloc[0]
    assert metals["IndustryName"] == "فلزات اساسی"
    assert metals["IndustryGroupCode"] == "27"
    assert metals["IndexChange"] == 100
    assert metals["IndexChangePct"] == 10
    assert metals["IndexPreviousValue"] == 1000
    assert pd.isna(metals["MemberCount"])
    assert result.attrs["member_count_requested"] is False


def test_list_industry_indices_can_fetch_and_cache_member_counts(provider):
    result = att.list_industry_indices(
        progress=False, include_member_count=True, max_workers=1
    )
    assert result["MemberCount"].eq(1).all()
    assert result["HasMembers"].all()
    assert result.attrs["membership_source"] == "GetIndexCompany"


def test_get_industry_members_uses_exact_identity_and_opt_in_enrichment(provider):
    result = att.get_industry_members(
        "فلزات اساسی",
        include_live=True,
        include_client_type=True,
        include_orderbook=True,
        progress=False,
    )
    assert list(result.columns) == industries.INDUSTRY_MEMBER_COLUMNS
    row = result.iloc[0]
    assert row["InsCode"] == MEMBER
    assert row["SectorCode"] == "27"
    assert row["ChangePct"] == 8
    assert row["ClientDataAvailable"]
    assert row["NetIndividualVolume"] == 100
    assert row["EstimatedNetIndividualFlow"] == 108_000
    assert row["EstimatedBuyQueueValue"] == 220_000
    assert row["IsRealtimeFresh"]
    assert result.attrs["universe"] == "exact_index_members"


def test_membership_cache_and_refresh_are_observable(provider):
    first = att.get_industry_members("فلزات", include_live=False, progress=False)
    second = att.get_industry_members("فلزات", include_live=False, progress=False)
    third = att.get_industry_members(
        "فلزات", include_live=False, progress=False, refresh=True
    )
    membership_calls = [url for url in provider if "GetIndexCompany" in url]
    assert len(membership_calls) == 2
    assert first.attrs["cache_hit"] is False
    assert second.attrs["cache_hit"] is True
    assert third.attrs["cache_hit"] is False


def test_industry_snapshot_exposes_breadth_flow_queue_and_provenance(provider):
    result = att.get_industry_snapshot(
        "فلزات اساسی",
        include_client_type=True,
        include_orderbook=True,
        progress=False,
    )
    assert list(result.columns) == industries.INDUSTRY_SNAPSHOT_COLUMNS
    row = result.iloc[0]
    assert row["IndexChange"] == 100
    assert row["IndexChangePct"] == 10
    assert row["MemberCount"] == 1
    assert row["Advances"] == 1
    assert row["AdvancePct"] == 100
    assert row["EqualWeightReturn"] == pytest.approx(10)
    assert row["EstimatedNetIndividualValue"] == 108_000
    assert row["IndividualPower"] == pytest.approx((700 / 2) / (600 / 4))
    assert row["BuyQueueCount"] == 1
    assert row["BuyQueueValue"] == 220_000
    assert row["MarketValueSharePct"] == 100
    assert result.attrs["historical_membership_available"] is False
    assert result.attrs["memberships_may_overlap"] is True


def test_industry_daily_history_filters_then_limits(provider):
    result = att.get_industry_history(
        "فلزات",
        start="1405-06-08",
        limit=2,
        ascending=False,
        progress=False,
    )
    assert list(result.columns) == industries.INDUSTRY_HISTORY_COLUMNS
    assert result["TradeDate"].tolist() == [
        pd.Timestamp("2026-08-31"),
        pd.Timestamp("2026-08-30"),
    ]
    assert result.iloc[0]["Change"] == 100
    assert result.iloc[0]["ChangePct"] == pytest.approx(10)
    assert "Volume" not in result
    assert result.attrs["volume_available"] is False


def test_member_history_is_long_form_and_warns_about_survivorship(provider):
    result = att.get_industry_members_history(
        "فلزات", days=1, progress=False
    )
    assert list(result.columns) == industries.INDUSTRY_MEMBER_HISTORY_COLUMNS
    assert len(result) == 1
    assert result.iloc[0]["TradeDate"] == pd.Timestamp("2026-08-31")
    assert result.iloc[0]["ChangePct"] == pytest.approx(8)
    assert result.attrs["point_in_time_membership"] is False
    assert result.attrs["survivorship_bias_possible"] is True


def test_compare_industries_builds_wide_panel_and_applies_limit_descending(monkeypatch):
    history_map = {
        CODE: [1000, 1100, 1200],
        ALT_CODE: [2000, 2100, 2200],
    }

    def fake_history_frames(resolved, start_date=None, end_date=None, max_workers=6):
        frames = {}
        for code, name, _ in resolved:
            closes = history_map.get(code)
            if closes is None:
                closes = [1000, 1010, 1020]
            frames[code] = _industry_history_frame(code, name, closes)
        return frames

    monkeypatch.setattr(industries, "_industry_history_frames", fake_history_frames)
    result = att.compare_industries(
        [CODE, ALT_CODE],
        limit=2,
        ascending=False,
        progress=False,
        max_workers=1,
    )
    expected_columns = [
        "TradeDate",
        "JalaliDate",
        industries._compare_columns_label(industries._canonical_name(CODE), CODE),
        industries._compare_columns_label(industries._canonical_name(ALT_CODE), ALT_CODE),
    ]
    assert list(result.columns) == expected_columns
    assert result.attrs["analysis"] == "compare_industries"
    assert result.attrs["industry_count"] == 2
    assert len(result) == 2
    assert result.iloc[0]["TradeDate"] == pd.Timestamp("2026-08-31")


def test_relative_strength_uses_benchmark_and_limits_per_industry(monkeypatch):
    history_map = {
        CODE: [1000, 1100, 1210],
        ALT_CODE: [2000, 2300, 2650],
        ALT_CODE_2: [5000, 5100, 5300],
    }

    def fake_history_frames(resolved, start_date=None, end_date=None, max_workers=6):
        frames = {}
        for code, name, _ in resolved:
            closes = history_map.get(code, [1000, 1010, 1020])
            frames[code] = _industry_history_frame(code, name, closes)
        return frames

    monkeypatch.setattr(industries, "_industry_history_frames", fake_history_frames)
    result = att.get_industry_relative_strength(
        [CODE, ALT_CODE],
        benchmark=ALT_CODE_2,
        limit=1,
        ascending=False,
        progress=False,
        max_workers=1,
    )
    result_price = att.get_industry_relative_strength(
        [CODE, ALT_CODE],
        benchmark=ALT_CODE_2,
        limit=1,
        metric="price",
        ascending=False,
        progress=False,
        max_workers=1,
    )
    assert result.attrs["analysis"] == "industry_relative_strength"
    assert result.attrs["industry_count"] == 2
    assert result.attrs["benchmark_index_code"] == ALT_CODE_2
    assert list(result.columns) == [
        "TradeDate",
        "JalaliDate",
        "BenchmarkIndexCode",
        "BenchmarkName",
        "IndustryIndexCode",
        "IndustryName",
        "IndustryReturn",
        "BenchmarkReturn",
        "RelativeStrength",
    ]
    assert len(result) == 2
    assert result_price[["IndustryReturn", "BenchmarkReturn", "RelativeStrength"]].equals(
        result[["IndustryReturn", "BenchmarkReturn", "RelativeStrength"]]
    )


def test_industry_correlation_generates_sorted_matrix_with_diagonal_one(monkeypatch):
    history_map = {
        CODE: [1000, 1100, 1210],
        ALT_CODE: [2000, 2200, 2420],
        ALT_CODE_2: [1200, 1320, 1452],
    }

    def fake_history_frames(resolved, start_date=None, end_date=None, max_workers=6):
        frames = {}
        for code, name, _ in resolved:
            closes = history_map.get(code, [1000, 1010, 1020])
            frames[code] = _industry_history_frame(code, name, closes)
        return frames

    monkeypatch.setattr(industries, "_industry_history_frames", fake_history_frames)
    result = att.get_industry_correlation(
        [CODE, ALT_CODE, ALT_CODE_2],
        ascending=False,
        progress=False,
        max_workers=1,
    )
    expected_labels = [
        industries._compare_columns_label(industries._canonical_name(CODE), CODE),
        industries._compare_columns_label(industries._canonical_name(ALT_CODE), ALT_CODE),
        industries._compare_columns_label(
            industries._canonical_name(ALT_CODE_2), ALT_CODE_2
        ),
    ]
    expected_labels = list(reversed(expected_labels))
    assert list(result.index) == expected_labels
    assert list(result.columns) == expected_labels
    assert result.shape == (3, 3)
    assert result.loc[expected_labels[0], expected_labels[0]] == pytest.approx(1.0)
    assert result.loc[expected_labels[1], expected_labels[1]] == pytest.approx(1.0)
    assert result.loc[expected_labels[2], expected_labels[2]] == pytest.approx(1.0)


def test_new_industry_analytics_validate_inputs(monkeypatch):
    monkeypatch.setattr(industries, "_industry_history_frames", lambda *args, **kwargs: {})
    with pytest.raises(att.InvalidParameterError):
        att.compare_industries(CODE, metric="invalid", progress=False)
    with pytest.raises(att.InvalidParameterError):
        att.get_industry_relative_strength(
            [CODE], benchmark=ALT_CODE, max_workers=99, progress=False
        )
    with pytest.raises(att.InvalidParameterError):
        att.get_industry_correlation(CODE, ascending="yes", progress=False)


def test_intraday_raw_and_resampled_candles_have_no_volume(provider):
    raw = att.get_industry_intraday("فلزات", interval="raw", progress=False)
    candle = att.get_industry_intraday("فلزات", interval="5min", progress=False)
    assert list(raw.columns) == industries.INDUSTRY_INTRADAY_COLUMNS
    assert len(raw) == 2
    assert len(candle) == 1
    assert candle.iloc[0]["Open"] == 1000
    assert candle.iloc[0]["High"] == 1100
    assert candle.iloc[0]["Close"] == 1100
    assert "Volume" not in candle
    assert candle.attrs["synthetic_volume"] is False
    assert str(candle.iloc[0]["Timestamp"].tz) == "Asia/Tehran"


def test_rank_industries_supports_aliases_and_stable_rank(monkeypatch):
    frame = pd.DataFrame(
        [
            {"IndustryName": "الف", "AdvancePct": 25.0},
            {"IndustryName": "ب", "AdvancePct": 75.0},
        ]
    ).reindex(columns=industries.INDUSTRY_SNAPSHOT_COLUMNS)
    frame.attrs["source"] = "fixture"
    monkeypatch.setattr(industries, "get_industry_snapshot", lambda **_: frame)
    ranked = att.rank_industries(metric="breadth", top=1, progress=False)
    assert ranked.iloc[0]["IndustryName"] == "ب"
    assert ranked.iloc[0]["Rank"] == 1
    assert ranked.attrs["ranking_metric"] == "AdvancePct"


def test_industry_parameter_validation_is_typed(provider):
    with pytest.raises(att.StockNotFoundError):
        att.get_industry_history("صنعت ساختگی", progress=False)
    with pytest.raises(att.InvalidParameterError):
        att.get_industry_members("فلزات", include_live=False, include_orderbook=True)
    with pytest.raises(att.InvalidParameterError):
        att.get_industry_members_history("فلزات", days=31, progress=False)
    with pytest.raises(att.InvalidParameterError):
        att.get_industry_intraday("فلزات", interval="2min", progress=False)
    with pytest.raises(att.InvalidParameterError):
        att.rank_industries(metric="official_weight", progress=False)


def test_legacy_list_indices_change_columns_are_no_longer_reversed(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "safe_get",
        lambda *_: _Response({"indexB1": [_index_rows()[0]]}),
    )
    result = instruments.list_indices(progress=False)
    assert result.iloc[0]["Change"] == 10
    assert result.iloc[0]["ChangePct"] == 1
