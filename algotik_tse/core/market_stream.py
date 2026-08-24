"""Stateful live feed, market events, breadth and sector-flow analytics.

The parsers in this module are deliberately network-free.  TSETMC's
``MarketWatchPlus`` response is a patch stream, not a snapshot: an omitted
field/row means unchanged while an explicit zero overwrites the old value.
``MarketWatcher`` validates a complete patch and commits it atomically.
"""

from __future__ import annotations

import copy
import datetime as _dt
import math
import random
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional

import numpy as np
import pandas as pd
import requests

from ..exceptions import (
    AmbiguousSymbolError,
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
    StockNotFoundError,
)
from ..http_client import safe_get
from ..settings import settings
from .market_data import (
    CLIENT_COLUMNS,
    ORDER_COLUMNS,
    STOCK_COLUMNS,
    _enrich_live_market,
    _instrument_mask,
    _normalise_symbol,
    _parse_market_timestamp,
    _parse_market_watch_response,
    _safe_float,
    _safe_int,
    market_client_type,
    market_watch,
)

FAST_VIEW_COLUMNS = [
    "timestamp",
    "tse_status",
    "index",
    "index_change_rendered",
    "market_value",
    "tse_volume",
    "tse_value",
    "tse_trade_count",
    "farabourse_status",
    "farabourse_volume",
    "farabourse_value",
    "farabourse_trade_count",
    "derivatives_status",
    "derivatives_volume",
    "derivatives_value",
    "derivatives_trade_count",
]
EQUITY_INSTRUMENT_TYPES = frozenset({300, 303, 309})
BASE_MARKET_INSTRUMENT_TYPE = 309
MAX_NOTIFICATION_TOP = 1000
MAX_SYMBOL_CACHE = 1024
MESSAGE_COLUMNS = [
    "message_id",
    "date",
    "time",
    "timestamp",
    "title",
    "description",
    "flow",
]
STATE_COLUMNS = [
    "event_id",
    "date",
    "time",
    "timestamp",
    "InsCode",
    "Symbol",
    "Name",
    "state_code",
    "state",
    "real_time",
    "under_supervision",
    "state_title",
]
SECTOR_FLOW_COLUMNS = [
    "SectorCode",
    "instrument_count",
    "advances",
    "declines",
    "unchanged",
    "no_trade",
    "missing_previous",
    "missing",
    "missing_previous_close",
    "missing_current_price",
    "advance_decline_difference",
    "advance_decline_ratio",
    "ad_difference",
    "ad_ratio",
    "advance_pct",
    "decline_pct",
    "advances_pct",
    "declines_pct",
    "total_volume",
    "total_value",
    "upper_limit_count",
    "lower_limit_count",
    "client_covered_count",
    "client_coverage",
    "net_individual_volume",
    "estimated_net_individual_value",
    "value_available",
    "value_method",
    "trade_date",
    "exchange_time",
    "fetched_at",
    "is_realtime_fresh",
    "is_stale",
]

BREADTH_COLUMNS = [
    "instrument_count",
    "advances",
    "declines",
    "unchanged",
    "no_trade",
    "missing_previous",
    "missing",
    "missing_previous_close",
    "missing_current_price",
    "advance_decline_difference",
    "advance_decline_ratio",
    "ad_difference",
    "ad_ratio",
    "advance_pct",
    "decline_pct",
    "advances_pct",
    "declines_pct",
    "total_volume",
    "total_value",
    "upper_limit_count",
    "lower_limit_count",
    "trade_date",
    "exchange_time",
    "fetched_at",
    "is_realtime_fresh",
]
MARKET_OVERVIEW_COLUMNS = ["flow"]

INSTRUMENT_STATE_LABELS = {
    "I": "invalid",
    "A": "allowed",
    "AG": "allowed_frozen",
    "AS": "allowed_suspended",
    "AR": "allowed_reserved",
    "IG": "invalid_frozen",
    "IS": "invalid_suspended",
    "IR": "invalid_reserved",
}


class _NeedResync(DataParsingError):
    """A valid continuation cannot be proven; fetch Init again."""


class _StorageError(DataParsingError):
    """Explicit local persistence failed; never enter transport retry."""


def _tehran_timestamp(value) -> pd.Timestamp:
    stamp = value if isinstance(value, pd.Timestamp) else pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("Asia/Tehran")
    return stamp.tz_convert("Asia/Tehran")


def _validate_top(top, name="top") -> int:
    try:
        value = int(top)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(f"{name} must be an integer") from exc
    if value < 1 or value > MAX_NOTIFICATION_TOP:
        raise InvalidParameterError(
            f"{name} must be between 1 and {MAX_NOTIFICATION_TOP}"
        )
    return value


def _typed_empty(columns, dtypes=None):
    dtypes = dtypes or {}
    return pd.DataFrame(
        {column: pd.Series(dtype=dtypes.get(column, "object")) for column in columns}
    )


def _present_identity_value(value) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        return False
    return str(value).strip() not in {"", "None", "nan", "<NA>", "NaT"}


def _stable_notification_identity(name, row):
    """Return a cross-batch stable identity, or ``None`` when unknowable.

    Returning ``None`` is intentional: unidentified provider rows must remain
    deliverable and may never be collapsed merely because their IDs are null.
    """
    primary = {
        "messages": "message_id",
        "state_changes": "event_id",
    }[name]
    value = row.get(primary)
    if _present_identity_value(value):
        return f"{primary}:{value}"
    if name == "messages":
        timestamp, title, description, flow = (
            row.get("timestamp"),
            row.get("title"),
            row.get("description"),
            row.get("flow"),
        )
        if _present_identity_value(timestamp) and (
            _present_identity_value(title) or _present_identity_value(description)
        ):
            return f"message:{timestamp!r}:{title!r}:{description!r}:{flow!r}"
        return None
    timestamp, inscode, state_code = (
        row.get("timestamp"),
        row.get("InsCode"),
        row.get("state_code"),
    )
    if all(
        _present_identity_value(value) for value in (timestamp, inscode, state_code)
    ):
        return f"state:{timestamp!r}:{inscode!r}:{state_code!r}"
    return None


def _dedupe_stable_rows(frame, name):
    """Dedupe only rows for which a stable identity is actually available."""
    if frame.empty:
        return frame
    identities = frame.apply(
        lambda row: _stable_notification_identity(name, row), axis=1
    )
    duplicates = identities.notna() & identities.duplicated(keep="last")
    return frame.loc[~duplicates].reset_index(drop=True)


def _response_text(url: str, request: Callable = safe_get) -> str:
    response = request(url)
    if response is None:
        raise ConnectionError(f"No response from {url}")
    status = getattr(response, "status_code", 200)
    if not 200 <= int(status) < 300:
        raise ConnectionError(f"HTTP {status} from {url}")
    text = getattr(response, "text", "") or ""
    lowered = text.lstrip().lower()
    if (
        not text.strip()
        or lowered.startswith("<!doctype html")
        or lowered.startswith("<html")
    ):
        raise DataParsingError(f"Unexpected non-data response from {url}")
    return text


def _response_json(url: str, request: Callable = safe_get) -> Mapping[str, Any]:
    response = request(url)
    if response is None:
        raise ConnectionError(f"No response from {url}")
    status = getattr(response, "status_code", 200)
    if not 200 <= int(status) < 300:
        raise ConnectionError(f"HTTP {status} from {url}")
    try:
        payload = response.json()
    except Exception as exc:
        raise DataParsingError(f"Invalid JSON from {url}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise DataParsingError(f"Expected a JSON object from {url}")
    return payload


def _wire_sections(text: str) -> tuple[str, str, str, str, str]:
    parts = (text or "").strip().split("@")
    if len(parts) != 5:
        raise DataParsingError(
            f"MarketWatch response must have 5 sections, got {len(parts)}"
        )
    return tuple(parts)  # type: ignore[return-value]


def _notification_tokens(value: str) -> tuple[str, str, str]:
    tokens = tuple(item.strip() for item in value.split(","))
    if len(tokens) != 3:
        raise DataParsingError("notification section must contain 3 tokens")
    return tokens  # type: ignore[return-value]


def _parse_fast_view(value: str) -> dict[str, Any]:
    # Some older Init responses contain only timestamp/state/index.  Preserve
    # that compatible subset, while parsing the documented 16-field view when
    # present.  Any other length is a schema failure.
    fields = [
        item.strip() for item in value.replace("\r", "").replace("\n", ",").split(",")
    ]
    if len(fields) not in (3, 16):
        raise DataParsingError(f"fast-view section has {len(fields)} fields")
    fields += [""] * (16 - len(fields))
    result = dict(zip(FAST_VIEW_COLUMNS, fields))
    result["exchange_time"] = _parse_market_timestamp(result["timestamp"])
    if result["exchange_time"] is None:
        raise DataParsingError("fast-view timestamp is missing or invalid")
    # Only GroupState S is documented as open. Other values remain explicit,
    # never fabricated into undocumented open/closed mappings.
    result["is_open"] = True if result["tse_status"] == "S" else pd.NA
    for name in (
        "index",
        "market_value",
        "tse_volume",
        "tse_value",
        "tse_trade_count",
        "farabourse_volume",
        "farabourse_value",
        "farabourse_trade_count",
        "derivatives_volume",
        "derivatives_value",
        "derivatives_trade_count",
    ):
        result[name] = _safe_float(result[name], np.nan)
    return result


def _parse_refid(value: str) -> int:
    value = value.strip()
    if not value or not value.isdigit():
        raise DataParsingError("invalid MarketWatch refID")
    return int(value)


def _valid_heven(value: int) -> bool:
    return 0 <= value <= 235959 and (value % 100) < 60 and ((value % 10000) // 100) < 60


def _parse_order_patch(value: str) -> list[dict[str, int | str]]:
    output = []
    if not value.strip():
        return output
    for raw in value.split(";"):
        fields = raw.split(",")
        if len(fields) != 8:
            raise DataParsingError("order-book patch row must have 8 fields")
        if not fields[0].strip().isdigit() or not fields[1].strip().isdigit():
            raise DataParsingError("invalid order-book instrument/depth")
        level = int(fields[1])
        if not 1 <= level <= 5:
            raise DataParsingError("order-book depth must be between 1 and 5")
        try:
            numbers = [int(float(item)) for item in fields[2:]]
        except (TypeError, ValueError) as exc:
            raise DataParsingError("non-numeric order-book patch") from exc
        output.append(dict(zip(ORDER_COLUMNS, [fields[0].strip(), level] + numbers)))
    return output


def _parse_price_patch(value: str) -> list[dict[str, Any]]:
    output = []
    if not value.strip():
        return output
    for raw in value.split(";"):
        fields = raw.split(",")
        if len(fields) not in (10, 26):
            raise DataParsingError(
                f"price patch row must have 10 or 26 fields, got {len(fields)}"
            )
        if not fields[0].strip().isdigit():
            raise DataParsingError("price patch lacks InsCode")
        if len(fields) == 10:
            try:
                values = [int(float(item)) for item in fields[1:]]
            except (TypeError, ValueError) as exc:
                raise DataParsingError("non-numeric price update") from exc
            if not _valid_heven(values[0]):
                raise DataParsingError("invalid hEven in price update")
            output.append(
                {
                    "kind": "update",
                    "InsCode": fields[0].strip(),
                    "hEven": values[0],
                    "FirstPrice": values[1],
                    "Close": values[2],
                    "Last": values[3],
                    "TradeCount": values[4],
                    "Volume": values[5],
                    "Value": values[6],
                    "Low": values[7],
                    "High": values[8],
                }
            )
        else:
            try:
                for index in list(range(4, 18)) + list(range(19, 25)):
                    # Provider permits blank nullable numeric metadata but a
                    # present numeric wire field may never be silently coerced.
                    if fields[index].strip():
                        numeric = float(fields[index])
                        if not math.isfinite(numeric):
                            raise ValueError
            except (TypeError, ValueError) as exc:
                raise DataParsingError("non-numeric full price row") from exc
            full_heven = int(float(fields[4]))
            if not _valid_heven(full_heven):
                raise DataParsingError("invalid hEven in full price row")
            # Reuse the canonical Init parser to keep legacy/canonical field
            # semantics exactly aligned with market_watch().
            parsed = _parse_market_watch_response(
                "0,0,0@00/01/01 00:00:00,@" + raw + "@@0"
            )["stocks"]
            if len(parsed) != 1:
                raise DataParsingError("invalid full price row")
            output.append(
                {
                    "kind": "full",
                    "InsCode": fields[0].strip(),
                    "hEven": full_heven,
                    "row": parsed.iloc[0].to_dict(),
                }
            )
    return output


def _snapshot_copy(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in snapshot.items():
        result[key] = (
            value.copy(deep=True)
            if isinstance(value, pd.DataFrame)
            else copy.deepcopy(value)
        )
    return result


def _apply_plus_patch(
    snapshot: Mapping[str, Any],
    text: str,
    current_refid: int,
    current_heven: int,
    fetched_at=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate and atomically apply one Plus response to a copied state."""
    token_raw, fast_raw, price_raw, order_raw, ref_raw = _wire_sections(text)
    tokens = _notification_tokens(token_raw)
    fast = _parse_fast_view(fast_raw)
    price_rows = _parse_price_patch(price_raw)
    order_rows = _parse_order_patch(order_raw)
    new_ref = _parse_refid(ref_raw)
    if new_ref and new_ref <= current_refid:
        raise _NeedResync("MarketWatch cursor regressed")

    old_trade_date = snapshot.get("trade_date")
    old_exchange_time = snapshot.get("exchange_time")
    exchange_time = fast.get("exchange_time")
    new_trade_date = (
        exchange_time.date() if exchange_time is not None else old_trade_date
    )
    if (
        old_trade_date is not None
        and new_trade_date is not None
        and new_trade_date != old_trade_date
    ):
        raise _NeedResync("MarketWatch trade date rolled over")
    skew = abs(float(getattr(settings, "market_clock_skew_tolerance_seconds", 5.0)))
    if (
        exchange_time is not None
        and old_exchange_time is not None
        and new_trade_date == old_trade_date
        and (exchange_time - old_exchange_time).total_seconds() < -skew
    ):
        raise _NeedResync("MarketWatch fast-view time regressed")

    candidate = _snapshot_copy(snapshot)
    stocks = candidate.get("stocks", pd.DataFrame())
    orders = candidate.get("order_book", pd.DataFrame())
    changed_inscodes: set[str] = set()
    changed_levels: set[tuple[str, int]] = set()
    next_heven = current_heven

    price_inscodes = [str(item["InsCode"]) for item in price_rows]
    if len(price_inscodes) != len(set(price_inscodes)):
        raise DataParsingError("duplicate instrument in one price patch")
    full_rows = []
    full_inscodes = set()
    for patch in price_rows:
        inscode, heven = str(patch["InsCode"]), int(patch["hEven"])
        if heven < current_heven:
            raise _NeedResync("out-of-order MarketWatch hEven")
        mask = (
            stocks["InsCode"].astype(str).eq(inscode)
            if not stocks.empty
            else pd.Series(dtype=bool)
        )
        if patch["kind"] == "update":
            if not mask.any():
                raise _NeedResync("update references unknown instrument")
            if mask.sum() != 1:
                raise _NeedResync("duplicate instrument in watcher state")
            idx = stocks.index[mask][0]
            for column in (
                "FirstPrice",
                "Close",
                "Last",
                "TradeCount",
                "Volume",
                "Value",
                "Low",
                "High",
            ):
                stocks.at[idx, column] = patch[column]
            stocks.at[idx, "Open"] = patch["FirstPrice"]
            stocks.at[idx, "Yesterday"] = patch["FirstPrice"]
            stocks.at[idx, "LegacyYesterday"] = patch["FirstPrice"]
            stocks.at[idx, "Time"] = (
                f"{heven // 10000:02d}:{(heven % 10000) // 100:02d}:{heven % 100:02d}"
            )
            stocks.at[idx, "Change"] = (
                stocks.at[idx, "Close"] - stocks.at[idx, "Yesterday"]
            )
            stocks.at[idx, "ChangePct"] = (
                stocks.at[idx, "Change"] / stocks.at[idx, "Yesterday"] * 100
                if stocks.at[idx, "Yesterday"]
                else np.nan
            )
            stocks.at[idx, "PreviousCloseChange"] = (
                stocks.at[idx, "Close"] - stocks.at[idx, "PreviousClose"]
            )
            stocks.at[idx, "PreviousCloseChangePct"] = (
                stocks.at[idx, "PreviousCloseChange"]
                / stocks.at[idx, "PreviousClose"]
                * 100
                if stocks.at[idx, "PreviousClose"]
                else np.nan
            )
        else:
            full_rows.append(patch["row"])
            full_inscodes.add(inscode)
        changed_inscodes.add(inscode)
        next_heven = max(next_heven, heven)

    if full_rows:
        replacement = pd.DataFrame(full_rows).reindex(columns=STOCK_COLUMNS)
        if stocks.empty:
            stocks = replacement
        else:
            stocks = pd.concat(
                [
                    stocks.loc[~stocks["InsCode"].astype(str).isin(full_inscodes)],
                    replacement,
                ],
                ignore_index=True,
            )

    if order_rows:
        patch_orders = pd.DataFrame(order_rows).reindex(columns=ORDER_COLUMNS)
        patch_keys = pd.MultiIndex.from_frame(
            patch_orders[["InsCode", "Level"]].astype({"InsCode": str, "Level": int})
        )
        if patch_keys.duplicated().any():
            raise DataParsingError("duplicate order level in one Plus payload")
    for row in order_rows:
        inscode, level = str(row["InsCode"]), int(row["Level"])
        if stocks.empty or not stocks["InsCode"].astype(str).eq(inscode).any():
            raise _NeedResync("order patch references unknown instrument")
        changed_levels.add((inscode, level))
    if order_rows:
        if orders.empty:
            orders = patch_orders
        else:
            existing_keys = pd.MultiIndex.from_arrays(
                [
                    orders["InsCode"].astype(str),
                    pd.to_numeric(orders["Level"], errors="raise").astype(int),
                ]
            )
            orders = pd.concat(
                [orders.loc[~existing_keys.isin(patch_keys)], patch_orders],
                ignore_index=True,
            )

    candidate["stocks"] = stocks.reindex(columns=STOCK_COLUMNS).reset_index(drop=True)
    candidate["order_book"] = (
        orders.reindex(columns=ORDER_COLUMNS)
        .sort_values(["InsCode", "Level"], kind="mergesort")
        .reset_index(drop=True)
    )
    candidate["notification_tokens"] = tokens
    candidate["fast_view"] = fast
    candidate["market_time"] = fast.get("timestamp", candidate.get("market_time", ""))
    candidate["index_value"] = fast.get("index", candidate.get("index_value", np.nan))
    candidate["market_state"] = fast.get(
        "tse_status", candidate.get("market_state", "")
    )
    candidate["exchange_time"] = exchange_time or candidate.get("exchange_time")
    candidate["trade_date"] = new_trade_date
    now = _tehran_timestamp(
        fetched_at if fetched_at is not None else pd.Timestamp.now(tz="Asia/Tehran")
    )
    candidate["fetched_at"] = now
    effective_exchange = candidate.get("exchange_time")
    age = (
        (now - effective_exchange).total_seconds()
        if effective_exchange is not None
        else np.nan
    )
    same_date = new_trade_date is not None and new_trade_date == now.date()
    threshold = float(getattr(settings, "market_snapshot_freshness_seconds", 120.0))
    fresh = bool(same_date and np.isfinite(age) and -skew <= age <= threshold + skew)
    candidate.update(
        {
            "snapshot_age_seconds": age,
            "is_today_trade_date": bool(same_date),
            "is_previous_trade_date": bool(
                new_trade_date is not None and not same_date
            ),
            "is_history_eligible": bool(same_date and not stocks.empty),
            "is_realtime_fresh": fresh,
            "is_stale": not fresh,
            "is_partial": pd.NA,
        }
    )
    effective_ref = new_ref if new_ref else current_refid
    return candidate, {
        "changed_inscodes": tuple(sorted(changed_inscodes)),
        "changed_order_levels": tuple(sorted(changed_levels)),
        "cursor_after": effective_ref,
        "heven_after": next_heven,
        "tokens": tokens,
    }


def _initial_state(text: str, fetched_at=None) -> tuple[dict[str, Any], int, int]:
    tokens_raw, fast_raw, prices_raw, orders_raw, ref_raw = _wire_sections(text)
    tokens = _notification_tokens(tokens_raw)
    fast = _parse_fast_view(fast_raw)
    refid = _parse_refid(ref_raw)
    initial_prices = _parse_price_patch(prices_raw)
    if any(item["kind"] != "full" for item in initial_prices):
        raise DataParsingError("MarketWatchInit may contain only 26-field rows")
    _parse_order_patch(orders_raw)
    snapshot = _parse_market_watch_response(
        text,
        fetched_at=_tehran_timestamp(
            fetched_at if fetched_at is not None else pd.Timestamp.now(tz="Asia/Tehran")
        ),
    )
    snapshot["notification_tokens"] = tokens
    snapshot["fast_view"] = fast
    heven = 0
    if not snapshot["stocks"].empty:
        values = (
            snapshot["stocks"]["Time"].astype(str).str.replace(":", "", regex=False)
        )
        heven = int(pd.to_numeric(values, errors="coerce").max() or 0)
    return snapshot, refid, heven


@dataclass
class MarketEvent:
    """One emitted watcher event.

    Frames and ``snapshot`` are defensive copies by default and are therefore
    safe for a consumer to mutate.  They are intentionally not immutable.
    """

    kind: str
    sequence: int
    fetched_at: pd.Timestamp
    trade_date: Optional[_dt.date]
    snapshot: dict[str, Any]
    changed_inscodes: tuple[str, ...] = ()
    changed_order_levels: tuple[tuple[str, int], ...] = ()
    market_state_changed: bool = False
    notification_tokens: tuple[str, str, str] = ("", "", "")
    messages: Optional[pd.DataFrame] = None
    state_changes: Optional[pd.DataFrame] = None
    cursor_before: int = 0
    cursor_after: int = 0
    retry_count: int = 0
    retry_error: Optional[str] = None
    notification_errors: tuple[str, ...] = ()
    persistence_status: Optional[str] = None
    persistence_error: Optional[str] = None

    def copy(self):
        """Return a deep, consumer-mutable copy of this event."""
        return replace(
            self,
            snapshot=_snapshot_copy(self.snapshot),
            messages=None if self.messages is None else self.messages.copy(deep=True),
            state_changes=(
                None
                if self.state_changes is None
                else self.state_changes.copy(deep=True)
            ),
        )


class MarketWatcher(Iterator[MarketEvent]):
    """Synchronous, stateful and stoppable MarketWatch iterator.

    ``initial`` is the mandatory full Init state, ``delta`` contains a scoped
    symbol/market/notification change, ``heartbeat`` contains no relevant
    change, and ``resync`` is a new full state after cursor/schema/time
    continuity could not be proven. Market state is committed before optional
    notification I/O; notification failures are reported on the event and are
    retried on later ticks without rolling market state back.
    """

    def __init__(
        self,
        symbol=None,
        interval=1.0,
        max_updates=None,
        include_initial=True,
        emit_heartbeats=True,
        notifications=("messages", "state"),
        notification_top=50,
        stop_event=None,
        error_policy="retry",
        max_backoff=30.0,
        jitter=0.1,
        callback_error_policy="raise",
        max_consecutive_retries=5,
        max_retries=None,
        max_seen_notifications=10000,
        copy_snapshot=True,
        request_timeout=None,
        *,
        record_to=None,
        record_heartbeats=False,
        checkpoint_interval=100,
        record_max_records=10000,
        record_retention_seconds=None,
        storage_error_policy="raise",
        _request=safe_get,
        _clock=None,
        _wait=None,
        _random=None,
    ):
        if error_policy not in {"retry", "raise", "stop"}:
            raise InvalidParameterError("error_policy must be retry, raise, or stop")
        if callback_error_policy not in {"raise", "ignore", "stop"}:
            raise InvalidParameterError("invalid callback_error_policy")
        if storage_error_policy not in {"raise", "ignore"}:
            raise InvalidParameterError("storage_error_policy must be raise or ignore")
        try:
            interval_value = float(interval)
            backoff_value = float(max_backoff)
            jitter_value = float(jitter)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError(
                "interval/backoff/jitter must be numeric"
            ) from exc
        if not math.isfinite(interval_value) or interval_value < 0:
            raise InvalidParameterError("interval must be finite and non-negative")
        if not math.isfinite(backoff_value) or backoff_value < 0:
            raise InvalidParameterError("max_backoff must be finite and non-negative")
        if not math.isfinite(jitter_value) or not 0 <= jitter_value <= 1:
            raise InvalidParameterError("jitter must be finite and between 0 and 1")
        retry_limit = max_consecutive_retries if max_retries is None else max_retries
        try:
            retry_limit = int(retry_limit)
            max_seen_notifications = int(max_seen_notifications)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("retry/dedupe limits must be integers") from exc
        if retry_limit < 0:
            raise InvalidParameterError("max_consecutive_retries must be non-negative")
        if max_seen_notifications < 1:
            raise InvalidParameterError("max_seen_notifications must be positive")
        try:
            checkpoint_interval = int(checkpoint_interval)
            record_max_records = int(record_max_records)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("record limits must be integers") from exc
        if checkpoint_interval < 1:
            raise InvalidParameterError("checkpoint_interval must be positive")
        if record_max_records < 1 or record_max_records > 10_000:
            raise InvalidParameterError(
                "record_max_records must be between 1 and 10000"
            )
        if record_retention_seconds is not None:
            try:
                record_retention_seconds = float(record_retention_seconds)
            except (TypeError, ValueError) as exc:
                raise InvalidParameterError(
                    "record_retention_seconds must be numeric"
                ) from exc
            if (
                not math.isfinite(record_retention_seconds)
                or record_retention_seconds <= 0
            ):
                raise InvalidParameterError(
                    "record_retention_seconds must be finite and positive"
                )
        if request_timeout is not None:
            try:
                request_timeout = float(request_timeout)
            except (TypeError, ValueError) as exc:
                raise InvalidParameterError("request_timeout must be numeric") from exc
            if not math.isfinite(request_timeout) or request_timeout <= 0:
                raise InvalidParameterError(
                    "request_timeout must be finite and positive"
                )
        self.symbol, self.interval = symbol, interval_value
        self.max_updates = None if max_updates is None else max(0, int(max_updates))
        self.include_initial, self.emit_heartbeats = bool(include_initial), bool(
            emit_heartbeats
        )
        self.notifications = tuple(notifications or ())
        unknown = set(self.notifications) - {"messages", "state"}
        if unknown:
            raise InvalidParameterError(f"unknown notifications: {sorted(unknown)}")
        self.notification_top = _validate_top(notification_top, "notification_top")
        self.error_policy, self.max_backoff, self.jitter = (
            error_policy,
            backoff_value,
            jitter_value,
        )
        self.max_consecutive_retries = retry_limit
        self.max_seen_notifications = max_seen_notifications
        self.copy_snapshot = bool(copy_snapshot)
        self.request_timeout = request_timeout
        self.record_to = record_to
        self.record_heartbeats = bool(record_heartbeats)
        self.checkpoint_interval = checkpoint_interval
        self.record_max_records = record_max_records
        self.record_retention_seconds = record_retention_seconds
        self.storage_error_policy = storage_error_policy
        self.session_id = str(uuid.uuid4())
        self.callback_error_policy = callback_error_policy
        self.stop_event = stop_event or threading.Event()
        self._request, self._clock = _request, (
            _clock or (lambda: pd.Timestamp.now(tz="Asia/Tehran"))
        )
        self._wait = _wait or (lambda delay: self.stop_event.wait(delay))
        self._random = _random or random.random
        self._snapshot = None
        self._refid = self._heven = self._sequence = self._emitted = (
            self._retry_count
        ) = 0
        self._resync_count = 0
        self._persisted_count = 0
        self._persisted_since_checkpoint = 0
        self._force_next_checkpoint = False
        self._initialized = self._closed = False
        self._pending_resync = False
        self._resync_reason = None
        self._last_retry_error = None
        self._notification_pending = set()
        self._seen_notifications = {
            "messages": OrderedDict(),
            "state_changes": OrderedDict(),
        }

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()

    def __iter__(self):
        return self

    def stop(self):
        self._closed = True
        self.stop_event.set()

    def _sleep(self, delay):
        return bool(self._wait(max(0.0, delay)))

    def _stopped(self):
        return self._closed or self.stop_event.is_set()

    def _now(self):
        return _tehran_timestamp(self._clock())

    def _transport(self, url):
        if self.request_timeout is None:
            return self._request(url)
        return self._request(url, timeout=self.request_timeout)

    def _fetch_init(self):
        return _response_text(settings.url_market_watch_init, self._transport)

    def _fetch_plus(self):
        h = 5 * (self._heven // 5)
        r = 25 * (self._refid // 25)
        url = settings.url_market_watch_plus.format(h, r)
        return _response_text(url, self._transport)

    def _filter_snapshot(self, snapshot):
        result = _snapshot_copy(snapshot) if self.copy_snapshot else snapshot
        stocks = result.get("stocks", pd.DataFrame())
        if self.symbol is not None and not stocks.empty:
            # Filtering necessarily creates a new scoped view even when the
            # caller explicitly opted out of the full defensive copy.
            if result is snapshot:
                result = dict(snapshot)
            chosen = stocks.loc[_instrument_mask(stocks, self.symbol)].copy()
            selected = set(chosen["InsCode"].astype(str))
            result["stocks"] = chosen.reset_index(drop=True)
            result["order_book"] = (
                result.get("order_book", pd.DataFrame())
                .loc[lambda x: x["InsCode"].astype(str).isin(selected)]
                .reset_index(drop=True)
            )
        return result

    def _selected_inscodes(self, snapshot):
        stocks = snapshot.get("stocks", pd.DataFrame())
        if stocks.empty or "InsCode" not in stocks:
            return set()
        if self.symbol is None:
            return set(stocks["InsCode"].astype(str))
        return set(
            stocks.loc[_instrument_mask(stocks, self.symbol), "InsCode"].astype(str)
        )

    def _dedupe_notifications(self, name, frame):
        if frame is None or frame.empty:
            return frame
        identities = frame.apply(
            lambda row: _stable_notification_identity(name, row), axis=1
        )
        seen = self._seen_notifications[name]
        # Unidentified rows are intentionally always delivered and never
        # placed in the cross-batch LRU.
        keep = identities.isna() | ~identities.isin(seen)
        for identity in identities.loc[keep & identities.notna()]:
            seen[identity] = None
            seen.move_to_end(identity)
            while len(seen) > self.max_seen_notifications:
                seen.popitem(last=False)
        return frame.loc[keep].reset_index(drop=True)

    def _notifications(self, old, new):
        data = {"messages": None, "state_changes": None}
        errors = []
        if old is None:
            return data, errors
        token_names = {
            "messages": ("messages", 0),
            "state_changes": ("state", 1),
        }
        fetchers = {
            "messages": lambda: get_market_messages(
                top=self.notification_top, _request=self._transport
            ),
            "state_changes": lambda: get_instrument_state_changes(
                top=self.notification_top, _request=self._transport
            ),
        }
        for name, (public_name, index) in token_names.items():
            if public_name not in self.notifications:
                continue
            if old[index] != new[index]:
                self._notification_pending.add(name)
            if name not in self._notification_pending:
                continue
            try:
                data[name] = self._dedupe_notifications(name, fetchers[name]())
                self._notification_pending.discard(name)
            except Exception as exc:
                # This is deliberately best effort and happens only after the
                # market candidate/cursor have committed. Pending delivery is
                # retained for the next tick and the failure is observable.
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
        return data, errors

    def _event(self, kind, before, after, fetched_at, info=None, retry_count=0):
        info = info or {}
        next_sequence = self._sequence + 1
        old_state = before.get("market_state") if before else None
        new_state = after.get("market_state")
        event = MarketEvent(
            kind=kind,
            sequence=next_sequence,
            fetched_at=fetched_at,
            trade_date=after.get("trade_date"),
            snapshot=self._filter_snapshot(after),
            changed_inscodes=info.get("changed_inscodes", ()),
            changed_order_levels=info.get("changed_order_levels", ()),
            market_state_changed=before is not None and old_state != new_state,
            notification_tokens=tuple(after.get("notification_tokens", ("", "", ""))),
            messages=info.get("messages"),
            state_changes=info.get("state_changes"),
            cursor_before=info.get("cursor_before", self._refid),
            cursor_after=info.get("cursor_after", self._refid),
            retry_count=retry_count,
            retry_error=info.get("retry_error"),
            notification_errors=tuple(info.get("notification_errors", ())),
        )
        should_record = self.record_to is not None and (
            kind != "heartbeat" or self.record_heartbeats
        )
        if should_record:
            # Local import avoids making the persistence module a mandatory
            # dependency for users of the in-memory watcher.
            from .market_history import record_market_event

            checkpoint = (
                self._persisted_count == 0
                or self._force_next_checkpoint
                or kind in {"initial", "resync"}
                or self._persisted_since_checkpoint >= self.checkpoint_interval - 1
            )
            try:
                record_market_event(
                    self.record_to,
                    event,
                    session_id=self.session_id,
                    include_snapshot=checkpoint,
                    max_records=self.record_max_records,
                    retention_seconds=self.record_retention_seconds,
                )
                event.persistence_status = "persisted"
                if checkpoint:
                    self._persisted_since_checkpoint = 0
                    self._force_next_checkpoint = False
                else:
                    self._persisted_since_checkpoint += 1
                self._persisted_count += 1
            except Exception as exc:
                if self.storage_error_policy == "raise":
                    state = info.get("_watcher_state_before")
                    if state is not None:
                        (
                            self._snapshot,
                            self._refid,
                            self._heven,
                            self._initialized,
                            self._pending_resync,
                            self._resync_reason,
                            self._last_retry_error,
                            self._retry_count,
                            self._resync_count,
                            self._notification_pending,
                            self._seen_notifications,
                        ) = state
                    raise _StorageError(
                        f"market event persistence failed: {exc}"
                    ) from exc
                event.persistence_status = "failed_ignored"
                event.persistence_error = f"{type(exc).__name__}: {exc}"
                self._force_next_checkpoint = True
        self._sequence = next_sequence
        self._emitted += 1
        if kind in {"initial", "resync"}:
            self._resync_count = 0
        return event

    def __next__(self):
        if self._stopped() or (
            self.max_updates is not None and self._emitted >= self.max_updates
        ):
            raise StopIteration
        while True:
            try:
                if not self._initialized or self._pending_resync:
                    watcher_state_before = (
                        self._snapshot,
                        self._refid,
                        self._heven,
                        self._initialized,
                        self._pending_resync,
                        self._resync_reason,
                        self._last_retry_error,
                        self._retry_count,
                        self._resync_count,
                        copy.deepcopy(self._notification_pending),
                        copy.deepcopy(self._seen_notifications),
                    )
                    before = self._snapshot
                    previous_ref = self._refid
                    text = self._fetch_init()
                    fetched_at = self._now()
                    if self._stopped():
                        raise StopIteration
                    snapshot, refid, heven = _initial_state(text, fetched_at=fetched_at)
                    if self._stopped():
                        raise StopIteration
                    old_tokens = (
                        tuple(before.get("notification_tokens", ("", "", "")))
                        if before is not None
                        else None
                    )
                    self._snapshot, self._refid, self._heven = snapshot, refid, heven
                    kind = "resync" if self._initialized else "initial"
                    self._initialized, self._pending_resync = True, False
                    notify, notification_errors = self._notifications(
                        old_tokens,
                        tuple(snapshot.get("notification_tokens", ("", "", ""))),
                    )
                    if self._stopped():
                        raise StopIteration
                    retry = self._retry_count
                    self._retry_count = 0
                    info = {
                        "cursor_before": 0 if before is None else previous_ref,
                        "cursor_after": refid,
                        "retry_error": self._resync_reason or self._last_retry_error,
                        "notification_errors": notification_errors,
                        "_watcher_state_before": watcher_state_before,
                        **notify,
                    }
                    self._resync_reason = self._last_retry_error = None
                    if kind == "initial" and not self.include_initial:
                        continue
                    return self._event(kind, before, snapshot, fetched_at, info, retry)

                if self._sleep(self.interval):
                    raise StopIteration
                if self._stopped():
                    raise StopIteration
                before_ref, before = self._refid, self._snapshot
                watcher_state_before = (
                    self._snapshot,
                    self._refid,
                    self._heven,
                    self._initialized,
                    self._pending_resync,
                    self._resync_reason,
                    self._last_retry_error,
                    self._retry_count,
                    self._resync_count,
                    copy.deepcopy(self._notification_pending),
                    copy.deepcopy(self._seen_notifications),
                )
                text = self._fetch_plus()
                fetched_at = self._now()
                if self._stopped():
                    raise StopIteration
                try:
                    candidate, info = _apply_plus_patch(
                        before,
                        text,
                        self._refid,
                        self._heven,
                        fetched_at=fetched_at,
                    )
                except (DataParsingError, _NeedResync) as exc:
                    self._resync_count += 1
                    if self._resync_count > self.max_consecutive_retries:
                        raise DataParsingError(
                            "maximum consecutive market resyncs exceeded"
                        ) from exc
                    self._pending_resync = True
                    self._resync_reason = f"{type(exc).__name__}: {exc}"
                    continue
                if self._stopped():
                    raise StopIteration
                old_tokens = tuple(before.get("notification_tokens", ("", "", "")))
                # Commit the fully validated market state and cursor first.
                self._snapshot = candidate
                self._refid, self._heven = info["cursor_after"], info["heven_after"]
                notify, notification_errors = self._notifications(
                    old_tokens, info["tokens"]
                )
                if self._stopped():
                    raise StopIteration
                info.update(notify)
                info["notification_errors"] = notification_errors
                info["cursor_before"] = before_ref
                info["_watcher_state_before"] = watcher_state_before
                selected = self._selected_inscodes(candidate)
                info["changed_inscodes"] = tuple(
                    code for code in info["changed_inscodes"] if code in selected
                )
                info["changed_order_levels"] = tuple(
                    item for item in info["changed_order_levels"] if item[0] in selected
                )
                changed = bool(info["changed_inscodes"] or info["changed_order_levels"])
                state_changed = before.get("market_state") != candidate.get(
                    "market_state"
                )
                token_changed = old_tokens != info["tokens"]
                notification_activity = bool(
                    notification_errors
                    or any(
                        isinstance(info.get(name), pd.DataFrame)
                        and not info[name].empty
                        for name in ("messages", "state_changes")
                    )
                )
                kind = (
                    "delta"
                    if (
                        changed
                        or state_changed
                        or token_changed
                        or notification_activity
                    )
                    else "heartbeat"
                )
                if kind == "heartbeat" and not self.emit_heartbeats:
                    continue
                retry = self._retry_count
                self._retry_count = 0
                info["retry_error"] = self._last_retry_error
                self._last_retry_error = None
                return self._event(kind, before, candidate, fetched_at, info, retry)
            except StopIteration:
                raise
            except _StorageError:
                raise
            except (
                ConnectionError,
                DataParsingError,
                requests.exceptions.RequestException,
            ) as exc:
                if self.error_policy == "raise":
                    raise
                if self.error_policy == "stop":
                    self.stop()
                    raise StopIteration
                self._retry_count += 1
                self._last_retry_error = f"{type(exc).__name__}: {exc}"
                if self._retry_count > self.max_consecutive_retries:
                    raise
                delay = min(
                    self.max_backoff,
                    max(self.interval, 0.1) * (2 ** min(self._retry_count - 1, 30)),
                )
                delay *= 1 + self.jitter * (2 * float(self._random()) - 1)
                self._pending_resync = self._initialized
                if self._sleep(delay):
                    raise StopIteration

    def run(self, callback: Callable[[MarketEvent], Any]):
        """Consume events until stopped; callback failures follow the explicit policy."""
        for event in self:
            try:
                callback(event)
            except Exception:
                if self.callback_error_policy == "raise":
                    raise
                if self.callback_error_policy == "stop":
                    self.stop()
                    break
        return self


def watch_market(*args, **kwargs):
    """Create a :class:`MarketWatcher` synchronous event iterator."""
    return MarketWatcher(*args, **kwargs)


def _records(payload, keys):
    for key in keys:
        value = payload.get(key)
        if value is not None:
            if isinstance(value, Mapping):
                return [value]
            if isinstance(value, list):
                return value
            raise DataParsingError(f"{key} must be a list or object")
    return []


def _provider_timestamp(deven, heven):
    try:
        date = _dt.datetime.strptime(str(int(deven)), "%Y%m%d").date()
        raw = int(heven or 0)
        h, m, s = raw // 10000, raw % 10000 // 100, raw % 100
        return pd.Timestamp(
            _dt.datetime.combine(date, _dt.time(h, m, s)), tz="Asia/Tehran"
        )
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _id_is_after(value, since_id):
    if value is None:
        return False
    try:
        return int(str(value).strip()) > int(str(since_id).strip())
    except (TypeError, ValueError):
        return str(value) > str(since_id)


def get_market_messages(
    flow=0,
    top=20,
    since_id=None,
    *,
    archive_to=None,
    _recorded_at=None,
    _request=safe_get,
):
    """Return recent TSETMC messages, deduplicated by provider message ID.

    ``since_id`` is a client-side filter; it is never sent as a provider
    cursor. ``top`` is bounded to protect accidental oversized requests.
    """
    top = _validate_top(top)
    payload = _response_json(
        settings.url_market_messages.format(int(flow), top), _request
    )
    rows = []
    for item in _records(payload, ("msg", "messages", "message")):
        mid = item.get("tseMsgIdn")
        rows.append(
            {
                "message_id": mid,
                "date": item.get("dEven"),
                "time": item.get("hEven"),
                "timestamp": _provider_timestamp(item.get("dEven"), item.get("hEven")),
                "title": item.get("tseTitle"),
                "description": item.get("tseDesc"),
                "flow": item.get("flow", flow),
            }
        )
    result = (
        pd.DataFrame(rows).reindex(columns=MESSAGE_COLUMNS)
        if rows
        else _typed_empty(
            MESSAGE_COLUMNS,
            {
                "date": "Int64",
                "time": "Int64",
                "timestamp": "datetime64[ns, Asia/Tehran]",
                "flow": "Int64",
            },
        )
    )
    if not result.empty:
        result["message_id"] = pd.Series(
            [item["message_id"] for item in rows], dtype="object"
        )
        for column in ("date", "time", "flow"):
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(
                "Int64"
            )
        result["timestamp"] = pd.to_datetime(
            result["timestamp"], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Tehran")
        result = _dedupe_stable_rows(result, "messages")
        if since_id is not None:
            result = result.loc[
                result["message_id"].map(lambda value: _id_is_after(value, since_id))
            ]
    result = result.reset_index(drop=True)
    if archive_to is not None:
        from .market_history import archive_market_records

        archive_market_records(
            archive_to, "messages", result, source="tsetmc", recorded_at=_recorded_at
        )
    return result


def get_instrument_state_changes(
    top=20, since_id=None, *, archive_to=None, _recorded_at=None, _request=safe_get
):
    """Return recent instrument-state events with documented code labels."""
    top = _validate_top(top)
    payload = _response_json(settings.url_instrument_state_top.format(top), _request)
    rows = []
    for item in _records(payload, ("instrumentState", "instrumentStateTop", "state")):
        code = str(item.get("cEtaval", "")).strip()
        event_id = item.get("idn")
        rows.append(
            {
                "event_id": event_id,
                "date": item.get("dEven"),
                "time": item.get("hEven"),
                "timestamp": _provider_timestamp(item.get("dEven"), item.get("hEven")),
                "InsCode": str(item.get("insCode", "")),
                "Symbol": item.get("lVal18AFC"),
                "Name": item.get("lVal30"),
                "state_code": code,
                "state": INSTRUMENT_STATE_LABELS.get(code, "unknown"),
                "real_time": item.get("realHeven"),
                "under_supervision": item.get("underSupervision"),
                "state_title": item.get("cEtavalTitle"),
            }
        )
    result = (
        pd.DataFrame(rows).reindex(columns=STATE_COLUMNS)
        if rows
        else _typed_empty(
            STATE_COLUMNS,
            {
                "date": "Int64",
                "time": "Int64",
                "timestamp": "datetime64[ns, Asia/Tehran]",
            },
        )
    )
    if not result.empty:
        result["event_id"] = pd.Series(
            [item["event_id"] for item in rows], dtype="object"
        )
        for column in ("date", "time"):
            result[column] = pd.to_numeric(result[column], errors="coerce").astype(
                "Int64"
            )
        result["timestamp"] = pd.to_datetime(
            result["timestamp"], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Tehran")
        result = _dedupe_stable_rows(result, "state_changes")
        if since_id is not None:
            result = result.loc[
                result["event_id"].map(lambda value: _id_is_after(value, since_id))
            ]
    result = result.reset_index(drop=True)
    if archive_to is not None:
        from .market_history import archive_market_records

        archive_market_records(
            archive_to,
            "state_changes",
            result,
            source="tsetmc",
            recorded_at=_recorded_at,
        )
    return result


_SYMBOL_CACHE: OrderedDict[str, tuple[str, str]] = OrderedDict()
_SYMBOL_CACHE_LOCK = threading.Lock()


def _resolve_one_inscode(symbol, request=safe_get):
    if symbol is None:
        return None, None
    text = str(symbol).strip()
    if text.isdigit():
        return text, None
    key = _normalise_symbol(symbol)
    with _SYMBOL_CACHE_LOCK:
        cached = _SYMBOL_CACHE.get(key)
        if cached is not None:
            _SYMBOL_CACHE.move_to_end(key)
    if cached is not None:
        return cached
    # Honor the caller's injected transport. No provider I/O happens while
    # the cache lock is held.
    text_response = _response_text(settings.url_market_watch_init, request)
    snapshot = _parse_market_watch_response(text_response)
    matches = snapshot["stocks"].loc[_instrument_mask(snapshot["stocks"], symbol)]
    if matches.empty:
        raise StockNotFoundError(f"No instrument matched {symbol!r}")
    unique = matches.drop_duplicates("InsCode")
    if len(unique) != 1:
        raise AmbiguousSymbolError(f"Selector {symbol!r} is ambiguous")
    resolved = str(unique.iloc[0]["InsCode"]), unique.iloc[0]["Symbol"]
    with _SYMBOL_CACHE_LOCK:
        _SYMBOL_CACHE[key] = resolved
        _SYMBOL_CACHE.move_to_end(key)
        while len(_SYMBOL_CACHE) > MAX_SYMBOL_CACHE:
            _SYMBOL_CACHE.popitem(last=False)
    return resolved


def get_market_overview(
    flow=0, *, archive_to=None, _recorded_at=None, _request=safe_get
):
    """Return the provider's market overview; an empty payload is zero rows."""
    payload = _response_json(settings.url_market_overview.format(int(flow)), _request)
    value = payload.get("marketOverview", payload)
    if value in ({}, [], None):
        result = _typed_empty(MARKET_OVERVIEW_COLUMNS, {"flow": "Int64"})
        if archive_to is not None:
            from .market_history import archive_market_records

            archive_market_records(
                archive_to,
                "overview",
                result,
                source="tsetmc",
                recorded_at=_recorded_at,
            )
        return result
    if isinstance(value, list):
        result = pd.json_normalize(value)
    elif isinstance(value, Mapping):
        result = pd.json_normalize([value])
    else:
        raise DataParsingError("marketOverview must be an object or list")
    if "flow" not in result:
        result["flow"] = int(flow)
    result["flow"] = pd.to_numeric(result["flow"], errors="coerce").astype("Int64")
    if archive_to is not None:
        from .market_history import archive_market_records

        archive_market_records(
            archive_to,
            "overview",
            result,
            source="tsetmc",
            recorded_at=_recorded_at,
        )
    return result


def _unique_market(frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=STOCK_COLUMNS)
    if "InsCode" not in frame:
        return pd.DataFrame(columns=STOCK_COLUMNS)
    conflicts = []
    for inscode, group in frame.groupby(frame["InsCode"].astype(str), sort=False):
        if len(group.drop_duplicates()) > 1:
            conflicts.append(inscode)
    if conflicts:
        raise DataParsingError(f"conflicting duplicate InsCode rows: {conflicts[:5]}")
    return frame.drop_duplicates("InsCode", keep="last").copy()


def _filter_universe(
    stocks,
    symbol=None,
    flow=None,
    sector=None,
    traded_only=False,
    include_base_market=True,
    instrument_types=None,
):
    frame = _unique_market(stocks)
    required = {
        "InsCode",
        "Symbol",
        "InstrumentType",
        "Flow",
        "SectorCode",
        "TradeCount",
        "Volume",
        "Value",
        "Last",
        "Close",
        "PreviousClose",
        "MaxAllowed",
        "MinAllowed",
    }
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=STOCK_COLUMNS)
    if instrument_types is None:
        # Package convention, already used by the legacy public docs.
        allowed = set(EQUITY_INSTRUMENT_TYPES)
        if not include_base_market:
            allowed.discard(BASE_MARKET_INSTRUMENT_TYPE)
    else:
        values = (
            [instrument_types]
            if isinstance(instrument_types, (str, int, np.integer))
            else list(instrument_types)
        )
        allowed = {int(value) for value in values}
    frame = frame.loc[
        pd.to_numeric(frame["InstrumentType"], errors="coerce").isin(allowed)
    ]
    if symbol is not None:
        frame = frame.loc[_instrument_mask(frame, symbol)]
    if flow is not None:
        flows = [flow] if isinstance(flow, (str, int, np.integer)) else list(flow)
        frame = frame.loc[
            pd.to_numeric(frame["Flow"], errors="coerce").isin(
                [int(value) for value in flows]
            )
        ]
    if sector is not None:
        choices = {
            str(x).strip()
            for x in ([sector] if isinstance(sector, (str, int)) else sector)
        }
        frame = frame.loc[frame["SectorCode"].astype(str).str.strip().isin(choices)]
    if traded_only:
        frame = frame.loc[
            pd.to_numeric(frame["TradeCount"], errors="coerce").gt(0)
            & pd.to_numeric(frame["Volume"], errors="coerce").gt(0)
        ]
    return frame.reset_index(drop=True)


def _breadth_record(frame):
    last = pd.to_numeric(frame["Last"], errors="coerce")
    close = pd.to_numeric(frame["Close"], errors="coerce")
    price = last.where(last.gt(0), close)
    previous = pd.to_numeric(frame["PreviousClose"], errors="coerce")
    traded = pd.to_numeric(frame["TradeCount"], errors="coerce").gt(0) & pd.to_numeric(
        frame["Volume"], errors="coerce"
    ).gt(0)
    missing_previous = previous.isna() | previous.le(0)
    missing_current = price.isna() | price.le(0)
    missing = missing_previous | missing_current
    valid = traded & ~missing
    advances, declines = int((valid & price.gt(previous)).sum()), int(
        (valid & price.lt(previous)).sum()
    )
    unchanged = int((valid & price.eq(previous)).sum())
    ratio = advances / declines if declines else (np.inf if advances else np.nan)
    upper = pd.to_numeric(frame["MaxAllowed"], errors="coerce")
    lower = pd.to_numeric(frame["MinAllowed"], errors="coerce")
    missing_count = int((traded & missing).sum())
    missing_previous_count = int((traded & missing_previous).sum())
    missing_current_count = int((traded & missing_current).sum())
    result = {
        "instrument_count": len(frame),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "no_trade": int((~traded).sum()),
        "missing_previous": missing_previous_count,
        "advance_decline_difference": advances - declines,
        "advance_decline_ratio": ratio,
        "advance_pct": advances / len(frame) * 100 if len(frame) else np.nan,
        "decline_pct": declines / len(frame) * 100 if len(frame) else np.nan,
        "total_volume": pd.to_numeric(frame["Volume"], errors="coerce").sum(
            min_count=1
        ),
        "total_value": pd.to_numeric(frame["Value"], errors="coerce").sum(min_count=1),
        "upper_limit_count": int((traded & price.eq(upper) & upper.gt(0)).sum()),
        "lower_limit_count": int((traded & price.eq(lower) & lower.gt(0)).sum()),
    }
    result.update(
        {
            "missing": missing_count,
            "missing_previous_close": missing_previous_count,
            "missing_current_price": missing_current_count,
            "ad_difference": result["advance_decline_difference"],
            "ad_ratio": result["advance_decline_ratio"],
            "advances_pct": result["advance_pct"],
            "declines_pct": result["decline_pct"],
        }
    )
    return result


def _cast_analytics_frame(frame, columns):
    result = frame.reindex(columns=columns)
    count_columns = {
        "instrument_count",
        "advances",
        "declines",
        "unchanged",
        "no_trade",
        "missing_previous",
        "missing",
        "missing_previous_close",
        "missing_current_price",
        "advance_decline_difference",
        "ad_difference",
        "upper_limit_count",
        "lower_limit_count",
        "client_covered_count",
    }
    for column in count_columns.intersection(result.columns):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    float_columns = {
        "advance_decline_ratio",
        "ad_ratio",
        "advance_pct",
        "decline_pct",
        "advances_pct",
        "declines_pct",
        "total_volume",
        "total_value",
        "client_coverage",
        "net_individual_volume",
        "estimated_net_individual_value",
    }
    for column in float_columns.intersection(result.columns):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "Float64"
        )
    for column in ("is_realtime_fresh", "is_stale", "value_available"):
        if column in result:
            result[column] = result[column].astype("boolean")
    for column in ("exchange_time", "fetched_at"):
        if column in result:
            if result.empty:
                result[column] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
            else:
                result[column] = pd.to_datetime(
                    result[column], errors="coerce", utc=True
                ).dt.tz_convert("Asia/Tehran")
    return result


def get_market_breadth(
    symbol=None,
    flow=None,
    sector=None,
    traded_only=False,
    include_base_market=True,
    instrument_types=None,
    *,
    _snapshot=None,
):
    """Aggregate current equity breadth from one market snapshot.

    The default package equity universe is instrument types 300, 303 and 309;
    set ``include_base_market=False`` to remove 309 or pass an explicit
    ``instrument_types`` override. Percentages use the selected instrument
    count as denominator. No-trade, missing previous close and missing current
    price are separate buckets.
    """
    snapshot = _snapshot if _snapshot is not None else market_watch()
    if not isinstance(snapshot, Mapping):
        return _cast_analytics_frame(pd.DataFrame(), BREADTH_COLUMNS)
    frame = _filter_universe(
        snapshot.get("stocks", pd.DataFrame()),
        symbol,
        flow,
        sector,
        traded_only,
        include_base_market,
        instrument_types,
    )
    if frame.empty:
        return _cast_analytics_frame(pd.DataFrame(), BREADTH_COLUMNS)
    record = _breadth_record(frame)
    record.update(
        {
            "trade_date": snapshot.get("trade_date"),
            "exchange_time": snapshot.get("exchange_time"),
            "fetched_at": snapshot.get("fetched_at"),
            "is_realtime_fresh": snapshot.get("is_realtime_fresh", False),
        }
    )
    return _cast_analytics_frame(pd.DataFrame([record]), BREADTH_COLUMNS)


def get_sector_flow(
    symbol=None,
    flow=None,
    sector=None,
    traded_only=False,
    include_base_market=True,
    instrument_types=None,
    *,
    _snapshot=None,
    _client_type=None,
):
    """Aggregate client flow and breadth by sector from two bulk feeds.

    Only rows whose client volumes reconcile to the market snapshot contribute
    to client-flow values. Monetary client flow is an estimate using that
    instrument's market VWAP; coverage and availability are explicit.
    """
    snapshot = _snapshot if _snapshot is not None else market_watch()
    client = _client_type if _client_type is not None else market_client_type()
    if not isinstance(snapshot, Mapping):
        return _cast_analytics_frame(pd.DataFrame(), SECTOR_FLOW_COLUMNS)
    if not isinstance(client, pd.DataFrame):
        client = _typed_empty(CLIENT_COLUMNS)
    frame = _filter_universe(
        snapshot.get("stocks", pd.DataFrame()),
        symbol,
        flow,
        sector,
        traded_only,
        include_base_market,
        instrument_types,
    )
    if frame.empty:
        return _cast_analytics_frame(pd.DataFrame(), SECTOR_FLOW_COLUMNS)
    if not client.empty:
        client = client.copy()
        client["InsCode"] = client["InsCode"].astype(str).str.strip()
        if client["InsCode"].astype(str).duplicated(keep=False).any():
            raise DataParsingError("client feed must be one-to-one by InsCode")
    frame = frame.copy()
    frame["InsCode"] = frame["InsCode"].astype(str).str.strip()
    live = _enrich_live_market(
        frame,
        client,
        snapshot.get("order_book", pd.DataFrame()),
        as_of=snapshot.get("fetched_at"),
        snapshot_metadata=snapshot,
    )
    sector_codes = live["SectorCode"].astype("string").str.strip()
    live["SectorCode"] = sector_codes.mask(
        sector_codes.isna() | sector_codes.isin(["", "nan", "<NA>"])
    )
    output = []
    for code, group in live.groupby("SectorCode", dropna=False, sort=True):
        if pd.isna(code):
            code = pd.NA
        consistent = group["client_snapshot_consistent"].fillna(False)
        covered = group.loc[consistent]
        estimated_values = pd.to_numeric(
            covered["EstimatedNetIndividualFlow"], errors="coerce"
        )
        value_available = bool(estimated_values.notna().any())
        record = {"SectorCode": code, **_breadth_record(group)}
        record.update(
            {
                "client_covered_count": int(consistent.sum()),
                "client_coverage": float(consistent.mean()) if len(group) else np.nan,
                "net_individual_volume": pd.to_numeric(
                    covered["NetIndividualVolume"], errors="coerce"
                ).sum(min_count=1),
                "estimated_net_individual_value": estimated_values.sum(min_count=1),
                "value_available": value_available,
                "value_method": (
                    "market_vwap_estimate" if value_available else "unavailable"
                ),
                "trade_date": snapshot.get("trade_date"),
                "exchange_time": snapshot.get("exchange_time"),
                "fetched_at": snapshot.get("fetched_at"),
                "is_realtime_fresh": snapshot.get("is_realtime_fresh", False),
                "is_stale": snapshot.get("is_stale", True),
            }
        )
        output.append(record)
    return _cast_analytics_frame(pd.DataFrame(output), SECTOR_FLOW_COLUMNS)


__all__ = [
    "MarketEvent",
    "MarketWatcher",
    "watch_market",
    "get_market_messages",
    "get_instrument_state_changes",
    "get_market_overview",
    "get_market_breadth",
    "get_sector_flow",
]
