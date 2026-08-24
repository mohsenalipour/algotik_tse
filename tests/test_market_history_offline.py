import datetime
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import market_history as mh
from algotik_tse.core import market_stream as ms
from algotik_tse.core.market_data import (
    _enrich_live_market,
    _parse_market_watch_response,
)
from algotik_tse.exceptions import DataParsingError, InvalidParameterError

FIXTURE = Path(__file__).parent / "fixtures" / "market_watch_init.txt"
AS_OF = pd.Timestamp("2026-08-23 10:15:31", tz="Asia/Tehran")


def live_frame():
    snapshot = _parse_market_watch_response(
        FIXTURE.read_text(encoding="utf-8"), fetched_at=AS_OF
    )
    snapshot.update(
        {
            "trade_date": datetime.date(2026, 8, 23),
            "exchange_time": AS_OF - pd.Timedelta(seconds=1),
            "fetched_at": AS_OF,
            "is_realtime_fresh": True,
            "is_today_trade_date": True,
            "is_previous_trade_date": False,
            "is_stale": False,
        }
    )
    client = pd.DataFrame(
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
            }
        ]
    )
    return _enrich_live_market(
        snapshot["stocks"],
        client,
        snapshot["order_book"],
        as_of=AS_OF,
        snapshot_metadata=snapshot,
    )


def test_save_load_idempotence_rich_metrics_and_provenance(tmp_path):
    path = tmp_path / "nested" / "market.sqlite"
    live = live_frame()
    first = mh.save_market_snapshot(path, live)
    second = mh.save_market_snapshot(path, live)
    assert first == second and path.exists()
    result = mh.load_market_snapshots(path)
    assert len(result) == len(live)
    assert result["SnapshotID"].nunique() == 1
    assert result.loc[result["InsCode"] == "111", "IndividualPower"].notna().all()
    assert result.loc[result["InsCode"] == "111", "Spread"].iloc[0] == 2
    assert result.attrs["SnapshotAtomic"] is True
    assert result.attrs["SourceAtomic"] is False
    assert not bool(result["SourceAtomic"].iloc[0])
    assert result["PriceSourceAsOf"].iloc[0] == AS_OF
    assert pd.isna(result["ClientSourceAsOf"].iloc[0])
    assert result.attrs["NoBackfill"] is True


def test_default_fetch_is_one_logical_call_and_same_snapshot_derivations(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return live_frame()

    path = tmp_path / "market.sqlite"
    mh.save_market_snapshot(path, _live_fetch=fetch)
    assert calls == [1]
    live = mh.get_live_market_history(path)
    breadth = mh.get_market_breadth_history(path)
    sector = mh.get_sector_flow_history(path)
    overview = mh.get_market_snapshot_summary_history(path)
    assert {live["SnapshotID"].iloc[0]} == set(breadth["SnapshotID"])
    assert set(sector["SnapshotID"]) == set(breadth["SnapshotID"])
    assert set(overview["SnapshotID"]) == set(breadth["SnapshotID"])
    assert breadth["AsOf"].iloc[0] == AS_OF


def test_filters_are_inclusive_strict_and_do_not_future_leak(tmp_path):
    path = tmp_path / "market.sqlite"
    first = live_frame()
    second = first.copy()
    second["as_of"] = AS_OF + pd.Timedelta(minutes=1)
    second["fetched_at"] = AS_OF + pd.Timedelta(minutes=1)
    mh.save_market_snapshot(path, first)
    mh.save_market_snapshot(path, second)
    exact = mh.get_live_market_history(path, start=AS_OF, end=AS_OF)
    assert exact["SnapshotID"].nunique() == 1
    future = mh.get_live_market_history(path, end=AS_OF)
    assert future["AsOf"].max() == AS_OF
    with pytest.raises(InvalidParameterError):
        mh.get_live_market_history(path, start=AS_OF, end=AS_OF - pd.Timedelta(1))


def test_missing_path_is_typed_empty_and_no_implicit_write(tmp_path):
    path = tmp_path / "absent.sqlite"
    result = mh.get_live_market_history(path)
    assert result.empty and not path.exists()
    assert str(result["AsOf"].dtype) == "datetime64[ns, Asia/Tehran]"
    assert str(result["NoBackfill"].dtype) == "boolean"
    with pytest.raises(InvalidParameterError):
        mh.save_market_snapshot(None, live_frame())


def test_concurrent_writers_are_idempotent(tmp_path):
    path = tmp_path / "market.sqlite"
    live = live_frame()
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: mh.save_market_snapshot(path, live), range(8)))
    assert len(set(ids)) == 1
    assert mh.get_live_market_history(path)["SnapshotID"].nunique() == 1


def test_same_asof_different_payload_rolls_back_without_hybrid(tmp_path):
    path = tmp_path / "market.sqlite"
    live = live_frame()
    mh.save_market_snapshot(path, live)
    changed = live.copy()
    changed.loc[0, "Last"] += 1
    with pytest.raises(DataParsingError):
        mh.save_market_snapshot(path, changed)
    loaded = mh.get_live_market_history(path)
    assert loaded.loc[0, "Last"] == live.loc[0, "Last"]
    assert loaded["SnapshotID"].nunique() == 1


def test_corrupt_and_future_schema_are_rejected(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(DataParsingError):
        mh.get_live_market_history(corrupt)
    future = tmp_path / "future.sqlite"
    mh.save_market_snapshot(future, live_frame())
    with sqlite3.connect(future) as connection:
        connection.execute(
            "UPDATE schema_info SET value=? WHERE key='schema_version'", ("999",)
        )
    with pytest.raises(DataParsingError, match="newer"):
        mh.get_live_market_history(future)


def test_market_event_roundtrip_and_dedupe(tmp_path):
    path = tmp_path / "market.sqlite"
    event = ms.MarketEvent(
        kind="initial",
        sequence=1,
        fetched_at=AS_OF,
        trade_date=AS_OF.date(),
        snapshot={"stocks": live_frame().iloc[:1], "market_state": "P"},
        changed_inscodes=("111",),
    )
    first = mh.record_market_event(path, event)
    assert mh.record_market_event(path, event) == first
    result = mh.get_market_event_history(path)
    assert len(result) == 1 and result.iloc[0]["kind"] == "initial"
    assert result.iloc[0]["snapshot"]["stocks"].iloc[0]["InsCode"] == "111"
    assert result.iloc[0]["fetched_at"] == AS_OF


def test_watcher_record_to_is_keyword_only_and_replays(tmp_path):
    class Response:
        status_code = 200
        text = FIXTURE.read_text(encoding="utf-8")

    path = tmp_path / "watch.sqlite"
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=1,
        notifications=(),
        record_to=path,
        _request=lambda _: Response(),
        _clock=lambda: AS_OF,
        _wait=lambda _: False,
    )
    event = next(watcher)
    replay = mh.get_market_event_history(path)
    assert event.kind == "initial" and replay["kind"].tolist() == ["initial"]


def test_message_and_state_archives_dedupe(tmp_path):
    path = tmp_path / "archive.sqlite"
    messages = pd.DataFrame(
        [
            {
                "message_id": 1,
                "date": 20260823,
                "time": 101500,
                "timestamp": AS_OF,
                "title": "a",
                "description": "b",
                "flow": 0,
            }
        ]
    )
    states = pd.DataFrame(
        [{"event_id": 2, "timestamp": AS_OF, "InsCode": "111", "state_code": "A"}]
    )
    for kind, frame in (
        ("messages", messages),
        ("state_changes", states),
    ):
        assert mh.archive_market_records(path, kind, frame, recorded_at=AS_OF) == 1
        assert mh.archive_market_records(path, kind, frame, recorded_at=AS_OF) == 0
    assert len(mh.get_market_messages_history(path)) == 1
    assert len(mh.get_instrument_state_changes_history(path)) == 1


def test_fetch_archive_to_additive_keyword(monkeypatch, tmp_path):
    class Response:
        status_code = 200

        def json(self):
            return {
                "msg": [
                    {
                        "tseMsgIdn": 1,
                        "dEven": 20260823,
                        "hEven": 101531,
                        "tseTitle": "a",
                        "tseDesc": "b",
                        "flow": 0,
                    }
                ]
            }

    path = tmp_path / "archive.sqlite"
    result = ms.get_market_messages(archive_to=path, _request=lambda _: Response())
    assert result["message_id"].tolist() == [1]
    assert mh.get_market_messages_history(path)["message_id"].tolist() == [1]


def test_top_level_exports():
    assert att.save_market_snapshot is mh.save_market_snapshot
    assert att.get_market_event_history is mh.get_market_event_history
    assert att.MARKET_HISTORY_SCHEMA_VERSION == 2


def test_snapshot_source_timestamp_mismatch_and_ambiguity_rejected(tmp_path):
    live = live_frame()
    with pytest.raises(InvalidParameterError, match="does not match"):
        mh.save_market_snapshot(
            tmp_path / "mismatch.sqlite",
            live,
            as_of=AS_OF + pd.Timedelta(seconds=1),
        )
    ambiguous = live.copy()
    ambiguous.loc[1, "fetched_at"] = AS_OF + pd.Timedelta(seconds=1)
    with pytest.raises(InvalidParameterError, match="ambiguous"):
        mh.save_market_snapshot(tmp_path / "ambiguous.sqlite", ambiguous)


def test_jalali_and_date_only_end_are_inclusive_and_dtype_stable(tmp_path):
    path = tmp_path / "market.sqlite"
    mh.save_market_snapshot(path, live_frame())
    jalali = mh.get_live_market_history(path, start="1405-06-01", end="1405-06-01")
    assert not jalali.empty and jalali["AsOf"].iloc[0] == AS_OF
    empty = mh.get_live_market_history(path, start="1405-06-02", end="1405-06-02")
    assert empty.empty
    assert list(empty.columns) == list(jalali.columns)
    assert empty.dtypes.astype(str).to_dict() == jalali.dtypes.astype(str).to_dict()


def test_archive_observation_time_not_old_provider_time_and_correction_versions(
    tmp_path,
):
    path = tmp_path / "archive.sqlite"
    observed1 = pd.Timestamp("2026-08-23 12:00", tz="Asia/Tehran")
    observed2 = observed1 + pd.Timedelta(hours=1)
    old_provider = pd.Timestamp("2020-01-01 09:00", tz="Asia/Tehran")
    first = pd.DataFrame(
        [
            {
                "message_id": 7,
                "date": 20200101,
                "time": 90000,
                "timestamp": old_provider,
                "title": "first",
                "description": "x",
                "flow": 0,
            }
        ]
    )
    corrected = first.copy()
    corrected["title"] = "corrected"
    assert (
        mh.archive_market_records(path, "messages", first, recorded_at=observed1) == 1
    )
    assert (
        mh.archive_market_records(path, "messages", first, recorded_at=observed2) == 0
    )
    assert mh.get_market_messages_history(path, end="2025-12-31").empty
    assert (
        mh.archive_market_records(path, "messages", corrected, recorded_at=observed2)
        == 1
    )
    before = mh.get_market_messages_history(path, end=observed1)
    after = mh.get_market_messages_history(path, end=observed2)
    assert before.iloc[0]["title"] == "first" and before.iloc[0]["Version"] == 1
    assert after.iloc[0]["title"] == "corrected" and after.iloc[0]["Version"] == 2
    assert after.iloc[0]["ObservedAt"] == observed2
    assert after.iloc[0]["ProviderTimestamp"] == old_provider
    assert after.iloc[0]["FirstObservedAt"] == observed1


def test_archive_source_identity_and_selectors(tmp_path):
    path = tmp_path / "archive.sqlite"
    at = pd.Timestamp("2026-08-23 12:00", tz="Asia/Tehran")
    rows = pd.DataFrame(
        [
            {
                "message_id": 1,
                "timestamp": at,
                "title": "a",
                "description": "x",
                "flow": 0,
            },
            {
                "message_id": 2,
                "timestamp": at,
                "title": "b",
                "description": "x",
                "flow": 1,
            },
        ]
    )
    mh.archive_market_records(path, "messages", rows, source="one", recorded_at=at)
    mh.archive_market_records(
        path, "messages", rows.iloc[[0]], source="two", recorded_at=at
    )
    selected = mh.get_market_messages_history(path, flow=1, since_id=1, source="one")
    assert selected["message_id"].tolist() == [2]
    both_sources = mh.get_market_messages_history(path, flow=None, source=None)
    assert len(both_sources) == 3
    empty = mh.get_market_messages_history(
        path, start=at + pd.Timedelta(days=1), source="one"
    )
    one = mh.get_market_messages_history(path, source="one")
    assert list(empty.columns) == list(one.columns)
    assert empty.dtypes.astype(str).to_dict() == one.dtypes.astype(str).to_dict()


def test_exact_provider_overview_archive_is_distinct_from_snapshot_summary(tmp_path):
    class Response:
        status_code = 200

        def json(self):
            return {"marketOverview": {"flow": 0, "marketValue": 12345}}

    path = tmp_path / "overview.sqlite"
    observed = pd.Timestamp("2026-08-23 12:00", tz="Asia/Tehran")
    live = ms.get_market_overview(
        archive_to=path, _recorded_at=observed, _request=lambda _: Response()
    )
    history = mh.get_market_overview_history(path)
    assert live.loc[0, "marketValue"] == history.loc[0, "marketValue"] == 12345
    assert history.loc[0, "ObservedAt"] == observed
    assert "SnapshotID" not in history.columns


def test_watcher_storage_failure_is_fail_fast_and_does_not_advance(
    monkeypatch, tmp_path
):
    class Response:
        status_code = 200
        text = FIXTURE.read_text(encoding="utf-8")

    original = mh.record_market_event
    attempts = [0]

    def flaky(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] == 1:
            raise sqlite3.OperationalError("disk full")
        return original(*args, **kwargs)

    monkeypatch.setattr(mh, "record_market_event", flaky)
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=1,
        notifications=(),
        record_to=tmp_path / "watch.sqlite",
        _request=lambda _: Response(),
        _clock=lambda: AS_OF,
        _wait=lambda _: False,
    )
    with pytest.raises(DataParsingError, match="persistence"):
        next(watcher)
    assert watcher._emitted == watcher._sequence == 0
    assert not watcher._initialized and watcher._refid == 0
    assert next(watcher).sequence == 1
    with pytest.raises(StopIteration):
        next(watcher)


def test_two_watcher_sessions_do_not_collide_and_heartbeat_not_recorded(tmp_path):
    class Response:
        status_code = 200

        def __init__(self, text):
            self.text = text

    path = tmp_path / "watch.sqlite"
    for _ in range(2):
        watcher = ms.MarketWatcher(
            interval=0,
            max_updates=1,
            notifications=(),
            record_to=path,
            _request=lambda _: Response(FIXTURE.read_text(encoding="utf-8")),
            _clock=lambda: AS_OF,
            _wait=lambda _: False,
        )
        next(watcher)
    events = mh.get_market_event_history(path)
    assert len(events) == 2 and events["SessionID"].nunique() == 2

    plus = "1,2,3@05/06/01 10:15:35,P,2500001@@@0"
    replies = iter([Response(FIXTURE.read_text(encoding="utf-8")), Response(plus)])
    heartbeat_path = tmp_path / "heartbeat.sqlite"
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=2,
        notifications=(),
        record_to=heartbeat_path,
        _request=lambda _: next(replies),
        _clock=lambda: AS_OF,
        _wait=lambda _: False,
    )
    assert next(watcher).kind == "initial"
    assert next(watcher).kind == "heartbeat"
    assert mh.get_market_event_history(heartbeat_path)["kind"].tolist() == ["initial"]


def test_delta_event_is_bounded_and_all_event_asof_are_row_specific(tmp_path):
    class Response:
        status_code = 200

        def __init__(self, text):
            self.text = text

    plus = (
        "1,2,3@05/06/01 10:15:35,P,2500001@"
        "111,101535,100,111,113,11,1100,124000,98,115@@1000"
    )
    replies = iter([Response(FIXTURE.read_text(encoding="utf-8")), Response(plus)])
    times = iter([AS_OF, AS_OF + pd.Timedelta(seconds=1)])
    path = tmp_path / "delta.sqlite"
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=2,
        notifications=(),
        record_to=path,
        checkpoint_interval=100,
        _request=lambda _: next(replies),
        _clock=lambda: next(times),
        _wait=lambda _: False,
    )
    next(watcher)
    next(watcher)
    events = mh.get_market_event_history(path)
    assert events["SnapshotMode"].tolist() == ["checkpoint", "delta"]
    assert events["AsOf"].tolist() == [AS_OF, AS_OF + pd.Timedelta(seconds=1)]
    assert len(events.iloc[1]["snapshot"]["stocks"]) == 1


def test_event_retention_and_max_records_are_bounded(tmp_path):
    path = tmp_path / "bounded.sqlite"
    for sequence in range(1, 4):
        event = ms.MarketEvent(
            kind="delta",
            sequence=sequence,
            fetched_at=AS_OF + pd.Timedelta(seconds=sequence),
            trade_date=AS_OF.date(),
            snapshot={"stocks": live_frame().iloc[[0]]},
            changed_inscodes=("111",),
        )
        mh.record_market_event(
            path,
            event,
            session_id="bounded",
            include_snapshot=sequence == 3,
            max_records=2,
        )
    result = mh.get_market_event_history(path)
    assert result["sequence"].tolist() == [3]
    assert result["SnapshotMode"].tolist() == ["checkpoint"]


def test_foreign_database_corrupt_payload_and_query_caps(tmp_path):
    foreign = tmp_path / "foreign.sqlite"
    with sqlite3.connect(foreign) as connection:
        connection.execute("CREATE TABLE user_data(x INTEGER)")
    with pytest.raises(DataParsingError, match="foreign|unowned"):
        mh.save_market_snapshot(foreign, live_frame())
    with sqlite3.connect(foreign) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='user_data'"
        ).fetchone()
        assert connection.execute("PRAGMA application_id").fetchone()[0] == 0

    path = tmp_path / "market.sqlite"
    mh.save_market_snapshot(path, live_frame())
    assert mh.check_market_history(path)["ok"] is True
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE snapshots SET payload_json='not-json'")
    with pytest.raises(DataParsingError, match="snapshots record"):
        mh.get_live_market_history(path)
    with pytest.raises(InvalidParameterError, match="limit"):
        mh.get_market_event_history(path, limit=10001)


def test_watcher_ignore_storage_failure_commits_and_reports_initial_and_delta(
    monkeypatch, tmp_path
):
    class Response:
        status_code = 200

        def __init__(self, text):
            self.text = text

    original = mh.record_market_event
    attempts = [0]

    def fail_second(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] == 2:
            raise sqlite3.OperationalError("disk full")
        return original(*args, **kwargs)

    plus = (
        "1,2,3@05/06/01 10:15:35,P,2500001@"
        "111,101535,100,111,113,11,1100,124000,98,115@@1000"
    )
    replies = iter([Response(FIXTURE.read_text(encoding="utf-8")), Response(plus)])
    times = iter([AS_OF, AS_OF + pd.Timedelta(seconds=1)])
    monkeypatch.setattr(mh, "record_market_event", fail_second)
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=2,
        notifications=(),
        record_to=tmp_path / "ignore.sqlite",
        storage_error_policy="ignore",
        _request=lambda _: next(replies),
        _clock=lambda: next(times),
        _wait=lambda _: False,
    )
    initial = next(watcher)
    delta = next(watcher)
    assert initial.persistence_status == "persisted"
    assert delta.persistence_status == "failed_ignored"
    assert "disk full" in delta.persistence_error
    assert watcher._refid == delta.cursor_after == 1000
    assert watcher._sequence == watcher._emitted == 2
    with pytest.raises(StopIteration):
        next(watcher)

    monkeypatch.setattr(
        mh,
        "record_market_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("read only")
        ),
    )
    initial_only = ms.MarketWatcher(
        interval=0,
        max_updates=1,
        notifications=(),
        record_to=tmp_path / "ignored-initial.sqlite",
        storage_error_policy="ignore",
        _request=lambda _: Response(FIXTURE.read_text(encoding="utf-8")),
        _clock=lambda: AS_OF,
        _wait=lambda _: False,
    )
    failed_initial = next(initial_only)
    assert failed_initial.persistence_status == "failed_ignored"
    assert initial_only._initialized and initial_only._emitted == 1


def test_first_persisted_event_is_checkpoint_and_heartbeat_gaps_do_not_count(tmp_path):
    class Response:
        status_code = 200

        def __init__(self, text):
            self.text = text

    plus = (
        "1,2,3@05/06/01 10:15:35,P,2500001@"
        "111,101535,100,111,113,11,1100,124000,98,115@@1000"
    )
    replies = iter([Response(FIXTURE.read_text(encoding="utf-8")), Response(plus)])
    first_path = tmp_path / "no-initial.sqlite"
    watcher = ms.MarketWatcher(
        interval=0,
        max_updates=1,
        include_initial=False,
        notifications=(),
        record_to=first_path,
        _request=lambda _: next(replies),
        _clock=lambda: AS_OF,
        _wait=lambda _: False,
    )
    assert next(watcher).kind == "delta"
    first = mh.get_market_event_history(first_path)
    assert first["SnapshotMode"].tolist() == ["checkpoint"]

    gap_path = tmp_path / "gaps.sqlite"
    gap_watcher = ms.MarketWatcher(
        record_to=gap_path,
        checkpoint_interval=2,
        notifications=(),
    )
    snapshot = {
        "stocks": live_frame().iloc[[0]],
        "order_book": pd.DataFrame(),
        "market_state": "P",
        "trade_date": AS_OF.date(),
    }
    gap_watcher._event("initial", None, snapshot, AS_OF)
    gap_watcher._event("heartbeat", snapshot, snapshot, AS_OF)
    gap_watcher._event(
        "delta", snapshot, snapshot, AS_OF, {"changed_inscodes": ("111",)}
    )
    gap_watcher._event("heartbeat", snapshot, snapshot, AS_OF)
    gap_watcher._event(
        "delta", snapshot, snapshot, AS_OF, {"changed_inscodes": ("111",)}
    )
    gaps = mh.get_market_event_history(gap_path)
    assert gaps["sequence"].tolist() == [1, 3, 5]
    assert gaps["SnapshotMode"].tolist() == ["checkpoint", "delta", "checkpoint"]


def test_checkpoint_boundary_pruning_keeps_replayable_oldest_row(tmp_path):
    path = tmp_path / "prune.sqlite"
    for sequence in range(1, 6):
        event = ms.MarketEvent(
            kind="delta",
            sequence=sequence,
            fetched_at=AS_OF + pd.Timedelta(seconds=sequence),
            trade_date=AS_OF.date(),
            snapshot={"stocks": live_frame().iloc[[0]]},
            changed_inscodes=("111",),
        )
        mh.record_market_event(
            path,
            event,
            session_id="replay",
            include_snapshot=sequence == 4,
            max_records=3,
        )
    replay = mh.get_market_event_history(path, session_id="replay")
    assert replay["sequence"].tolist() == [4, 5]
    assert replay.iloc[0]["SnapshotMode"] == "checkpoint"


def test_archive_filters_are_sql_bounded_before_pagination_and_state_since_id(
    tmp_path,
):
    path = tmp_path / "many.sqlite"
    rows = pd.DataFrame(
        {
            "message_id": range(1, 10002),
            "title": ["x"] * 10001,
            "flow": [0] * 10000 + [1],
        }
    )
    assert mh.archive_market_records(path, "messages", rows, recorded_at=AS_OF) == 10001
    selected = mh.get_market_messages_history(path, flow=1, limit=1)
    assert selected["message_id"].tolist() == [10001]

    states = pd.DataFrame(
        [
            {"event_id": 10, "InsCode": "111", "Symbol": "الف"},
            {"event_id": 11, "InsCode": "222", "Symbol": "ب"},
        ]
    )
    mh.archive_market_records(path, "state_changes", states, recorded_at=AS_OF)
    state = mh.get_instrument_state_changes_history(
        path, symbol="222", since_id=10, limit=1
    )
    assert state["event_id"].tolist() == [11]


def test_nested_typed_json_errors_are_contextual_for_all_history_tables(tmp_path):
    snapshot_path = tmp_path / "snapshot.sqlite"
    mh.save_market_snapshot(snapshot_path, live_frame())
    with sqlite3.connect(snapshot_path) as connection:
        raw = connection.execute("SELECT payload_json FROM snapshots").fetchone()[0]
        payload = json.loads(raw)
        column = payload["live"]["columns"].index("fetched_at")
        payload["live"]["rows"][0][column] = {
            "__type__": "timestamp",
            "value": "not-a-timestamp",
        }
        connection.execute(
            "UPDATE snapshots SET payload_json=?",
            (json.dumps(payload, separators=(",", ":")),),
        )
    with pytest.raises(DataParsingError, match="snapshots record.*field live"):
        mh.get_live_market_history(snapshot_path)

    event_path = tmp_path / "event.sqlite"
    event = ms.MarketEvent(
        kind="initial",
        sequence=1,
        fetched_at=AS_OF,
        trade_date=AS_OF.date(),
        snapshot={"stocks": live_frame().iloc[[0]]},
    )
    mh.record_market_event(event_path, event, session_id="bad-event")
    with sqlite3.connect(event_path) as connection:
        raw = connection.execute("SELECT payload_json FROM events").fetchone()[0]
        payload = json.loads(raw)
        payload["fetched_at"] = {"__type__": "timestamp", "value": "bad"}
        connection.execute(
            "UPDATE events SET payload_json=?",
            (json.dumps(payload, separators=(",", ":")),),
        )
    with pytest.raises(DataParsingError, match="events record"):
        mh.get_market_event_history(event_path)

    archive_path = tmp_path / "archive-corrupt.sqlite"
    message = pd.DataFrame(
        [{"message_id": 1, "timestamp": AS_OF, "title": "x", "flow": 0}]
    )
    mh.archive_market_records(archive_path, "messages", message, recorded_at=AS_OF)
    with sqlite3.connect(archive_path) as connection:
        raw = connection.execute("SELECT payload_json FROM archives").fetchone()[0]
        payload = json.loads(raw)
        payload["row"]["timestamp"] = {
            "__type__": "timestamp",
            "value": "bad",
        }
        connection.execute(
            "UPDATE archives SET payload_json=?",
            (json.dumps(payload, separators=(",", ":")),),
        )
    with pytest.raises(DataParsingError, match="archives record"):
        mh.get_market_messages_history(archive_path)


def test_owned_weakened_schema_is_rejected(tmp_path):
    path = tmp_path / "weakened.sqlite"
    mh.save_market_snapshot(path, live_frame())
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX ix_events_asof")
    with pytest.raises(DataParsingError, match="index ix_events_asof"):
        mh.get_market_event_history(path)


def test_application_id_without_owner_marker_is_not_mutated(tmp_path):
    path = tmp_path / "application-id-collision.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA application_id={mh.MARKET_HISTORY_APPLICATION_ID}")
        connection.execute("CREATE TABLE user_data(x INTEGER)")
    with pytest.raises(DataParsingError, match="schema|owner|metadata"):
        mh.save_market_snapshot(path, live_frame())
    with sqlite3.connect(path) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert names == {"user_data"}


def test_direct_event_retention_is_hard_bounded_without_requested_checkpoints(
    tmp_path,
):
    path = tmp_path / "hard-bound.sqlite"
    for sequence in range(1, 5):
        event = ms.MarketEvent(
            kind="delta",
            sequence=sequence,
            fetched_at=AS_OF + pd.Timedelta(seconds=sequence),
            trade_date=AS_OF.date(),
            snapshot={"stocks": live_frame().iloc[[0]]},
            changed_inscodes=("111",),
        )
        mh.record_market_event(
            path,
            event,
            session_id="direct",
            include_snapshot=False,
            max_records=2,
        )
    replay = mh.get_market_event_history(path, session_id="direct")
    assert len(replay) <= 2
    assert replay["sequence"].tolist() == [3, 4]
    assert replay["SnapshotMode"].tolist() == ["checkpoint", "delta"]


def test_event_bounds_are_global_across_sessions_and_retention(tmp_path):
    max_path = tmp_path / "global-max.sqlite"
    for session, offset in (("old", 0), ("new", 1)):
        event = ms.MarketEvent(
            kind="initial",
            sequence=1,
            fetched_at=AS_OF + pd.Timedelta(seconds=offset),
            trade_date=AS_OF.date(),
            snapshot={"stocks": live_frame().iloc[[0]]},
        )
        mh.record_market_event(max_path, event, session_id=session, max_records=1)
    bounded = mh.get_market_event_history(max_path)
    assert len(bounded) == 1
    assert bounded["SessionID"].tolist() == ["new"]
    assert bounded["SnapshotMode"].tolist() == ["checkpoint"]

    retention_path = tmp_path / "global-retention.sqlite"
    for session, offset in (("expired", 0), ("fresh", 20)):
        event = ms.MarketEvent(
            kind="initial",
            sequence=1,
            fetched_at=AS_OF + pd.Timedelta(seconds=offset),
            trade_date=AS_OF.date(),
            snapshot={"stocks": live_frame().iloc[[0]]},
        )
        mh.record_market_event(
            retention_path,
            event,
            session_id=session,
            max_records=100,
            retention_seconds=10,
        )
    retained = mh.get_market_event_history(retention_path)
    assert retained["SessionID"].tolist() == ["fresh"]
    assert retained.iloc[0]["SnapshotMode"] == "checkpoint"


def test_ignored_persistence_gap_forces_next_successful_checkpoint(
    monkeypatch, tmp_path
):
    path = tmp_path / "gap.sqlite"
    original = mh.record_market_event
    calls = [0]

    def fail_second(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:
            raise sqlite3.OperationalError("temporary storage failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(mh, "record_market_event", fail_second)
    watcher = ms.MarketWatcher(
        record_to=path,
        checkpoint_interval=100,
        storage_error_policy="ignore",
        notifications=(),
    )
    snapshot = {
        "stocks": live_frame().iloc[[0]],
        "order_book": pd.DataFrame(),
        "market_state": "P",
        "trade_date": AS_OF.date(),
    }
    first = watcher._event("initial", None, snapshot, AS_OF)
    failed = watcher._event(
        "delta",
        snapshot,
        snapshot,
        AS_OF + pd.Timedelta(seconds=1),
        {"changed_inscodes": ("111",)},
    )
    recovered = watcher._event(
        "delta",
        snapshot,
        snapshot,
        AS_OF + pd.Timedelta(seconds=2),
        {"changed_inscodes": ("111",)},
    )
    assert first.persistence_status == "persisted"
    assert failed.persistence_status == "failed_ignored"
    assert recovered.persistence_status == "persisted"
    replay = mh.get_market_event_history(path)
    assert replay["sequence"].tolist() == [1, 3]
    assert replay["SnapshotMode"].tolist() == ["checkpoint", "checkpoint"]


def test_initializer_publishes_application_id_owner_and_schema_atomically(
    monkeypatch, tmp_path
):
    path = tmp_path / "atomic-publish.sqlite"
    reached = threading.Event()
    release = threading.Event()
    original = mh._validate_schema
    calls = [0]

    def pause_first_validation(connection):
        calls[0] += 1
        if calls[0] == 1:
            reached.set()
            assert release.wait(5)
        return original(connection)

    monkeypatch.setattr(mh, "_validate_schema", pause_first_validation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(mh.save_market_snapshot, path, live_frame())
        assert reached.wait(5)
        with sqlite3.connect(path, timeout=1) as observer:
            assert observer.execute("PRAGMA application_id").fetchone()[0] == 0
            visible = {
                row[0]
                for row in observer.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "schema_info" not in visible
        second = pool.submit(mh.save_market_snapshot, path, live_frame())
        assert not second.done()
        release.set()
        assert first.result(timeout=10) == second.result(timeout=10)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("PRAGMA application_id").fetchone()[0]
            == mh.MARKET_HISTORY_APPLICATION_ID
        )
        assert (
            connection.execute(
                "SELECT value FROM schema_info WHERE key='owner'"
            ).fetchone()[0]
            == "algotik-tse-market-history"
        )


def test_archive_coverage_start_uses_source_and_selectors(tmp_path):
    path = tmp_path / "coverage.sqlite"
    early = AS_OF
    late = AS_OF + pd.Timedelta(hours=1)
    mh.archive_market_records(
        path,
        "messages",
        pd.DataFrame([{"message_id": 1, "flow": 0, "title": "early"}]),
        source="early-source",
        recorded_at=early,
    )
    mh.archive_market_records(
        path,
        "messages",
        pd.DataFrame([{"message_id": 2, "flow": 1, "title": "late"}]),
        source="late-source",
        recorded_at=late,
    )
    selected = mh.get_market_messages_history(path, flow=1, source="late-source")
    assert selected.attrs["CoverageStart"] == late
    assert selected["CoverageStart"].tolist() == [late]
