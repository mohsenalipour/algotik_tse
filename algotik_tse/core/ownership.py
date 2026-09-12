"""Recent market-wide major-shareholder snapshots and derived activity.

TSETMC's public market-wide feed is a rolling, provider-controlled window of
at most five published trading dates.  It is not a historical database and it
does not contain every major shareholder: it contains holders that appear in
the recent-changes board.  The long-running per-instrument history remains
available through :func:`algotik_tse.get_shareholders`.
"""

from __future__ import annotations

import datetime
import math
from numbers import Integral

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from .._clock import tehran_now
from ..exceptions import ConnectionError, DataParsingError, InvalidParameterError
from ..http_client import safe_get
from ..settings import settings
from .conventions import coerce_financial_date
from .resolver import normalize_instrument_text, resolve_instrument

_DAY_FIELDS = ("firstDay", "secondDay", "thirdDay", "fourthDay", "fifthDay")
_SOURCE = "tsetmc_recent_major_shareholder_changes"

MAJOR_SHAREHOLDER_SNAPSHOT_COLUMNS = [
    "HolderRecord",
    "HolderName",
    "InsCode",
    "Symbol",
    "InstrumentName",
    "GregorianDate",
    "JalaliDate",
    "Holdings",
    "Source",
    "FetchedAt",
]

MAJOR_SHAREHOLDER_CHANGE_COLUMNS = [
    "HolderRecord",
    "HolderName",
    "InsCode",
    "Symbol",
    "InstrumentName",
    "PreviousGregorianDate",
    "PreviousJalaliDate",
    "GregorianDate",
    "JalaliDate",
    "PreviousHoldings",
    "Holdings",
    "ChangeShares",
    "Direction",
    "Source",
    "FetchedAt",
]

ACTIVE_SHAREHOLDER_COLUMNS = [
    "HolderRecord",
    "HolderName",
    "InsCode",
    "Symbol",
    "InstrumentName",
    "FirstGregorianDate",
    "FirstJalaliDate",
    "LastGregorianDate",
    "LastJalaliDate",
    "InitialHoldings",
    "LatestHoldings",
    "NetChangeShares",
    "GrossIncreaseShares",
    "GrossDecreaseShares",
    "ActiveDays",
    "ActivityDirection",
    "Source",
    "FetchedAt",
]

SHAREHOLDER_ACCUMULATION_RANK_COLUMNS = [
    "Rank",
    "HolderRecord",
    "HolderName",
    "InsCode",
    "Symbol",
    "InstrumentName",
    "FirstGregorianDate",
    "FirstJalaliDate",
    "LastGregorianDate",
    "LastJalaliDate",
    "InitialHoldings",
    "LatestHoldings",
    "NetChangeShares",
    "NetChangePercent",
    "GrossIncreaseShares",
    "GrossDecreaseShares",
    "ActiveDays",
    "ActivityDirection",
    "RankingMetric",
    "Score",
    "Source",
    "FetchedAt",
]

SHAREHOLDER_NETWORK_COLUMNS = [
    "EdgeRecord",
    "HolderRecord",
    "HolderNode",
    "HolderName",
    "InstrumentNode",
    "InsCode",
    "Symbol",
    "InstrumentName",
    "GregorianDate",
    "JalaliDate",
    "Holdings",
    "HolderInstrumentCount",
    "InstrumentHolderCount",
    "Source",
    "FetchedAt",
]

OWNERSHIP_CONCENTRATION_COLUMNS = [
    "InsCode",
    "Symbol",
    "InstrumentName",
    "TradeDate",
    "EffectiveDate",
    "EffectiveDateJalali",
    "MajorHolderCount",
    "DisclosedOwnershipPercent",
    "UndisclosedOrBelowThresholdPercent",
    "LargestHolderPercent",
    "Top1Percent",
    "Top3Percent",
    "Top5Percent",
    "Top10Percent",
    "TopN",
    "TopNPercent",
    "MajorHolderHHI",
    "NormalizedDisclosedHHI",
    "Source",
]


def _positive_days(value):
    if isinstance(value, bool):
        raise InvalidParameterError("days must be an integer between 1 and 5")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("days must be an integer between 1 and 5") from exc
    if not math.isfinite(number) or not number.is_integer() or not 1 <= number <= 5:
        raise InvalidParameterError("days must be an integer between 1 and 5")
    return int(number)


def _bool(value, name):
    if not isinstance(value, bool):
        raise InvalidParameterError("{} must be bool".format(name))
    return value


def _date(value):
    if value is None:
        return None
    try:
        return coerce_financial_date(value, "date")
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _provider_date(value, context):
    if isinstance(value, bool) or isinstance(value, float):
        raise DataParsingError("{} must be an exact YYYYMMDD date".format(context))
    if isinstance(value, Integral):
        text = str(int(value))
    else:
        text = "" if value is None else str(value).strip()
    if len(text) != 8 or not text.isascii() or not text.isdigit():
        raise DataParsingError("{} must be an exact YYYYMMDD date".format(context))
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise DataParsingError("{} is not a valid date".format(context)) from exc


def _ins_code(value, context):
    if isinstance(value, bool) or isinstance(value, float):
        raise DataParsingError("{} must be an exact decimal InsCode".format(context))
    if isinstance(value, Integral):
        text = str(int(value))
    else:
        text = "" if value is None else str(value).strip()
    if not text or not text.isascii() or not text.isdigit() or int(text) <= 0:
        raise DataParsingError("{} must be an exact decimal InsCode".format(context))
    return text


def _holdings(value, context):
    if value is None or isinstance(value, bool):
        raise DataParsingError("{} must be a non-negative integer".format(context))
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataParsingError(
            "{} must be a non-negative integer".format(context)
        ) from exc
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise DataParsingError("{} must be a non-negative integer".format(context))
    return int(number)


def _typed_empty(columns):
    frame = pd.DataFrame(columns=columns)
    string_columns = {
        "HolderName",
        "InsCode",
        "Symbol",
        "InstrumentName",
        "JalaliDate",
        "PreviousJalaliDate",
        "FirstJalaliDate",
        "LastJalaliDate",
        "Direction",
        "ActivityDirection",
        "RankingMetric",
        "HolderNode",
        "InstrumentNode",
        "EffectiveDateJalali",
        "Source",
    }
    integer_columns = {
        "HolderRecord",
        "Holdings",
        "PreviousHoldings",
        "ChangeShares",
        "InitialHoldings",
        "LatestHoldings",
        "NetChangeShares",
        "GrossIncreaseShares",
        "GrossDecreaseShares",
        "ActiveDays",
        "Rank",
        "EdgeRecord",
        "HolderInstrumentCount",
        "InstrumentHolderCount",
        "MajorHolderCount",
        "TopN",
    }
    float_columns = {
        "NetChangePercent",
        "Score",
        "DisclosedOwnershipPercent",
        "UndisclosedOrBelowThresholdPercent",
        "LargestHolderPercent",
        "Top1Percent",
        "Top3Percent",
        "Top5Percent",
        "Top10Percent",
        "TopNPercent",
        "MajorHolderHHI",
        "NormalizedDisclosedHHI",
    }
    for column in columns:
        if column in string_columns:
            frame[column] = pd.Series(dtype="string")
        elif column in integer_columns:
            frame[column] = pd.Series(dtype="Int64")
        elif column in float_columns:
            frame[column] = pd.Series(dtype="Float64")
        elif column == "FetchedAt":
            frame[column] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
        else:
            frame[column] = pd.Series(dtype="object")
    return frame


def _cast(frame, columns):
    if frame.empty:
        return _typed_empty(columns)
    result = frame.reindex(columns=columns).copy()
    empty = _typed_empty(columns)
    for column in columns:
        if column == "FetchedAt":
            result[column] = pd.to_datetime(result[column], utc=True).dt.tz_convert(
                "Asia/Tehran"
            )
        else:
            result[column] = result[column].astype(empty[column].dtype)
    return result


def _payload(response):
    try:
        payload = response.json()
    except (ValueError, AttributeError, TypeError) as exc:
        raise DataParsingError("invalid TSETMC shareholder-activity response") from exc
    if not isinstance(payload, dict):
        raise DataParsingError("shareholder-activity response must be an object")
    dates = payload.get("dates")
    holders = payload.get("shareHoldersChanges")
    if not isinstance(dates, list) or not isinstance(holders, list):
        raise DataParsingError(
            "shareholder-activity response requires dates and shareHoldersChanges lists"
        )
    if not 1 <= len(dates) <= 5:
        raise DataParsingError("TSETMC shareholder window must contain 1 to 5 dates")
    parsed_dates = [
        _provider_date(value, "dates[{}]".format(index))
        for index, value in enumerate(dates)
    ]
    if parsed_dates != sorted(set(parsed_dates)):
        raise DataParsingError("TSETMC shareholder dates must be unique and ascending")
    return parsed_dates, holders


def _identity_map():
    """Return current display identity keyed only by exact InsCode."""
    from .market_data import market_watch

    snapshot = market_watch()
    stocks = snapshot.get("stocks") if isinstance(snapshot, dict) else None
    if not isinstance(stocks, pd.DataFrame) or "InsCode" not in stocks:
        raise DataParsingError("market snapshot has no usable stocks identity table")
    result = {}
    for row in stocks.to_dict(orient="records"):
        code = str(row.get("InsCode", "")).strip()
        if code and code.isascii() and code.isdigit() and code not in result:
            result[code] = (row.get("Symbol"), row.get("Name"))
    return result


def _base_attrs(*, fetched_at, available_dates, requested_days, selected_date):
    return {
        "source": _SOURCE,
        "endpoint": "Shareholder/GetShareHolderChanges/false",
        "fetched_at": fetched_at,
        "available_dates": tuple(value.isoformat() for value in available_dates),
        "coverage_start": available_dates[0].isoformat(),
        "coverage_end": available_dates[-1].isoformat(),
        "requested_days": requested_days,
        "selected_date": None if selected_date is None else selected_date.isoformat(),
        "provider_window_max_sessions": 5,
        "rolling_window": True,
        "no_backfill": True,
        "is_complete_major_shareholder_list": False,
        "coverage": "holders_present_on_tsetmc_recent_changes_board_only",
        "stable_shareholder_id_available": False,
        "holder_record_is_provider_position_not_stable_identity": True,
        "change_may_include_non_trade_transfers": True,
        "official_inquiry_required_for_legal_reliance": True,
        "date_semantics": (
            "provider_display_date; during the trading session holdings refer to the "
            "previous completed session and same-day transfers publish after processing"
        ),
    }


def get_major_shareholder_snapshots(
    date=None,
    days=5,
    symbol=None,
    *,
    ins_code=None,
    holder=None,
    enrich_identity=True,
    progress=True,
):
    """Return TSETMC's rolling market-wide major-shareholder snapshots.

    The source publishes at most five recent trading dates and only holders
    appearing on its recent-changes board. ``date`` selects one published date
    and overrides ``days``.  This function does not replace the full
    per-instrument history returned by :func:`get_shareholders`.
    """
    requested_days = _positive_days(days)
    selected_date = _date(date)
    _bool(enrich_identity, "enrich_identity")
    _bool(progress, "progress")
    if holder is not None and (
        not isinstance(holder, str) or not normalize_instrument_text(holder)
    ):
        raise InvalidParameterError("holder must be a non-empty string or None")

    identity = None
    if symbol is not None or ins_code is not None:
        identity = resolve_instrument(
            symbol,
            ins_code=ins_code,
            asset_type="auto",
            require_active=False,
        )

    fetched_at = tehran_now()
    try:
        response = safe_get(settings.url_major_shareholder_changes)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ConnectionError("TSETMC shareholder-activity request failed") from exc
    available_dates, holder_rows = _payload(response)
    if selected_date is not None and selected_date not in available_dates:
        raise InvalidParameterError(
            "date is outside the five-date provider window; available dates: {}".format(
                ", ".join(value.isoformat() for value in available_dates)
            )
        )
    chosen_dates = (
        [selected_date]
        if selected_date is not None
        else available_dates[-requested_days:]
    )

    identities = {}
    enrichment_error = None
    if enrich_identity:
        try:
            identities = _identity_map()
        except (
            ConnectionError,
            DataParsingError,
            requests.exceptions.RequestException,
        ) as exc:
            enrichment_error = "{}: {}".format(type(exc).__name__, exc)

    rows = []
    holder_filter = None if holder is None else normalize_instrument_text(holder)
    for holder_index, holder_row in enumerate(holder_rows, start=1):
        context = "shareHoldersChanges[{}]".format(holder_index - 1)
        if not isinstance(holder_row, dict):
            raise DataParsingError("{} must be an object".format(context))
        holder_name = normalize_instrument_text(holder_row.get("name"))
        if not holder_name:
            raise DataParsingError("{}.name must be non-empty".format(context))
        if holder_filter is not None and holder_name != holder_filter:
            continue
        instruments = holder_row.get("insList")
        if not isinstance(instruments, list):
            raise DataParsingError("{}.insList must be a list".format(context))
        for instrument_index, instrument in enumerate(instruments):
            item_context = "{}.insList[{}]".format(context, instrument_index)
            if not isinstance(instrument, dict):
                raise DataParsingError("{} must be an object".format(item_context))
            code = _ins_code(instrument.get("insCode"), item_context + ".insCode")
            if identity is not None and code != identity.ins_code:
                continue
            provider_name = normalize_instrument_text(instrument.get("name"))
            current_symbol, current_name = identities.get(code, (None, None))
            output_symbol = (
                identity.symbol
                if identity is not None
                else normalize_instrument_text(current_symbol) or pd.NA
            )
            output_name = (
                normalize_instrument_text(current_name) or provider_name or pd.NA
            )
            for day_index, day in enumerate(available_dates):
                if day not in chosen_dates:
                    continue
                rows.append(
                    {
                        "HolderRecord": holder_index,
                        "HolderName": holder_name,
                        "InsCode": code,
                        "Symbol": output_symbol,
                        "InstrumentName": output_name,
                        "GregorianDate": day,
                        "JalaliDate": JalaliDate.to_jalali(day).isoformat(),
                        "Holdings": _holdings(
                            instrument.get(_DAY_FIELDS[day_index]),
                            item_context + "." + _DAY_FIELDS[day_index],
                        ),
                        "Source": _SOURCE,
                        "FetchedAt": fetched_at,
                    }
                )
    frame = _cast(pd.DataFrame(rows), MAJOR_SHAREHOLDER_SNAPSHOT_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(
            ["GregorianDate", "InsCode", "HolderRecord"], kind="mergesort"
        ).reset_index(drop=True)
    attrs = _base_attrs(
        fetched_at=fetched_at,
        available_dates=available_dates,
        requested_days=requested_days,
        selected_date=selected_date,
    )
    attrs.update(
        {
            "analysis": "major_shareholder_snapshots",
            "enrich_identity": enrich_identity,
            "identity_enrichment_partial": enrichment_error is not None,
            "identity_enrichment_error": enrichment_error,
            "unmatched_identity_count": int(
                frame.loc[frame["Symbol"].isna(), "InsCode"].nunique()
            ),
            "is_partial": True,
        }
    )
    frame.attrs.update(attrs)
    return frame


def get_major_shareholder_changes(
    date=None,
    days=5,
    symbol=None,
    *,
    ins_code=None,
    holder=None,
    direction="both",
    enrich_identity=True,
    progress=True,
):
    """Return changes between consecutive recent TSETMC snapshots.

    ``direction`` accepts ``both`` (non-zero changes), ``increase``,
    ``decrease`` or ``unchanged``. A requested date must be one of the dates
    currently published by the rolling five-date source.
    """
    requested_days = _positive_days(days)
    selected_date = _date(date)
    direction_key = str(direction).strip().lower()
    if direction_key not in {"both", "increase", "decrease", "unchanged"}:
        raise InvalidParameterError(
            "direction must be one of: both, increase, decrease, unchanged"
        )
    snapshots = get_major_shareholder_snapshots(
        days=5,
        symbol=symbol,
        ins_code=ins_code,
        holder=holder,
        enrich_identity=enrich_identity,
        progress=progress,
    )
    base_attrs = dict(snapshots.attrs)
    available_dates = [
        datetime.date.fromisoformat(x) for x in base_attrs["available_dates"]
    ]
    if selected_date is not None and selected_date not in available_dates:
        raise InvalidParameterError(
            "date is outside the five-date provider window; available dates: {}".format(
                ", ".join(value.isoformat() for value in available_dates)
            )
        )
    if snapshots.empty:
        result = _typed_empty(MAJOR_SHAREHOLDER_CHANGE_COLUMNS)
    else:
        work = snapshots.sort_values(
            ["HolderRecord", "InsCode", "GregorianDate"], kind="mergesort"
        ).copy()
        groups = work.groupby(["HolderRecord", "InsCode"], sort=False)
        work["PreviousHoldings"] = groups["Holdings"].shift(1)
        work["PreviousGregorianDate"] = groups["GregorianDate"].shift(1)
        work["PreviousJalaliDate"] = groups["JalaliDate"].shift(1)
        work = work.loc[work["PreviousHoldings"].notna()].copy()
        work["ChangeShares"] = work["Holdings"] - work["PreviousHoldings"]
        work["Direction"] = "unchanged"
        work.loc[work["ChangeShares"] > 0, "Direction"] = "increase"
        work.loc[work["ChangeShares"] < 0, "Direction"] = "decrease"
        if selected_date is not None:
            work = work.loc[work["GregorianDate"] == selected_date]
        else:
            selected_dates = set(available_dates[-requested_days:])
            work = work.loc[work["GregorianDate"].isin(selected_dates)]
        if direction_key == "both":
            work = work.loc[work["ChangeShares"] != 0]
        else:
            work = work.loc[work["Direction"] == direction_key]
        result = _cast(work, MAJOR_SHAREHOLDER_CHANGE_COLUMNS)
        result = result.sort_values(
            ["GregorianDate", "ChangeShares", "InsCode", "HolderRecord"],
            ascending=[True, False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
    base_attrs.update(
        {
            "analysis": "major_shareholder_changes",
            "requested_days": requested_days,
            "selected_date": (
                None if selected_date is None else selected_date.isoformat()
            ),
            "direction": direction_key,
            "comparison_semantics": "Holdings minus PreviousHoldings",
            "oldest_snapshot_has_no_prior_comparison": True,
        }
    )
    result.attrs.update(base_attrs)
    return result


def get_active_shareholders(
    symbol=None,
    days=5,
    *,
    ins_code=None,
    holder=None,
    enrich_identity=True,
    progress=True,
):
    """Summarize holders with non-zero activity in the recent rolling window."""
    changes = get_major_shareholder_changes(
        days=days,
        symbol=symbol,
        ins_code=ins_code,
        holder=holder,
        direction="both",
        enrich_identity=enrich_identity,
        progress=progress,
    )
    base_attrs = dict(changes.attrs)
    if changes.empty:
        result = _typed_empty(ACTIVE_SHAREHOLDER_COLUMNS)
    else:
        rows = []
        group_columns = [
            "HolderRecord",
            "HolderName",
            "InsCode",
            "Symbol",
            "InstrumentName",
        ]
        for keys, group in changes.groupby(group_columns, dropna=False, sort=False):
            ordered = group.sort_values("GregorianDate", kind="mergesort")
            net = int(ordered["ChangeShares"].sum())
            gross_increase = int(ordered["ChangeShares"].clip(lower=0).sum())
            gross_decrease = int((-ordered["ChangeShares"].clip(upper=0)).sum())
            if net > 0:
                activity = "accumulation"
            elif net < 0:
                activity = "distribution"
            else:
                activity = "mixed"
            first, last = ordered.iloc[0], ordered.iloc[-1]
            rows.append(
                {
                    **dict(zip(group_columns, keys)),
                    "FirstGregorianDate": first["PreviousGregorianDate"],
                    "FirstJalaliDate": first["PreviousJalaliDate"],
                    "LastGregorianDate": last["GregorianDate"],
                    "LastJalaliDate": last["JalaliDate"],
                    "InitialHoldings": first["PreviousHoldings"],
                    "LatestHoldings": last["Holdings"],
                    "NetChangeShares": net,
                    "GrossIncreaseShares": gross_increase,
                    "GrossDecreaseShares": gross_decrease,
                    "ActiveDays": len(ordered),
                    "ActivityDirection": activity,
                    "Source": _SOURCE,
                    "FetchedAt": last["FetchedAt"],
                }
            )
        result = _cast(pd.DataFrame(rows), ACTIVE_SHAREHOLDER_COLUMNS)
        result = result.assign(_AbsNet=result["NetChangeShares"].abs()).sort_values(
            ["_AbsNet", "GrossIncreaseShares", "InsCode"],
            ascending=[False, False, True],
            kind="mergesort",
        )
        result = result.drop(columns="_AbsNet").reset_index(drop=True)
    base_attrs.update(
        {
            "analysis": "active_shareholders",
            "activity_definition": (
                "at least one non-zero consecutive-snapshot change"
            ),
            "net_change_semantics": (
                "sum of observed changes in selected rolling window"
            ),
        }
    )
    result.attrs.update(base_attrs)
    return result


def rank_shareholder_accumulation(
    days=5,
    symbol=None,
    *,
    ins_code=None,
    holder=None,
    direction="both",
    metric="percent",
    top=20,
    enrich_identity=True,
    progress=True,
):
    """Rank recent holder/instrument activity without merging unlike shares.

    Each ranked row remains one holder/instrument pair. This avoids adding raw
    share counts across instruments with different prices and capital bases.
    ``metric`` is ``percent`` (relative to initial disclosed holdings) or
    ``shares``. ``direction`` is ``both``, ``accumulation`` or ``distribution``.
    """
    requested_top = _positive_integer(top, "top")
    direction_key = _choice(
        direction,
        "direction",
        {"both", "accumulation", "distribution"},
    )
    metric_key = _choice(metric, "metric", {"percent", "shares"})
    active = get_active_shareholders(
        symbol=symbol,
        days=days,
        ins_code=ins_code,
        holder=holder,
        enrich_identity=enrich_identity,
        progress=progress,
    )
    base_attrs = dict(active.attrs)
    if active.empty:
        result = _typed_empty(SHAREHOLDER_ACCUMULATION_RANK_COLUMNS)
    else:
        work = active.copy()
        if direction_key != "both":
            work = work.loc[work["ActivityDirection"] == direction_key].copy()
        denominator = pd.to_numeric(work["InitialHoldings"], errors="coerce")
        numerator = pd.to_numeric(work["NetChangeShares"], errors="coerce")
        work["NetChangePercent"] = pd.array(
            (numerator / denominator.where(denominator > 0) * 100), dtype="Float64"
        )
        score_source = (
            work["NetChangePercent"]
            if metric_key == "percent"
            else work["NetChangeShares"].astype("Float64")
        )
        work["Score"] = score_source.abs()
        work["RankingMetric"] = metric_key
        work = work.sort_values(
            ["Score", "GrossIncreaseShares", "InsCode", "HolderRecord"],
            ascending=[False, False, True, True],
            na_position="last",
            kind="mergesort",
        ).head(requested_top)
        work["Rank"] = pd.array(range(1, len(work) + 1), dtype="Int64")
        result = _cast(work, SHAREHOLDER_ACCUMULATION_RANK_COLUMNS)
        result = result.reset_index(drop=True)
    base_attrs.update(
        {
            "analysis": "shareholder_accumulation_ranking",
            "direction": direction_key,
            "ranking_metric": metric_key,
            "top": requested_top,
            "ranking_unit": "holder_instrument_pair",
            "cross_instrument_share_counts_are_not_summed": True,
            "score_semantics": "absolute magnitude of selected metric",
        }
    )
    result.attrs.update(base_attrs)
    return result


def get_shareholder_network(
    date=None,
    symbol=None,
    *,
    ins_code=None,
    holder=None,
    min_holdings=0,
    enrich_identity=True,
    progress=True,
):
    """Return a bipartite holder-instrument edge list for one recent snapshot.

    ``date`` must be one of the at-most-five dates currently published by the
    market-wide feed. When omitted, only its latest date is used. Holder node
    IDs are scoped to this response because TSETMC does not publish a stable
    holder identifier in this feed.
    """
    minimum = _non_negative_integer(min_holdings, "min_holdings")
    snapshots = get_major_shareholder_snapshots(
        date=date,
        days=1,
        symbol=symbol,
        ins_code=ins_code,
        holder=holder,
        enrich_identity=enrich_identity,
        progress=progress,
    )
    base_attrs = dict(snapshots.attrs)
    if snapshots.empty:
        result = _typed_empty(SHAREHOLDER_NETWORK_COLUMNS)
    else:
        work = snapshots.loc[snapshots["Holdings"] >= minimum].copy()
        work["HolderNode"] = work["HolderRecord"].map(
            lambda value: "holder:{}".format(int(value))
        )
        work["InstrumentNode"] = work["InsCode"].map(
            lambda value: "instrument:{}".format(value)
        )
        work["HolderInstrumentCount"] = work.groupby("HolderNode")[
            "InstrumentNode"
        ].transform("nunique")
        work["InstrumentHolderCount"] = work.groupby("InstrumentNode")[
            "HolderNode"
        ].transform("nunique")
        work = work.sort_values(
            ["HolderInstrumentCount", "Holdings", "HolderRecord", "InsCode"],
            ascending=[False, False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
        work["EdgeRecord"] = pd.array(range(1, len(work) + 1), dtype="Int64")
        result = _cast(work, SHAREHOLDER_NETWORK_COLUMNS)
    base_attrs.update(
        {
            "analysis": "shareholder_instrument_network",
            "network_type": "bipartite_edge_list",
            "snapshot_only": True,
            "min_holdings": minimum,
            "holder_node_scope": "current provider response only",
            "stable_shareholder_id_available": False,
        }
    )
    result.attrs.update(base_attrs)
    return result


def get_ownership_concentration(
    symbol="",
    date=None,
    *,
    ins_code=None,
    asset_type="auto",
    top_n=5,
    progress=True,
):
    """Summarize concentration within TSETMC's disclosed major-holder list.

    The result is not a full ownership-register concentration measure. HHI is
    calculated once on total-company percentage points (``MajorHolderHHI``)
    and once after normalizing only the disclosed major-holder slice
    (``NormalizedDisclosedHHI``).
    """
    requested_top = _positive_integer(top_n, "top_n")
    _bool(progress, "progress")
    identity = resolve_instrument(
        symbol,
        ins_code=ins_code,
        asset_type=asset_type,
        require_active=False,
    )
    from .shareholders import shareholders

    snapshot = shareholders(
        "",
        date=date,
        include_id=False,
        ins_code=identity.ins_code,
        # Identity and asset type have already been resolved above. Supplying
        # only the canonical code avoids a second symbol/code reconciliation.
        asset_type="auto",
    )
    if snapshot is None:
        raise DataParsingError("shareholder snapshot could not be constructed")
    percentages = pd.to_numeric(
        snapshot.get("percentage_of_shares", pd.Series(dtype="float64")),
        errors="coerce",
    ).dropna()
    if (percentages < 0).any():
        raise DataParsingError("shareholder percentages must be non-negative")
    if (percentages > 100).any():
        raise DataParsingError("each shareholder percentage cannot exceed 100")
    ordered = percentages.sort_values(ascending=False, kind="mergesort")
    disclosed = float(ordered.sum())
    if disclosed > 100.5:
        raise DataParsingError(
            "disclosed shareholder percentages cannot materially exceed 100"
        )

    def top_percent(count):
        return float(ordered.head(count).sum())

    major_hhi = float((ordered**2).sum())
    normalized_hhi = (
        float(((ordered / disclosed) ** 2).sum() * 10000)
        if disclosed > 0
        else float("nan")
    )
    effective_values = (
        snapshot["effective_date"].dropna().astype(str).unique().tolist()
        if "effective_date" in snapshot
        else []
    )
    trade_values = (
        snapshot["trade_date"].dropna().astype(str).unique().tolist()
        if "trade_date" in snapshot
        else []
    )
    jalali_values = (
        snapshot["effective_date_jalali"].dropna().astype(str).unique().tolist()
        if "effective_date_jalali" in snapshot
        else []
    )
    row = {
        "InsCode": identity.ins_code,
        "Symbol": identity.symbol or pd.NA,
        "InstrumentName": identity.name or pd.NA,
        "TradeDate": trade_values[0] if len(trade_values) == 1 else pd.NA,
        "EffectiveDate": (effective_values[0] if len(effective_values) == 1 else pd.NA),
        "EffectiveDateJalali": (jalali_values[0] if len(jalali_values) == 1 else pd.NA),
        "MajorHolderCount": len(snapshot),
        "DisclosedOwnershipPercent": disclosed,
        "UndisclosedOrBelowThresholdPercent": max(0.0, 100.0 - disclosed),
        "LargestHolderPercent": top_percent(1),
        "Top1Percent": top_percent(1),
        "Top3Percent": top_percent(3),
        "Top5Percent": top_percent(5),
        "Top10Percent": top_percent(10),
        "TopN": requested_top,
        "TopNPercent": top_percent(requested_top),
        "MajorHolderHHI": major_hhi,
        "NormalizedDisclosedHHI": normalized_hhi,
        "Source": snapshot.attrs.get("source", "tsetmc_major_shareholders"),
    }
    result = _cast(pd.DataFrame([row]), OWNERSHIP_CONCENTRATION_COLUMNS)
    result.attrs.update(dict(snapshot.attrs))
    result.attrs.update(
        {
            "analysis": "ownership_concentration",
            "top_n": requested_top,
            "hhi_scale": "0_to_10000",
            "major_holder_hhi_basis": "reported percentages of total company",
            "major_holder_hhi_is_lower_bound_on_full_hhi": True,
            "normalized_disclosed_hhi_basis": (
                "reported major-holder slice normalized to 100 percent"
            ),
            "is_full_ownership_register": False,
            "unreported_remainder_is_not_assumed_to_be_one_holder": True,
        }
    )
    if progress:
        print(
            "Done. Ownership concentration calculated for {}.".format(identity.ins_code)
        )
    return result


def _positive_integer(value, name):
    if isinstance(value, bool):
        raise InvalidParameterError("{} must be a positive integer".format(name))
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(
            "{} must be a positive integer".format(name)
        ) from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise InvalidParameterError("{} must be a positive integer".format(name))
    return int(number)


def _non_negative_integer(value, name):
    if isinstance(value, bool):
        raise InvalidParameterError("{} must be a non-negative integer".format(name))
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(
            "{} must be a non-negative integer".format(name)
        ) from exc
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise InvalidParameterError("{} must be a non-negative integer".format(name))
    return int(number)


def _choice(value, name, choices):
    key = str(value).strip().lower()
    if key not in choices:
        raise InvalidParameterError(
            "{} must be one of: {}".format(name, ", ".join(sorted(choices)))
        )
    return key


__all__ = [
    "MAJOR_SHAREHOLDER_SNAPSHOT_COLUMNS",
    "MAJOR_SHAREHOLDER_CHANGE_COLUMNS",
    "ACTIVE_SHAREHOLDER_COLUMNS",
    "SHAREHOLDER_ACCUMULATION_RANK_COLUMNS",
    "SHAREHOLDER_NETWORK_COLUMNS",
    "OWNERSHIP_CONCENTRATION_COLUMNS",
    "get_major_shareholder_snapshots",
    "get_major_shareholder_changes",
    "get_active_shareholders",
    "rank_shareholder_accumulation",
    "get_shareholder_network",
    "get_ownership_concentration",
]
