import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algotik_tse.core import market_stream as ms
from algotik_tse.core.market_data import _parse_market_watch_response
from algotik_tse.exceptions import DataParsingError, InvalidParameterError

FIXTURE = Path(__file__).parent / "fixtures" / "market_watch_init.txt"


class Response:
    def __init__(self, text="", payload=None, status=200):
        self.text, self._payload, self.status_code = text, payload, status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def init_text():
    return FIXTURE.read_text(encoding="utf-8")


def plus(price="", order="", ref="1000", tokens="1,2,3", fast=None):
    fast = fast or "05/06/01 10:15:35,P,2500001"
    return "@".join([tokens, fast, price, order, ref])


def test_init_and_plus_patch_zero_overwrite_and_absence_unchanged():
    snapshot, refid, heven = ms._initial_state(init_text())
    old_second = snapshot["stocks"].set_index("InsCode").loc["222", "Last"]
    text = plus(
        "111,101535,100,111,0,0,0,0,0,0",
        "111,1,0,0,0,0,0,0",
    )
    result, info = ms._apply_plus_patch(snapshot, text, refid, heven)
    one = result["stocks"].set_index("InsCode").loc["111"]
    assert one["Last"] == 0 and one["Volume"] == 0
    assert result["stocks"].set_index("InsCode").loc["222", "Last"] == old_second
    book = result["order_book"].set_index(["InsCode", "Level"]).loc[("111", 1)]
    assert book["BidPrice"] == 0 and book["AskVolume"] == 0
    assert info["cursor_after"] == 1000


def test_refid_zero_is_unchanged_and_cursor_regression_resync():
    snapshot, refid, heven = ms._initial_state(init_text())
    _, info = ms._apply_plus_patch(snapshot, plus(ref="0"), refid, heven)
    assert info["cursor_after"] == refid
    with pytest.raises(ms._NeedResync):
        ms._apply_plus_patch(snapshot, plus(ref="998"), refid, heven)


def test_malformed_patch_is_atomic_and_unknown_update_resync():
    snapshot, refid, heven = ms._initial_state(init_text())
    original = snapshot["stocks"].copy(deep=True)
    with pytest.raises(DataParsingError):
        ms._apply_plus_patch(snapshot, plus(price="111,1,2"), refid, heven)
    pd.testing.assert_frame_equal(snapshot["stocks"], original)
    with pytest.raises(ms._NeedResync):
        ms._apply_plus_patch(
            snapshot, plus(price="999,101535,1,1,1,1,1,1,1,1"), refid, heven
        )


def test_watcher_initial_delta_heartbeat_defensive_copy_and_max_updates():
    replies = iter(
        [
            Response(init_text()),
            Response(plus(price="111,101535,100,111,113,11,1100,124000,98,115")),
            Response(plus(ref="0")),
        ]
    )
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=3,
        notifications=(),
        _request=lambda _: next(replies),
        _wait=lambda _: False,
        _random=lambda: 0.5,
    )
    initial = next(watcher)
    initial.snapshot["stocks"].loc[:, "Last"] = -1
    delta = next(watcher)
    assert delta.kind == "delta" and delta.snapshot["stocks"]["Last"].max() > 0
    assert delta.cursor_before == 999 and delta.cursor_after == 1000
    assert next(watcher).kind == "heartbeat"
    with pytest.raises(StopIteration):
        next(watcher)


def test_watcher_resyncs_unknown_patch_without_committing():
    replies = iter(
        [
            Response(init_text()),
            Response(plus(price="999,101535,1,1,1,1,1,1,1,1")),
            Response(init_text().replace("@999", "@1100")),
        ]
    )
    watcher = ms.MarketWatcher(
        interval=0,
        notifications=(),
        _request=lambda _: next(replies),
        _wait=lambda _: False,
    )
    assert next(watcher).kind == "initial"
    event = next(watcher)
    assert event.kind == "resync" and "999" not in set(
        event.snapshot["stocks"]["InsCode"]
    )


def test_watcher_stop_and_callback_policy():
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=1,
        notifications=(),
        _request=lambda _: Response(init_text()),
        _wait=lambda _: False,
        callback_error_policy="ignore",
    )
    watcher.run(lambda _: (_ for _ in ()).throw(RuntimeError("callback")))
    assert watcher._emitted == 1
    watcher.stop()
    with pytest.raises(StopIteration):
        next(watcher)


def test_notification_apis_dedupe_since_and_unknown_state():
    messages = {
        "msg": [
            {
                "tseMsgIdn": 1,
                "dEven": 20260823,
                "hEven": 90000,
                "tseTitle": "a",
                "tseDesc": "x",
                "flow": 0,
            },
            {
                "tseMsgIdn": 2,
                "dEven": 20260823,
                "hEven": 90100,
                "tseTitle": "b",
                "tseDesc": "y",
                "flow": 0,
            },
            {
                "tseMsgIdn": 2,
                "dEven": 20260823,
                "hEven": 90100,
                "tseTitle": "b",
                "tseDesc": "y",
                "flow": 0,
            },
        ]
    }
    result = ms.get_market_messages(
        since_id=1, _request=lambda _: Response(payload=messages)
    )
    assert result["message_id"].tolist() == [2]
    states = {
        "instrumentState": [
            {
                "idn": 3,
                "dEven": 20260823,
                "hEven": 90200,
                "insCode": 111,
                "lVal18AFC": "تست",
                "lVal30": "شرکت",
                "cEtaval": "ZZ",
            },
        ]
    }
    result = ms.get_instrument_state_changes(
        _request=lambda _: Response(payload=states)
    )
    assert result.iloc[0]["state"] == "unknown"
    assert str(result.iloc[0]["timestamp"].tz) == "Asia/Tehran"


def current_snapshot():
    snapshot = _parse_market_watch_response(
        init_text(), fetched_at=pd.Timestamp("2026-08-23 10:15:31", tz="Asia/Tehran")
    )
    snapshot.update(
        {
            "trade_date": datetime.date(2026, 8, 23),
            "exchange_time": pd.Timestamp("2026-08-23 10:15:30", tz="Asia/Tehran"),
            "fetched_at": pd.Timestamp("2026-08-23 10:15:31", tz="Asia/Tehran"),
            "is_realtime_fresh": True,
            "is_today_trade_date": True,
            "is_previous_trade_date": False,
            "is_stale": False,
        }
    )
    return snapshot


def test_market_breadth_uses_previous_close_and_no_trade_bucket():
    snapshot = current_snapshot()
    result = ms.get_market_breadth(_snapshot=snapshot).iloc[0]
    assert result["instrument_count"] == 2
    assert result["advances"] == 1
    assert result["no_trade"] == 1
    assert result["declines"] == 0


def test_breadth_conflicting_duplicate_and_base_market_filter():
    snapshot = current_snapshot()
    duplicate = snapshot["stocks"].iloc[[0]].copy()
    duplicate["Last"] = 999
    snapshot["stocks"] = pd.concat([snapshot["stocks"], duplicate], ignore_index=True)
    with pytest.raises(DataParsingError):
        ms.get_market_breadth(_snapshot=snapshot)


def test_sector_flow_excludes_inconsistent_client_rows_and_is_bounded():
    snapshot = current_snapshot()
    client = pd.DataFrame(
        [
            {
                "InsCode": "111",
                "Buy_I_Count": 2,
                "Buy_N_Count": 1,
                "Buy_I_Volume": 600,
                "Buy_N_Volume": 400,
                "Sell_I_Count": 3,
                "Sell_N_Count": 1,
                "Sell_I_Volume": 500,
                "Sell_N_Volume": 500,
                "Net_I_Volume": 100,
                "Net_N_Volume": -100,
            },
            {
                "InsCode": "222",
                "Buy_I_Count": 1,
                "Buy_N_Count": 1,
                "Buy_I_Volume": 10,
                "Buy_N_Volume": 0,
                "Sell_I_Count": 1,
                "Sell_N_Count": 1,
                "Sell_I_Volume": 0,
                "Sell_N_Volume": 0,
                "Net_I_Volume": 10,
                "Net_N_Volume": 0,
            },
        ]
    ).reindex(columns=ms.CLIENT_COLUMNS)
    result = ms.get_sector_flow(_snapshot=snapshot, _client_type=client).iloc[0]
    assert result["instrument_count"] == 2
    assert result["client_covered_count"] == 1
    assert result["net_individual_volume"] == 100
    assert result["value_method"] == "market_vwap_estimate"


def test_notification_failure_does_not_rollback_and_recovers_next_tick():
    plus_calls = iter(
        [
            plus(price="111,101535,100,111,119,11,1100,130000,98,119", tokens="2,2,3"),
            plus(ref="0", tokens="2,2,3"),
        ]
    )
    message_attempts = [0]

    def request(url, **_):
        if "MarketWatchInit" in url:
            return Response(init_text())
        if "MarketWatchPlus" in url:
            return Response(next(plus_calls))
        if "GetMsgByFlow" in url:
            message_attempts[0] += 1
            if message_attempts[0] == 1:
                return Response(status=503)
            return Response(
                payload={
                    "msg": [
                        {
                            "tseMsgIdn": 10,
                            "dEven": 20260823,
                            "hEven": 101536,
                            "tseTitle": "خبر",
                            "tseDesc": "متن",
                            "flow": 0,
                        }
                    ]
                }
            )
        raise AssertionError(url)

    watcher = ms.MarketWatcher(
        interval=0,
        notifications=("messages",),
        _request=request,
        _wait=lambda _: False,
    )
    next(watcher)
    failed = next(watcher)
    assert failed.cursor_after == 1000
    assert failed.snapshot["stocks"].set_index("InsCode").loc["111", "Last"] == 119
    assert failed.notification_errors and "messages" in failed.notification_errors[0]
    recovered = next(watcher)
    assert recovered.kind == "delta"
    assert recovered.messages["message_id"].tolist() == [10]


def test_resync_token_change_refreshes_notifications_after_commit():
    resync = init_text().replace("1,2,3@", "2,2,3@").replace("@999", "@1100")
    market_responses = iter(
        [
            Response(init_text()),
            Response(plus(ref="998", tokens="2,2,3")),
            Response(resync),
        ]
    )

    def request(url, **_):
        if "GetMsgByFlow" in url:
            return Response(payload={"msg": []})
        return next(market_responses)

    watcher = ms.MarketWatcher(
        interval=0,
        notifications=("messages",),
        _request=request,
        _wait=lambda _: False,
    )
    next(watcher)
    event = next(watcher)
    assert event.kind == "resync" and event.cursor_before == 999
    assert event.cursor_after == 1100
    assert event.notification_tokens[0] == "2"


def test_symbol_scope_external_change_becomes_heartbeat_or_suppressed():
    replies = iter(
        [
            Response(init_text()),
            Response(plus(price="222,101535,200,201,202,1,10,2020,200,202")),
        ]
    )
    watcher = ms.MarketWatcher(
        symbol="111",
        interval=0,
        notifications=(),
        _request=lambda _, **__: next(replies),
        _wait=lambda _: False,
    )
    next(watcher)
    event = next(watcher)
    assert event.kind == "heartbeat"
    assert event.changed_inscodes == () and event.changed_order_levels == ()
    assert event.snapshot["stocks"]["InsCode"].tolist() == ["111"]


def test_retry_cap_and_unexpected_bug_propagates():
    waits = []
    watcher = ms.MarketWatcher(
        interval=0,
        notifications=(),
        max_consecutive_retries=1,
        _request=lambda _, **__: Response(status=503),
        _wait=lambda delay: waits.append(delay) or False,
    )
    with pytest.raises(ms.ConnectionError):
        next(watcher)
    assert len(waits) == 1

    buggy = ms.MarketWatcher(
        interval=0,
        notifications=(),
        _request=lambda _, **__: (_ for _ in ()).throw(KeyError("bug")),
        _wait=lambda _: False,
    )
    with pytest.raises(KeyError):
        next(buggy)


def test_stop_after_fetch_prevents_commit_and_emit():
    holder = {}

    def request(_, **__):
        holder["watcher"].stop()
        return Response(init_text())

    holder["watcher"] = ms.MarketWatcher(
        interval=0,
        notifications=(),
        _request=request,
        _wait=lambda _: False,
    )
    with pytest.raises(StopIteration):
        next(holder["watcher"])
    assert holder["watcher"]._snapshot is None


def test_injected_naive_clock_sampled_once_and_normalized():
    calls = [0]

    def clock():
        calls[0] += 1
        return pd.Timestamp("2030-01-02 03:04:05")

    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=1,
        notifications=(),
        _request=lambda _, **__: Response(init_text()),
        _wait=lambda _: False,
        _clock=clock,
    )
    event = next(watcher)
    assert calls[0] == 1
    assert event.fetched_at == event.snapshot["fetched_at"]
    assert str(event.fetched_at.tz) == "Asia/Tehran"


def test_strict_full_numeric_fields_negative_ref_and_unsorted_updates():
    with pytest.raises(DataParsingError):
        ms._parse_refid("-1")
    raw = init_text().split("@")[2].split(";")[0].split(",")
    for index in (4, 5, 13, 14, 17, 19, 21, 24):
        corrupted = raw.copy()
        corrupted[index] = "bad"
        with pytest.raises(DataParsingError):
            ms._parse_price_patch(",".join(corrupted))
    nonfinite = raw.copy()
    nonfinite[14] = "nan"
    with pytest.raises(DataParsingError):
        ms._parse_price_patch(",".join(nonfinite))

    snapshot, refid, heven = ms._initial_state(init_text())
    updates = ";".join(
        [
            "111,101540,100,111,113,11,1100,124000,98,115",
            "222,101535,200,201,202,1,10,2020,200,202",
        ]
    )
    _, info = ms._apply_plus_patch(snapshot, plus(price=updates), refid, heven)
    assert info["heven_after"] == 101540


def test_fast_view_regression_requires_resync():
    snapshot, refid, heven = ms._initial_state(init_text())
    with pytest.raises(ms._NeedResync):
        ms._apply_plus_patch(
            snapshot,
            plus(fast="05/06/01 10:15:20,P,2500001"),
            refid,
            heven,
        )


def test_bounded_notification_dedupe_and_missing_id_fallbacks():
    watcher = ms.MarketWatcher(
        notifications=(),
        max_seen_notifications=2,
        _request=lambda _, **__: Response(init_text()),
        _wait=lambda _: False,
    )
    first = pd.DataFrame(
        [
            {
                "message_id": None,
                "timestamp": "a",
                "title": "one",
                "description": "x",
                "flow": 0,
            },
            {
                "message_id": None,
                "timestamp": "b",
                "title": "two",
                "description": "x",
                "flow": 0,
            },
            {
                "message_id": None,
                "timestamp": "c",
                "title": "three",
                "description": "x",
                "flow": 0,
            },
        ]
    )
    result = watcher._dedupe_notifications("messages", first)
    assert len(result) == 3
    assert len(watcher._seen_notifications["messages"]) == 2

    unidentified = pd.DataFrame(
        [
            {
                "message_id": None,
                "timestamp": pd.NaT,
                "title": None,
                "description": None,
                "flow": None,
            },
            {
                "message_id": None,
                "timestamp": pd.NaT,
                "title": None,
                "description": None,
                "flow": None,
            },
        ]
    )
    assert len(watcher._dedupe_notifications("messages", unidentified)) == 2
    assert len(watcher._dedupe_notifications("messages", unidentified.copy())) == 2
    assert len(watcher._seen_notifications["messages"]) == 2


def test_injected_symbol_resolver_is_cached_and_bounded():
    ms._SYMBOL_CACHE.clear()
    calls = [0]

    def request(_, **__):
        calls[0] += 1
        return Response(init_text())

    assert ms._resolve_one_inscode("تست", request)[0] == "111"
    assert ms._resolve_one_inscode("تست", request)[0] == "111"
    assert calls[0] == 1


def test_universe_contract_missing_split_and_typed_empty():
    snapshot = current_snapshot()
    extra = snapshot["stocks"].iloc[[0]].copy()
    extra["InsCode"] = "3090"
    extra["Symbol"] = "پایه"
    extra["InstrumentType"] = 309
    guessed = snapshot["stocks"].iloc[[0]].copy()
    guessed["InsCode"] = "3130"
    guessed["Symbol"] = "حدس"
    guessed["InstrumentType"] = 313
    guessed["PreviousClose"] = 0
    guessed["Last"] = 0
    guessed["Close"] = 0
    snapshot["stocks"] = pd.concat(
        [snapshot["stocks"], extra, guessed], ignore_index=True
    )
    default = ms.get_market_breadth(_snapshot=snapshot).iloc[0]
    assert default["instrument_count"] == 3  # two 300 rows plus verified 309
    without_base = ms.get_market_breadth(
        _snapshot=snapshot, include_base_market=False
    ).iloc[0]
    assert without_base["instrument_count"] == 2
    explicit = ms.get_market_breadth(_snapshot=snapshot, instrument_types=[313]).iloc[0]
    assert explicit["missing_previous_close"] == 1
    assert explicit["missing_current_price"] == 1
    assert explicit["missing"] == 1
    empty = ms.get_market_breadth(_snapshot={"stocks": pd.DataFrame({"x": []})})
    assert empty.empty and list(empty.columns) == ms.BREADTH_COLUMNS
    assert str(empty["instrument_count"].dtype) == "Int64"


def test_sector_zero_coverage_metadata_and_unknown_sector_not_stringified():
    snapshot = current_snapshot()
    snapshot["stocks"].loc[:, "SectorCode"] = pd.NA
    empty_client = pd.DataFrame(columns=ms.CLIENT_COLUMNS)
    result = ms.get_sector_flow(_snapshot=snapshot, _client_type=empty_client)
    assert len(result) == 1 and pd.isna(result.iloc[0]["SectorCode"])
    assert result.iloc[0]["client_covered_count"] == 0
    assert result.iloc[0]["value_method"] == "unavailable"
    assert not bool(result.iloc[0]["value_available"])
    assert result.iloc[0]["exchange_time"] == snapshot["exchange_time"]


def test_typed_empty_notification_and_overview_shapes():
    request = lambda _: Response(payload={})
    assert ms.get_market_messages(_request=request).empty
    assert (
        str(ms.get_market_messages(_request=request)["timestamp"].dtype)
        == "datetime64[ns, Asia/Tehran]"
    )
    assert ms.get_instrument_state_changes(_request=request).empty
    overview = ms.get_market_overview(_request=request)
    assert overview.empty and list(overview.columns) == ["flow"]
    with pytest.raises(InvalidParameterError):
        ms.get_market_messages(top=0, _request=request)
    with pytest.raises(InvalidParameterError):
        ms.MarketWatcher(interval=float("inf"))


def test_one_shot_apis_never_collapse_unidentified_rows():
    messages = {
        "msg": [
            {
                "tseMsgIdn": None,
                "dEven": None,
                "hEven": None,
                "tseTitle": None,
                "tseDesc": None,
                "flow": None,
            },
            {
                "tseMsgIdn": None,
                "dEven": None,
                "hEven": None,
                "tseTitle": None,
                "tseDesc": None,
                "flow": None,
            },
        ]
    }
    result = ms.get_market_messages(_request=lambda _: Response(payload=messages))
    assert len(result) == 2

    states = {
        "instrumentState": [
            {
                "idn": None,
                "dEven": None,
                "hEven": None,
                "insCode": None,
                "cEtaval": None,
            },
            {
                "idn": None,
                "dEven": None,
                "hEven": None,
                "insCode": None,
                "cEtaval": None,
            },
        ]
    }
    result = ms.get_instrument_state_changes(
        _request=lambda _: Response(payload=states)
    )
    assert len(result) == 2


def test_analytics_exact_nullable_dtypes_and_sector_missing_current():
    snapshot = current_snapshot()
    breadth = ms.get_market_breadth(_snapshot=snapshot)
    sector = ms.get_sector_flow(
        _snapshot=snapshot, _client_type=pd.DataFrame(columns=ms.CLIENT_COLUMNS)
    )
    assert "missing_current_price" in sector.columns
    for frame in (breadth, sector):
        for column in (
            "advance_decline_ratio",
            "ad_ratio",
            "advance_pct",
            "decline_pct",
            "advances_pct",
            "declines_pct",
            "total_volume",
            "total_value",
        ):
            assert str(frame[column].dtype) == "Float64"
        assert str(frame["instrument_count"].dtype) == "Int64"
    for column in (
        "client_coverage",
        "net_individual_volume",
        "estimated_net_individual_value",
    ):
        assert str(sector[column].dtype) == "Float64"
    assert str(sector["value_available"].dtype) == "boolean"

    empty_sector = ms.get_sector_flow(
        _snapshot={"stocks": pd.DataFrame()},
        _client_type=pd.DataFrame(columns=ms.CLIENT_COLUMNS),
    )
    assert str(empty_sector["missing_current_price"].dtype) == "Int64"
    assert str(empty_sector["client_coverage"].dtype) == "Float64"


def test_order_patch_is_one_batch_concat(monkeypatch):
    snapshot, refid, heven = ms._initial_state(init_text())
    original_concat = ms.pd.concat
    calls = [0]

    def counted(*args, **kwargs):
        calls[0] += 1
        return original_concat(*args, **kwargs)

    monkeypatch.setattr(ms.pd, "concat", counted)
    orders = ";".join(
        [
            "111,1,1,1,100,101,10,20",
            "111,2,1,1,99,102,10,20",
            "222,1,1,1,200,201,10,20",
        ]
    )
    ms._apply_plus_patch(snapshot, plus(order=orders), refid, heven)
    assert calls[0] == 1
