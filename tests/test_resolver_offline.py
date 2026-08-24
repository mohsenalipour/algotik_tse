import ast
import datetime
import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import market_data
from algotik_tse.core import resolver
from algotik_tse.exceptions import (
    AmbiguousSymbolError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)


class Response:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = 200

    def json(self):
        return self._payload


def search_response(*rows):
    return Response({"instrumentSearch": list(rows)})


def info_response(ins_code="111", symbol="الف", name="شرکت الف", yval=300):
    return Response(
        {
            "instrumentInfo": {
                "insCode": ins_code,
                "lVal18AFC": symbol,
                "lVal30": name,
                "yVal": yval,
            }
        }
    )


def test_instrument_ref_is_frozen_without_slots():
    source = Path(resolver.__file__).read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 8))
    ref = att.InstrumentRef("1")
    assert "__slots__" not in att.InstrumentRef.__dict__
    with pytest.raises(FrozenInstanceError):
        ref.ins_code = "2"


def test_exact_ticker_beats_legacy_industry_and_explicit_industry_wins(monkeypatch):
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: search_response(
            {
                "insCode": "65883838195688438",
                "lVal18AFC": "خودرو",
                "lVal30": "ایران خودرو",
                "type": "سهام",
                "isActive": True,
            }
        ),
    )
    equity = att.resolve_instrument("خودرو")
    industry = att.resolve_instrument("شاخص خودرو")
    requested = att.resolve_instrument("خودرو", asset_type="industry")
    assert equity.ins_code == "65883838195688438"
    assert equity.asset_type == "equity"
    assert industry.ins_code == requested.ins_code == "20213770409093165"
    assert industry.asset_type == requested.asset_type == "industry"


def test_full_name_normalization_and_no_fuzzy_first_hit(monkeypatch):
    responses = {
        "ایران خودرو": [
            {"insCode": "1", "lVal18AFC": "خاور", "lVal30": "ایران خودرو دیزل"},
            {
                "insCode": "65883838195688438",
                "lVal18AFC": "خودرو",
                "lVal30": "ایران‌ خودرو",
            },
        ],
        "قند": [{"insCode": "2", "lVal18AFC": "قشهد", "lVal30": "قند خوی"}],
        "فلزات": [{"insCode": "3", "lVal18AFC": "فملی", "lVal30": "ملی مس"}],
    }
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda url: search_response(*next(v for k, v in responses.items() if k in url)),
    )
    assert att.resolve_instrument("ایران خودرو").ins_code == "65883838195688438"
    with pytest.raises(StockNotFoundError):
        att.resolve_instrument("قند")
    with pytest.raises(StockNotFoundError):
        att.resolve_instrument("فلزات")


@pytest.mark.parametrize(
    ("selector", "wire"),
    [("فملی", "فملي"), ("فملي", "فملی"), ("کگل", "كگل"), ("كگل", "کگل")],
)
def test_arabic_persian_variants(selector, wire, monkeypatch):
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: search_response({"insCode": "1", "lVal18AFC": wire, "lVal30": "نام"}),
    )
    assert att.resolve_instrument(selector).ins_code == "1"


def test_active_preference_ambiguity_and_explicit_code_contract(monkeypatch):
    rows = [
        {"insCode": "1", "lVal18AFC": "الف", "isActive": False},
        {"insCode": "2", "lVal18AFC": "الف", "isActive": True},
    ]
    monkeypatch.setattr(resolver, "safe_get", lambda _: search_response(*rows))
    assert att.resolve_instrument("الف").ins_code == "2"
    rows.append({"insCode": "3", "lVal18AFC": "الف", "isActive": True})
    with pytest.raises(AmbiguousSymbolError):
        att.resolve_instrument("الف")
    with pytest.raises(InvalidParameterError):
        att.resolve_instrument("الف", ins_code="9")

    calls = []

    def explicit_info(url):
        calls.append(url)
        return info_response("65883838195688438", "خودرو", "ایران خودرو", 300)

    monkeypatch.setattr(resolver, "safe_get", explicit_info)
    explicit = att.resolve_instrument(ins_code="65883838195688438")
    assert explicit.ins_code == "65883838195688438"
    assert explicit.symbol == "خودرو"
    assert explicit.asset_type == "equity"
    assert len(calls) == 1


def _snapshot(rows):
    stocks = pd.DataFrame(rows).reindex(columns=market_data.STOCK_COLUMNS)
    now = pd.Timestamp.now(tz="Asia/Tehran")
    return {
        "stocks": stocks,
        "order_book": pd.DataFrame(columns=market_data.ORDER_COLUMNS),
        "trade_date": now.date(),
        "market_state": "A",
        "exchange_time": now,
        "fetched_at": now,
        "snapshot_age_seconds": 0.0,
        "is_today_trade_date": True,
        "is_history_eligible": not stocks.empty,
        "is_realtime_fresh": True,
        "is_previous_trade_date": False,
        "is_stale": False,
        "is_partial": pd.NA,
        "migration": {},
    }


def test_live_market_missing_attrs_and_strict(monkeypatch):
    snapshot = _snapshot([{"InsCode": "1", "Symbol": "الف", "Name": "شرکت الف"}])
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(
        market_data,
        "market_client_type",
        lambda: pd.DataFrame(columns=market_data.CLIENT_COLUMNS),
    )
    result = market_data.get_live_market(["الف", "مفقود"])
    assert result["InsCode"].tolist() == ["1"]
    assert result.attrs["missing_selectors"] == ["مفقود"]
    with pytest.raises(StockNotFoundError):
        market_data.get_live_market(["الف", "مفقود"], strict=True)


def test_empty_live_snapshot_is_authoritative_and_never_searches(monkeypatch):
    snapshot = _snapshot([])
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(
        market_data,
        "market_client_type",
        lambda: pd.DataFrame(columns=market_data.CLIENT_COLUMNS),
    )
    monkeypatch.setattr(
        resolver, "safe_get", lambda _: pytest.fail("no per-selector request allowed")
    )
    result = market_data.get_live_market(["الف", "الف"])
    assert result.empty
    assert result.attrs["missing_selectors"] == ["الف"]


@pytest.mark.parametrize(
    ("trade_count", "volume", "state_title"),
    [(0, 0, "مجاز"), (1, 100, "متوقف")],
)
def test_point_fallback_is_non_actionable_for_no_trade_or_halt(
    monkeypatch, trade_count, volume, state_title
):
    snapshot = _snapshot([])
    now = pd.Timestamp.now(tz="Asia/Tehran")
    payload = {
        "closingPriceInfo": {
            "insCode": 0,
            "dEven": int(now.strftime("%Y%m%d")),
            "hEven": int(now.strftime("%H%M%S")),
            "pClosing": 100,
            "pDrCotVal": 101,
            "priceYesterday": 99,
            "zTotTran": trade_count,
            "qTotTran5J": volume,
            "qTotCap": volume * 100,
            "priceMin": 98,
            "priceMax": 102,
            "instrumentState": {"cEtaval": "A", "cEtavalTitle": state_title},
        }
    }
    monkeypatch.setattr(market_data, "market_watch", lambda: snapshot)
    monkeypatch.setattr(
        market_data,
        "market_client_type",
        lambda: pd.DataFrame(columns=market_data.CLIENT_COLUMNS),
    )
    monkeypatch.setattr(market_data, "safe_get", lambda _: Response(payload))
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: info_response("111", "الف", "شرکت الف", 300),
    )
    result = market_data.get_live_symbol(ins_code="111", fallback="point")
    row = result.iloc[0]
    assert row["InsCode"] == "111"
    assert row["SnapshotSource"] == "closing_price_info_fallback"
    assert not row["PresentInMarketWatch"]
    assert not row["PriceActionable"]
    assert row["FallbackReason"] == "absent_from_market_watch"
    assert not row["IdentityVerified"]
    assert pd.isna(row["IndividualPower"])
    assert pd.isna(row["BidPrice1"])


def test_get_history_accepts_explicit_ins_code_without_changing_ohlcv(monkeypatch):
    stock_module = importlib.import_module("algotik_tse.core.stock")
    csv = (
        "<TICKER>,<DTYYYYMMDD>,<FIRST>,<HIGH>,<LOW>,<CLOSE>,<VALUE>,"
        "<VOL>,<OPENINT>,<OPEN>,<LAST>,<PER>,<OPENINT>\n"
        "TEST,20260823,100,115,95,110,110000,1000,10,90,112,D,10"
    )
    monkeypatch.setattr(stock_module, "safe_get", lambda _: Response(text=csv))
    result = att.get_history(
        ins_code="111", date_format="gregorian", progress=False, auto_adjust=False
    )
    assert list(result.columns) == [
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
    ]
    assert result.iloc[0]["Close"] == 112


def test_asset_type_real_fields_fail_closed_and_lastdate_merge(monkeypatch):
    rows = [
        {
            "insCode": "10",
            "lVal18AFC": "خاور",
            "lVal30": "ایران خودرو دیزل",
            "lastDate": 0,
            "yVal": 300,
        },
        {
            "insCode": "10",
            "lVal18AFC": "خاور",
            "lVal30": "ایران خودرو دیزل",
            "lastDate": 1,
            "yVal": 300,
        },
    ]
    monkeypatch.setattr(resolver, "safe_get", lambda _: search_response(*rows))
    ref = att.resolve_instrument("خاور", asset_type="equity")
    assert ref.ins_code == "10"
    assert ref.asset_type == "equity"
    assert ref.is_active is True

    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda url: (
            search_response({"insCode": "20", "lVal18AFC": "صندوق", "lastDate": 1})
            if "GetInstrumentSearch" in url
            else info_response("20", "صندوق", "صندوق نمونه", 305)
        ),
    )
    assert att.resolve_instrument("صندوق", asset_type="fund").asset_type == "fund"

    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda url: (
            search_response({"insCode": "30", "lVal18AFC": "ناشناخته", "lastDate": 1})
            if "GetInstrumentSearch" in url
            else info_response("30", "ناشناخته", "ناشناخته", 999)
        ),
    )
    with pytest.raises(InvalidParameterError):
        att.resolve_instrument("ناشناخته", asset_type="fund")


def test_instrument_info_requires_exact_authoritative_inscode(monkeypatch):
    missing_id = Response(
        {
            "instrumentInfo": {
                "lVal18AFC": "نماد اشتباه",
                "lVal30": "نام اشتباه",
                "yVal": 300,
            }
        }
    )
    monkeypatch.setattr(resolver, "safe_get", lambda _: missing_id)
    with pytest.raises(DataParsingError):
        att.resolve_instrument(ins_code="111")

    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: info_response("999", "الف", "شرکت الف", 300),
    )
    with pytest.raises(DataParsingError):
        att.resolve_instrument(ins_code="111")


def test_requested_type_enriches_every_unknown_exact_rival(monkeypatch):
    rows = [
        {
            "insCode": "10",
            "lVal18AFC": "صندوق",
            "lastDate": 1,
            "yVal": 305,
        },
        {"insCode": "20", "lVal18AFC": "صندوق", "lastDate": 1},
    ]
    calls = []

    def fake_get(url):
        calls.append(url)
        if "GetInstrumentSearch" in url:
            return search_response(*rows)
        return info_response("20", "صندوق", "صندوق دوم", 305)

    monkeypatch.setattr(resolver, "safe_get", fake_get)
    with pytest.raises(AmbiguousSymbolError):
        att.resolve_instrument("صندوق", asset_type="fund")
    assert sum("Instrument/GetInstrumentInfo" in url for url in calls) == 1


def test_explicit_code_filters_rivals_before_type_enrichment(monkeypatch):
    rows = [
        {
            "insCode": "10",
            "lVal18AFC": "الف",
            "lVal30": "صندوق",
            "lastDate": 1,
        },
        {"insCode": "20", "lVal18AFC": "صندوق", "lastDate": 1},
    ]
    calls = []

    def fake_get(url):
        calls.append(url)
        if "GetInstrumentSearch" in url:
            return search_response(*rows)
        if url.endswith("/10"):
            return info_response("10", "الف", "صندوق", 305)
        return info_response("999", "صندوق", "هویت نامعتبر", 305)

    monkeypatch.setattr(resolver, "safe_get", fake_get)
    ref = att.resolve_instrument("صندوق", ins_code="10", asset_type="fund")
    assert ref.ins_code == "10"
    assert ref.asset_type == "fund"
    assert sum("Instrument/GetInstrumentInfo" in url for url in calls) == 1
    assert not any(url.endswith("/20") for url in calls)


@pytest.mark.parametrize(("last_date", "expected_active"), [(1, True), (None, None)])
def test_explicit_code_accepts_authoritative_active_or_omitted_status(
    monkeypatch, last_date, expected_active
):
    payload = info_response("111", "الف", "شرکت الف", 300)._payload
    if last_date is not None:
        payload["instrumentInfo"]["lastDate"] = last_date
    monkeypatch.setattr(resolver, "safe_get", lambda _: Response(payload))
    ref = att.resolve_instrument(ins_code="111", require_active=True)
    assert ref.is_active is expected_active


def test_explicit_code_rejects_authoritative_inactive_status(monkeypatch):
    payload = info_response("111", "الف", "شرکت الف", 300)._payload
    payload["instrumentInfo"]["lastDate"] = 0
    monkeypatch.setattr(resolver, "safe_get", lambda _: Response(payload))
    with pytest.raises(StockNotFoundError):
        att.resolve_instrument(ins_code="111", require_active=True)
    ref = att.resolve_instrument(ins_code="111", require_active=False)
    assert ref.is_active is False


def test_active_merge_false_plus_unknown_stays_inactive(monkeypatch):
    rows = [
        {"insCode": "10", "lVal18AFC": "خاور", "lastDate": 0, "yVal": 300},
        {"insCode": "10", "lVal18AFC": "خاور", "yVal": 300},
    ]
    monkeypatch.setattr(resolver, "safe_get", lambda _: search_response(*rows))
    with pytest.raises(StockNotFoundError):
        att.resolve_instrument("خاور")
    ref = att.resolve_instrument("خاور", require_active=False)
    assert ref.is_active is False


@pytest.mark.parametrize("code", [306, 706])
def test_verified_bond_type_codes_and_textual_fallback(code):
    assert resolver._asset_type_from_row({"yVal": code}) == "bond"
    assert (
        resolver._asset_type_from_row({"InstrumentType": 999, "typeName": "اوراق بدهی"})
        == "bond"
    )


def test_local_index_and_industry_inscodes_route_without_resolver_network(
    monkeypatch,
):
    search_module = importlib.import_module("algotik_tse.core.search")
    stock_module = importlib.import_module("algotik_tse.core.stock")
    index_code = "32097828799138957"
    industry_code = "20213770409093165"
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: pytest.fail("known local codes must not call resolver provider"),
    )
    assert att.resolve_instrument(ins_code=index_code).asset_type == "index"
    assert att.resolve_instrument(ins_code=industry_code).asset_type == "industry"
    assert search_module.search_stock(index_code) == index_code + "index"
    assert search_module.search_stock(industry_code) == industry_code + "industry"

    def history_response(url):
        if industry_code in url:
            return Response(
                {
                    "indexB2": [
                        {
                            "dEven": 20260823,
                            "xNivInuClMresIbs": 100,
                            "xNivInuPhMresIbs": 110,
                            "xNivInuPbMresIbs": 90,
                        }
                    ]
                }
            )
        return Response(text="20260823,110,90,100,105,1000,104")

    monkeypatch.setattr(stock_module, "safe_get", history_response)
    index_history = att.get_history(
        ins_code=index_code,
        date_format="gregorian",
        progress=False,
        auto_adjust=False,
    )
    industry_history = att.get_history(
        ins_code=industry_code,
        date_format="gregorian",
        progress=False,
        auto_adjust=False,
    )
    assert list(index_history.columns) == [
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
    ]
    assert list(industry_history.columns) == ["High", "Low", "Close"]


@pytest.mark.parametrize("invalid", ["0", "123456789012345678901", "۱۲۳", "١٢٣"])
def test_numeric_fast_paths_share_canonical_inscode_validation(invalid):
    search_module = importlib.import_module("algotik_tse.core.search")
    with pytest.raises(InvalidParameterError):
        att.resolve_instrument(invalid)
    with pytest.raises(InvalidParameterError):
        search_module.search_stock(invalid)
    with pytest.raises(InvalidParameterError):
        search_module.search_stock_symbol(invalid)


def test_full_name_uses_one_bounded_alternate_query(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "ایران خودرو" in url:
            return search_response()
        return search_response(
            {
                "insCode": "65883838195688438",
                "lVal18AFC": "خودرو",
                "lVal30": "ایران‌ خودرو",
                "lastDate": 1,
                "yVal": 300,
            }
        )

    monkeypatch.setattr(resolver, "safe_get", fake_get)
    assert att.resolve_instrument("ایران خودرو").ins_code == "65883838195688438"
    assert len(calls) == 2
    assert calls[-1].endswith("/خودرو")
    assert att.normalize_instrument_text(pd.NA) == ""


def test_point_identity_mismatch_and_normal_fallback_schema_parity(monkeypatch):
    now = pd.Timestamp.now(tz="Asia/Tehran")
    normal_snapshot = _snapshot(
        [
            {
                "InsCode": "111",
                "Symbol": "الف",
                "Name": "شرکت الف",
                "TradeCount": 1,
                "Volume": 100,
                "Close": 100,
                "Last": 101,
                "PreviousClose": 99,
            }
        ]
    )
    empty_snapshot = _snapshot([])
    monkeypatch.setattr(
        market_data,
        "market_client_type",
        lambda: pd.DataFrame(columns=market_data.CLIENT_COLUMNS),
    )
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: info_response("111", "الف", "شرکت الف", 300),
    )
    monkeypatch.setattr(market_data, "market_watch", lambda: normal_snapshot)
    normal = market_data.get_live_symbol("الف")

    point = {
        "closingPriceInfo": {
            "insCode": "111",
            "dEven": int(now.strftime("%Y%m%d")),
            "hEven": int(now.strftime("%H%M%S")),
            "pClosing": 100,
            "pDrCotVal": 101,
            "priceYesterday": 99,
            "zTotTran": 1,
            "qTotTran5J": 100,
            "qTotCap": 10000,
            "priceMin": 99,
            "priceMax": 101,
            "instrumentState": {"cEtaval": "A", "cEtavalTitle": "مجاز"},
        }
    }
    monkeypatch.setattr(market_data, "market_watch", lambda: empty_snapshot)
    monkeypatch.setattr(market_data, "safe_get", lambda _: Response(point))
    fallback = market_data.get_live_symbol(ins_code="111", fallback="point")
    assert list(normal.columns) == list(fallback.columns)
    assert normal.dtypes.astype(str).to_dict() == fallback.dtypes.astype(str).to_dict()
    for column in (
        "Time",
        "Value",
        "Low",
        "High",
        "PriceYesterday",
        "Change",
        "PreviousCloseChange",
    ):
        assert normal[column].dtype == fallback[column].dtype
    assert normal.iloc[0]["SnapshotSource"] == "market_watch"
    assert fallback.iloc[0]["IdentityVerified"]

    point["closingPriceInfo"]["insCode"] = "999"
    with pytest.raises(DataParsingError):
        market_data.get_live_symbol(ins_code="111", fallback="point")


def test_inscode_introduction_is_blocked_before_resolution(monkeypatch):
    detail_module = importlib.import_module("algotik_tse.core.stock_detail")
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: pytest.fail("resolver network called"),
    )
    urls = []

    def publisher(url):
        urls.append(url)
        pytest.fail("publisher network called")

    monkeypatch.setattr(detail_module, "safe_get", publisher)
    with pytest.raises(att.UnsupportedDataSourceError):
        att.get_introduction(ins_code="111")
    assert not urls


def test_intraday_explicit_symbol_and_inscode_mismatch(monkeypatch):
    intraday_module = importlib.import_module("algotik_tse.core.intraday")
    monkeypatch.setattr(
        resolver,
        "safe_get",
        lambda _: search_response(
            {
                "insCode": "2",
                "lVal18AFC": "الف",
                "lVal30": "شرکت الف",
                "lastDate": 1,
                "yVal": 300,
            }
        ),
    )
    monkeypatch.setattr(
        intraday_module,
        "safe_get",
        lambda _: pytest.fail("trade endpoint must not run after mismatch"),
    )
    with pytest.raises(InvalidParameterError):
        att.get_intraday("الف", ins_code="1", progress=False)


def test_live_orderbook_exact_duplicate_and_missing_selector_contract(monkeypatch):
    duplicate = _snapshot(
        [
            {"InsCode": "1", "Symbol": "الف", "Name": "الف یک"},
            {"InsCode": "2", "Symbol": "الف", "Name": "الف دو"},
        ]
    )
    monkeypatch.setattr(market_data, "market_watch", lambda: duplicate)
    with pytest.raises(AmbiguousSymbolError):
        market_data.get_order_book("الف")

    empty = _snapshot([])
    monkeypatch.setattr(market_data, "market_watch", lambda: empty)
    result = market_data.get_order_book("مفقود")
    assert result.empty
    assert result.attrs["missing_selectors"] == ["مفقود"]
    with pytest.raises(StockNotFoundError):
        market_data.get_order_book("مفقود", selector_strict=True)
