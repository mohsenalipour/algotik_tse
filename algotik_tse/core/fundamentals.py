"""Point-in-time market fundamentals derived from bulk MarketWatch snapshots."""

import math
from collections.abc import Iterable

import numpy as np
import pandas as pd

from ..exceptions import InvalidParameterError
from .market_data import _resolve_live_selection, market_watch
from .resolver import normalize_instrument_text

DEFAULT_FUNDAMENTAL_INSTRUMENT_TYPES = (300, 303, 309)
FUNDAMENTAL_COLUMNS = [
    "InsCode",
    "Symbol",
    "Name",
    "SectorCode",
    "InstrumentType",
    "Close",
    "Last",
    "EPS",
    "PE",
    "PECalculated",
    "EPSSource",
    "PriceSource",
    "PEStatus",
    "TradeDate",
    "ExchangeTime",
    "AsOf",
    "SnapshotAgeSeconds",
    "IsRealtimeFresh",
    "IsStale",
    "Source",
    "NoLookahead",
]


def _typed_empty():
    frame = pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)
    for column in (
        "InsCode",
        "Symbol",
        "Name",
        "SectorCode",
        "EPSSource",
        "PriceSource",
        "PEStatus",
        "Source",
    ):
        frame[column] = pd.Series(dtype="string")
    frame["InstrumentType"] = pd.Series(dtype="Int64")
    for column in ("Close", "Last", "EPS", "PE", "SnapshotAgeSeconds"):
        frame[column] = pd.Series(dtype="Float64")
    for column in ("PECalculated", "IsRealtimeFresh", "IsStale", "NoLookahead"):
        frame[column] = pd.Series(dtype="boolean")
    frame["TradeDate"] = pd.Series(dtype="object")
    for column in ("ExchangeTime", "AsOf"):
        frame[column] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    return frame


def _one_request_budget(max_requests):
    if isinstance(max_requests, bool):
        raise InvalidParameterError("max_requests must be a positive integer")
    try:
        value = float(max_requests)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("max_requests must be a positive integer") from exc
    if not math.isfinite(value) or value <= 0 or not value.is_integer():
        raise InvalidParameterError("max_requests must be a positive integer")
    if int(value) < 1:
        raise InvalidParameterError("max_requests=0 cannot cover the one bulk request")
    return int(value)


def _range(value, name):
    if value is None:
        return None
    if isinstance(value, bool):
        raise InvalidParameterError("{} must be a finite number".format(name))
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("{} must be a finite number".format(name)) from exc
    if not math.isfinite(result):
        raise InvalidParameterError("{} must be a finite number".format(name))
    return result


def _instrument_types(value):
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        value = [value]
    result = []
    for item in value:
        if isinstance(item, bool):
            raise InvalidParameterError("instrument_types must contain integers")
        try:
            numeric = float(item)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError(
                "instrument_types must contain integers"
            ) from exc
        if not math.isfinite(numeric) or not numeric.is_integer():
            raise InvalidParameterError("instrument_types must contain integers")
        result.append(int(numeric))
    return tuple(dict.fromkeys(result))


def _symbol_selectors(value):
    if value is None:
        return None
    if isinstance(value, (str, int, np.integer)):
        choices = [value]
        scalar = True
    else:
        try:
            choices = list(value)
        except TypeError as exc:
            raise InvalidParameterError(
                "symbols must be a selector or iterable"
            ) from exc
        scalar = False
    for item in choices:
        if not normalize_instrument_text(item):
            raise InvalidParameterError("symbols cannot contain empty selectors")
    return choices[0] if scalar else choices


def _validated_filters(pe_min, pe_max, positive_pe, instrument_types, strict):
    if not isinstance(positive_pe, bool):
        raise InvalidParameterError("positive_pe must be bool")
    if not isinstance(strict, bool):
        raise InvalidParameterError("strict must be bool")
    lower, upper = _range(pe_min, "pe_min"), _range(pe_max, "pe_max")
    if lower is not None and upper is not None and lower > upper:
        raise InvalidParameterError("pe_min must be less than or equal to pe_max")
    return lower, upper, _instrument_types(instrument_types)


def _filter_symbols(frame, symbols, strict):
    # The snapshot is authoritative, so the central resolver performs exact
    # symbol/InsCode selection without falling back to a network search.
    selected, missing = _resolve_live_selection(
        frame, symbols, {"stocks": frame}, strict=strict
    )
    return selected.copy(), list(missing)


def _status(close, eps):
    close_missing = close.isna()
    eps_missing = eps.isna()
    close_nonfinite = ~close_missing & ~np.isfinite(close)
    eps_nonfinite = ~eps_missing & ~np.isfinite(eps)
    return np.select(
        [
            close_missing,
            close_nonfinite,
            close.le(0) & ~close_missing,
            eps_missing,
            eps_nonfinite,
            eps.le(0) & ~eps_missing,
        ],
        [
            "price_missing",
            "price_nonfinite",
            "price_nonpositive",
            "eps_missing",
            "eps_nonfinite",
            "eps_nonpositive",
        ],
        default="ok",
    )


def _derive(frame, metadata, *, source, no_lookahead):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return _typed_empty()
    result = pd.DataFrame(index=frame.index)
    for column in ("InsCode", "Symbol", "Name", "SectorCode", "InstrumentType"):
        result[column] = frame[column] if column in frame else pd.NA
    numeric = {}
    for column in ("Close", "Last", "EPS"):
        numeric[column] = pd.to_numeric(
            frame[column] if column in frame else pd.Series(pd.NA, index=frame.index),
            errors="coerce",
        )
    validity = frame.attrs.get("field_validity", {})
    eps_validity = validity.get("EPS", {}) if isinstance(validity, dict) else {}
    schema_presence = frame.attrs.get("source_schema_presence", {})
    eps_schema_signal = (
        schema_presence.get("EPS", "EPS" in frame.columns)
        if isinstance(schema_presence, dict)
        else "EPS" in frame.columns
    )
    try:
        eps_in_source_schema = bool(eps_schema_signal)
    except (TypeError, ValueError):
        eps_in_source_schema = "EPS" in frame.columns
    if isinstance(eps_validity, dict):
        validity_signal = frame["InsCode"].astype("string").map(eps_validity)
    else:
        validity_signal = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    explicitly_missing_eps = validity_signal.eq(False).fillna(False)
    numeric["EPS"] = numeric["EPS"].mask(
        explicitly_missing_eps | (not eps_in_source_schema)
    )
    result["PEStatus"] = _status(numeric["Close"], numeric["EPS"])
    for column in ("Close", "Last", "EPS"):
        result[column] = numeric[column].where(np.isfinite(numeric[column]))
    result["PE"] = (result["Close"] / result["EPS"]).where(result["PEStatus"] == "ok")
    result["PECalculated"] = True
    if not eps_in_source_schema:
        result["EPSSource"] = "unavailable_in_snapshot_schema"
    else:
        result["EPSSource"] = np.where(
            explicitly_missing_eps, "missing_in_market_watch", "market_watch"
        )
    result["PriceSource"] = "Close"
    result["TradeDate"] = metadata.get("trade_date")
    result["ExchangeTime"] = metadata.get("exchange_time")
    result["AsOf"] = metadata.get("as_of", metadata.get("fetched_at"))
    result["SnapshotAgeSeconds"] = metadata.get("snapshot_age_seconds", np.nan)
    result["IsRealtimeFresh"] = bool(metadata.get("is_realtime_fresh", False))
    result["IsStale"] = bool(metadata.get("is_stale", True))
    result["Source"] = source
    result["NoLookahead"] = bool(no_lookahead)
    return _cast(result)


def _cast(frame):
    if frame.empty:
        return _typed_empty()
    result = frame.reindex(columns=FUNDAMENTAL_COLUMNS).copy()
    for column in (
        "InsCode",
        "Symbol",
        "Name",
        "SectorCode",
        "EPSSource",
        "PriceSource",
        "PEStatus",
        "Source",
    ):
        result[column] = result[column].astype("string")
    result["InstrumentType"] = pd.to_numeric(
        result["InstrumentType"], errors="coerce"
    ).astype("Int64")
    for column in ("Close", "Last", "EPS", "PE", "SnapshotAgeSeconds"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "Float64"
        )
    for column in ("PECalculated", "IsRealtimeFresh", "IsStale", "NoLookahead"):
        result[column] = result[column].astype("boolean")
    for column in ("ExchangeTime", "AsOf"):
        result[column] = pd.to_datetime(
            result[column], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Tehran")
    return result.reset_index(drop=True)


def _apply_filters(
    frame,
    symbols,
    *,
    pe_min,
    pe_max,
    positive_pe,
    instrument_types,
    strict,
):
    lower, upper, types = _validated_filters(
        pe_min, pe_max, positive_pe, instrument_types, strict
    )
    selected = frame
    if types is not None:
        selected = selected.loc[selected["InstrumentType"].isin(types)].copy()
    selected, missing = _filter_symbols(selected, symbols, strict)
    if positive_pe:
        selected = selected.loc[selected["PE"].gt(0)].copy()
    if lower is not None:
        selected = selected.loc[selected["PE"].ge(lower)].copy()
    if upper is not None:
        selected = selected.loc[selected["PE"].le(upper)].copy()
    return selected.reset_index(drop=True), missing


def _attrs(frame, **values):
    frame.attrs.update(values)
    return frame


def get_market_fundamentals(
    symbols=None,
    *,
    pe_min=None,
    pe_max=None,
    positive_pe=True,
    instrument_types=DEFAULT_FUNDAMENTAL_INSTRUMENT_TYPES,
    strict=False,
    allow_stale=False,
    archive_to=None,
    max_requests=1,
    progress=True,
):
    """Screen current market EPS and calculated P/E in one bulk request.

    ``pe_min`` and ``pe_max`` are inclusive. P/E is finite only where both the
    MarketWatch ``Close`` and ``EPS`` are positive; undefined observations are
    retained with ``PEStatus`` when ``positive_pe=False``. No per-symbol Codal
    or InstrumentInfo calls are made.
    """
    budget = _one_request_budget(max_requests)
    if not isinstance(allow_stale, bool):
        raise InvalidParameterError("allow_stale must be bool")
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    normalized_symbols = _symbol_selectors(symbols)
    lower, upper, normalized_types = _validated_filters(
        pe_min, pe_max, positive_pe, instrument_types, strict
    )
    snapshot = market_watch()
    if archive_to is not None:
        from .market_history import save_market_snapshot

        save_market_snapshot(
            archive_to, snapshot=snapshot, as_of=snapshot.get("fetched_at")
        )
    metadata = {
        "trade_date": snapshot.get("trade_date"),
        "exchange_time": snapshot.get("exchange_time"),
        "fetched_at": snapshot.get("fetched_at"),
        "snapshot_age_seconds": snapshot.get("snapshot_age_seconds", np.nan),
        "is_realtime_fresh": snapshot.get("is_realtime_fresh", False),
        "is_stale": snapshot.get("is_stale", True),
    }
    stale_rejected = bool(metadata["is_stale"] and not allow_stale)
    derived = _derive(
        snapshot.get("stocks", pd.DataFrame()),
        metadata,
        source="tsetmc_market_watch",
        no_lookahead=True,
    )
    result, missing = _apply_filters(
        derived,
        normalized_symbols,
        pe_min=lower,
        pe_max=upper,
        positive_pe=positive_pe,
        instrument_types=normalized_types,
        strict=strict,
    )
    if stale_rejected:
        result = result.iloc[0:0].copy()
    return _attrs(
        result,
        request_count=1,
        max_requests=budget,
        missing_selectors=tuple(missing),
        strict=bool(strict),
        stale_rejected=stale_rejected,
        source="tsetmc_market_watch",
        price_source="Close",
        eps_source="market_watch",
        no_lookahead=True,
        no_backfill=True,
        archive_path=None if archive_to is None else str(archive_to),
    )


def get_market_fundamentals_history(
    path,
    start=None,
    end=None,
    symbols=None,
    *,
    pe_min=None,
    pe_max=None,
    positive_pe=True,
    instrument_types=DEFAULT_FUNDAMENTAL_INSTRUMENT_TYPES,
    strict=False,
    allow_stale=True,
    limit=1000,
    offset=0,
):
    """Derive point-in-time P/E only from locally persisted snapshots.

    Each row uses the ``Close`` and ``EPS`` stored in that same observation;
    current EPS is never joined onto an old close. The local archive starts
    when the caller opts into recording and does not claim provider backfill.
    """
    if not isinstance(allow_stale, bool):
        raise InvalidParameterError("allow_stale must be bool")
    normalized_symbols = _symbol_selectors(symbols)
    lower, upper, normalized_types = _validated_filters(
        pe_min, pe_max, positive_pe, instrument_types, strict
    )
    from .market_history import load_market_snapshots

    saved = load_market_snapshots(
        path, start=start, end=end, limit=limit, offset=offset
    )
    coverage_start = saved.attrs.get("CoverageStart")
    coverage_end = saved.attrs.get("CoverageEnd")
    if not saved.empty and "AsOf" in saved:
        observed = pd.to_datetime(saved["AsOf"], errors="coerce", utc=True).dropna()
        if not observed.empty:
            coverage_start = observed.min().tz_convert("Asia/Tehran")
            coverage_end = observed.max().tz_convert("Asia/Tehran")
    if saved.empty:
        result, missing = _apply_filters(
            _typed_empty(),
            normalized_symbols,
            pe_min=lower,
            pe_max=upper,
            positive_pe=positive_pe,
            instrument_types=normalized_types,
            strict=strict,
        )
    else:
        # ``load_market_snapshots`` attaches point-in-time metadata row-wise.
        metadata_columns = {
            "trade_date": "trade_date",
            "exchange_time": "exchange_time",
            "as_of": "AsOf",
            "snapshot_age_seconds": "snapshot_age_seconds",
            "is_realtime_fresh": "is_realtime_fresh",
            "is_stale": "is_stale",
        }
        parts = []
        group_column = "SnapshotID" if "SnapshotID" in saved else "AsOf"
        snapshot_attrs = saved.attrs.get("SnapshotFrameAttrs", {})
        for group_key, group in saved.groupby(group_column, dropna=False, sort=False):
            if isinstance(snapshot_attrs, dict):
                group.attrs.update(snapshot_attrs.get(str(group_key), {}))
            metadata = {}
            for target, column in metadata_columns.items():
                if column in group and group[column].notna().any():
                    metadata[target] = group[column].dropna().iloc[0]
            parts.append(
                _derive(
                    group,
                    metadata,
                    source="local_market_snapshot",
                    no_lookahead=True,
                )
            )
        derived = (
            pd.concat(parts, ignore_index=True, sort=False) if parts else _typed_empty()
        )
        if not allow_stale:
            derived = derived.loc[~derived["IsStale"].fillna(True)].copy()
        result, missing = _apply_filters(
            derived,
            normalized_symbols,
            pe_min=lower,
            pe_max=upper,
            positive_pe=positive_pe,
            instrument_types=normalized_types,
            strict=strict,
        )
    if not result.empty:
        result = result.sort_values(["AsOf", "InsCode"], kind="mergesort").reset_index(
            drop=True
        )
    return _attrs(
        result,
        missing_selectors=tuple(missing),
        strict=bool(strict),
        source="local_market_snapshots",
        price_source="Close",
        eps_source="same_persisted_snapshot",
        current_eps_used=False,
        no_lookahead=True,
        no_backfill=True,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )


__all__ = [
    "DEFAULT_FUNDAMENTAL_INSTRUMENT_TYPES",
    "FUNDAMENTAL_COLUMNS",
    "get_market_fundamentals",
    "get_market_fundamentals_history",
]
