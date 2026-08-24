"""Explicit local history for live TSETMC snapshots and event feeds.

TSETMC does not expose point-in-time history for every live field.  This
module therefore records observations only after the user supplies a path;
it never writes implicitly and never labels locally recorded observations as
provider backfill.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import math
import sqlite3
import warnings
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from persiantools.jdatetime import JalaliDate

from ..exceptions import DataParsingError, InvalidParameterError
from .market_data import (
    CLIENT_COLUMNS,
    ORDER_COLUMNS,
    STOCK_COLUMNS,
    _enrich_live_market,
    _instrument_mask,
)
from .market_stream import (
    BREADTH_COLUMNS,
    MESSAGE_COLUMNS,
    SECTOR_FLOW_COLUMNS,
    STATE_COLUMNS,
    MarketEvent,
    _breadth_record,
    _cast_analytics_frame,
    _filter_universe,
    get_market_breadth,
)

MARKET_HISTORY_SCHEMA_VERSION = 2
MARKET_HISTORY_APPLICATION_ID = 0x41545345  # ASCII "ATSE"
_OWNER_MARKER = "algotik-tse-market-history"
_TEHRAN = "Asia/Tehran"
_MAX_QUERY_LIMIT = 10_000
_DEFAULT_QUERY_LIMIT = 1_000
_WATCHER_EVENT_KINDS = frozenset({"initial", "delta", "heartbeat", "resync"})
_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_META_COLUMNS = [
    "SnapshotID",
    "AsOf",
    "Source",
    "SchemaVersion",
    "NoBackfill",
    "CoverageStart",
    "SnapshotAtomic",
    "PersistenceAtomic",
    "SourceAtomic",
    "PriceSourceAsOf",
    "ClientSourceAsOf",
    "NoLookahead",
]
_EVENT_COLUMNS = [
    "event_id",
    "SessionID",
    "kind",
    "SnapshotMode",
    "sequence",
    "fetched_at",
    "trade_date",
    "changed_inscodes",
    "changed_order_levels",
    "market_state_changed",
    "notification_tokens",
    "cursor_before",
    "cursor_after",
    "retry_count",
    "retry_error",
    "notification_errors",
    "snapshot",
    "messages",
    "state_changes",
]
_OVERVIEW_COLUMNS = [
    "flow",
    "instrument_count",
    "trade_count",
    "total_volume",
    "total_value",
    "market_cap",
    "trade_date",
    "exchange_time",
    "fetched_at",
    "is_realtime_fresh",
]


def _path(value, *, create_parent=False) -> Path:
    if value is None or not str(value).strip():
        raise InvalidParameterError(
            "an explicit non-empty persistence path is required"
        )
    text = str(value).strip()
    if text == ":memory:" or text.lower().startswith("file::memory:"):
        raise InvalidParameterError("in-memory SQLite paths are not supported")
    path = Path(text).expanduser()
    if path.stem.upper() in _DEVICE_NAMES:
        raise InvalidParameterError("device paths are not supported")
    if path.exists() and path.is_dir():
        raise InvalidParameterError("persistence path must be a SQLite file")
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(value, *, create=False):
    path = _path(value, create_parent=create)
    if not create and not path.exists():
        return None
    connection = None
    try:
        connection = sqlite3.connect(
            str(path), timeout=10.0, isolation_level=None, check_same_thread=False
        )
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        if create:
            application_id = int(
                connection.execute("PRAGMA application_id").fetchone()[0]
            )
            if application_id not in {0, MARKET_HISTORY_APPLICATION_ID}:
                raise DataParsingError("refusing to mutate a foreign SQLite database")
            initialise = application_id == 0
            if not initialise:
                # Both ownership signals must already be valid before any
                # write-side PRAGMA or DDL can touch a pre-existing file.
                # The lock also waits for a concurrent first writer to finish
                # creating the marker/schema before validation begins.
                connection.execute("BEGIN IMMEDIATE")
                try:
                    _validate_schema(connection)
                finally:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
            if initialise:
                _initialise(connection)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                # A concurrent validated writer can be switching journal
                # mode. The following write transaction observes busy_timeout.
                if "locked" not in str(exc).lower():
                    raise
        else:
            _validate_schema(connection)
        return connection
    except sqlite3.DatabaseError as exc:
        if connection is not None:
            connection.close()
        raise DataParsingError(
            f"invalid or corrupted market history database: {exc}"
        ) from exc
    except Exception:
        if connection is not None:
            connection.close()
        raise


def _initialise(connection):
    try:
        connection.execute("BEGIN IMMEDIATE")
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        if application_id == MARKET_HISTORY_APPLICATION_ID:
            # Another first writer may have completed while this connection
            # waited for BEGIN IMMEDIATE. Validate its atomically published
            # schema rather than attempting a second initialization.
            _validate_schema(connection)
            connection.execute("COMMIT")
            return
        if application_id != 0:
            raise DataParsingError("refusing to initialize a foreign SQLite database")
        objects = connection.execute(
            "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if objects:
            raise DataParsingError(
                "refusing to initialize an unowned non-empty SQLite database"
            )
        connection.execute(f"PRAGMA application_id={MARKET_HISTORY_APPLICATION_ID}")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_info ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        owner = connection.execute(
            "SELECT value FROM schema_info WHERE key='owner'"
        ).fetchone()
        if owner is None:
            connection.execute(
                "INSERT INTO schema_info(key,value) VALUES('owner',?)",
                (_OWNER_MARKER,),
            )
        elif owner[0] != _OWNER_MARKER:
            raise DataParsingError("market history ownership marker is invalid")
        row = connection.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO schema_info(key,value) VALUES('schema_version',?)",
                (str(MARKET_HISTORY_SCHEMA_VERSION),),
            )
        else:
            _check_version(row[0])
        connection.execute(
            "CREATE TABLE IF NOT EXISTS snapshots ("
            "snapshot_id TEXT PRIMARY KEY, as_of_utc TEXT NOT NULL UNIQUE, "
            "payload_json TEXT NOT NULL, created_at_utc TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "event_id TEXT PRIMARY KEY, as_of_utc TEXT NOT NULL, "
            "session_id TEXT NOT NULL, sequence INTEGER NOT NULL, kind TEXT NOT NULL, "
            "snapshot_mode TEXT NOT NULL CHECK(snapshot_mode IN ('checkpoint','delta')), "
            "payload_json TEXT NOT NULL, UNIQUE(session_id,sequence))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS archives ("
            "kind TEXT NOT NULL, source TEXT NOT NULL, identity TEXT NOT NULL, "
            "version INTEGER NOT NULL CHECK(version >= 1), observed_at_utc TEXT NOT NULL, "
            "provider_timestamp_utc TEXT, payload_hash TEXT NOT NULL, "
            "flow INTEGER, provider_id TEXT, provider_id_num INTEGER, "
            "inscode TEXT, symbol TEXT, payload_json TEXT NOT NULL, "
            "PRIMARY KEY(kind, source, identity, version))"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_snapshots_asof ON snapshots(as_of_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_events_asof ON events(as_of_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_events_session_replay "
            "ON events(session_id,sequence)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_archives_kind_asof "
            "ON archives(kind, observed_at_utc)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_archives_lookup "
            "ON archives(kind,source,observed_at_utc,flow,provider_id_num,inscode,symbol)"
        )
        _validate_schema(connection)
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


def _check_version(raw):
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise DataParsingError("market history schema version is corrupted") from exc
    if version > MARKET_HISTORY_SCHEMA_VERSION:
        raise DataParsingError(
            f"market history schema {version} is newer than supported "
            f"schema {MARKET_HISTORY_SCHEMA_VERSION}"
        )
    if version != MARKET_HISTORY_SCHEMA_VERSION:
        raise DataParsingError(f"unsupported market history schema {version}")


def _validate_schema(connection):
    try:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        if application_id != MARKET_HISTORY_APPLICATION_ID:
            raise DataParsingError(
                "SQLite database is not owned by algotik-tse market history"
            )
        row = connection.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'"
        ).fetchone()
        if row is None:
            raise DataParsingError("market history schema metadata is missing")
        _check_version(row[0])
        owner = connection.execute(
            "SELECT value FROM schema_info WHERE key='owner'"
        ).fetchone()
        if owner is None or owner[0] != _OWNER_MARKER:
            raise DataParsingError("market history ownership marker is invalid")
        required = {"schema_info", "snapshots", "events", "archives"}
        present = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required.issubset(present):
            raise DataParsingError("market history schema tables are missing")
        expected_columns = {
            "schema_info": {
                "key": ("TEXT", 0, 1),
                "value": ("TEXT", 1, 0),
            },
            "snapshots": {
                "snapshot_id": ("TEXT", 0, 1),
                "as_of_utc": ("TEXT", 1, 0),
                "payload_json": ("TEXT", 1, 0),
                "created_at_utc": ("TEXT", 1, 0),
            },
            "events": {
                "event_id": ("TEXT", 0, 1),
                "as_of_utc": ("TEXT", 1, 0),
                "session_id": ("TEXT", 1, 0),
                "sequence": ("INTEGER", 1, 0),
                "kind": ("TEXT", 1, 0),
                "snapshot_mode": ("TEXT", 1, 0),
                "payload_json": ("TEXT", 1, 0),
            },
            "archives": {
                "kind": ("TEXT", 1, 1),
                "source": ("TEXT", 1, 2),
                "identity": ("TEXT", 1, 3),
                "version": ("INTEGER", 1, 4),
                "observed_at_utc": ("TEXT", 1, 0),
                "provider_timestamp_utc": ("TEXT", 0, 0),
                "payload_hash": ("TEXT", 1, 0),
                "flow": ("INTEGER", 0, 0),
                "provider_id": ("TEXT", 0, 0),
                "provider_id_num": ("INTEGER", 0, 0),
                "inscode": ("TEXT", 0, 0),
                "symbol": ("TEXT", 0, 0),
                "payload_json": ("TEXT", 1, 0),
            },
        }
        for table, expected in expected_columns.items():
            table_info = list(connection.execute(f"PRAGMA table_info({table})"))
            actual = {
                item[1]: (str(item[2]).upper(), int(item[3]), int(item[5]))
                for item in table_info
            }
            if actual != expected:
                raise DataParsingError(
                    f"market history table {table} has incompatible column declarations"
                )
            if list(connection.execute(f"PRAGMA foreign_key_list({table})")):
                raise DataParsingError(
                    f"market history table {table} has incompatible foreign keys"
                )
        expected_indexes = {
            "ix_snapshots_asof": ("snapshots", ("as_of_utc",)),
            "ix_events_asof": ("events", ("as_of_utc",)),
            "ix_events_session_replay": ("events", ("session_id", "sequence")),
            "ix_archives_kind_asof": ("archives", ("kind", "observed_at_utc")),
            "ix_archives_lookup": (
                "archives",
                (
                    "kind",
                    "source",
                    "observed_at_utc",
                    "flow",
                    "provider_id_num",
                    "inscode",
                    "symbol",
                ),
            ),
        }
        indexes = {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                "SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index'"
            )
        }
        for name, (table, columns) in expected_indexes.items():
            if name not in indexes or indexes[name][0] != table:
                raise DataParsingError(f"market history index {name} is missing")
            actual = tuple(
                row[2] for row in connection.execute(f"PRAGMA index_info('{name}')")
            )
            if actual != columns:
                raise DataParsingError(
                    f"market history index {name} has incompatible columns"
                )
        for table, required_unique in {
            "snapshots": {("as_of_utc",)},
            "events": {("session_id", "sequence")},
        }.items():
            unique_columns = set()
            for index in connection.execute(f"PRAGMA index_list({table})"):
                if not index[2]:
                    continue
                columns = tuple(
                    row[2]
                    for row in connection.execute(f"PRAGMA index_info('{index[1]}')")
                )
                unique_columns.add(columns)
            if not required_unique.issubset(unique_columns):
                raise DataParsingError(
                    f"market history table {table} is missing unique constraints"
                )
        table_sql = {
            row[0]: "".join(str(row[1]).lower().split())
            for row in connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table'"
            )
        }
        constraints = {
            "events": "check(snapshot_modein('checkpoint','delta'))",
            "archives": "check(version>=1)",
        }
        for table, fragment in constraints.items():
            if fragment not in table_sql.get(table, ""):
                raise DataParsingError(
                    f"market history table {table} is missing required constraints"
                )
    except sqlite3.DatabaseError as exc:
        raise DataParsingError(
            f"invalid or corrupted market history database: {exc}"
        ) from exc


def check_market_history(path):
    """Run an explicit SQLite integrity check and return schema metadata."""
    connection = _connect(path, create=False)
    if connection is None:
        raise InvalidParameterError("market history database does not exist")
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise DataParsingError("market history database failed integrity check")
        return {
            "ok": True,
            "SchemaVersion": MARKET_HISTORY_SCHEMA_VERSION,
            "ApplicationID": MARKET_HISTORY_APPLICATION_ID,
        }
    except sqlite3.DatabaseError as exc:
        raise DataParsingError(f"market history integrity check failed: {exc}") from exc
    finally:
        connection.close()


def _json_value(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return {"__type__": "timestamp", "value": value.isoformat()}
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return {"__type__": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return {"__type__": "float", "value": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, bool)):
        return value
    return {"__type__": "repr", "value": str(value)}


def _from_json_value(value):
    if isinstance(value, list):
        return [_from_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("__type__")
    if kind == "timestamp":
        return pd.Timestamp(value["value"])
    if kind == "datetime":
        return _dt.datetime.fromisoformat(value["value"])
    if kind == "date":
        return _dt.date.fromisoformat(value["value"])
    if kind == "time":
        return _dt.time.fromisoformat(value["value"])
    if kind == "float":
        return np.inf if value["value"] == "inf" else -np.inf
    if kind == "repr":
        return value["value"]
    return {key: _from_json_value(item) for key, item in value.items()}


def _frame_payload(frame):
    frame = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if frame.columns.duplicated().any():
        raise InvalidParameterError("persisted DataFrame columns must be unique")
    return {
        "columns": [str(column) for column in frame.columns],
        "dtypes": {str(column): str(frame[column].dtype) for column in frame.columns},
        "rows": [
            [_json_value(value) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ],
        "attrs": _json_value(dict(frame.attrs)),
    }


def _cast_column(series, dtype):
    try:
        if dtype.startswith("datetime64["):
            converted = pd.to_datetime(series, errors="coerce", utc=True)
            if ", " in dtype and dtype.endswith("]"):
                return converted.dt.tz_convert(dtype.split(", ", 1)[1][:-1])
            return converted.dt.tz_localize(None)
        if dtype in {"Int64", "Float64", "boolean", "string", "str"}:
            return series.astype(dtype)
        if dtype.startswith("int") or dtype.startswith("uint"):
            return pd.to_numeric(series, errors="raise").astype(dtype)
        if dtype.startswith("float"):
            return pd.to_numeric(series, errors="coerce").astype(dtype)
        if dtype == "bool":
            return series.astype(bool)
    except (TypeError, ValueError):
        pass
    return series.astype("object") if dtype == "object" else series


def _payload_frame(payload, *, context=None):
    try:
        _validate_frame_payload(payload)
        columns = payload["columns"]
        rows = [[_from_json_value(value) for value in row] for row in payload["rows"]]
        frame = pd.DataFrame(rows, columns=columns)
        for column, dtype in payload["dtypes"].items():
            if column in frame:
                frame[column] = _cast_column(frame[column], dtype)
        attrs = _from_json_value(payload["attrs"])
        if not isinstance(attrs, Mapping):
            raise TypeError("frame attrs are not an object")
        frame.attrs.update(attrs)
        return frame
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        if context is None:
            raise
        raise DataParsingError(f"corrupted {context}: {exc}") from exc


def _validate_frame_payload(payload):
    if not isinstance(payload, Mapping):
        raise TypeError("frame payload is not an object")
    if not {"columns", "dtypes", "rows", "attrs"}.issubset(payload):
        raise KeyError("frame payload keys are missing")
    if not isinstance(payload["columns"], list) or not isinstance(
        payload["rows"], list
    ):
        raise TypeError("frame columns/rows must be lists")
    if not isinstance(payload["dtypes"], Mapping):
        raise TypeError("frame dtypes must be an object")
    width = len(payload["columns"])
    if any(not isinstance(row, list) or len(row) != width for row in payload["rows"]):
        raise ValueError("frame row width does not match columns")


def _as_tehran(value, name="timestamp"):
    if isinstance(value, str):
        text = value.strip().replace("/", "-")
        date_part = text.split(" ", 1)[0].split("T", 1)[0]
        parts = date_part.split("-")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            year, month, day = map(int, parts)
            if 1200 <= year < 1700:
                try:
                    gregorian = JalaliDate(year, month, day).to_gregorian()
                except (TypeError, ValueError) as exc:
                    raise InvalidParameterError(
                        f"{name} is not a valid Jalali date"
                    ) from exc
                suffix = text[len(date_part) :]
                value = gregorian.isoformat() + suffix
    try:
        stamp = pd.Timestamp(value)
    except Exception as exc:
        raise InvalidParameterError(f"{name} must be a valid timestamp") from exc
    if pd.isna(stamp):
        raise InvalidParameterError(f"{name} must be a valid timestamp")
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(_TEHRAN, ambiguous="raise", nonexistent="raise")
    else:
        stamp = stamp.tz_convert(_TEHRAN)
    return stamp


def _storage_time(value):
    return _as_tehran(value).tz_convert("UTC").isoformat()


def _bounds(start=None, end=None):
    start_stamp = _as_tehran(start, "start") if start is not None else None
    end_stamp = _as_tehran(end, "end") if end is not None else None
    if end_stamp is not None and _is_date_only(end):
        end_stamp = end_stamp + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    if start_stamp is not None and end_stamp is not None and start_stamp > end_stamp:
        raise InvalidParameterError("start must be less than or equal to end")
    return (
        None if start_stamp is None else start_stamp.tz_convert("UTC").isoformat(),
        None if end_stamp is None else end_stamp.tz_convert("UTC").isoformat(),
    )


def _is_date_only(value):
    if isinstance(value, _dt.datetime) or isinstance(value, pd.Timestamp):
        return False
    if isinstance(value, _dt.date):
        return True
    if isinstance(value, str):
        text = value.strip()
        return (
            "T" not in text
            and " " not in text
            and len(text.replace("/", "-").split("-")) == 3
        )
    return False


def _validate_page(limit, offset=0):
    try:
        limit_value, offset_value = int(limit), int(offset)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("limit and offset must be integers") from exc
    if limit_value < 1 or limit_value > _MAX_QUERY_LIMIT:
        raise InvalidParameterError(f"limit must be between 1 and {_MAX_QUERY_LIMIT}")
    if offset_value < 0:
        raise InvalidParameterError("offset must be non-negative")
    return limit_value, offset_value


def _where(start=None, end=None, column="as_of_utc"):
    start_utc, end_utc = _bounds(start, end)
    clauses, parameters = [], []
    if start_utc is not None:
        clauses.append(f"{column} >= ?")
        parameters.append(start_utc)
    if end_utc is not None:
        clauses.append(f"{column} <= ?")
        parameters.append(end_utc)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), parameters


def _unique_source_timestamp(frame, columns, name):
    candidates = []
    for column in columns:
        if column not in frame:
            continue
        for value in frame[column].dropna():
            candidates.append(_as_tehran(value, column).tz_convert("UTC"))
    unique = pd.DatetimeIndex(candidates).unique()
    if len(unique) > 1:
        raise InvalidParameterError(
            f"{name} timestamps are ambiguous within one snapshot"
        )
    return None if len(unique) == 0 else pd.Timestamp(unique[0]).tz_convert(_TEHRAN)


def _snapshot_as_of(frame, explicit=None):
    price_source = _unique_source_timestamp(
        frame,
        (
            "as_of",
            "AsOf",
            "fetched_at",
            "FetchedAt",
            "price_source_as_of",
            "PriceSourceAsOf",
        ),
        "price source",
    )
    if explicit is None:
        if price_source is None:
            raise InvalidParameterError(
                "as_of is required when the snapshot has no unique source timestamp"
            )
        stamp = price_source
    else:
        stamp = _as_tehran(explicit, "as_of")
        if price_source is not None and stamp.tz_convert(
            "UTC"
        ) != price_source.tz_convert("UTC"):
            raise InvalidParameterError(
                "explicit as_of does not match snapshot source timestamps"
            )
    client_source = _unique_source_timestamp(
        frame,
        (
            "client_as_of",
            "ClientAsOf",
            "client_fetched_at",
            "ClientFetchedAt",
            "ClientSourceAsOf",
        ),
        "client source",
    )
    return stamp, client_source


def _live_frame(snapshot, as_of=None):
    if isinstance(snapshot, pd.DataFrame):
        frame = snapshot.copy(deep=True)
    elif isinstance(snapshot, Mapping):
        if isinstance(snapshot.get("live"), pd.DataFrame):
            frame = snapshot["live"].copy(deep=True)
        elif isinstance(snapshot.get("stocks"), pd.DataFrame):
            client = snapshot.get("client_type", pd.DataFrame())
            order_book = snapshot.get("order_book", pd.DataFrame())
            frame = _enrich_live_market(
                snapshot["stocks"],
                client if isinstance(client, pd.DataFrame) else pd.DataFrame(),
                order_book if isinstance(order_book, pd.DataFrame) else pd.DataFrame(),
                as_of=as_of if as_of is not None else snapshot.get("fetched_at"),
                snapshot_metadata=snapshot,
            )
            client_stamp = snapshot.get(
                "client_fetched_at", snapshot.get("client_as_of")
            )
            if client_stamp is not None:
                try:
                    if not bool(pd.isna(client_stamp)):
                        frame["ClientSourceAsOf"] = _as_tehran(
                            client_stamp, "client_fetched_at"
                        )
                except (TypeError, ValueError):
                    raise InvalidParameterError(
                        "client_fetched_at must be one timestamp"
                    )
        else:
            raise InvalidParameterError(
                "snapshot mapping must contain a live or stocks DataFrame"
            )
    else:
        raise InvalidParameterError(
            "snapshot must be a DataFrame or market snapshot mapping"
        )
    if "InsCode" not in frame:
        raise InvalidParameterError("snapshot must contain InsCode")
    frame["InsCode"] = frame["InsCode"].astype("string")
    if frame["InsCode"].dropna().duplicated().any():
        raise InvalidParameterError("snapshot must contain one row per InsCode")
    source_attrs = copy.deepcopy(frame.attrs)
    result = frame.reset_index(drop=True)
    result.attrs.update(source_attrs)
    return result


def _metadata_from_live(live, as_of):
    metadata = {"fetched_at": as_of}
    for column in (
        "trade_date",
        "exchange_time",
        "is_realtime_fresh",
        "is_stale",
        "is_today_trade_date",
        "is_previous_trade_date",
        "market_state",
    ):
        if column in live and live[column].notna().any():
            metadata[column] = live[column].dropna().iloc[0]
    return metadata


def _overview_from_live(live, metadata):
    if live.empty:
        result = pd.DataFrame(columns=_OVERVIEW_COLUMNS)
        for column in ("flow", "instrument_count", "trade_count"):
            result[column] = pd.Series(dtype="Int64")
        for column in ("total_volume", "total_value", "market_cap"):
            result[column] = pd.Series(dtype="Float64")
        result["is_realtime_fresh"] = pd.Series(dtype="boolean")
        for column in ("exchange_time", "fetched_at"):
            result[column] = pd.Series(dtype=f"datetime64[ns, {_TEHRAN}]")
        return result
    rows = []
    grouping = (
        live.groupby("Flow", dropna=False, sort=True)
        if "Flow" in live
        else [(pd.NA, live)]
    )
    for flow, group in grouping:

        def total(column):
            if column not in group:
                return np.nan
            return pd.to_numeric(group[column], errors="coerce").sum(min_count=1)

        rows.append(
            {
                "flow": flow,
                "instrument_count": len(group),
                "trade_count": total("TradeCount"),
                "total_volume": total("Volume"),
                "total_value": total("Value"),
                "market_cap": total("MarketCap"),
                "trade_date": metadata.get("trade_date"),
                "exchange_time": metadata.get("exchange_time"),
                "fetched_at": metadata.get("fetched_at"),
                "is_realtime_fresh": metadata.get("is_realtime_fresh", False),
            }
        )
    result = pd.DataFrame(rows).reindex(columns=_OVERVIEW_COLUMNS)
    for column in ("flow", "instrument_count", "trade_count"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    for column in ("total_volume", "total_value", "market_cap"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "Float64"
        )
    result["is_realtime_fresh"] = result["is_realtime_fresh"].astype("boolean")
    for column in ("exchange_time", "fetched_at"):
        result[column] = pd.to_datetime(
            result[column], errors="coerce", utc=True
        ).dt.tz_convert(_TEHRAN)
    return result


def _sector_from_live(
    live,
    metadata,
    symbol=None,
    flow=None,
    sector=None,
    traded_only=False,
    include_base_market=True,
    instrument_types=None,
):
    frame = _filter_universe(
        live,
        symbol,
        flow,
        sector,
        traded_only,
        include_base_market,
        instrument_types,
    )
    required = {
        "client_snapshot_consistent",
        "NetIndividualVolume",
        "EstimatedNetIndividualFlow",
    }
    if frame.empty or not required.issubset(frame.columns):
        return _cast_analytics_frame(pd.DataFrame(), SECTOR_FLOW_COLUMNS)
    frame = frame.copy()
    sector_codes = frame["SectorCode"].astype("string").str.strip()
    frame["SectorCode"] = sector_codes.mask(
        sector_codes.isna() | sector_codes.isin(["", "nan", "<NA>"])
    )
    rows = []
    for code, group in frame.groupby("SectorCode", dropna=False, sort=True):
        consistent = group["client_snapshot_consistent"].fillna(False).astype(bool)
        covered = group.loc[consistent]
        values = pd.to_numeric(covered["EstimatedNetIndividualFlow"], errors="coerce")
        available = bool(values.notna().any())
        record = {
            "SectorCode": pd.NA if pd.isna(code) else code,
            **_breadth_record(group),
        }
        record.update(
            {
                "client_covered_count": int(consistent.sum()),
                "client_coverage": float(consistent.mean()) if len(group) else np.nan,
                "net_individual_volume": pd.to_numeric(
                    covered["NetIndividualVolume"], errors="coerce"
                ).sum(min_count=1),
                "estimated_net_individual_value": values.sum(min_count=1),
                "value_available": available,
                "value_method": "market_vwap_estimate" if available else "unavailable",
                "trade_date": metadata.get("trade_date"),
                "exchange_time": metadata.get("exchange_time"),
                "fetched_at": metadata.get("fetched_at"),
                "is_realtime_fresh": metadata.get("is_realtime_fresh", False),
                "is_stale": metadata.get("is_stale", True),
            }
        )
        rows.append(record)
    return _cast_analytics_frame(pd.DataFrame(rows), SECTOR_FLOW_COLUMNS)


def save_market_snapshot(path, snapshot=None, *, as_of=None, _live_fetch=None):
    """Atomically persist one whole live-market observation.

    If ``snapshot`` is omitted, :func:`get_live_market` is called exactly once.
    The caller-provided path is mandatory; no package-global cache is used.
    """
    if snapshot is None:
        if _live_fetch is None:
            from .market_data import get_live_market

            _live_fetch = get_live_market
        snapshot = _live_fetch()
    if as_of is None and isinstance(snapshot, Mapping):
        candidate = snapshot.get("fetched_at", snapshot.get("as_of"))
        if candidate is not None:
            try:
                if not bool(pd.isna(candidate)):
                    as_of = candidate
            except (TypeError, ValueError) as exc:
                raise InvalidParameterError(
                    "snapshot fetched_at must be one timestamp"
                ) from exc
    live = _live_frame(snapshot, as_of=as_of)
    stamp, client_source_as_of = _snapshot_as_of(live, explicit=as_of)
    metadata = _metadata_from_live(live, stamp)
    raw_snapshot = {
        "stocks": live.reindex(columns=[c for c in STOCK_COLUMNS if c in live]),
        **metadata,
    }
    breadth = get_market_breadth(_snapshot=raw_snapshot)
    sector = _sector_from_live(live, metadata)
    overview = _overview_from_live(live, metadata)
    payload = {
        "live": _frame_payload(live),
        "snapshot_summary": _frame_payload(overview),
        "breadth": _frame_payload(breadth),
        "sector_flow": _frame_payload(sector),
        "provenance": {
            "price_source_as_of_utc": _storage_time(stamp),
            "client_source_as_of_utc": (
                None
                if client_source_as_of is None
                else _storage_time(client_source_as_of)
            ),
        },
    }
    payload_json = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    as_of_utc = _storage_time(stamp)
    snapshot_id = hashlib.sha256(as_of_utc.encode("utf-8")).hexdigest()
    connection = _connect(path, create=True)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT snapshot_id,payload_json FROM snapshots WHERE as_of_utc=?",
            (as_of_utc,),
        ).fetchone()
        if existing is not None:
            if existing[1] != payload_json:
                raise DataParsingError(
                    "a different snapshot already exists for this exact AsOf"
                )
            connection.execute("COMMIT")
            return existing[0]
        connection.execute(
            "INSERT INTO snapshots(snapshot_id,as_of_utc,payload_json,created_at_utc) "
            "VALUES(?,?,?,?)",
            (
                snapshot_id,
                as_of_utc,
                payload_json,
                pd.Timestamp.now(tz="UTC").isoformat(),
            ),
        )
        connection.execute("COMMIT")
        return snapshot_id
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _snapshot_rows(path, start=None, end=None, limit=_DEFAULT_QUERY_LIMIT, offset=0):
    limit, offset = _validate_page(limit, offset)
    connection = _connect(path, create=False)
    if connection is None:
        return []
    clause, parameters = _where(start, end)
    try:
        return connection.execute(
            "SELECT snapshot_id,as_of_utc,payload_json FROM snapshots"
            + clause
            + " ORDER BY as_of_utc,snapshot_id LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise DataParsingError(f"could not read market history: {exc}") from exc
    finally:
        connection.close()


def _decode_snapshot_record(raw, snapshot_id):
    try:
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise TypeError("payload is not an object")
        required = {"live", "snapshot_summary", "breadth", "sector_flow", "provenance"}
        if not required.issubset(payload):
            raise KeyError(f"missing keys {sorted(required - set(payload))}")
        for key in ("live", "snapshot_summary", "breadth", "sector_flow"):
            _validate_frame_payload(payload[key])
        return payload
    except (json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        raise DataParsingError(
            f"corrupted snapshots record {snapshot_id}: {exc}"
        ) from exc


def _coverage(rows):
    if not rows:
        return pd.NaT
    return pd.Timestamp(rows[0][1]).tz_convert(_TEHRAN)


def _table_coverage(path, table, *, kind=None):
    if table not in {"snapshots", "events", "archives"}:
        raise InvalidParameterError("unknown history table")
    connection = _connect(path, create=False)
    if connection is None:
        return pd.NaT
    try:
        time_column = "observed_at_utc" if table == "archives" else "as_of_utc"
        if kind is None:
            row = connection.execute(
                f"SELECT MIN({time_column}) FROM {table}"
            ).fetchone()
        else:
            row = connection.execute(
                f"SELECT MIN({time_column}) FROM {table} WHERE kind=?", (kind,)
            ).fetchone()
    finally:
        connection.close()
    return (
        pd.Timestamp(row[0]).tz_convert(_TEHRAN)
        if row is not None and row[0] is not None
        else pd.NaT
    )


def _with_history_metadata(
    frame,
    snapshot_id,
    as_of,
    coverage,
    *,
    price_source_as_of=None,
    client_source_as_of=None,
):
    result = frame.copy(deep=True)
    values = {
        "SnapshotID": snapshot_id,
        "AsOf": pd.Timestamp(as_of).tz_convert(_TEHRAN),
        "Source": "local_sqlite",
        "SchemaVersion": MARKET_HISTORY_SCHEMA_VERSION,
        "NoBackfill": True,
        "CoverageStart": coverage,
        "SnapshotAtomic": True,
        "PersistenceAtomic": True,
        # One transaction prevents row hybrids.  It does not imply that the
        # provider's price and client-type bulk feeds were exchange-atomic.
        "SourceAtomic": False,
        "PriceSourceAsOf": pd.Timestamp(
            as_of if price_source_as_of is None else price_source_as_of
        ).tz_convert(_TEHRAN),
        "ClientSourceAsOf": (
            pd.NaT
            if client_source_as_of is None
            else pd.Timestamp(client_source_as_of).tz_convert(_TEHRAN)
        ),
        "NoLookahead": True,
    }
    for column, value in values.items():
        result[column] = value
    return result


def _attrs(frame, coverage):
    for column in ("AsOf", "CoverageStart", "PriceSourceAsOf", "ClientSourceAsOf"):
        if column in frame:
            frame[column] = (
                pd.to_datetime(frame[column], errors="coerce", utc=True)
                .dt.tz_convert(_TEHRAN)
                .astype(f"datetime64[ns, {_TEHRAN}]")
            )
    for column in ("SchemaVersion", "Version"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(
                "Int64"
            )
    for column in ("SnapshotID", "Source", "ArchiveIdentity", "SessionID"):
        if column in frame:
            frame[column] = frame[column].astype("string")
    for column in (
        "NoBackfill",
        "SnapshotAtomic",
        "PersistenceAtomic",
        "SourceAtomic",
        "NoLookahead",
    ):
        if column in frame:
            frame[column] = frame[column].astype("boolean")
    source_atomic = False
    if "SourceAtomic" in frame and not frame.empty:
        source_atomic = bool(frame["SourceAtomic"].fillna(False).all())
    snapshot_atomic = True
    if "SnapshotAtomic" in frame and not frame.empty:
        snapshot_atomic = bool(frame["SnapshotAtomic"].fillna(False).all())
    frame.attrs.update(
        {
            "Source": "local_sqlite",
            "SchemaVersion": MARKET_HISTORY_SCHEMA_VERSION,
            "NoBackfill": True,
            "CoverageStart": coverage,
            "SnapshotAtomic": snapshot_atomic,
            "PersistenceAtomic": True,
            "SourceAtomic": source_atomic,
            "PriceSourceAsOf": "AsOf column",
            "ClientSourceAsOf": pd.NaT,
            "NoLookahead": True,
        }
    )
    return frame


def _empty_history(base_columns=()):
    if isinstance(base_columns, pd.DataFrame):
        result = base_columns.iloc[0:0].copy()
    else:
        result = pd.DataFrame(
            {column: pd.Series(dtype="object") for column in base_columns}
        )
    result = result.drop(
        columns=[column for column in _META_COLUMNS if column in result]
    )
    for column in _META_COLUMNS:
        if column in {"SnapshotID", "Source"}:
            dtype = "string"
        elif column == "SchemaVersion":
            dtype = "Int64"
        elif column in {"AsOf", "CoverageStart", "PriceSourceAsOf", "ClientSourceAsOf"}:
            dtype = f"datetime64[ns, {_TEHRAN}]"
        else:
            dtype = "boolean"
        result[column] = pd.Series(dtype=dtype)
    return _attrs(result, pd.NaT)


def _empty_live_history():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
        live = _enrich_live_market(
            pd.DataFrame(columns=STOCK_COLUMNS),
            pd.DataFrame(columns=CLIENT_COLUMNS),
            pd.DataFrame(columns=ORDER_COLUMNS),
            as_of=pd.Timestamp("1970-01-01", tz=_TEHRAN),
            snapshot_metadata={},
        ).iloc[0:0]
    return _empty_history(live)


def load_market_snapshots(
    path,
    start=None,
    end=None,
    symbol=None,
    *,
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Load locally observed live rows using inclusive point-in-time filters."""
    rows = _snapshot_rows(path, start, end, limit=limit, offset=offset)
    if not rows:
        available = _snapshot_rows(path)
        if available:
            payload = _decode_snapshot_record(available[0][2], available[0][0])
            return _empty_history(
                _payload_frame(
                    payload["live"],
                    context=f"snapshots record {available[0][0]} field live",
                )
            )
        return _empty_live_history()
    coverage = _table_coverage(path, "snapshots")
    frames = []
    snapshot_frame_attrs = {}
    for snapshot_id, as_of, raw in rows:
        payload = _decode_snapshot_record(raw, snapshot_id)
        frame = _payload_frame(
            payload["live"], context=f"snapshots record {snapshot_id} field live"
        )
        snapshot_frame_attrs[str(snapshot_id)] = dict(frame.attrs)
        if symbol is not None:
            frame = frame.loc[_instrument_mask(frame, symbol)].reset_index(drop=True)
        provenance = payload["provenance"]
        frames.append(
            _with_history_metadata(
                frame,
                snapshot_id,
                as_of,
                coverage,
                price_source_as_of=provenance.get("price_source_as_of_utc"),
                client_source_as_of=provenance.get("client_source_as_of_utc"),
            )
        )
    result = (
        pd.concat(frames, ignore_index=True, sort=False) if frames else _empty_history()
    )
    result = _attrs(result, coverage)
    result.attrs["SnapshotFrameAttrs"] = snapshot_frame_attrs
    return result


def get_live_market_history(
    path, start=None, end=None, symbol=None, *, limit=_DEFAULT_QUERY_LIMIT, offset=0
):
    """Return persisted rich live-market observations for selected instruments."""
    return load_market_snapshots(
        path, start=start, end=end, symbol=symbol, limit=limit, offset=offset
    )


def _derived_history(
    path, key, start=None, end=None, *, limit=_DEFAULT_QUERY_LIMIT, offset=0
):
    rows = _snapshot_rows(path, start, end, limit=limit, offset=offset)
    if not rows:
        available = _snapshot_rows(path)
        if available:
            payload = _decode_snapshot_record(available[0][2], available[0][0])
            return _empty_history(
                _payload_frame(
                    payload[key],
                    context=f"snapshots record {available[0][0]} field {key}",
                )
            )
        columns = {
            "breadth": BREADTH_COLUMNS,
            "sector_flow": SECTOR_FLOW_COLUMNS,
            "snapshot_summary": _OVERVIEW_COLUMNS,
        }[key]
        if key in {"breadth", "sector_flow"}:
            return _empty_history(_cast_analytics_frame(pd.DataFrame(), columns))
        return _empty_history(_overview_from_live(pd.DataFrame(), {}))
    coverage = _table_coverage(path, "snapshots")
    frames = []
    for snapshot_id, as_of, raw in rows:
        payload = _decode_snapshot_record(raw, snapshot_id)
        frame = _payload_frame(
            payload[key], context=f"snapshots record {snapshot_id} field {key}"
        )
        provenance = payload["provenance"]
        frames.append(
            _with_history_metadata(
                frame,
                snapshot_id,
                as_of,
                coverage,
                price_source_as_of=provenance.get("price_source_as_of_utc"),
                client_source_as_of=provenance.get("client_source_as_of_utc"),
            )
        )
    return _attrs(pd.concat(frames, ignore_index=True, sort=False), coverage)


def get_market_snapshot_summary_history(
    path,
    start=None,
    end=None,
    flow=None,
    *,
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Return summaries derived from each atomic locally persisted market snapshot."""
    result = _derived_history(
        path, "snapshot_summary", start, end, limit=limit, offset=offset
    )
    if flow is not None and not result.empty:
        choices = [flow] if isinstance(flow, (str, int, np.integer)) else list(flow)
        result = result.loc[
            pd.to_numeric(result["flow"], errors="coerce").isin(
                [int(x) for x in choices]
            )
        ].reset_index(drop=True)
    return result


def get_market_breadth_history(
    path,
    start=None,
    end=None,
    symbol=None,
    flow=None,
    sector=None,
    traded_only=False,
    include_base_market=True,
    instrument_types=None,
    *,
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Return point-in-time breadth derived only from persisted snapshots."""
    if (
        all(
            value is None or value is False
            for value in (symbol, flow, sector, traded_only, instrument_types)
        )
        and include_base_market
    ):
        return _derived_history(path, "breadth", start, end, limit=limit, offset=offset)
    rows = _snapshot_rows(path, start, end, limit=limit, offset=offset)
    if not rows:
        return _empty_history(_cast_analytics_frame(pd.DataFrame(), BREADTH_COLUMNS))
    coverage, output = _table_coverage(path, "snapshots"), []
    for snapshot_id, as_of, raw in rows:
        payload = _decode_snapshot_record(raw, snapshot_id)
        live = _payload_frame(
            payload["live"], context=f"snapshots record {snapshot_id} field live"
        )
        metadata = _metadata_from_live(live, pd.Timestamp(as_of).tz_convert(_TEHRAN))
        raw_snapshot = {"stocks": live, **metadata}
        frame = get_market_breadth(
            symbol=symbol,
            flow=flow,
            sector=sector,
            traded_only=traded_only,
            include_base_market=include_base_market,
            instrument_types=instrument_types,
            _snapshot=raw_snapshot,
        )
        provenance = payload["provenance"]
        output.append(
            _with_history_metadata(
                frame,
                snapshot_id,
                as_of,
                coverage,
                price_source_as_of=provenance.get("price_source_as_of_utc"),
                client_source_as_of=provenance.get("client_source_as_of_utc"),
            )
        )
    return _attrs(pd.concat(output, ignore_index=True, sort=False), coverage)


def get_sector_flow_history(
    path,
    start=None,
    end=None,
    symbol=None,
    flow=None,
    sector=None,
    traded_only=False,
    include_base_market=True,
    instrument_types=None,
    *,
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Return sector client-flow history computed from persisted rich live rows."""
    if (
        all(
            value is None or value is False
            for value in (symbol, flow, sector, traded_only, instrument_types)
        )
        and include_base_market
    ):
        return _derived_history(
            path, "sector_flow", start, end, limit=limit, offset=offset
        )
    rows = _snapshot_rows(path, start, end, limit=limit, offset=offset)
    if not rows:
        return _empty_history(
            _cast_analytics_frame(pd.DataFrame(), SECTOR_FLOW_COLUMNS)
        )
    coverage, output = _table_coverage(path, "snapshots"), []
    for snapshot_id, as_of, raw in rows:
        payload = _decode_snapshot_record(raw, snapshot_id)
        live = _payload_frame(
            payload["live"], context=f"snapshots record {snapshot_id} field live"
        )
        metadata = _metadata_from_live(live, pd.Timestamp(as_of).tz_convert(_TEHRAN))
        frame = _sector_from_live(
            live,
            metadata,
            symbol,
            flow,
            sector,
            traded_only,
            include_base_market,
            instrument_types,
        )
        provenance = payload["provenance"]
        output.append(
            _with_history_metadata(
                frame,
                snapshot_id,
                as_of,
                coverage,
                price_source_as_of=provenance.get("price_source_as_of_utc"),
                client_source_as_of=provenance.get("client_source_as_of_utc"),
            )
        )
    return _attrs(pd.concat(output, ignore_index=True, sort=False), coverage)


def _event_snapshot_payload(event, include_snapshot):
    snapshot = event.snapshot
    if include_snapshot:
        selected = snapshot
        mode = "checkpoint"
    else:
        selected = {
            key: value
            for key, value in snapshot.items()
            if not isinstance(value, pd.DataFrame)
        }
        stocks = snapshot.get("stocks")
        if isinstance(stocks, pd.DataFrame):
            changed = set(event.changed_inscodes)
            selected["stocks"] = stocks.loc[
                stocks.get("InsCode", pd.Series(index=stocks.index, dtype="object"))
                .astype(str)
                .isin(changed)
            ].reset_index(drop=True)
        order_book = snapshot.get("order_book")
        if isinstance(order_book, pd.DataFrame):
            changed_levels = set(event.changed_order_levels)
            if {"InsCode", "Level"}.issubset(order_book.columns):
                mask = [
                    (str(code), int(level)) in changed_levels
                    for code, level in zip(order_book["InsCode"], order_book["Level"])
                ]
                selected["order_book"] = order_book.loc[mask].reset_index(drop=True)
            else:
                selected["order_book"] = order_book.iloc[0:0].copy()
        mode = "delta"
    payload = {
        key: (
            _frame_payload(value)
            if isinstance(value, pd.DataFrame)
            else _json_value(value)
        )
        for key, value in selected.items()
    }
    frame_keys = [
        key for key, value in selected.items() if isinstance(value, pd.DataFrame)
    ]
    return payload, frame_keys, mode


def _event_payload(event, include_snapshot=True):
    snapshot_payload, frame_keys, mode = _event_snapshot_payload(
        event, include_snapshot
    )
    return {
        "kind": event.kind,
        "sequence": int(event.sequence),
        "fetched_at": _json_value(event.fetched_at),
        "trade_date": _json_value(event.trade_date),
        "changed_inscodes": list(event.changed_inscodes),
        "changed_order_levels": [list(item) for item in event.changed_order_levels],
        "market_state_changed": bool(event.market_state_changed),
        "notification_tokens": list(event.notification_tokens),
        "cursor_before": int(event.cursor_before),
        "cursor_after": int(event.cursor_after),
        "retry_count": int(event.retry_count),
        "retry_error": event.retry_error,
        "notification_errors": list(event.notification_errors),
        "snapshot": snapshot_payload,
        "snapshot_frames": frame_keys,
        "snapshot_mode": mode,
        "price_source_as_of": _json_value(event.fetched_at),
        "messages": None if event.messages is None else _frame_payload(event.messages),
        "state_changes": (
            None if event.state_changes is None else _frame_payload(event.state_changes)
        ),
    }


def _prune_event_history(connection, max_records, retention_seconds, preferred_session):
    newest = connection.execute("SELECT MAX(as_of_utc) FROM events").fetchone()[0]
    cutoff = None
    if retention_seconds is not None and newest is not None:
        cutoff = (
            pd.Timestamp(newest) - pd.Timedelta(seconds=retention_seconds)
        ).isoformat()
    connection.execute("DROP TABLE IF EXISTS temp.event_keep_sessions")
    connection.execute(
        "CREATE TEMP TABLE event_keep_sessions("
        "session_id TEXT PRIMARY KEY,boundary_sequence INTEGER NOT NULL)"
    )
    session_where = " WHERE as_of_utc>=?" if cutoff is not None else ""
    session_parameters = [cutoff] if cutoff is not None else []
    sessions = connection.execute(
        "SELECT session_id,MAX(as_of_utc) AS latest FROM events"
        + session_where
        + " GROUP BY session_id ORDER BY (session_id=?) DESC,latest DESC,session_id",
        [*session_parameters, preferred_session],
    ).fetchall()
    remaining = max_records
    for session_id, _ in sessions:
        if remaining <= 0:
            break
        retention_checkpoint = " AND c.as_of_utc>=?" if cutoff is not None else ""
        retention_event = " AND e.as_of_utc>=?" if cutoff is not None else ""
        boundary = connection.execute(
            "SELECT c.sequence,COUNT(e.event_id) AS suffix_count FROM events c "
            "JOIN events e ON e.session_id=c.session_id AND e.sequence>=c.sequence"
            + retention_event
            + " WHERE c.session_id=? AND c.snapshot_mode='checkpoint'"
            + retention_checkpoint
            + " GROUP BY c.sequence HAVING suffix_count<=? "
            "ORDER BY c.sequence LIMIT 1",
            # SQL placeholder order follows JOIN, WHERE, HAVING.
            (
                [cutoff, session_id, cutoff, remaining]
                if cutoff is not None
                else [session_id, remaining]
            ),
        ).fetchone()
        if boundary is None:
            continue
        connection.execute(
            "INSERT INTO event_keep_sessions(session_id,boundary_sequence) VALUES(?,?)",
            (session_id, int(boundary[0])),
        )
        remaining -= int(boundary[1])
    connection.execute(
        "DELETE FROM events WHERE NOT EXISTS (SELECT 1 FROM event_keep_sessions k "
        "WHERE k.session_id=events.session_id)"
    )
    delete_clause = (
        "DELETE FROM events WHERE sequence < (SELECT boundary_sequence FROM "
        "event_keep_sessions k WHERE k.session_id=events.session_id)"
    )
    delete_parameters = []
    if cutoff is not None:
        delete_clause += " OR as_of_utc<?"
        delete_parameters.append(cutoff)
    connection.execute(delete_clause, delete_parameters)
    connection.execute("DROP TABLE temp.event_keep_sessions")


def record_market_event(
    path,
    event,
    *,
    session_id=None,
    include_snapshot=True,
    max_records=10_000,
    retention_seconds=None,
):
    """Persist one watcher event transactionally with replay-safe retention.

    The first persisted row in every session is forced to a full checkpoint.
    Pruning occurs only when a checkpoint is committed, so the oldest retained
    row is always independently replayable.
    """
    if not isinstance(event, MarketEvent):
        raise InvalidParameterError("event must be a MarketEvent")
    max_records, _ = _validate_page(max_records, 0)
    if retention_seconds is not None:
        try:
            retention_seconds = float(retention_seconds)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("retention_seconds must be numeric") from exc
        if not math.isfinite(retention_seconds) or retention_seconds <= 0:
            raise InvalidParameterError("retention_seconds must be finite and positive")
    as_of_utc = _storage_time(event.fetched_at)
    standalone_payload = _event_payload(event, include_snapshot=True)
    standalone_raw = json.dumps(
        standalone_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    standalone_hash = hashlib.sha256(standalone_raw.encode("utf-8")).hexdigest()
    session_value = (
        str(session_id).strip()
        if session_id is not None
        else (f"standalone:{standalone_hash}")
    )
    if not session_value:
        raise InvalidParameterError("session_id must be non-empty")
    connection = _connect(path, create=True)
    try:
        connection.execute("BEGIN IMMEDIATE")
        sequence_existing = connection.execute(
            "SELECT event_id,snapshot_mode,payload_json FROM events "
            "WHERE session_id=? AND sequence=?",
            (session_value, int(event.sequence)),
        ).fetchone()
        if sequence_existing is not None:
            expected = _event_payload(
                event, include_snapshot=sequence_existing[1] == "checkpoint"
            )
            expected_raw = json.dumps(
                expected,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if sequence_existing[2] != expected_raw:
                raise DataParsingError(
                    "watcher session sequence already exists with a different payload"
                )
            connection.execute("COMMIT")
            return sequence_existing[0]
        first_in_session = (
            connection.execute(
                "SELECT 1 FROM events WHERE session_id=? LIMIT 1", (session_value,)
            ).fetchone()
            is None
        )
        if not first_in_session:
            maximum_sequence = int(
                connection.execute(
                    "SELECT MAX(sequence) FROM events WHERE session_id=?",
                    (session_value,),
                ).fetchone()[0]
            )
            if int(event.sequence) <= maximum_sequence:
                raise DataParsingError(
                    "watcher session sequences must be strictly increasing"
                )
        existing_count, existing_oldest, existing_newest = connection.execute(
            "SELECT COUNT(*),MIN(as_of_utc),MAX(as_of_utc) FROM events"
        ).fetchone()
        force_for_bound = int(existing_count) + 1 > max_records
        if retention_seconds is not None:
            newest_candidate = max(
                value for value in (existing_newest, as_of_utc) if value is not None
            )
            oldest_candidate = min(
                value for value in (existing_oldest, as_of_utc) if value is not None
            )
            cutoff_candidate = (
                pd.Timestamp(newest_candidate) - pd.Timedelta(seconds=retention_seconds)
            ).isoformat()
            force_for_bound = force_for_bound or oldest_candidate < cutoff_candidate
        effective_checkpoint = (
            bool(include_snapshot) or first_in_session or force_for_bound
        )
        payload = _event_payload(event, include_snapshot=effective_checkpoint)
        raw = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        payload_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        identity_raw = (
            f"{session_value}|{as_of_utc}|{event.sequence}|{event.kind}|{payload_hash}"
        )
        event_id = hashlib.sha256(identity_raw.encode("utf-8")).hexdigest()
        existing = connection.execute(
            "SELECT payload_json FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        if existing is not None and existing[0] != raw:
            raise DataParsingError("event identity collision with different payload")
        connection.execute(
            "INSERT INTO events(event_id,as_of_utc,session_id,sequence,kind,"
            "snapshot_mode,payload_json) VALUES(?,?,?,?,?,?,?)",
            (
                event_id,
                as_of_utc,
                session_value,
                int(event.sequence),
                event.kind,
                payload["snapshot_mode"],
                raw,
            ),
        )
        if effective_checkpoint:
            _prune_event_history(
                connection, max_records, retention_seconds, session_value
            )
        connection.execute("COMMIT")
        return event_id
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _decode_event_snapshot(payload, context):
    frame_keys = set(payload.get("snapshot_frames", []))
    return {
        key: (
            _payload_frame(value, context=f"{context} snapshot field {key}")
            if key in frame_keys
            else _from_json_value(value)
        )
        for key, value in payload.get("snapshot", {}).items()
    }


def _empty_event_history():
    result = _empty_history(_EVENT_COLUMNS)
    result["SessionID"] = pd.Series(dtype="string")
    result["kind"] = pd.Series(dtype="string")
    result["SnapshotMode"] = pd.Series(dtype="string")
    result["sequence"] = pd.Series(dtype="Int64")
    result["fetched_at"] = pd.Series(dtype=f"datetime64[ns, {_TEHRAN}]")
    for column in ("cursor_before", "cursor_after", "retry_count"):
        result[column] = pd.Series(dtype="Int64")
    result["market_state_changed"] = pd.Series(dtype="boolean")
    return result.reindex(columns=_EVENT_COLUMNS + _META_COLUMNS)


def get_market_event_history(
    path,
    start=None,
    end=None,
    kind=None,
    *,
    session_id=None,
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Replay bounded persisted watcher events without transport lookahead.

    ``kind`` may be ``None``, one watcher event kind, or an iterable containing
    only ``initial``, ``delta``, ``heartbeat`` and ``resync``. Unknown values
    raise :class:`InvalidParameterError` instead of silently returning an empty
    result for a typo.
    """
    limit, offset = _validate_page(limit, offset)
    kinds = None
    if kind is not None:
        try:
            kinds = [kind] if isinstance(kind, str) else list(kind)
        except TypeError as exc:
            raise InvalidParameterError(
                "kind must be a watcher event kind or an iterable of kinds"
            ) from exc
        unknown = sorted(
            {str(value) for value in kinds}.difference(_WATCHER_EVENT_KINDS)
        )
        if unknown:
            raise InvalidParameterError(
                "unknown watcher event kind(s): {}; expected initial, delta, "
                "heartbeat or resync".format(", ".join(unknown))
            )
    connection = _connect(path, create=False)
    if connection is None:
        return _empty_event_history()
    clause, parameters = _where(start, end)
    if kinds is not None:
        if not kinds:
            connection.close()
            return _empty_event_history()
        placeholders = ",".join("?" for _ in kinds)
        clause += (" AND " if clause else " WHERE ") + f"kind IN ({placeholders})"
        parameters.extend([str(value) for value in kinds])
    if session_id is not None:
        clause += (" AND " if clause else " WHERE ") + "session_id=?"
        parameters.append(str(session_id))
    try:
        rows = connection.execute(
            "SELECT event_id,as_of_utc,session_id,snapshot_mode,payload_json FROM events"
            + clause
            + " ORDER BY as_of_utc,sequence,event_id LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        return _empty_event_history()
    coverage, output = _table_coverage(path, "events"), []
    for event_id, as_of, session_value, stored_mode, raw in rows:
        context = f"events record {event_id}"
        try:
            payload = json.loads(raw)
            required = {
                "kind",
                "sequence",
                "fetched_at",
                "trade_date",
                "changed_inscodes",
                "changed_order_levels",
                "market_state_changed",
                "notification_tokens",
                "cursor_before",
                "cursor_after",
                "retry_count",
                "retry_error",
                "notification_errors",
                "snapshot",
                "snapshot_frames",
                "snapshot_mode",
                "price_source_as_of",
                "messages",
                "state_changes",
            }
            if not isinstance(payload, Mapping) or not required.issubset(payload):
                raise TypeError("invalid event payload shape")
            if not isinstance(payload["snapshot"], Mapping):
                raise TypeError("event snapshot is not an object")
            if not isinstance(payload["snapshot_frames"], list):
                raise TypeError("event snapshot_frames is not a list")
            if payload["snapshot_mode"] != stored_mode:
                raise ValueError("event snapshot mode disagrees with indexed metadata")
            for frame_key in payload["snapshot_frames"]:
                if frame_key not in payload["snapshot"]:
                    raise KeyError(f"missing snapshot frame {frame_key}")
                _validate_frame_payload(payload["snapshot"][frame_key])
            observed = pd.Timestamp(as_of).tz_convert(_TEHRAN)
            record = {
                "event_id": event_id,
                "SessionID": session_value,
                "kind": payload["kind"],
                "SnapshotMode": payload["snapshot_mode"],
                "sequence": payload["sequence"],
                "fetched_at": _from_json_value(payload["fetched_at"]),
                "trade_date": _from_json_value(payload["trade_date"]),
                "changed_inscodes": tuple(payload["changed_inscodes"]),
                "changed_order_levels": tuple(
                    tuple(x) for x in payload["changed_order_levels"]
                ),
                "market_state_changed": payload["market_state_changed"],
                "notification_tokens": tuple(payload["notification_tokens"]),
                "cursor_before": payload["cursor_before"],
                "cursor_after": payload["cursor_after"],
                "retry_count": payload["retry_count"],
                "retry_error": payload["retry_error"],
                "notification_errors": tuple(payload["notification_errors"]),
                "snapshot": _decode_event_snapshot(payload, context),
                "messages": (
                    None
                    if payload["messages"] is None
                    else _payload_frame(
                        payload["messages"], context=f"{context} field messages"
                    )
                ),
                "state_changes": (
                    None
                    if payload["state_changes"] is None
                    else _payload_frame(
                        payload["state_changes"],
                        context=f"{context} field state_changes",
                    )
                ),
                "SnapshotID": pd.NA,
                "AsOf": observed,
                "Source": "local_sqlite",
                "SchemaVersion": MARKET_HISTORY_SCHEMA_VERSION,
                "NoBackfill": True,
                "CoverageStart": coverage,
                "SnapshotAtomic": payload["snapshot_mode"] == "checkpoint",
                "PersistenceAtomic": True,
                "SourceAtomic": False,
                "PriceSourceAsOf": _from_json_value(payload["price_source_as_of"]),
                "ClientSourceAsOf": pd.NaT,
                "NoLookahead": True,
            }
        except DataParsingError:
            raise
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise DataParsingError(f"corrupted {context}: {exc}") from exc
        output.append(record)
    result = pd.DataFrame(output).reindex(columns=_EVENT_COLUMNS + _META_COLUMNS)
    result["sequence"] = result["sequence"].astype("Int64")
    result["fetched_at"] = (
        pd.to_datetime(result["fetched_at"], utc=True)
        .dt.tz_convert(_TEHRAN)
        .astype(f"datetime64[ns, {_TEHRAN}]")
    )
    for column in ("cursor_before", "cursor_after", "retry_count"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    result["market_state_changed"] = result["market_state_changed"].astype("boolean")
    for column in (
        "fetched_at",
        "AsOf",
        "PriceSourceAsOf",
        "ClientSourceAsOf",
        "CoverageStart",
    ):
        result[column] = pd.to_datetime(
            result[column], errors="coerce", utc=True
        ).dt.tz_convert(_TEHRAN)
    result["SchemaVersion"] = result["SchemaVersion"].astype("Int64")
    for column in (
        "NoBackfill",
        "SnapshotAtomic",
        "PersistenceAtomic",
        "SourceAtomic",
        "NoLookahead",
    ):
        result[column] = result[column].astype("boolean")
    return _attrs(result, coverage)


def _present(value):
    if value is None:
        return False
    try:
        return not bool(pd.isna(value)) and str(value).strip() not in {
            "",
            "<NA>",
            "nan",
            "None",
        }
    except (TypeError, ValueError):
        return False


def _archive_identity(kind, row_payload, observed_at):
    fields = {
        "messages": ("message_id",),
        "state_changes": ("event_id",),
        "overview": ("flow",),
    }[kind]
    for field in fields:
        value = row_payload.get(field)
        if _present(value):
            identity = f"{field}:{value}"
            if kind == "overview":
                identity += f":observed:{_storage_time(observed_at)}"
            return identity
    raw = json.dumps(_json_value(row_payload), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"unidentified:{digest}:observed:{_storage_time(observed_at)}"


def _provider_timestamp(kind, row):
    candidates = []
    if kind in {"messages", "state_changes"}:
        candidates.append(row.get("timestamp"))
    for value in candidates:
        if not _present(value):
            continue
        try:
            return _as_tehran(value, "provider timestamp")
        except InvalidParameterError:
            continue
    return None


def _archive_selector_values(kind, row):
    provider_fields = {
        "messages": ("message_id",),
        "state_changes": ("event_id",),
        "overview": (),
    }[kind]
    provider_id = next(
        (
            str(row.get(field)).strip()
            for field in provider_fields
            if _present(row.get(field))
        ),
        None,
    )
    try:
        provider_id_num = None if provider_id is None else int(provider_id)
    except (TypeError, ValueError, OverflowError):
        provider_id_num = None
    flow = row.get("flow")
    try:
        flow = int(flow) if _present(flow) else None
    except (TypeError, ValueError, OverflowError):
        flow = None
    inscode = row.get("InsCode")
    symbol = row.get("Symbol")
    return (
        flow,
        provider_id,
        provider_id_num,
        str(inscode).strip() if _present(inscode) else None,
        str(symbol).strip() if _present(symbol) else None,
    )


def archive_market_records(path, kind, frame, *, source="tsetmc", recorded_at=None):
    """Transactionally archive one provider response with observation-time versioning."""
    if kind not in {"messages", "state_changes", "overview"}:
        raise InvalidParameterError("unknown market archive kind")
    if not isinstance(frame, pd.DataFrame):
        raise InvalidParameterError("archive records must be a DataFrame")
    observed = _as_tehran(
        recorded_at if recorded_at is not None else pd.Timestamp.now(tz=_TEHRAN),
        "recorded_at",
    )
    source = str(source).strip()
    if not source:
        raise InvalidParameterError("source must be non-empty")
    connection = _connect(path, create=True)
    inserted = 0
    dtypes = {str(column): str(frame[column].dtype) for column in frame.columns}
    try:
        connection.execute("BEGIN IMMEDIATE")
        for row in frame.to_dict("records"):
            identity = _archive_identity(kind, row, observed)
            payload_json = json.dumps(
                {"row": _json_value(row), "dtypes": dtypes},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            latest = connection.execute(
                "SELECT version,payload_hash FROM archives "
                "WHERE kind=? AND source=? AND identity=? ORDER BY version DESC LIMIT 1",
                (kind, source, identity),
            ).fetchone()
            if latest is not None and latest[1] == payload_hash:
                continue
            version = 1 if latest is None else int(latest[0]) + 1
            provider = _provider_timestamp(kind, row)
            flow, provider_id, provider_id_num, inscode, symbol = (
                _archive_selector_values(kind, row)
            )
            connection.execute(
                "INSERT INTO archives(kind,source,identity,version,observed_at_utc,"
                "provider_timestamp_utc,payload_hash,flow,provider_id,provider_id_num,"
                "inscode,symbol,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    kind,
                    source,
                    identity,
                    version,
                    _storage_time(observed),
                    None if provider is None else _storage_time(provider),
                    payload_hash,
                    flow,
                    provider_id,
                    provider_id_num,
                    inscode,
                    symbol,
                    payload_json,
                ),
            )
            inserted += 1
        connection.execute("COMMIT")
        return inserted
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


_ARCHIVE_META_COLUMNS = [
    "ArchiveIdentity",
    "Version",
    "FirstObservedAt",
    "ObservedAt",
    "ProviderTimestamp",
    "AsOf",
    "Source",
    "SchemaVersion",
    "NoBackfill",
    "CoverageStart",
    "SnapshotAtomic",
    "PersistenceAtomic",
    "SourceAtomic",
    "NoLookahead",
]


def _empty_archive(kind, columns, dtypes=None, coverage=pd.NaT):
    result = pd.DataFrame(
        {
            column: pd.Series(dtype="object")
            for column in list(columns) + _ARCHIVE_META_COLUMNS
        }
    )
    for column, dtype in (dtypes or {}).items():
        if column in result:
            result[column] = _cast_column(result[column], dtype)
    for column in (
        "timestamp",
        "FirstObservedAt",
        "ObservedAt",
        "ProviderTimestamp",
        "AsOf",
        "CoverageStart",
    ):
        if column in result:
            result[column] = pd.Series(dtype=f"datetime64[ns, {_TEHRAN}]")
    for column in ("ArchiveIdentity", "Source"):
        result[column] = pd.Series(dtype="string")
    for column in ("Version", "SchemaVersion"):
        result[column] = pd.Series(dtype="Int64")
    for column in (
        "NoBackfill",
        "SnapshotAtomic",
        "PersistenceAtomic",
        "SourceAtomic",
        "NoLookahead",
    ):
        result[column] = pd.Series(dtype="boolean")
    if kind == "messages":
        for column in ("date", "time", "flow"):
            result[column] = pd.Series(dtype="Int64")
    elif kind == "state_changes":
        for column in ("date", "time"):
            result[column] = pd.Series(dtype="Int64")
    return _attrs(result, coverage)


def _archive_history(
    path,
    kind,
    columns,
    start=None,
    end=None,
    *,
    source=None,
    flow=None,
    since_id=None,
    symbol=None,
    inscode=None,
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    limit, offset = _validate_page(limit, offset)
    connection = _connect(path, create=False)
    if connection is None:
        return _empty_archive(kind, columns)
    start_utc, end_utc = _bounds(start, end)
    inner_clauses = ["kind=?"]
    inner_parameters = [kind]
    coverage_clauses = ["kind=?"]
    coverage_parameters = [kind]
    if source is not None:
        inner_clauses.append("source=?")
        inner_parameters.append(str(source))
        coverage_clauses.append("source=?")
        coverage_parameters.append(str(source))
    if end_utc is not None:
        inner_clauses.append("observed_at_utc<=?")
        inner_parameters.append(end_utc)
    outer_clauses = ["version_rank=1"]
    outer_parameters = []
    if start_utc is not None:
        outer_clauses.append("observed_at_utc>=?")
        outer_parameters.append(start_utc)
    if flow is not None:
        try:
            flow = int(flow)
        except (TypeError, ValueError, OverflowError) as exc:
            connection.close()
            raise InvalidParameterError("flow must be an integer") from exc
        outer_clauses.append("flow=?")
        outer_parameters.append(flow)
        coverage_clauses.append("flow=?")
        coverage_parameters.append(flow)
    if since_id is not None:
        since_text = str(since_id).strip()
        try:
            since_number = int(since_text)
        except (TypeError, ValueError, OverflowError):
            outer_clauses.append("provider_id>?")
            outer_parameters.append(since_text)
            coverage_clauses.append("provider_id>?")
            coverage_parameters.append(since_text)
        else:
            since_clause = (
                "((provider_id_num IS NOT NULL AND provider_id_num>?) OR "
                "(provider_id_num IS NULL AND provider_id>?))"
            )
            outer_clauses.append(since_clause)
            outer_parameters.extend((since_number, since_text))
            coverage_clauses.append(since_clause)
            coverage_parameters.extend((since_number, since_text))

    def choices(value, name):
        if value is None:
            return None
        raw = [value] if isinstance(value, (str, int)) else list(value)
        selected = [str(item).strip() for item in raw if str(item).strip()]
        if not selected:
            raise InvalidParameterError(f"{name} selector must not be empty")
        return selected

    try:
        symbols = choices(symbol, "symbol")
        inscodes = choices(inscode, "inscode")
    except (TypeError, ValueError) as exc:
        connection.close()
        if isinstance(exc, InvalidParameterError):
            raise
        raise InvalidParameterError(
            "symbol selectors must be scalar or iterable"
        ) from exc
    if symbols is not None:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f"(symbol IN ({placeholders}) OR inscode IN ({placeholders}))"
        outer_clauses.append(symbol_clause)
        outer_parameters.extend(symbols)
        outer_parameters.extend(symbols)
        coverage_clauses.append(symbol_clause)
        coverage_parameters.extend(symbols)
        coverage_parameters.extend(symbols)
    if inscodes is not None:
        placeholders = ",".join("?" for _ in inscodes)
        inscode_clause = f"inscode IN ({placeholders})"
        outer_clauses.append(inscode_clause)
        outer_parameters.extend(inscodes)
        coverage_clauses.append(inscode_clause)
        coverage_parameters.extend(inscodes)
    ranked_sql = (
        "WITH ranked AS (SELECT source,identity,version,observed_at_utc,"
        "provider_timestamp_utc,payload_json,flow,provider_id,provider_id_num,"
        "inscode,symbol,MIN(observed_at_utc) OVER (PARTITION BY kind,source,identity) "
        "AS first_observed_at_utc,ROW_NUMBER() OVER (PARTITION BY kind,source,identity "
        "ORDER BY version DESC,observed_at_utc DESC) AS version_rank FROM archives WHERE "
        + " AND ".join(inner_clauses)
        + ") SELECT source,identity,version,observed_at_utc,provider_timestamp_utc,"
        "payload_json,first_observed_at_utc FROM ranked WHERE "
        + " AND ".join(outer_clauses)
        + " ORDER BY observed_at_utc,source,identity LIMIT ? OFFSET ?"
    )
    try:
        rows = connection.execute(
            ranked_sql,
            [*inner_parameters, *outer_parameters, limit, offset],
        ).fetchall()
        coverage_raw = connection.execute(
            "SELECT MIN(observed_at_utc) FROM archives WHERE "
            + " AND ".join(coverage_clauses),
            coverage_parameters,
        ).fetchone()[0]
        template_row = connection.execute(
            "SELECT payload_json FROM archives WHERE kind=? "
            + ("AND source=? " if source is not None else "")
            + "ORDER BY observed_at_utc LIMIT 1",
            (kind, str(source)) if source is not None else (kind,),
        ).fetchone()
    finally:
        connection.close()
    coverage = (
        pd.NaT
        if coverage_raw is None
        else pd.Timestamp(coverage_raw).tz_convert(_TEHRAN)
    )
    if not rows:
        if template_row is None:
            return _empty_archive(kind, columns, coverage=coverage)
        try:
            template = json.loads(template_row[0])
            row_template = template["row"]
            dtypes = template["dtypes"]
            dynamic = list(columns)
            if isinstance(row_template, Mapping):
                for column in row_template:
                    if column not in dynamic:
                        dynamic.append(column)
            return _empty_archive(kind, dynamic, dtypes=dtypes, coverage=coverage)
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise DataParsingError(
                f"corrupted archives template for {kind}: {exc}"
            ) from exc
    records, dynamic_columns, stored_dtypes = [], list(columns), {}
    for (
        source_value,
        identity,
        version,
        observed_at,
        provider_at,
        raw,
        first_observed_at,
    ) in rows:
        context = f"archives record {kind}/{source_value}/{identity}/v{version}"
        try:
            wrapper = json.loads(raw)
            record = _from_json_value(wrapper["row"])
            dtypes = wrapper["dtypes"]
            if not isinstance(dtypes, Mapping):
                raise TypeError("payload dtypes are not an object")
            stored_dtypes.update(dtypes)
            if not isinstance(record, Mapping):
                raise TypeError("payload is not an object")
            record = dict(record)
            observed_stamp = pd.Timestamp(observed_at).tz_convert(_TEHRAN)
            first_observed_stamp = pd.Timestamp(first_observed_at).tz_convert(_TEHRAN)
            provider_stamp = (
                pd.NaT
                if provider_at is None
                else pd.Timestamp(provider_at).tz_convert(_TEHRAN)
            )
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise DataParsingError(f"corrupted {context}: {exc}") from exc
        for column in record:
            if column not in dynamic_columns:
                dynamic_columns.append(column)
        record.update(
            {
                "ArchiveIdentity": identity,
                "Version": version,
                "FirstObservedAt": first_observed_stamp,
                "ObservedAt": observed_stamp,
                "ProviderTimestamp": provider_stamp,
                "AsOf": observed_stamp,
                "Source": source_value,
                "SchemaVersion": MARKET_HISTORY_SCHEMA_VERSION,
                "NoBackfill": True,
                "CoverageStart": coverage,
                "SnapshotAtomic": True,
                "PersistenceAtomic": True,
                "SourceAtomic": kind == "overview",
                "NoLookahead": True,
            }
        )
        records.append(record)
    result = pd.DataFrame(records).reindex(
        columns=dynamic_columns + _ARCHIVE_META_COLUMNS
    )
    for column, dtype in stored_dtypes.items():
        if column in result:
            result[column] = _cast_column(result[column], dtype)
    for column in (
        "timestamp",
        "FirstObservedAt",
        "ObservedAt",
        "ProviderTimestamp",
        "AsOf",
        "CoverageStart",
    ):
        if column in result:
            result[column] = (
                pd.to_datetime(result[column], errors="coerce", utc=True)
                .dt.tz_convert(_TEHRAN)
                .astype(f"datetime64[ns, {_TEHRAN}]")
            )
    if kind == "messages":
        for column in ("date", "time", "flow"):
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(
                "Int64"
            )
    elif kind == "state_changes":
        for column in ("date", "time"):
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(
                "Int64"
            )
    for column in ("Version", "SchemaVersion"):
        result[column] = result[column].astype("Int64")
    for column in (
        "NoBackfill",
        "SnapshotAtomic",
        "PersistenceAtomic",
        "SourceAtomic",
        "NoLookahead",
    ):
        result[column] = result[column].astype("boolean")
    return _attrs(result, coverage)


def get_market_messages_history(
    path,
    start=None,
    end=None,
    flow=0,
    since_id=None,
    *,
    source="tsetmc",
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Return latest message versions known by each local observation time."""
    return _archive_history(
        path,
        "messages",
        MESSAGE_COLUMNS,
        start,
        end,
        source=source,
        flow=flow,
        since_id=since_id,
        limit=limit,
        offset=offset,
    )


def get_instrument_state_changes_history(
    path,
    start=None,
    end=None,
    symbol=None,
    since_id=None,
    *,
    inscode=None,
    source="tsetmc",
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Return locally observed instrument-state versions with symbol selectors."""
    return _archive_history(
        path,
        "state_changes",
        STATE_COLUMNS,
        start,
        end,
        source=source,
        since_id=since_id,
        symbol=symbol,
        inscode=inscode,
        limit=limit,
        offset=offset,
    )


def get_market_overview_history(
    path,
    start=None,
    end=None,
    flow=0,
    *,
    source="tsetmc",
    limit=_DEFAULT_QUERY_LIMIT,
    offset=0,
):
    """Return exact provider overview payloads previously archived by the live API."""
    return _archive_history(
        path,
        "overview",
        ["flow"],
        start,
        end,
        source=source,
        flow=flow,
        limit=limit,
        offset=offset,
    )


__all__ = [
    "MARKET_HISTORY_SCHEMA_VERSION",
    "MARKET_HISTORY_APPLICATION_ID",
    "check_market_history",
    "save_market_snapshot",
    "load_market_snapshots",
    "get_live_market_history",
    "get_market_overview_history",
    "get_market_snapshot_summary_history",
    "get_market_breadth_history",
    "get_sector_flow_history",
    "record_market_event",
    "get_market_event_history",
    "archive_market_records",
    "get_market_messages_history",
    "get_instrument_state_changes_history",
]
