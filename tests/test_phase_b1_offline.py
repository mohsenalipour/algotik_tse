import datetime as dt
import inspect

import numpy as np
import pandas as pd
import pytest
from persiantools.jdatetime import JalaliDate

import algotik_tse as att
from algotik_tse.core import fundamentals as fundamental_module
from algotik_tse.core import instruments as instrument_module
from algotik_tse.core import market_data as market_data_module
from algotik_tse.core import market_history as market_history_module
from algotik_tse.core import trades as trade_module
from algotik_tse.core.market_data import CLIENT_COLUMNS, ORDER_COLUMNS, STOCK_COLUMNS
from algotik_tse.core.resolver import InstrumentRef
from algotik_tse.exceptions import (
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _ref(symbol="فولاد", code="123"):
    return InstrumentRef(
        code,
        symbol=symbol,
        name="فولاد مبارکه اصفهان",
        asset_type="equity",
        is_active=True,
        provenance="test",
    )


def _trade(n, *, date=0, code=None, time=90101, canceled=0, price=1000, volume=5):
    return {
        "insCode": code,
        "dEven": date,
        "nTran": n,
        "hEven": time,
        "qTitTran": volume,
        "pTran": price,
        "qTitNgJ": 1,
        "iSensVarP": 2,
        "pPhSeaCotJ": 3,
        "pPbSeaCotJ": 4,
        "iAnuTran": 5,
        "xqVarPJDrPRf": 6,
        "canceled": canceled,
    }


@pytest.fixture
def trade_identity(monkeypatch):
    calls = []

    def resolve(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return _ref(
            symbol=str(symbol or "فولاد"), code=str(kwargs.get("ins_code") or "123")
        )

    monkeypatch.setattr(trade_module, "resolve_instrument", resolve)
    monkeypatch.setattr(trade_module, "tehran_today", lambda: dt.date(2026, 8, 25))
    return calls


def test_trade_history_uses_lossless_false_and_stable_ordering(
    monkeypatch, trade_identity
):
    urls = []
    payload = {
        "tradeHistory": [
            _trade(3091, date=20260824, code=123, time=101500, price=1100),
            _trade(2, time=90101),
            _trade(1, time=90101),  # same second is a distinct transaction
            _trade(2, time=90101),  # exact date + trade number is a duplicate
            _trade(3, time=90102, canceled=1),
        ]
    }

    def request(url):
        urls.append(url)
        return Response(payload)

    monkeypatch.setattr(trade_module, "safe_get", request)
    result = att.get_trades(
        "فولاد", start="2026-08-24", end="2026-08-24", progress=False
    )

    assert urls == [
        "https://cdn.tsetmc.com/api/Trade/GetTradeHistory/123/20260824/false"
    ]
    assert "/true" not in urls[0]
    assert result["TradeNo"].tolist() == [1, 2, 3091]
    assert result.loc[:1, "Time"].tolist() == ["09:01:01", "09:01:01"]
    assert result["Value"].tolist() == [5000, 5000, 5500]
    assert list(result.columns) == trade_module.TRADE_COLUMNS
    assert result.attrs["request_count"] == 1
    assert result.attrs["trade_request_count"] == 1
    assert result.attrs["request_budget_scope"] == "trade_endpoint_only"
    assert result.attrs["resolver_request_count"] is None
    assert result.attrs["resolver_request_count_known"] is False
    assert result.attrs["total_request_count"] is None
    assert result.attrs["reconciliation"] == {
        "provider_rows": 5,
        "parsed_rows": 5,
        "canceled_filtered": 1,
        "duplicates_removed": 1,
        "returned_rows": 3,
    }


def test_trade_include_canceled_raw_and_today_schema(monkeypatch, trade_identity):
    def request(url):
        assert url.endswith("/api/Trade/GetTrade/123")
        return Response({"trade": [_trade(7, canceled=1)]})

    monkeypatch.setattr(trade_module, "safe_get", request)
    result = att.get_live_trades(
        "فولاد", include_canceled=True, raw=True, progress=False
    )
    assert list(result.columns) == trade_module.TRADE_RAW_COLUMNS
    assert result.loc[0, "Canceled"] == True  # noqa: E712
    assert result.loc[0, "RawDate"] == 0
    assert result.loc[0, "Source"] == "tsetmc_trade_live"
    assert result.loc[0, "GregorianDate"] == dt.date(2026, 8, 25)
    assert result.loc[0, "Timestamp"].tz is not None


def test_trade_jalali_input_and_empty_holiday_are_valid(monkeypatch, trade_identity):
    requested = dt.date(2026, 8, 24)
    jalali = JalaliDate.to_jalali(requested).isoformat()
    monkeypatch.setattr(
        trade_module, "safe_get", lambda _: Response({"tradeHistory": []})
    )
    empty = att.get_trades("فولاد", start=jalali, end=jalali, progress=False)
    assert empty.empty
    assert list(empty.columns) == trade_module.TRADE_COLUMNS
    assert empty.attrs["partial"] is False
    assert empty.attrs["source_coverage"][0]["rows"] == 0


def test_trade_weekend_skips_provider_but_still_resolves(monkeypatch, trade_identity):
    monkeypatch.setattr(
        trade_module,
        "safe_get",
        lambda _: pytest.fail("closed weekdays must not call the trade endpoint"),
    )
    result = att.get_trades(
        "فولاد", start="2026-08-20", end="2026-08-21", progress=False
    )
    assert result.empty
    assert len(trade_identity) == 1
    assert result.attrs["request_count"] == 0
    assert result.attrs["resolved_ins_code"] == "123"


def test_trade_request_cap_preflight_has_no_network_or_resolution(monkeypatch):
    monkeypatch.setattr(trade_module, "tehran_today", lambda: dt.date(2026, 8, 25))
    monkeypatch.setattr(
        trade_module,
        "resolve_instrument",
        lambda *a, **k: pytest.fail("cap must run before resolver"),
    )
    monkeypatch.setattr(
        trade_module, "safe_get", lambda _: pytest.fail("cap must run before network")
    )
    with pytest.raises(InvalidParameterError, match="exceeding max_requests=1"):
        att.get_trades(
            "فولاد",
            start="2026-08-23",
            end="2026-08-25",
            max_requests=1,
            progress=False,
        )


def test_trade_huge_range_stops_at_budget_plus_one_before_network(monkeypatch):
    monkeypatch.setattr(trade_module, "tehran_today", lambda: dt.date(2026, 8, 25))
    monkeypatch.setattr(
        trade_module,
        "resolve_instrument",
        lambda *args, **kwargs: pytest.fail("bounded preflight must precede resolver"),
    )
    monkeypatch.setattr(
        trade_module,
        "safe_get",
        lambda _: pytest.fail("bounded preflight must precede provider network"),
    )
    with pytest.raises(InvalidParameterError, match="exceeding max_requests=1"):
        att.get_trades(
            "فولاد",
            start="0001-01-01",
            end="2026-08-25",
            max_requests=1,
            progress=False,
        )


@pytest.mark.parametrize(
    "row,match",
    [
        (_trade(1, code=999), "insCode 999 does not match"),
        (_trade(1, date=20260823), "dEven 20260823 does not match"),
        (_trade(1, time=250000), "hEven is not a valid time"),
    ],
)
def test_trade_rejects_provider_identity_date_and_time_mismatch(
    monkeypatch, trade_identity, row, match
):
    monkeypatch.setattr(
        trade_module,
        "safe_get",
        lambda _: Response({"tradeHistory": [row]}),
    )
    with pytest.raises(DataParsingError, match=match):
        att.get_trades("فولاد", start="2026-08-24", end="2026-08-24", progress=False)


def test_trade_null_numeric_is_nullable_not_zero(monkeypatch, trade_identity):
    monkeypatch.setattr(
        trade_module,
        "safe_get",
        lambda _: Response({"tradeHistory": [_trade(1, price=None, volume=None)]}),
    )
    result = att.get_trades(
        "فولاد", start="2026-08-24", end="2026-08-24", progress=False
    )
    assert pd.isna(result.loc[0, "Price"])
    assert pd.isna(result.loc[0, "Volume"])
    assert pd.isna(result.loc[0, "Value"])


def test_trade_real_17_digit_identity_is_parsed_losslessly(monkeypatch):
    code = "65883838195688438"
    monkeypatch.setattr(trade_module, "tehran_today", lambda: dt.date(2026, 8, 25))
    monkeypatch.setattr(
        trade_module,
        "resolve_instrument",
        lambda *args, **kwargs: _ref(code=code),
    )
    monkeypatch.setattr(
        trade_module,
        "safe_get",
        lambda url: Response({"tradeHistory": [_trade(1, code=code, date="20260824")]}),
    )
    result = att.get_trades(
        "خودرو", start="2026-08-24", end="2026-08-24", progress=False
    )
    assert result.loc[0, "InsCode"] == code

    monkeypatch.setattr(
        trade_module,
        "safe_get",
        lambda url: Response({"tradeHistory": [_trade(1, code="65883838195688439")]}),
    )
    with pytest.raises(DataParsingError, match="does not match requested"):
        att.get_trades("خودرو", start="2026-08-24", end="2026-08-24", progress=False)


def test_trade_partial_transport_failure_is_reported(monkeypatch, trade_identity):
    def request(url):
        if "20260823" in url:
            return Response({}, status_code=503)
        return Response({"tradeHistory": [_trade(1)]})

    monkeypatch.setattr(trade_module, "safe_get", request)
    result = att.get_trades(
        "فولاد", start="2026-08-23", end="2026-08-24", progress=False
    )
    assert len(result) == 1
    assert result.attrs["partial"] is True
    assert result.attrs["request_count"] == 2
    assert result.attrs["failures"][0]["date"] == "2026-08-23"


def _stock_rows(eps=(10, 0, -5, None), close=(100, 100, 100, 100)):
    rows = []
    for position, (row_eps, row_close) in enumerate(zip(eps, close), start=1):
        row = {column: 0 for column in STOCK_COLUMNS}
        row.update(
            {
                "InsCode": str(position),
                "ISIN": "IRO1TEST{:04d}".format(position),
                "Symbol": "نماد{}".format(position),
                "Name": "شرکت {}".format(position),
                "SectorCode": "10",
                "InstrumentType": 300 if position < 4 else 305,
                "Close": row_close,
                "Last": row_close,
                "EPS": row_eps,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=STOCK_COLUMNS)


def _snapshot(stocks=None, *, as_of="2026-08-25 10:00:00+03:30", stale=False):
    stamp = pd.Timestamp(as_of)
    return {
        "stocks": _stock_rows() if stocks is None else stocks,
        "order_book": pd.DataFrame(columns=ORDER_COLUMNS),
        "trade_date": stamp.date(),
        "exchange_time": stamp,
        "fetched_at": stamp,
        "snapshot_age_seconds": 0.0 if not stale else 1000.0,
        "is_today_trade_date": True,
        "is_history_eligible": True,
        "is_realtime_fresh": not stale,
        "is_previous_trade_date": False,
        "is_stale": stale,
        "market_state": "open",
    }


def test_fundamentals_one_request_pe_edges_and_typed_schema(monkeypatch):
    calls = []
    monkeypatch.setattr(
        fundamental_module,
        "market_watch",
        lambda: calls.append(1) or _snapshot(),
    )
    result = att.get_market_fundamentals(
        positive_pe=False, instrument_types=None, progress=False
    )
    assert calls == [1]
    assert result["PE"].tolist()[0] == 10.0
    assert result["PEStatus"].tolist() == [
        "ok",
        "eps_nonpositive",
        "eps_nonpositive",
        "eps_missing",
    ]
    assert result["PE"].iloc[1:].isna().all()
    assert result["PECalculated"].all()
    assert set(result["EPSSource"]) == {"market_watch"}
    assert set(result["PriceSource"]) == {"Close"}
    assert str(result["PE"].dtype) == "Float64"
    assert result.attrs["request_count"] == 1


def test_fundamental_filters_are_inclusive_and_default_types(monkeypatch):
    monkeypatch.setattr(fundamental_module, "market_watch", lambda: _snapshot())
    inclusive = att.get_market_fundamentals(pe_min=10, pe_max=10, progress=False)
    assert inclusive["InsCode"].tolist() == ["1"]
    all_rows = att.get_market_fundamentals(
        positive_pe=False, instrument_types=None, progress=False
    )
    assert "4" in all_rows["InsCode"].tolist()
    default_rows = att.get_market_fundamentals(positive_pe=False, progress=False)
    assert "4" not in default_rows["InsCode"].tolist()


def test_fundamental_exact_symbols_strict_missing_and_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(
        fundamental_module,
        "market_watch",
        lambda: calls.append(1) or _snapshot(),
    )
    selected = att.get_market_fundamentals(
        ["نماد1", "999"], positive_pe=False, strict=False, progress=False
    )
    assert selected["InsCode"].tolist() == ["1"]
    assert selected.attrs["missing_selectors"] == ("999",)
    with pytest.raises(StockNotFoundError):
        att.get_market_fundamentals(
            "999", positive_pe=False, strict=True, progress=False
        )
    before = len(calls)
    with pytest.raises(InvalidParameterError, match="positive integer"):
        att.get_market_fundamentals(max_requests=0, progress=False)
    assert len(calls) == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"positive_pe": "yes"},
        {"strict": 1},
        {"allow_stale": "yes"},
        {"progress": "yes"},
        {"pe_min": np.inf},
        {"pe_min": 5, "pe_max": 4},
        {"instrument_types": [300.5]},
        {"symbols": [""]},
    ],
)
def test_fundamental_all_arguments_preflight_before_market_watch(monkeypatch, kwargs):
    monkeypatch.setattr(
        fundamental_module,
        "market_watch",
        lambda: pytest.fail("invalid arguments must fail before network"),
    )
    with pytest.raises(InvalidParameterError):
        att.get_market_fundamentals(**kwargs)


def test_fundamental_normalizes_string_request_budget(monkeypatch):
    monkeypatch.setattr(fundamental_module, "market_watch", lambda: _snapshot())
    result = att.get_market_fundamentals(max_requests="1.0", progress=False)
    assert result.attrs["max_requests"] == 1


def test_fundamental_stale_policy_returns_typed_empty(monkeypatch):
    monkeypatch.setattr(
        fundamental_module, "market_watch", lambda: _snapshot(stale=True)
    )
    rejected = att.get_market_fundamentals(progress=False)
    assert rejected.empty
    assert list(rejected.columns) == fundamental_module.FUNDAMENTAL_COLUMNS
    assert str(rejected["PE"].dtype) == "Float64"
    assert rejected.attrs["stale_rejected"] is True
    allowed = att.get_market_fundamentals(allow_stale=True, progress=False)
    assert len(allowed) == 1
    assert allowed["IsStale"].all()


def test_fundamental_stale_strict_resolves_before_rejection(monkeypatch):
    monkeypatch.setattr(
        fundamental_module, "market_watch", lambda: _snapshot(stale=True)
    )
    present = att.get_market_fundamentals(
        "نماد1", strict=True, allow_stale=False, progress=False
    )
    assert present.empty
    assert present.attrs["missing_selectors"] == ()
    assert present.attrs["stale_rejected"] is True
    with pytest.raises(StockNotFoundError):
        att.get_market_fundamentals(
            "ناشناخته", strict=True, allow_stale=False, progress=False
        )


def test_fundamental_nonfinite_inputs_never_produce_pe(monkeypatch):
    stocks = _stock_rows(
        eps=(10, np.inf, -np.inf, 10),
        close=(np.inf, 100, 100, -np.inf),
    )
    monkeypatch.setattr(
        fundamental_module,
        "market_watch",
        lambda: _snapshot(stocks=stocks),
    )
    result = att.get_market_fundamentals(
        positive_pe=False, instrument_types=None, progress=False
    )
    assert result["PEStatus"].tolist() == [
        "price_nonfinite",
        "eps_nonfinite",
        "eps_nonfinite",
        "price_nonfinite",
    ]
    assert result["PE"].isna().all()
    assert result["Close"].iloc[[0, 3]].isna().all()
    assert result["EPS"].iloc[[1, 2]].isna().all()


def _parsed_market_snapshot_with_eps(raw_eps):
    fields = [""] * 26
    fields[0:14] = [
        "65883838195688438",
        "IRO1IKCO0001",
        "خودرو",
        "ایران خودرو",
        "100000",
        "1000",
        "1100",
        "1110",
        "2",
        "100",
        "110000",
        "990",
        "1120",
        "1050",
    ]
    fields[14:] = [
        raw_eps,
        "1",
        "2",
        "1",
        "34",
        "1200",
        "900",
        "1000000",
        "300",
        "0",
        "",
        "1",
    ]
    text = "x@1405/06/03 10:00:00,open,0@{}@".format(",".join(fields))
    return market_data_module._parse_market_watch_response(
        text, fetched_at=pd.Timestamp("2026-08-25 10:00", tz="Asia/Tehran")
    )


def test_blank_eps_preserves_legacy_market_watch_and_marks_fundamental_missing(
    monkeypatch,
):
    snapshot = _parsed_market_snapshot_with_eps("")
    stocks = snapshot["stocks"]
    assert list(stocks.columns) == STOCK_COLUMNS
    assert stocks.loc[0, "EPS"] == 0
    assert stocks.attrs["field_validity"]["EPS"]["65883838195688438"] is False
    monkeypatch.setattr(fundamental_module, "market_watch", lambda: snapshot)
    result = att.get_market_fundamentals(
        positive_pe=False, allow_stale=True, progress=False
    )
    assert pd.isna(result.loc[0, "EPS"])
    assert pd.isna(result.loc[0, "PE"])
    assert result.loc[0, "PEStatus"] == "eps_missing"
    assert result.loc[0, "EPSSource"] == "missing_in_market_watch"


def test_blank_eps_validity_survives_snapshot_archive(monkeypatch, tmp_path):
    snapshot = _parsed_market_snapshot_with_eps("")
    monkeypatch.setattr(fundamental_module, "market_watch", lambda: snapshot)
    path = tmp_path / "blank-eps.sqlite"
    att.get_market_fundamentals(
        positive_pe=False,
        allow_stale=True,
        archive_to=path,
        progress=False,
    )
    result = att.get_market_fundamentals_history(path, positive_pe=False)
    assert pd.isna(result.loc[0, "EPS"])
    assert result.loc[0, "PEStatus"] == "eps_missing"
    assert result.loc[0, "EPSSource"] == "missing_in_market_watch"


@pytest.mark.parametrize(
    ("with_client", "with_order_book"),
    [(True, False), (False, True), (True, True)],
)
def test_blank_eps_metadata_survives_all_live_merges_and_archive(
    monkeypatch, tmp_path, with_client, with_order_book
):
    snapshot = _parsed_market_snapshot_with_eps("")
    ins_code = "65883838195688438"
    if with_client:
        client_row = {column: 1 for column in CLIENT_COLUMNS}
        client_row["InsCode"] = ins_code
        snapshot["client_type"] = pd.DataFrame([client_row], columns=CLIENT_COLUMNS)
    if with_order_book:
        order_row = {column: 1 for column in ORDER_COLUMNS}
        order_row.update(
            {
                "InsCode": ins_code,
                "Level": 1,
                "BidPrice": 1090,
                "AskPrice": 1110,
            }
        )
        snapshot["order_book"] = pd.DataFrame([order_row], columns=ORDER_COLUMNS)

    monkeypatch.setattr(fundamental_module, "market_watch", lambda: snapshot)
    path = tmp_path / "blank-eps-merged.sqlite"
    att.get_market_fundamentals(
        positive_pe=False,
        allow_stale=True,
        archive_to=path,
        progress=False,
    )
    result = att.get_market_fundamentals_history(path, positive_pe=False)
    assert pd.isna(result.loc[0, "EPS"])
    assert pd.isna(result.loc[0, "PE"])
    assert result.loc[0, "PEStatus"] == "eps_missing"
    assert result.loc[0, "EPSSource"] == "missing_in_market_watch"


def test_fundamental_history_is_chronological_not_snapshot_hash_order(monkeypatch):
    earlier = _stock_rows(eps=(10,), close=(100,))
    later = _stock_rows(eps=(20,), close=(100,))
    earlier["SnapshotID"] = "z-hash"
    later["SnapshotID"] = "a-hash"
    earlier["AsOf"] = pd.Timestamp("2026-08-24 10:00", tz="Asia/Tehran")
    later["AsOf"] = pd.Timestamp("2026-08-25 10:00", tz="Asia/Tehran")
    saved = pd.concat([earlier, later], ignore_index=True)
    saved.attrs["SnapshotFrameAttrs"] = {"z-hash": {}, "a-hash": {}}
    monkeypatch.setattr(
        market_history_module, "load_market_snapshots", lambda *args, **kwargs: saved
    )
    result = att.get_market_fundamentals_history("unused", positive_pe=False)
    assert result["AsOf"].tolist() == [
        pd.Timestamp("2026-08-24 10:00", tz="Asia/Tehran"),
        pd.Timestamp("2026-08-25 10:00", tz="Asia/Tehran"),
    ]
    assert result["PE"].tolist() == [10.0, 5.0]
    assert result.attrs["coverage_start"] == pd.Timestamp(
        "2026-08-24 10:00", tz="Asia/Tehran"
    )
    assert result.attrs["coverage_end"] == pd.Timestamp(
        "2026-08-25 10:00", tz="Asia/Tehran"
    )


def test_fundamental_archive_history_is_same_snapshot_no_lookahead(
    monkeypatch, tmp_path
):
    path = tmp_path / "fundamentals.sqlite"
    snapshots = [
        _snapshot(
            _stock_rows(eps=(10,), close=(100,)),
            as_of="2026-08-24 10:00:00+03:30",
        ),
        _snapshot(
            _stock_rows(eps=(20,), close=(100,)),
            as_of="2026-08-25 10:00:00+03:30",
        ),
    ]
    calls = []

    def market():
        calls.append(1)
        return snapshots[len(calls) - 1]

    monkeypatch.setattr(fundamental_module, "market_watch", market)
    att.get_market_fundamentals(archive_to=path, progress=False)
    att.get_market_fundamentals(archive_to=path, progress=False)
    history = att.get_market_fundamentals_history(path, positive_pe=False)
    assert calls == [1, 1]
    assert history["PE"].tolist() == [10.0, 5.0]
    assert history["EPS"].tolist() == [10.0, 20.0]
    assert history.attrs["current_eps_used"] is False
    assert history.attrs["no_lookahead"] is True
    assert history.attrs["no_backfill"] is True


def test_fundamental_old_snapshot_without_eps_is_unavailable(monkeypatch, tmp_path):
    path = tmp_path / "old.sqlite"
    stocks = _stock_rows(eps=(10,), close=(100,)).drop(columns=["EPS"])
    monkeypatch.setattr(
        fundamental_module, "market_watch", lambda: _snapshot(stocks=stocks)
    )
    att.get_market_fundamentals(positive_pe=False, archive_to=path, progress=False)
    history = att.get_market_fundamentals_history(path, positive_pe=False)
    assert history["PE"].isna().all()
    assert history.loc[0, "PEStatus"] == "eps_missing"
    assert history.loc[0, "EPSSource"] == "unavailable_in_snapshot_schema"


def _etf_snapshot():
    rows = []
    for code, symbol, name in (("11", "طلا", "پشتوانه طلای لوتوس"), ("12", "زر", "زر")):
        row = {column: 0 for column in STOCK_COLUMNS}
        row.update(
            {
                "InsCode": code,
                "ISIN": "IRTK{}".format(code),
                "Symbol": symbol,
                "Name": name,
                "InstrumentType": 305,
                "Close": 100,
                "Last": 101,
                "NAV": 110,
            }
        )
        rows.append(row)
    return _snapshot(pd.DataFrame(rows, columns=STOCK_COLUMNS))


def test_listed_funds_one_bulk_call_exact_identity_and_shape(monkeypatch):
    calls = []
    monkeypatch.setattr(
        instrument_module,
        "market_watch",
        lambda: calls.append(1) or _etf_snapshot(),
    )
    result = att.list_listed_funds(progress=False)
    assert calls == [1]
    assert result[["Symbol", "InsCode", "ISIN"]].to_dict("records") == [
        {"Symbol": "طلا", "InsCode": "11", "ISIN": "IRTK11"},
        {"Symbol": "زر", "InsCode": "12", "ISIN": "IRTK12"},
    ]
    assert list(result.columns) == [
        "InsCode",
        "ISIN",
        "Symbol",
        "Name",
        "Last",
        "Close",
        "Yesterday",
        "Volume",
        "Value",
        "TradeCount",
        "Low",
        "High",
        "NAV",
        "NAV_Discount",
        "Change",
        "ChangePct",
        "MarketCode",
    ]
    assert result.attrs["no_fuzzy_join"] is True
    assert result.attrs["registry_joined"] is False


def test_listed_funds_empty_has_same_typed_schema_without_changing_list_etfs(
    monkeypatch,
):
    monkeypatch.setattr(instrument_module, "market_watch", _etf_snapshot)
    populated = att.list_listed_funds(progress=False)

    no_etfs = _snapshot(_stock_rows(eps=(10,), close=(100,)))
    monkeypatch.setattr(instrument_module, "market_watch", lambda: no_etfs)
    empty = att.list_listed_funds(progress=False)
    assert empty.empty
    assert list(empty.columns) == list(populated.columns)
    assert empty.dtypes.astype(str).to_dict() == populated.dtypes.astype(str).to_dict()
    assert empty.attrs.keys() == populated.attrs.keys()
    assert empty.attrs == populated.attrs

    legacy_empty = instrument_module.list_etfs(progress=False)
    assert legacy_empty.empty
    assert list(legacy_empty.columns) == []


def test_list_funds_default_signature_and_registry_behavior_unchanged(monkeypatch):
    signature = inspect.signature(instrument_module.list_funds)
    assert str(signature) == "(fund_type=None, progress=True, *, listed_only=False)"
    calls = []

    def request(url):
        calls.append(url)
        return Response(
            {
                "funds": [
                    {
                        "mfName": "صندوق ثبتی",
                        "regNo": "42",
                        "navRed": 100,
                    }
                ]
            }
        )

    monkeypatch.setattr(instrument_module, "safe_get", request)
    monkeypatch.setattr(instrument_module.time, "sleep", lambda _: None)
    result = att.list_funds(progress=False)
    assert len(calls) == len(att.settings.fund_type_ids)
    assert "fund_name" in result and "Symbol" not in result
    assert result["fund_name"].eq("صندوق ثبتی").all()


def test_list_funds_listed_delegates_without_fuzzy_registry_join(monkeypatch):
    calls = []
    monkeypatch.setattr(
        instrument_module,
        "market_watch",
        lambda: calls.append("market") or _etf_snapshot(),
    )
    monkeypatch.setattr(
        instrument_module,
        "safe_get",
        lambda _: pytest.fail("listed_only must not call the fund registry"),
    )
    result = att.list_funds(listed_only=True, progress=False)
    assert calls == ["market"]
    assert result["InsCode"].tolist() == ["11", "12"]
    with pytest.raises(InvalidParameterError, match="cannot be combined"):
        att.list_funds("equity", listed_only=True, progress=False)


def test_phase_b1_public_exports_exist():
    for name in (
        "get_trades",
        "get_live_trades",
        "get_market_fundamentals",
        "get_market_fundamentals_history",
        "list_listed_funds",
    ):
        assert name in att.__all__
        assert callable(getattr(att, name))
