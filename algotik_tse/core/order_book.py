"""Historical five-level order book and queue reconstruction.

TSETMC's dated ``BestLimits`` endpoint is a delta log, not a collection of
complete book snapshots.  This module performs an atomic, day-scoped replay
and exposes the result without changing the established bulk
``get_order_book()`` live API.
"""

from __future__ import annotations

import copy
import datetime as _dt
import os
import warnings
from collections.abc import Iterable

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from ..exceptions import (
    AmbiguousSymbolError,
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)
from ..http_client import safe_get
from ..settings import settings
from .resolver import normalize_instrument_text

BOOK_VALUE_COLUMNS = [
    "BidOrderCount",
    "BidVolume",
    "BidPrice",
    "AskPrice",
    "AskVolume",
    "AskOrderCount",
]
IDENTITY_COLUMNS = ["InsCode", "Symbol", "Name"]
AUDIT_COLUMNS = [
    "Date",
    "GregorianDate",
    "JalaliDate",
    "Time",
    "Timestamp",
    "DEven",
    "hEven",
    "refID",
    "_sequence",
    "Level",
]
PROVENANCE_COLUMNS = [
    "is_partial",
    "is_complete",
    "market_partial_status",
    "is_reconstructed",
    "is_stale",
    "record_type",
    "source",
]
LONG_COLUMNS = (
    IDENTITY_COLUMNS + AUDIT_COLUMNS + BOOK_VALUE_COLUMNS + PROVENANCE_COLUMNS
)
RAW_COLUMNS = list(LONG_COLUMNS)
WIDE_BOOK_COLUMNS = [
    f"{column}{level}" for level in range(1, 6) for column in BOOK_VALUE_COLUMNS
]
WIDE_COLUMNS = (
    IDENTITY_COLUMNS
    + [
        "Date",
        "GregorianDate",
        "JalaliDate",
        "Time",
        "Timestamp",
        "DEven",
        "hEven",
        "refID",
        "_sequence",
    ]
    + WIDE_BOOK_COLUMNS
    + PROVENANCE_COLUMNS
)

QUEUE_COLUMNS = IDENTITY_COLUMNS + [
    "Date",
    "GregorianDate",
    "JalaliDate",
    "Time",
    "Timestamp",
    "DEven",
    "hEven",
    "Side",
    "QueuePrice",
    "QueueVolume",
    "QueueOrders",
    "QueueValue",
    "PriceLimit",
    "is_strict",
    "is_queue",
    "is_partial",
    "is_complete",
    "market_partial_status",
    "book_state",
    "is_crossed",
    "is_preopen_or_stopped",
    "threshold_hEven",
    "threshold_source",
    "book_source",
    "source",
]

_NUMERIC_COLUMNS = {
    "DEven",
    "hEven",
    "refID",
    "_sequence",
    "Level",
    *BOOK_VALUE_COLUMNS,
    *WIDE_BOOK_COLUMNS,
    "QueuePrice",
    "QueueVolume",
    "QueueOrders",
    "QueueValue",
    "PriceLimit",
    "threshold_hEven",
    "UpperLimit",
    "LowerLimit",
}
_BOOLEAN_COLUMNS = {
    "is_partial",
    "is_complete",
    "is_reconstructed",
    "is_stale",
    "is_strict",
    "is_queue",
    "is_crossed",
    "is_preopen_or_stopped",
    "market_partial_status",
}


def _typed_empty(columns):
    data = {}
    for column in columns:
        if column == "Timestamp":
            data[column] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
        elif column in _NUMERIC_COLUMNS:
            data[column] = pd.Series(dtype="Int64")
        elif column in _BOOLEAN_COLUMNS:
            data[column] = pd.Series(dtype="boolean")
        elif column == "GregorianDate":
            data[column] = pd.Series(dtype="object")
        else:
            data[column] = pd.Series(dtype="string")
    return pd.DataFrame(data, columns=columns)


def _as_selector_list(symbol):
    if symbol is None or (isinstance(symbol, str) and symbol == ""):
        return ["شتران"]
    if isinstance(symbol, str) or not isinstance(symbol, Iterable):
        return [symbol]
    return list(symbol)


def _identity_from_row(row):
    return {
        "InsCode": str(row.get("InsCode", row.get("insCode", ""))).strip(),
        "Symbol": str(
            row.get("Symbol", row.get("lVal18AFC", row.get("lVal18", "")))
        ).strip(),
        "Name": str(row.get("Name", row.get("lVal30", ""))).strip(),
    }


def _resolve_instruments(
    symbol, snapshot=None, memo=None, response_cache=None, request_budget=None
):
    """Resolve selectors exactly, never silently accepting the first hit."""
    memo = {} if memo is None else memo
    response_cache = {} if response_cache is None else response_cache
    resolved = []
    stocks = None if snapshot is None else snapshot.get("stocks")
    for selector in _as_selector_list(symbol):
        text = str(selector).strip()
        if not text:
            raise InvalidParameterError("symbol selectors must not be empty")
        memo_key = (
            f"inscode:{text}"
            if text.isdigit()
            else f"symbol:{normalize_instrument_text(text)}"
        )
        if memo_key in memo:
            resolved.append(copy.deepcopy(memo[memo_key]))
            continue
        candidates = []
        if isinstance(stocks, pd.DataFrame) and not stocks.empty:
            if text.isdigit():
                matches = stocks.loc[stocks["InsCode"].astype(str).eq(text)]
            else:
                wanted = normalize_instrument_text(text)
                ticker_matches = stocks.loc[
                    stocks["Symbol"].map(normalize_instrument_text).eq(wanted)
                ]
                name_matches = stocks.loc[
                    stocks["Name"].map(normalize_instrument_text).eq(wanted)
                ]
                matches = ticker_matches if not ticker_matches.empty else name_matches
            candidates = [_identity_from_row(row) for _, row in matches.iterrows()]

        if text.isdigit() and not candidates:
            candidates = [{"InsCode": text, "Symbol": text, "Name": ""}]
        elif not candidates:
            search_url = settings.url_search.format(text)
            payload = _fetch_json_cached(
                search_url,
                "instrument search",
                response_cache,
                request_budget=request_budget,
            )
            rows = payload.get("instrumentSearch")
            if not isinstance(rows, list):
                raise DataParsingError("instrument search response has no list")
            wanted = normalize_instrument_text(text)
            ticker_candidates = [
                _identity_from_row(row)
                for row in rows
                if normalize_instrument_text(
                    row.get("lVal18AFC", row.get("lVal18", ""))
                )
                == wanted
            ]
            name_candidates = [
                _identity_from_row(row)
                for row in rows
                if normalize_instrument_text(row.get("lVal30", "")) == wanted
            ]
            candidates = ticker_candidates or name_candidates

        unique = {item["InsCode"]: item for item in candidates if item["InsCode"]}
        if not unique:
            raise StockNotFoundError(f"No exact instrument matched {selector!r}")
        if len(unique) != 1:
            raise AmbiguousSymbolError(
                f"Selector {selector!r} matched {len(unique)} instruments: "
                f"{list(unique.values())}"
            )
        identity = next(iter(unique.values()))
        identity["_verified"] = bool(
            candidates
            and not (
                text.isdigit()
                and len(candidates) == 1
                and candidates[0].get("Symbol") == text
                and candidates[0].get("Name") == ""
            )
        )
        memo[memo_key] = copy.deepcopy(identity)
        resolved.append(identity)

    # Repeated aliases for the same instrument must not trigger duplicate HTTP
    # requests or duplicate replay rows.
    return list({item["InsCode"]: item for item in resolved}.values())


def _response_json(response, endpoint):
    if response is None:
        raise ConnectionError(f"No response from {endpoint}")
    status = getattr(response, "status_code", 200)
    if status is not None and int(status) >= 400:
        raise ConnectionError(f"{endpoint} returned HTTP {status}")
    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        raise DataParsingError(f"Invalid JSON from {endpoint}") from exc
    if not isinstance(payload, dict):
        raise DataParsingError(f"Unexpected JSON shape from {endpoint}")
    return payload


def _fetch_json_cached(url, endpoint, cache, request_budget=None):
    """Fetch one endpoint key at most once in a public API call."""
    key = (endpoint, url)
    if key not in cache:
        if request_budget is not None:
            request_budget.consume(endpoint)
        cache[key] = _response_json(safe_get(url), endpoint)
    return copy.deepcopy(cache[key])


def _coerce_date(value):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        if text[:2] in {"13", "14", "15"}:
            return JalaliDate.fromisoformat(text).to_gregorian()
        return _dt.date.fromisoformat(text)
    except (ValueError, TypeError) as exc:
        raise InvalidParameterError(f"Invalid date {value!r}") from exc


def _requested_dates(start, end, limit):
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    try:
        numeric_limit = int(limit or 0)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("limit must be a non-negative integer") from exc
    if numeric_limit < 0:
        raise InvalidParameterError("limit must be a non-negative integer")
    first, last = _coerce_date(start), _coerce_date(end)
    if first is None and last is None:
        count = (
            max(int(getattr(settings, "order_book_discovery_lookback_days", 10)), 1)
            if numeric_limit
            else 1
        )
        last = today
        first = last - _dt.timedelta(days=count - 1)
    elif first is None:
        count = (
            max(int(getattr(settings, "order_book_discovery_lookback_days", 10)), 1)
            if numeric_limit
            else 1
        )
        first = last - _dt.timedelta(days=count - 1)
    elif last is None:
        last = today
    if first > last:
        raise InvalidParameterError("start must be on or before end")
    return list(pd.date_range(first, last, freq="D").date)


def _request_budget(max_requests):
    value = (
        getattr(settings, "order_book_max_requests", 250)
        if max_requests is None
        else max_requests
    )
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("max_requests must be a positive integer") from exc
    if value < 1:
        raise InvalidParameterError("max_requests must be a positive integer")
    return value


class _RequestBudget:
    """Shared hard cap across search, live, history and threshold calls."""

    def __init__(self, limit):
        self.limit = int(limit)
        self.used = 0

    @property
    def remaining(self):
        return self.limit - self.used

    def consume(self, operation):
        if self.used >= self.limit:
            raise InvalidParameterError(
                f"Request budget exhausted before {operation}; "
                f"max_requests={self.limit}"
            )
        self.used += 1


def _selector_request_plan(symbol):
    keys = set()
    search_keys = set()
    for selector in _as_selector_list(symbol):
        text = str(selector).strip()
        if not text:
            raise InvalidParameterError("symbol selectors must not be empty")
        if text.isdigit():
            keys.add(f"inscode:{text}")
        else:
            normalized = normalize_instrument_text(text)
            key = f"symbol:{normalized}"
            keys.add(key)
            search_keys.add(key)
    return len(keys), len(search_keys)


def _guard_requests(estimated, budget, operation):
    if estimated > budget:
        raise InvalidParameterError(
            f"{operation} would require approximately {estimated} provider "
            f"requests, exceeding max_requests={budget}; narrow the date range "
            "or explicitly raise max_requests"
        )


def _valid_heven(value):
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or numeric > 235959:
        return None
    text = str(numeric).zfill(6)
    if int(text[2:4]) > 59 or int(text[4:]) > 59:
        return None
    return numeric


def _timestamp(deven, heven):
    date_text = str(int(deven)).zfill(8)
    time_text = str(int(heven)).zfill(6)
    try:
        value = _dt.datetime.strptime(date_text + time_text, "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise DataParsingError(f"Invalid DEven/hEven pair: {deven}/{heven}") from exc
    return pd.Timestamp(value, tz="Asia/Tehran")


def _display_date(gregorian_date, date_format):
    jalali = JalaliDate.to_jalali(gregorian_date).isoformat()
    if date_format == "jalali":
        return jalali, jalali
    if date_format == "gregorian":
        return gregorian_date.isoformat(), jalali
    if date_format == "both":
        return gregorian_date.isoformat(), jalali
    raise InvalidParameterError("date_format must be 'jalali', 'gregorian', or 'both'")


def _parse_history_records(records, requested_date, identity, date_format):
    """Normalize and validate dated delta records for one instrument/day."""
    if records in (None, []):
        return _typed_empty(RAW_COLUMNS)
    if not isinstance(records, list):
        raise DataParsingError("bestLimitsHistory must be a list")
    parsed, invalid = [], 0
    requested_deven = int(requested_date.strftime("%Y%m%d"))
    for sequence, row in enumerate(records):
        if not isinstance(row, dict):
            invalid += 1
            continue
        try:
            level = int(row.get("number"))
            heven = _valid_heven(row.get("hEven"))
            deven = int(row.get("dEven", requested_deven))
            refid = int(row.get("refID", 0))
            values = {
                "BidOrderCount": int(row["zOrdMeDem"]),
                "BidVolume": int(row["qTitMeDem"]),
                "BidPrice": int(row["pMeDem"]),
                "AskPrice": int(row["pMeOf"]),
                "AskVolume": int(row["qTitMeOf"]),
                "AskOrderCount": int(row["zOrdMeOf"]),
            }
            if level not in range(1, 6) or heven is None or deven != requested_deven:
                raise ValueError
            timestamp = _timestamp(deven, heven)
        except (KeyError, TypeError, ValueError, DataParsingError):
            invalid += 1
            continue
        gregorian = timestamp.date()
        shown_date, jalali = _display_date(gregorian, date_format)
        parsed.append(
            {
                **identity,
                "Date": shown_date,
                "GregorianDate": gregorian,
                "JalaliDate": jalali,
                "Time": timestamp.strftime("%H:%M:%S"),
                "Timestamp": timestamp,
                "DEven": deven,
                "hEven": heven,
                "refID": refid,
                "_sequence": sequence,
                "Level": level,
                **values,
                "is_partial": pd.NA,
                "is_complete": pd.NA,
                "market_partial_status": pd.NA,
                "is_reconstructed": False,
                "is_stale": False,
                "record_type": "delta",
                "source": "tsetmc_best_limits_history_delta",
            }
        )
    if invalid:
        warnings.warn(
            f"Skipped {invalid} malformed BestLimits history record(s) for "
            f"{identity['InsCode']} on {requested_date}",
            RuntimeWarning,
            stacklevel=3,
        )
    if records and not parsed:
        raise DataParsingError("No valid BestLimits history records remained")
    result = pd.DataFrame(parsed).reindex(columns=RAW_COLUMNS)
    for _, event_group in result.groupby(["DEven", "hEven"], sort=False):
        complete = (
            set(event_group["Level"].astype(int)) >= set(range(1, 6))
            and not event_group[BOOK_VALUE_COLUMNS].isna().to_numpy().any()
        )
        result.loc[event_group.index, "is_complete"] = complete
        result.loc[event_group.index, "is_partial"] = not complete
    return _cast_frame(result, RAW_COLUMNS)


def _cast_frame(frame, columns):
    result = frame.reindex(columns=columns).copy()
    for column in _NUMERIC_COLUMNS.intersection(result.columns):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    for column in _BOOLEAN_COLUMNS.intersection(result.columns):
        result[column] = result[column].astype("boolean")
    if "Timestamp" in result.columns:
        result["Timestamp"] = (
            pd.to_datetime(result["Timestamp"], errors="coerce", utc=True)
            .dt.tz_convert("Asia/Tehran")
            .astype("datetime64[ns, Asia/Tehran]")
        )
    for column in result.columns:
        if (
            column not in _NUMERIC_COLUMNS
            and column not in _BOOLEAN_COLUMNS
            and column not in {"Timestamp", "GregorianDate"}
        ):
            result[column] = result[column].astype("string")
    return result


def _reconstruct_day(raw, complete_only=False):
    """Replay one day without leaking future level values backwards."""
    if raw.empty:
        return _typed_empty(LONG_COLUMNS)
    ordered = raw.sort_values(
        ["DEven", "hEven", "refID", "_sequence"], kind="mergesort"
    )
    # Identical feed events occasionally repeat. Replay each event only once.
    ordered = ordered.drop_duplicates(
        subset=["DEven", "hEven", "refID", "Level", *BOOK_VALUE_COLUMNS],
        keep="last",
    )
    state = {level: None for level in range(1, 6)}
    output = []
    for (_, heven), group in ordered.groupby(["DEven", "hEven"], sort=False):
        # All deltas in one second are applied before emitting the snapshot;
        # repeated levels follow refID/_sequence last-write-wins semantics.
        for _, event in group.iterrows():
            state[int(event["Level"])] = {
                column: event[column] for column in BOOK_VALUE_COLUMNS
            }
        last = group.iloc[-1]
        complete = all(state[level] is not None for level in range(1, 6))
        if complete_only and not complete:
            continue
        for level in range(1, 6):
            values = state[level] or {column: pd.NA for column in BOOK_VALUE_COLUMNS}
            output.append(
                {
                    **{column: last[column] for column in IDENTITY_COLUMNS},
                    **{
                        column: last[column]
                        for column in AUDIT_COLUMNS
                        if column != "Level"
                    },
                    "Level": level,
                    **values,
                    "is_partial": not complete,
                    "is_complete": complete,
                    "market_partial_status": pd.NA,
                    "is_reconstructed": True,
                    "is_stale": False,
                    "record_type": "reconstructed_snapshot",
                    "source": "tsetmc_best_limits_history_reconstructed",
                }
            )
    if not output:
        return _typed_empty(LONG_COLUMNS)
    return _cast_frame(pd.DataFrame(output), LONG_COLUMNS)


def _to_wide(long_frame):
    if long_frame.empty:
        return _typed_empty(WIDE_COLUMNS)
    metadata_columns = [
        *IDENTITY_COLUMNS,
        "Date",
        "GregorianDate",
        "JalaliDate",
        "Time",
        "Timestamp",
        "DEven",
        "hEven",
        "refID",
        "_sequence",
        *PROVENANCE_COLUMNS,
    ]
    rows = []
    for _, snapshot in long_frame.groupby(["InsCode", "Timestamp"], sort=False):
        last = snapshot.iloc[-1]
        row = {column: last[column] for column in metadata_columns}
        for _, level_row in snapshot.iterrows():
            level = int(level_row["Level"])
            for column in BOOK_VALUE_COLUMNS:
                row[f"{column}{level}"] = level_row[column]
        rows.append(row)
    return _cast_frame(pd.DataFrame(rows), WIDE_COLUMNS)


def _live_rows(snapshot, identities, date_format, include_empty=False):
    """Translate one bulk MarketWatch book into one atomic current snapshot."""
    if not snapshot or not snapshot.get("is_history_eligible", False):
        return _typed_empty(LONG_COLUMNS)
    trade_date = snapshot.get("trade_date")
    today = pd.Timestamp.now(tz="Asia/Tehran").date()
    exchange_time = snapshot.get("exchange_time")
    orders = snapshot.get("order_book")
    if (
        trade_date != today
        or not isinstance(exchange_time, pd.Timestamp)
        or not isinstance(orders, pd.DataFrame)
        or (orders.empty and not include_empty)
        or bool(snapshot.get("is_stale", False))
        or (
            "is_realtime_fresh" in snapshot
            and not bool(snapshot.get("is_realtime_fresh"))
        )
    ):
        return _typed_empty(LONG_COLUMNS)
    if exchange_time.tzinfo is None:
        exchange_time = exchange_time.tz_localize("Asia/Tehran")
    shown, jalali = _display_date(trade_date, date_format)
    output = []
    books_by_inscode = (
        {
            str(inscode): group
            for inscode, group in orders.groupby(
                orders["InsCode"].astype(str), sort=False
            )
        }
        if "InsCode" in orders.columns
        else {}
    )
    for identity in identities:
        book = books_by_inscode.get(identity["InsCode"], orders.iloc[0:0])
        if book.empty and not include_empty:
            continue
        available_levels = (
            set(pd.to_numeric(book["Level"], errors="coerce").dropna().astype(int))
            if "Level" in book.columns
            else set()
        )
        complete = available_levels >= set(range(1, 6))
        level_events = (
            {
                int(event["Level"]): event
                for _, event in book.sort_values("Level").iterrows()
                if pd.notna(event["Level"]) and int(event["Level"]) in range(1, 6)
            }
            if "Level" in book.columns
            else {}
        )
        for level in range(1, 6):
            event = level_events.get(level)
            values = (
                {column: pd.NA for column in BOOK_VALUE_COLUMNS}
                if event is None
                else {column: event[column] for column in BOOK_VALUE_COLUMNS}
            )
            output.append(
                {
                    **identity,
                    "Date": shown,
                    "GregorianDate": trade_date,
                    "JalaliDate": jalali,
                    "Time": exchange_time.strftime("%H:%M:%S"),
                    "Timestamp": exchange_time,
                    "DEven": int(trade_date.strftime("%Y%m%d")),
                    "hEven": int(exchange_time.strftime("%H%M%S")),
                    "refID": pd.NA,
                    "_sequence": int(level - 1),
                    "Level": level,
                    **values,
                    "is_partial": not complete,
                    "is_complete": complete,
                    "market_partial_status": snapshot.get("is_partial", pd.NA),
                    "is_reconstructed": False,
                    "is_stale": bool(snapshot.get("is_stale", False)),
                    "record_type": "full_snapshot",
                    "source": "market_watch_live_snapshot",
                }
            )
    if not output:
        return _typed_empty(LONG_COLUMNS)
    return _cast_frame(pd.DataFrame(output), LONG_COLUMNS)


def _group_quality(group):
    """Return (complete, populated-level-count) for atomic source selection."""
    complete_values = group.get("is_complete")
    if complete_values is not None and complete_values.notna().any():
        complete = bool(complete_values.dropna().all())
    else:
        available = group.loc[~group[BOOK_VALUE_COLUMNS].isna().all(axis=1), "Level"]
        complete = set(pd.to_numeric(available, errors="coerce").dropna()) >= set(
            range(1, 6)
        )
    populated = int((~group[BOOK_VALUE_COLUMNS].isna().all(axis=1)).sum())
    return complete, populated


def _merge_live_atomic(history, live):
    """Upsert whole snapshots without ever creating a hybrid source book."""
    if live.empty:
        return history.copy()
    result = history.copy()
    winners = []
    for (inscode, timestamp), live_group in live.groupby(
        ["InsCode", "Timestamp"], sort=False
    ):
        collision = result.loc[
            result["InsCode"].astype(str).eq(str(inscode))
            & result["Timestamp"].eq(timestamp)
        ]
        live_complete, live_populated = _group_quality(live_group)
        history_complete, history_populated = _group_quality(collision)
        live_wins = (
            collision.empty
            or live_complete
            or (not history_complete and live_populated >= history_populated)
        )
        if live_wins:
            if not collision.empty:
                result = result.drop(index=collision.index)
            winners.append(live_group)
    if winners:
        result = pd.concat([result, *winners], ignore_index=True)
    return result


def _drop_empty_books(frame, output_type, raw, dropna):
    if not dropna or frame.empty:
        return frame
    if output_type == "wide" and not raw:
        return frame.loc[~frame[WIDE_BOOK_COLUMNS].isna().all(axis=1)].copy()
    if raw:
        full_mask = frame["record_type"].eq("full_snapshot")
        keep_indices = frame.loc[
            ~full_mask & ~frame[BOOK_VALUE_COLUMNS].isna().all(axis=1)
        ].index.tolist()
        for _, snapshot in frame.loc[full_mask].groupby(
            ["InsCode", "Timestamp", "record_type"], sort=False
        ):
            # A full_snapshot is an atomic unit. Placeholder levels are part
            # of its auditable partial-book shape and must not be row-dropped.
            if not snapshot[BOOK_VALUE_COLUMNS].isna().to_numpy().all():
                keep_indices.extend(snapshot.index.tolist())
        return frame.loc[sorted(keep_indices)].copy()
    keep_indices = []
    for _, snapshot in frame.groupby(["InsCode", "Timestamp"], sort=False):
        if not snapshot[BOOK_VALUE_COLUMNS].isna().to_numpy().all():
            keep_indices.extend(snapshot.index.tolist())
    return frame.loc[keep_indices].copy()


def _apply_final_limit(frame, limit, output_type, raw):
    count = int(limit or 0)
    if count <= 0 or frame.empty:
        return frame
    sort_candidates = ["InsCode", "Timestamp", "refID", "_sequence", "Level"]
    ordered = frame.sort_values(
        [column for column in sort_candidates if column in frame],
        kind="mergesort",
    )
    if raw:
        kept = []
        for _, instrument in ordered.groupby("InsCode", sort=False):
            instrument = instrument.copy()
            full_snapshot = instrument["record_type"].eq("full_snapshot")
            delta_units = pd.Series(
                [f"delta:{position}" for position in range(len(instrument))],
                index=instrument.index,
                dtype="string",
            )
            snapshot_units = "snapshot:" + instrument["Timestamp"].astype("string")
            instrument["_limit_unit"] = delta_units.where(
                ~full_snapshot, snapshot_units
            )
            units = instrument["_limit_unit"].drop_duplicates().tail(count)
            kept.append(
                instrument.loc[instrument["_limit_unit"].isin(units)].drop(
                    columns="_limit_unit"
                )
            )
        return pd.concat(kept, ignore_index=True) if kept else ordered.iloc[0:0]
    if output_type == "wide":
        return ordered.groupby("InsCode", sort=False, group_keys=False).tail(count)
    kept = []
    for _, instrument in ordered.groupby("InsCode", sort=False):
        timestamps = instrument["Timestamp"].drop_duplicates().tail(count)
        kept.append(instrument.loc[instrument["Timestamp"].isin(timestamps)])
    return pd.concat(kept, ignore_index=True) if kept else ordered.iloc[0:0]


def _sort_result(frame, ascending):
    if frame.empty:
        return frame
    keys = [
        column
        for column in ["InsCode", "Timestamp", "refID", "_sequence", "Level"]
        if column in frame
    ]
    directions = [bool(ascending) if key == "Timestamp" else True for key in keys]
    return frame.sort_values(keys, ascending=directions, kind="mergesort").reset_index(
        drop=True
    )


def get_order_book_history(
    symbol="",
    start=None,
    end=None,
    limit=0,
    raw=False,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    ascending=True,
    save_path=None,
    include_today=False,
    complete_only=False,
    *,
    max_requests=None,
    _request_budget_state=None,
    **kwargs,
):
    """Get and reconstruct historical five-level order-book snapshots.

    ``BestLimits`` history is replayed independently for each Gregorian trade
    date.  The default long result has five rows per atomic snapshot.  Use
    ``raw=True`` for provider deltas or ``output_type='wide'`` for one row per
    snapshot. ``limit`` is applied after chronological reconstruction: raw
    delta rows, long snapshots (all five levels retained), or wide rows per
    symbol. Without a range, ``limit`` uses a bounded discovery lookback;
    without either, only Tehran today is queried. ``max_requests`` prevents
    accidental request fan-out and counts selector search, MarketWatch live,
    history and (through queue history) threshold calls under one hard cap.

    With ``raw=True, include_today=True``, historical rows keep
    ``record_type='delta'`` while the current five-level group is appended as
    an atomic ``record_type='full_snapshot'``. Such output declares
    ``attrs['schema'] == 'raw_mixed'``. A raw ``limit`` counts each delta as a
    unit but always retains every level of a selected full-snapshot unit.

    Non-trading dates return no rows. Provider/parse failures are aggregated in
    ``result.attrs['failed_requests']`` and emit one ``RuntimeWarning`` while
    successful dates remain available. ``dropna`` removes only wholly empty
    book rows/snapshots and preserves meaningful partial books. A numeric
    ``InsCode`` is accepted without an extra verification request and this is
    disclosed through ``result.attrs['selector_verified']``.
    """
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "values" in kwargs:
        limit = kwargs.pop("values")
    if "multi_stock_drop" in kwargs:
        dropna = kwargs.pop("multi_stock_drop")
    if "tse_format" in kwargs:
        raw = kwargs.pop("tse_format")
    if output_type == "complete":
        output_type = "wide"
    if output_type not in {"standard", "long", "wide"}:
        raise InvalidParameterError("output_type must be 'standard', 'long', or 'wide'")
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"Unexpected keyword argument(s): {unknown}")

    dates = _requested_dates(start, end, limit)
    budget_limit = _request_budget(max_requests)
    selector_count, search_count = _selector_request_plan(symbol)
    estimated_requests = selector_count * len(dates)
    estimated_total_requests = (
        estimated_requests + search_count + (1 if include_today else 0)
    )
    request_budget = (
        _request_budget_state
        if _request_budget_state is not None
        else _RequestBudget(budget_limit)
    )
    _guard_requests(
        estimated_total_requests,
        request_budget.remaining,
        "order-book history including selector/live resolution",
    )

    live_snapshot = None
    include_warning = None
    if include_today:
        request_budget.consume("MarketWatch live snapshot")
        try:
            from .market_data import market_watch

            live_snapshot = market_watch()  # exactly one bulk call per API call
        except Exception as exc:  # live is optional; historical data must survive
            include_warning = (
                f"include_today skipped; live order book unavailable: {exc}"
            )
            warnings.warn(include_warning, RuntimeWarning, stacklevel=2)

    response_cache = {}
    selector_memo = {}
    identities = _resolve_instruments(
        symbol,
        snapshot=live_snapshot,
        memo=selector_memo,
        response_cache=response_cache,
        request_budget=request_budget,
    )
    # Exact resolution can collapse aliases to one InsCode. The conservative
    # preflight above is intentionally not relaxed after network work starts.
    raw_parts, failures = [], []
    total = len(identities) * len(dates)
    done = 0
    for identity in identities:
        for requested_date in dates:
            done += 1
            if progress:
                print(
                    f"{done}/{total}: Getting order book of "
                    f"{identity['Symbol']} for {requested_date}"
                )
            deven = requested_date.strftime("%Y%m%d")
            url = settings.url_best_limits_history.format(identity["InsCode"], deven)
            try:
                payload = _fetch_json_cached(
                    url,
                    "BestLimits history",
                    response_cache,
                    request_budget=request_budget,
                )
                records = payload.get("bestLimitsHistory")
                if records is None:
                    raise DataParsingError(
                        "BestLimits response lacks bestLimitsHistory"
                    )
                part = _parse_history_records(
                    records, requested_date, identity, date_format
                )
                if not part.empty:
                    raw_parts.append(part)
            except (
                ConnectionError,
                DataParsingError,
                requests.exceptions.RequestException,
            ) as exc:
                message = f"Skipped {identity['InsCode']}/{deven}: {exc}"
                failures.append(message)
    if failures:
        warnings.warn(
            f"{len(failures)} order-book request(s) failed; inspect "
            "result.attrs['failed_requests']",
            RuntimeWarning,
            stacklevel=2,
        )

    raw_frame = (
        pd.concat(raw_parts, ignore_index=True)
        if raw_parts
        else _typed_empty(RAW_COLUMNS)
    )
    if raw:
        result = raw_frame
        if include_today and live_snapshot is not None:
            live = _live_rows(live_snapshot, identities, date_format)
            if live.empty:
                include_warning = (
                    "include_today skipped; MarketWatch snapshot is stale, "
                    "undated, or has no selected order book"
                )
                warnings.warn(include_warning, RuntimeWarning, stacklevel=2)
            else:
                result = _merge_live_atomic(result, live)
    else:
        reconstructed = []
        if not raw_frame.empty:
            for _, day in raw_frame.groupby(["InsCode", "DEven"], sort=False):
                reconstructed.append(_reconstruct_day(day, complete_only=complete_only))
        result = (
            pd.concat(reconstructed, ignore_index=True)
            if reconstructed
            else _typed_empty(LONG_COLUMNS)
        )
        if include_today and live_snapshot is not None:
            live = _live_rows(live_snapshot, identities, date_format)
            if complete_only and not live.empty:
                live = live.loc[live["is_complete"].fillna(False)].copy()
            if live.empty:
                include_warning = (
                    "include_today skipped; MarketWatch snapshot is stale, "
                    "undated, or has no selected order book"
                )
                warnings.warn(include_warning, RuntimeWarning, stacklevel=2)
            else:
                result = _merge_live_atomic(result, live)
        if output_type == "wide":
            result = _to_wide(result)

    result = _drop_empty_books(result, output_type, raw, dropna)
    result = _apply_final_limit(result, limit, output_type, raw)
    expected_columns = (
        RAW_COLUMNS
        if raw
        else (WIDE_COLUMNS if output_type == "wide" else LONG_COLUMNS)
    )
    result = _cast_frame(result, expected_columns)
    result = _sort_result(result, ascending=ascending)
    result.attrs.update(
        {
            "failed_requests": failures,
            "include_today_requested": bool(include_today),
            "include_today_appended": bool(
                not result.empty
                and "source" in result
                and result["source"].eq("market_watch_live_snapshot").any()
            ),
            "include_today_warning": include_warning,
            "date_range_default": (
                "today_only" if start is None and end is None and not limit else None
            ),
            "schema": (
                (
                    "raw_mixed"
                    if not result.empty
                    and result["record_type"].eq("full_snapshot").any()
                    else "raw_delta"
                )
                if raw
                else ("wide_snapshot" if output_type == "wide" else "long_snapshot")
            ),
            "request_count": request_budget.used,
            "estimated_history_requests": estimated_requests,
            "estimated_total_requests": estimated_total_requests,
            "max_requests": request_budget.limit,
            "selector_verified": all(
                bool(item.get("_verified", False)) for item in identities
            ),
            "selector_verification_note": (
                None
                if all(bool(item.get("_verified", False)) for item in identities)
                else "numeric InsCode accepted without a separate verification request"
            ),
        }
    )
    if save_to_file:
        target_dir = save_path or "."
        os.makedirs(target_dir, exist_ok=True)
        names = "-".join(item["Symbol"] or item["InsCode"] for item in identities)
        result.to_csv(
            os.path.join(target_dir, f"{names}-order-book-history.csv"),
            index=False,
            encoding="utf-8-sig",
        )
    return result


def _parse_threshold_records(records, requested_date):
    columns = ["DEven", "hEven", "UpperLimit", "LowerLimit", "ThresholdSource"]
    if records in (None, []):
        return _cast_frame(pd.DataFrame(), columns)
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise DataParsingError("staticThreshold must be a list or object")
    default_deven = int(requested_date.strftime("%Y%m%d"))
    output, invalid = [], 0
    for row in records:
        try:
            if not isinstance(row, dict):
                raise TypeError
            heven = _valid_heven(row.get("hEven", 0))
            deven = int(row.get("dEven", default_deven))
            if heven is None or deven != default_deven:
                raise ValueError
            output.append(
                {
                    "DEven": deven,
                    "hEven": heven,
                    "UpperLimit": int(row["psGelStaMax"]),
                    "LowerLimit": int(row["psGelStaMin"]),
                    "ThresholdSource": "tsetmc_static_threshold_asof",
                }
            )
        except (KeyError, TypeError, ValueError):
            invalid += 1
    if invalid:
        warnings.warn(
            f"Skipped {invalid} malformed or cross-date static-threshold "
            f"record(s) for {default_deven}",
            RuntimeWarning,
            stacklevel=3,
        )
    if not output:
        return _cast_frame(pd.DataFrame(), columns)
    return _cast_frame(
        pd.DataFrame(output).sort_values("hEven", kind="mergesort"), columns
    )


def _book_state(level_one):
    bid = level_one.get("BidPrice")
    ask = level_one.get("AskPrice")
    bid_empty = pd.isna(bid) or int(bid) == 0
    ask_empty = pd.isna(ask) or int(ask) == 0
    if bid_empty and ask_empty:
        return "empty"
    if bid_empty or ask_empty:
        return "one_sided"
    if int(bid) > int(ask):
        return "crossed"
    return "normal"


def _empty_side(level_one, side):
    fields = (
        ["AskPrice", "AskVolume", "AskOrderCount"]
        if side == "ask"
        else ["BidPrice", "BidVolume", "BidOrderCount"]
    )
    return all(
        pd.isna(level_one.get(field)) or int(level_one.get(field)) == 0
        for field in fields
    )


def _validate_queue_side(side):
    value = str(side).lower()
    if value not in {"both", "buy", "sell"}:
        raise InvalidParameterError("side must be 'both', 'buy', or 'sell'")
    return value


def _derive_queue_rows(books, thresholds, side, strict):
    output = []
    selected_sides = ["buy", "sell"] if side == "both" else [side]
    for (_, _), snapshot in books.groupby(["InsCode", "Timestamp"], sort=False):
        first = snapshot.iloc[0]
        l1_rows = snapshot.loc[snapshot["Level"].eq(1)]
        if l1_rows.empty:
            continue
        l1 = l1_rows.iloc[-1]
        limits = thresholds.get((str(first["InsCode"]), int(first["DEven"])))
        asof = (
            pd.DataFrame()
            if limits is None or limits.empty
            else limits.loc[
                limits["DEven"].eq(int(first["DEven"]))
                & limits["hEven"].le(int(first["hEven"]))
            ]
        )
        threshold = None if asof.empty else asof.iloc[-1]
        state = _book_state(l1)
        l1_missing = l1[BOOK_VALUE_COLUMNS].isna().all()
        book_source = str(first["source"])
        for queue_side in selected_sides:
            buy = queue_side == "buy"
            price_field = "BidPrice" if buy else "AskPrice"
            volume_field = "BidVolume" if buy else "AskVolume"
            orders_field = "BidOrderCount" if buy else "AskOrderCount"
            limit_field = "UpperLimit" if buy else "LowerLimit"
            raw_limit = pd.NA if threshold is None else threshold[limit_field]
            price_limit = (
                pd.NA if pd.isna(raw_limit) or int(raw_limit) <= 0 else int(raw_limit)
            )
            needed = [price_field, volume_field, orders_field]
            data_missing = l1_missing or any(pd.isna(l1[field]) for field in needed)
            if state == "crossed":
                is_queue = False
            elif pd.isna(price_limit) or data_missing:
                is_queue = pd.NA
            else:
                at_limit = int(l1[price_field]) == int(price_limit)
                positive = int(l1[volume_field]) > 0 and int(l1[orders_field]) > 0
                opposition_empty = _empty_side(l1, "ask" if buy else "bid")
                is_queue = bool(
                    at_limit and positive and (opposition_empty if strict else True)
                )
            queue_true = pd.notna(is_queue) and bool(is_queue)
            queue_price = int(l1[price_field]) if queue_true else pd.NA
            queue_volume = int(l1[volume_field]) if queue_true else pd.NA
            queue_orders = int(l1[orders_field]) if queue_true else pd.NA
            output.append(
                {
                    **{column: first[column] for column in IDENTITY_COLUMNS},
                    **{
                        column: first[column]
                        for column in [
                            "Date",
                            "GregorianDate",
                            "JalaliDate",
                            "Time",
                            "Timestamp",
                            "DEven",
                            "hEven",
                        ]
                    },
                    "Side": queue_side,
                    "QueuePrice": queue_price,
                    "QueueVolume": queue_volume,
                    "QueueOrders": queue_orders,
                    "QueueValue": (queue_price * queue_volume if queue_true else pd.NA),
                    "PriceLimit": price_limit,
                    "is_strict": bool(strict),
                    "is_queue": is_queue,
                    "is_partial": first["is_partial"],
                    "is_complete": first["is_complete"],
                    "market_partial_status": first["market_partial_status"],
                    "book_state": state,
                    "is_crossed": state == "crossed",
                    "is_preopen_or_stopped": (
                        state == "empty"
                        and pd.notna(first["is_partial"])
                        and bool(first["is_partial"])
                    ),
                    "threshold_hEven": (
                        pd.NA if threshold is None else int(threshold["hEven"])
                    ),
                    "threshold_source": (
                        "unavailable"
                        if threshold is None
                        else str(threshold["ThresholdSource"])
                    ),
                    "book_source": book_source,
                    "source": f"derived_from_{book_source}",
                }
            )
    return (
        _typed_empty(QUEUE_COLUMNS)
        if not output
        else _cast_frame(pd.DataFrame(output), QUEUE_COLUMNS)
    )


def _finalize_queue(
    result,
    base_attrs,
    failures,
    strict,
    ascending,
    save_to_file=False,
    save_path=None,
    filename="queue-history.csv",
):
    result = _cast_frame(result, QUEUE_COLUMNS)
    result = _sort_result(result, ascending=ascending)
    result.attrs.update(copy.deepcopy(base_attrs))
    result.attrs.update(
        {
            "failed_requests": list(failures),
            "queue_strict": bool(strict),
            "schema": "canonical_queue",
        }
    )
    if save_to_file:
        target_dir = save_path or "."
        os.makedirs(target_dir, exist_ok=True)
        result.to_csv(
            os.path.join(target_dir, filename),
            index=False,
            encoding="utf-8-sig",
        )
    return result


def get_queue_history(
    symbol="",
    start=None,
    end=None,
    limit=0,
    date_format="jalali",
    progress=True,
    save_to_file=False,
    dropna=True,
    ascending=True,
    save_path=None,
    include_today=False,
    complete_only=False,
    side="both",
    strict=True,
    *,
    max_requests=None,
    **kwargs,
):
    """Derive queue history from reconstructed books and same-day limits.

    Thresholds are selected as-of each snapshot and cross-date records are
    discarded. Missing thresholds/L1 data produce nullable ``is_queue`` rather
    than a false signal, while crossed books are explicitly false. ``limit``
    counts reconstructed snapshots per symbol. Endpoint failures are retained
    in ``attrs['failed_requests']``; exact attempted-call count and the shared
    cap are exposed through ``request_count`` and ``max_requests``.
    """
    if not symbol and "stock" in kwargs:
        symbol = kwargs.pop("stock")
    if "values" in kwargs:
        limit = kwargs.pop("values")
    if "multi_stock_drop" in kwargs:
        dropna = kwargs.pop("multi_stock_drop")
    incompatible = {"raw", "tse_format", "output_type"}.intersection(kwargs)
    if incompatible:
        raise InvalidParameterError(
            "queue history is always reconstructed long data; incompatible "
            f"argument(s): {', '.join(sorted(incompatible))}"
        )
    if kwargs:
        raise TypeError(f"Unexpected keyword argument(s): {', '.join(sorted(kwargs))}")
    side = _validate_queue_side(side)
    budget_limit = _request_budget(max_requests)
    request_budget = _RequestBudget(budget_limit)
    selector_count, search_count = _selector_request_plan(symbol)
    planned_dates = _requested_dates(start, end, limit)
    estimated_total = (
        selector_count * len(planned_dates) * 2
        + search_count
        + (1 if include_today else 0)
    )
    _guard_requests(
        estimated_total,
        budget_limit,
        "queue history including thresholds",
    )
    books = get_order_book_history(
        symbol=symbol,
        start=start,
        end=end,
        limit=limit,
        raw=False,
        output_type="long",
        date_format=date_format,
        progress=progress,
        save_to_file=False,
        dropna=dropna,
        ascending=True,
        include_today=include_today,
        complete_only=complete_only,
        max_requests=budget_limit,
        _request_budget_state=request_budget,
    )
    failures = list(books.attrs.get("failed_requests", []))
    if books.empty:
        empty_attrs = copy.deepcopy(books.attrs)
        empty_attrs["request_count"] = request_budget.used
        empty_attrs["estimated_total_requests"] = estimated_total
        return _finalize_queue(
            _typed_empty(QUEUE_COLUMNS),
            empty_attrs,
            failures,
            strict,
            ascending,
            save_to_file,
            save_path,
        )

    thresholds, threshold_cache = {}, {}
    for (inscode, deven), group in books.groupby(["InsCode", "DEven"], sort=False):
        requested_date = group.iloc[0]["GregorianDate"]
        url = settings.url_static_threshold.format(inscode, int(deven))
        try:
            payload = _fetch_json_cached(
                url,
                "static threshold",
                threshold_cache,
                request_budget=request_budget,
            )
            records = payload.get("staticThreshold")
            if records is None:
                raise DataParsingError("response lacks staticThreshold")
            thresholds[(str(inscode), int(deven))] = _parse_threshold_records(
                records, requested_date
            )
        except (
            ConnectionError,
            DataParsingError,
            requests.exceptions.RequestException,
        ) as exc:
            failures.append(f"Threshold unavailable for {inscode}/{deven}: {exc}")
            thresholds[(str(inscode), int(deven))] = _parse_threshold_records(
                [], requested_date
            )
    threshold_failures = len(failures) - len(books.attrs.get("failed_requests", []))
    if threshold_failures:
        warnings.warn(
            f"{threshold_failures} threshold request(s) failed; inspect "
            "result.attrs['failed_requests']",
            RuntimeWarning,
            stacklevel=2,
        )
    result = _derive_queue_rows(books, thresholds, side, strict)
    attrs = copy.deepcopy(books.attrs)
    attrs["request_count"] = request_budget.used
    attrs["estimated_total_requests"] = estimated_total
    return _finalize_queue(
        result,
        attrs,
        failures,
        strict,
        ascending,
        save_to_file,
        save_path,
    )


def get_queue(symbol=None, side="both", strict=True, *, selector_strict=False):
    """Return current buy/sell queues from one bulk MarketWatch snapshot.

    ``symbol`` follows :func:`get_order_book`: scalar, iterable, or ``None``
    for all instruments. No per-symbol request is performed.
    """
    from .market_data import _resolve_live_selection, market_watch

    side = _validate_queue_side(side)
    if not isinstance(selector_strict, bool):
        raise InvalidParameterError("selector_strict must be bool")
    snapshot = market_watch()
    stocks = snapshot.get("stocks", pd.DataFrame())
    selected, missing = _resolve_live_selection(
        stocks, symbol, snapshot, strict=selector_strict
    )
    unique_selected = (
        selected.drop_duplicates("InsCode")
        if "InsCode" in selected.columns
        else selected.iloc[0:0]
    )
    identities = [_identity_from_row(row) for _, row in unique_selected.iterrows()]
    books = _live_rows(snapshot, identities, "both", include_empty=True)
    thresholds = {}
    if not books.empty:
        for _, row in unique_selected.iterrows():
            identity = _identity_from_row(row)
            deven = int(snapshot["trade_date"].strftime("%Y%m%d"))
            thresholds[(identity["InsCode"], deven)] = _cast_frame(
                pd.DataFrame(
                    [
                        {
                            "DEven": deven,
                            "hEven": 0,
                            "UpperLimit": row.get("MaxAllowed", pd.NA),
                            "LowerLimit": row.get("MinAllowed", pd.NA),
                            "ThresholdSource": "market_watch_price_limits",
                        }
                    ]
                ),
                [
                    "DEven",
                    "hEven",
                    "UpperLimit",
                    "LowerLimit",
                    "ThresholdSource",
                ],
            )
    result = _derive_queue_rows(books, thresholds, side, strict)
    attrs = {
        "migration": copy.deepcopy(snapshot.get("migration", {})),
        "trade_date": snapshot.get("trade_date"),
        "exchange_time": snapshot.get("exchange_time"),
        "is_realtime_fresh": snapshot.get("is_realtime_fresh", False),
        "request_count": 1,
        "queue_mode": "live_bulk_market_watch",
        "missing_selectors": list(missing),
    }
    return _finalize_queue(result, attrs, [], strict, True, filename="queue-live.csv")


# Common spelling used by market-data libraries; this is additive, not a
# deprecation shim, so it intentionally emits no warning.
get_orderbook_history = get_order_book_history


__all__ = [
    "get_order_book_history",
    "get_orderbook_history",
    "get_queue",
    "get_queue_history",
]
