import datetime

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import order_book as ob
from algotik_tse.exceptions import AmbiguousSymbolError, InvalidParameterError


class Response:
    def __init__(self, payload=None, status_code=200, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def delta(level, time, ref, bid=100, ask=101, bid_volume=10, ask_volume=11):
    return {
        "hEven": time,
        "refID": ref,
        "number": level,
        "pMeDem": bid,
        "pMeOf": ask,
        "qTitMeDem": bid_volume,
        "qTitMeOf": ask_volume,
        "zOrdMeDem": 1,
        "zOrdMeOf": 2,
    }


def baseline(time=90000):
    return [
        delta(level, time, level, bid=100 - level, ask=100 + level)
        for level in range(1, 6)
    ]


def parsed(records, day=datetime.date(2026, 8, 23), inscode="1"):
    return ob._parse_history_records(
        records,
        day,
        {"InsCode": inscode, "Symbol": "نماد", "Name": "نام"},
        "gregorian",
    )


def test_reconstruction_atomic_last_wins_zero_clear_and_no_future_leak():
    records = baseline()
    records += [
        delta(2, 91503, 9, bid=95, ask=105, bid_volume=50),
        delta(1, 91503, 8, bid=99, ask=101, bid_volume=20),
        delta(1, 91503, 10, bid=0, ask=0, bid_volume=0, ask_volume=0),
    ]
    # Provider order is not chronological; replay must be stable by time/refID.
    records = [records[-1], *records[:-1]]
    result = ob._reconstruct_day(parsed(records))

    assert result["Timestamp"].nunique() == 2
    first = result.loc[result["hEven"].eq(90000)].set_index("Level")
    second = result.loc[result["hEven"].eq(91503)].set_index("Level")
    assert first.loc[1, "BidPrice"] == 99  # no future zero leaked backwards
    assert second.loc[1, "BidPrice"] == 0  # explicit zero clears
    assert second.loc[2, "BidVolume"] == 50
    assert len(second) == 5  # same-second deltas emitted atomically once
    assert str(second.iloc[0]["Timestamp"].tz) == "Asia/Tehran"
    assert second.iloc[0]["Time"] == "09:15:03"


def test_partial_initial_complete_only_and_day_state_reset():
    day_one = ob._reconstruct_day(parsed([delta(1, 90000, 1)]))
    assert len(day_one) == 5
    assert day_one["is_partial"].all()
    assert ob._reconstruct_day(parsed([delta(1, 90000, 1)]), complete_only=True).empty

    # A new day is replayed in a fresh call/state; unseen level 2 stays null.
    day_two = ob._reconstruct_day(
        parsed([delta(1, 90000, 1, bid=200)], datetime.date(2026, 8, 24))
    ).set_index("Level")
    assert pd.isna(day_two.loc[2, "BidPrice"])


def test_duplicate_events_are_idempotent_and_wide_long_parity():
    records = baseline() + baseline()
    long = ob._reconstruct_day(parsed(records))
    wide = ob._to_wide(long)
    assert len(long) == 5
    assert len(wide) == 1
    for level in range(1, 6):
        row = long.loc[long["Level"].eq(level)].iloc[0]
        assert wide.iloc[0][f"BidPrice{level}"] == row["BidPrice"]
        assert wide.iloc[0][f"AskVolume{level}"] == row["AskVolume"]


def test_public_raw_long_wide_and_typed_empty(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        return Response({"bestLimitsHistory": baseline()})

    monkeypatch.setattr(ob, "safe_get", fake_get)
    common = dict(
        symbol="123",
        start="2026-08-23",
        end="2026-08-23",
        date_format="both",
        progress=False,
    )
    raw = att.get_order_book_history(raw=True, **common)
    long = att.get_order_book_history(**common)
    wide = att.get_order_book_history(output_type="wide", **common)
    assert len(raw) == 5 and not raw["is_reconstructed"].any()
    assert len(long) == 5 and long["is_reconstructed"].all()
    assert len(wide) == 1 and len([c for c in wide if c.startswith("BidPrice")]) == 5
    assert all("20260823" in url for url in calls)

    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    empty = att.get_order_book_history(**common)
    assert empty.empty
    assert str(empty["Timestamp"].dtype) == "datetime64[ns, Asia/Tehran]"
    assert str(empty["BidPrice"].dtype) == "Int64"


def test_bad_json_and_http_failure_preserve_empty_history(monkeypatch):
    common = dict(symbol="123", start="2026-08-23", end="2026-08-23", progress=False)
    monkeypatch.setattr(
        ob, "safe_get", lambda url: Response(json_error=ValueError("html"))
    )
    with pytest.warns(RuntimeWarning, match=r"request\(s\) failed"):
        result = att.get_order_book_history(**common)
    assert result.empty and "Invalid JSON" in result.attrs["failed_requests"][0]

    monkeypatch.setattr(ob, "safe_get", lambda url: Response({}, status_code=500))
    with pytest.warns(RuntimeWarning, match=r"request\(s\) failed"):
        result = att.get_order_book_history(**common)
    assert result.empty


def test_queue_strict_buy_sell_and_threshold_asof(monkeypatch):
    # First snapshot buy queue at upper=99. At 10:00 the threshold changes;
    # the later record must not leak into the 09:00 snapshot.
    records = baseline()
    records[0] = delta(1, 90000, 1, bid=99, ask=0, bid_volume=100, ask_volume=0)
    records[0]["zOrdMeOf"] = 0
    late_sell = delta(1, 100000, 10, bid=0, ask=90, bid_volume=0, ask_volume=200)
    late_sell["zOrdMeDem"] = 0
    records += [late_sell]
    thresholds = [
        {"hEven": 0, "psGelStaMax": 99, "psGelStaMin": 90},
        {"hEven": 93000, "psGelStaMax": 98, "psGelStaMin": 90},
    ]

    def fake_get(url):
        if "GetStaticThreshold" in url:
            return Response({"staticThreshold": thresholds})
        return Response({"bestLimitsHistory": records})

    monkeypatch.setattr(ob, "safe_get", fake_get)
    queues = att.get_queue_history(
        "123",
        start="2026-08-23",
        end="2026-08-23",
        date_format="gregorian",
        progress=False,
    )
    buy_early = queues.loc[queues["hEven"].eq(90000) & queues["Side"].eq("buy")].iloc[0]
    sell_late = queues.loc[queues["hEven"].eq(100000) & queues["Side"].eq("sell")].iloc[
        0
    ]
    assert buy_early["is_queue"] and buy_early["PriceLimit"] == 99
    assert buy_early["threshold_hEven"] == 0
    assert sell_late["is_queue"] and sell_late["QueueValue"] == 18000


def test_queue_no_threshold_has_explicit_unavailable_provenance(monkeypatch):
    def fake_get(url):
        if "GetStaticThreshold" in url:
            return Response({"staticThreshold": []})
        return Response({"bestLimitsHistory": baseline()})

    monkeypatch.setattr(ob, "safe_get", fake_get)
    result = att.get_queue_history(
        "123", start="2026-08-23", end="2026-08-23", progress=False
    )
    assert result["PriceLimit"].isna().all()
    assert result["is_queue"].isna().all()
    assert result["threshold_source"].eq("unavailable").all()


def live_snapshot(today, stale=False):
    timestamp = pd.Timestamp(
        datetime.datetime.combine(today, datetime.time(10, 0)),
        tz="Asia/Tehran",
    )
    order_rows = []
    for inscode in ["1", "2"]:
        for level in range(1, 6):
            order_rows.append(
                {
                    "InsCode": inscode,
                    "Level": level,
                    "BidOrderCount": 1,
                    "BidVolume": 10,
                    "BidPrice": 100 - level,
                    "AskPrice": 100 + level,
                    "AskVolume": 11,
                    "AskOrderCount": 2,
                }
            )
    return {
        "stocks": pd.DataFrame(
            [
                {"InsCode": "1", "Symbol": "الف", "Name": "الف"},
                {"InsCode": "2", "Symbol": "ب", "Name": "ب"},
            ]
        ).assign(MaxAllowed=99, MinAllowed=90),
        "order_book": pd.DataFrame(order_rows),
        "trade_date": today,
        "exchange_time": timestamp,
        "is_history_eligible": not stale,
        "is_realtime_fresh": not stale,
        "is_partial": True,
        "is_stale": stale,
    }


def test_include_today_one_bulk_call_multi_and_deduplicates(monkeypatch):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    calls = {"market": 0}

    def fake_market():
        calls["market"] += 1
        return live_snapshot(today)

    monkeypatch.setattr("algotik_tse.core.market_data.market_watch", fake_market)
    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    result = att.get_order_book_history(
        ["الف", "ب"], start=today, end=today, include_today=True, progress=False
    )
    assert calls["market"] == 1
    assert len(result) == 10
    assert result.attrs["include_today_appended"]
    assert not result.duplicated(["InsCode", "Timestamp", "Level"]).any()


def test_include_today_stale_or_failure_returns_history(monkeypatch):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    monkeypatch.setattr(
        ob, "safe_get", lambda url: Response({"bestLimitsHistory": baseline()})
    )
    monkeypatch.setattr(
        "algotik_tse.core.market_data.market_watch",
        lambda: live_snapshot(today, stale=True),
    )
    with pytest.warns(RuntimeWarning, match="stale"):
        stale = att.get_order_book_history(
            "1", start=today, end=today, include_today=True, progress=False
        )
    assert len(stale) == 5 and not stale.attrs["include_today_appended"]

    monkeypatch.setattr(
        "algotik_tse.core.market_data.market_watch",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    with pytest.warns(RuntimeWarning, match="unavailable"):
        failed = att.get_order_book_history(
            "1", start=today, end=today, include_today=True, progress=False
        )
    assert len(failed) == 5


def test_exact_symbol_ambiguity_propagates(monkeypatch):
    payload = {
        "instrumentSearch": [
            {"insCode": "1", "lVal18AFC": "الف", "lVal30": "A"},
            {"insCode": "2", "lVal18AFC": "الف", "lVal30": "B"},
        ]
    }
    monkeypatch.setattr(ob, "safe_get", lambda url: Response(payload))
    with pytest.raises(AmbiguousSymbolError):
        att.get_order_book_history(
            "الف", start="2026-08-23", end="2026-08-23", progress=False
        )


def test_existing_live_get_order_book_contract_unchanged(monkeypatch):
    expected = pd.DataFrame({"legacy": [1]})
    monkeypatch.setattr(
        "algotik_tse.core.market_data.get_order_book", lambda symbol=None: expected
    )
    # Top-level binding remains the pre-existing function, not the history API.
    assert att.get_order_book.__name__ == "get_order_book"


def test_atomic_collision_never_creates_hybrid_snapshot():
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    history = ob._reconstruct_day(parsed(baseline(100000), today))
    partial_snapshot = live_snapshot(today)
    partial_snapshot["order_book"] = partial_snapshot["order_book"].loc[
        partial_snapshot["order_book"]["InsCode"].eq("1")
        & partial_snapshot["order_book"]["Level"].eq(1)
    ]
    live_partial = ob._live_rows(
        partial_snapshot,
        [{"InsCode": "1", "Symbol": "الف", "Name": "الف"}],
        "gregorian",
    )
    kept = ob._merge_live_atomic(history, live_partial)
    assert len(kept) == 5
    assert kept["source"].eq("tsetmc_best_limits_history_reconstructed").all()

    history_partial = history.copy()
    history_partial.loc[history_partial["Level"].gt(1), ob.BOOK_VALUE_COLUMNS] = pd.NA
    history_partial["is_complete"] = False
    history_partial["is_partial"] = True
    full_snapshot = live_snapshot(today)
    full_snapshot["order_book"] = full_snapshot["order_book"].loc[
        full_snapshot["order_book"]["InsCode"].eq("1")
    ]
    live_full = ob._live_rows(
        full_snapshot,
        [{"InsCode": "1", "Symbol": "الف", "Name": "الف"}],
        "gregorian",
    )
    replaced = ob._merge_live_atomic(history_partial, live_full)
    assert len(replaced) == 5
    assert replaced["source"].eq("market_watch_live_snapshot").all()


def test_threshold_rejects_cross_date_and_all_bad_is_typed_empty():
    day = datetime.date(2026, 8, 23)
    with pytest.warns(RuntimeWarning, match="cross-date"):
        result = ob._parse_threshold_records(
            [
                {
                    "dEven": 20260824,
                    "hEven": 90000,
                    "psGelStaMax": 100,
                    "psGelStaMin": 80,
                },
                {"bad": "record"},
            ],
            day,
        )
    assert result.empty
    assert str(result["UpperLimit"].dtype) == "Int64"


def test_queue_tristate_crossed_and_provenance():
    day = datetime.date(2026, 8, 23)
    books = ob._reconstruct_day(parsed(baseline(), day))
    no_threshold = ob._derive_queue_rows(books, {}, "buy", True)
    assert pd.isna(no_threshold.iloc[0]["is_queue"])

    crossed = books.copy()
    crossed.loc[crossed["Level"].eq(1), "BidPrice"] = 110
    crossed.loc[crossed["Level"].eq(1), "AskPrice"] = 100
    threshold = ob._parse_threshold_records(
        [{"hEven": 0, "psGelStaMax": 110, "psGelStaMin": 90}], day
    )
    result = ob._derive_queue_rows(crossed, {("1", 20260823): threshold}, "buy", False)
    assert result.iloc[0]["is_queue"] is False or not result.iloc[0]["is_queue"]
    assert result.iloc[0]["is_crossed"]
    assert result.iloc[0]["book_source"] == crossed.iloc[0]["source"]
    assert result.iloc[0]["source"].startswith("derived_from_tsetmc")


def test_live_get_queue_one_bulk_call_and_canonical_status(monkeypatch):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    snapshot = live_snapshot(today)
    mask = snapshot["order_book"]["InsCode"].eq("1") & snapshot["order_book"][
        "Level"
    ].eq(1)
    snapshot["order_book"].loc[mask, ["BidPrice", "BidVolume", "BidOrderCount"]] = [
        99,
        100,
        2,
    ]
    snapshot["order_book"].loc[mask, ["AskPrice", "AskVolume", "AskOrderCount"]] = 0
    calls = {"count": 0}

    def fake_market():
        calls["count"] += 1
        return snapshot

    monkeypatch.setattr("algotik_tse.core.market_data.market_watch", fake_market)
    result = att.get_queue("الف", side="buy")
    assert calls["count"] == 1
    assert len(result) == 1 and result.iloc[0]["is_queue"]
    assert result.iloc[0]["book_source"] == "market_watch_live_snapshot"
    assert result.iloc[0]["source"] == "derived_from_market_watch_live_snapshot"
    assert result.iloc[0]["threshold_source"] == "market_watch_price_limits"
    assert result.iloc[0]["is_complete"] and not result.iloc[0]["is_partial"]
    assert result.iloc[0]["market_partial_status"]


def test_raw_include_today_appends_explicit_full_snapshot(monkeypatch):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    monkeypatch.setattr(
        "algotik_tse.core.market_data.market_watch", lambda: live_snapshot(today)
    )
    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    result = att.get_order_book_history(
        "1", start=today, end=today, raw=True, include_today=True, progress=False
    )
    assert len(result) == 5
    assert result["record_type"].eq("full_snapshot").all()
    assert result.attrs["include_today_appended"]


@pytest.mark.parametrize("limit", [1, 2])
def test_raw_live_snapshot_limit_is_atomic(monkeypatch, limit):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    monkeypatch.setattr(
        "algotik_tse.core.market_data.market_watch", lambda: live_snapshot(today)
    )
    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    result = att.get_order_book_history(
        "1",
        start=today,
        end=today,
        raw=True,
        include_today=True,
        limit=limit,
        max_requests=2,
        progress=False,
    )
    assert len(result) == 5
    assert result["Level"].tolist() == [1, 2, 3, 4, 5]
    assert result["record_type"].eq("full_snapshot").all()
    assert result.attrs["schema"] == "raw_mixed"


@pytest.mark.parametrize("limit", [1, 2])
def test_raw_partial_live_keeps_all_placeholder_levels(monkeypatch, limit):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    snapshot = live_snapshot(today)
    snapshot["order_book"] = (
        snapshot["order_book"]
        .loc[
            snapshot["order_book"]["InsCode"].eq("1")
            & snapshot["order_book"]["Level"].eq(1)
        ]
        .copy()
    )
    monkeypatch.setattr("algotik_tse.core.market_data.market_watch", lambda: snapshot)
    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    result = att.get_order_book_history(
        "1",
        start=today,
        end=today,
        raw=True,
        include_today=True,
        dropna=True,
        limit=limit,
        max_requests=2,
        progress=False,
    )
    assert result["Level"].tolist() == [1, 2, 3, 4, 5]
    assert len(result) == 5
    assert not result["is_complete"].any()
    assert result["is_partial"].all()
    placeholders = result.loc[result["Level"].gt(1), ob.BOOK_VALUE_COLUMNS]
    assert placeholders.isna().all().all()


def test_limit_is_final_snapshot_or_delta_count(monkeypatch):
    records = baseline(90000) + [
        delta(1, 91000, 10, bid=98),
        delta(1, 92000, 11, bid=97),
    ]
    monkeypatch.setattr(
        ob, "safe_get", lambda url: Response({"bestLimitsHistory": records})
    )
    common = dict(
        symbol="1",
        start="2026-08-23",
        end="2026-08-23",
        limit=2,
        progress=False,
    )
    long = att.get_order_book_history(**common)
    raw = att.get_order_book_history(raw=True, **common)
    wide = att.get_order_book_history(output_type="wide", **common)
    assert long["Timestamp"].nunique() == 2 and len(long) == 10
    assert len(raw) == 2
    assert len(wide) == 2


def test_request_guard_and_duplicate_cache(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        return Response({"bestLimitsHistory": baseline()})

    monkeypatch.setattr(ob, "safe_get", fake_get)
    with pytest.raises(InvalidParameterError, match="max_requests"):
        att.get_order_book_history(
            "1",
            start="2026-08-20",
            end="2026-08-23",
            max_requests=3,
            progress=False,
        )
    assert not calls

    result = att.get_order_book_history(
        ["1", "1"],
        start="2026-08-23",
        end="2026-08-23",
        progress=False,
    )
    assert len(calls) == 1 and result["InsCode"].nunique() == 1

    with pytest.raises(InvalidParameterError, match="including thresholds"):
        att.get_queue_history(
            "1",
            start="2026-08-22",
            end="2026-08-23",
            max_requests=3,
            progress=False,
        )


def test_budget_preflight_counts_search_live_and_actual_calls(monkeypatch):
    calls = {"safe": 0, "live": 0}

    def fake_get(url):
        calls["safe"] += 1
        if "GetInstrumentSearch" in url:
            return Response(
                {
                    "instrumentSearch": [
                        {"insCode": "1", "lVal18AFC": "الف", "lVal30": "الف"}
                    ]
                }
            )
        return Response({"bestLimitsHistory": baseline()})

    def fake_live():
        calls["live"] += 1
        return live_snapshot(pd.Timestamp.now(tz="Asia/Tehran").date())

    monkeypatch.setattr(ob, "safe_get", fake_get)
    monkeypatch.setattr("algotik_tse.core.market_data.market_watch", fake_live)
    selectors = [f"نماد{i}" for i in range(1000)]
    with pytest.raises(InvalidParameterError, match="max_requests"):
        att.get_order_book_history(
            selectors,
            start="2026-08-23",
            end="2026-08-23",
            include_today=True,
            max_requests=10,
            progress=False,
        )
    assert calls == {"safe": 0, "live": 0}

    result = att.get_order_book_history(
        "الف",
        start="2026-08-23",
        end="2026-08-23",
        max_requests=2,
        progress=False,
    )
    assert calls["safe"] == 2
    assert result.attrs["request_count"] == 2
    assert result.attrs["request_count"] <= result.attrs["max_requests"]


def test_normalized_duplicate_symbol_search_is_memoized(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        if "GetInstrumentSearch" in url:
            return Response(
                {
                    "instrumentSearch": [
                        {"insCode": "1", "lVal18AFC": "ی", "lVal30": "نام"}
                    ]
                }
            )
        return Response({"bestLimitsHistory": baseline()})

    monkeypatch.setattr(ob, "safe_get", fake_get)
    result = att.get_order_book_history(
        ["ی", "ي"], start="2026-08-23", end="2026-08-23", progress=False
    )
    assert len([url for url in calls if "GetInstrumentSearch" in url]) == 1
    assert len([url for url in calls if "BestLimits" in url]) == 1
    assert result.attrs["selector_verified"]


def test_queue_kwargs_conflict_empty_finalize_save_and_dtypes(monkeypatch, tmp_path):
    with pytest.raises(InvalidParameterError, match="incompatible"):
        att.get_queue_history("1", raw=True, progress=False)
    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    result = att.get_queue_history(
        "1",
        start="2026-08-23",
        end="2026-08-23",
        progress=False,
        save_to_file=True,
        save_path=str(tmp_path),
    )
    assert result.empty and result.attrs["schema"] == "canonical_queue"
    assert result.attrs["queue_strict"]
    assert (tmp_path / "queue-history.csv").exists()
    assert str(result["is_queue"].dtype) == "boolean"
    assert str(result["QueueVolume"].dtype) == "Int64"
    assert str(result["book_source"].dtype) == "string"


def test_timestamp_dtype_exactly_matches_empty_and_nonempty(monkeypatch):
    monkeypatch.setattr(
        ob, "safe_get", lambda url: Response({"bestLimitsHistory": baseline()})
    )
    nonempty = att.get_order_book_history(
        "1", start="2026-08-23", end="2026-08-23", progress=False
    )
    monkeypatch.setattr(ob, "safe_get", lambda url: Response({"bestLimitsHistory": []}))
    empty = att.get_order_book_history(
        "1", start="2026-08-23", end="2026-08-23", progress=False
    )
    expected = "datetime64[ns, Asia/Tehran]"
    assert str(nonempty["Timestamp"].dtype) == expected
    assert str(empty["Timestamp"].dtype) == expected


def test_dropna_removes_only_wholly_empty_snapshot():
    meaningful = ob._reconstruct_day(parsed([delta(1, 90000, 1)]))
    empty = meaningful.copy()
    empty["Timestamp"] = empty["Timestamp"] + pd.Timedelta(seconds=1)
    empty["hEven"] = 90001
    empty[ob.BOOK_VALUE_COLUMNS] = pd.NA
    combined = pd.concat([meaningful, empty], ignore_index=True)
    filtered = ob._drop_empty_books(combined, "long", False, True)
    assert filtered["Timestamp"].nunique() == 1
    assert filtered["is_partial"].all()  # meaningful partial snapshot is retained
