"""TSETMC price-adjustment events with explicit identity provenance.

The provider reports price discontinuities but does not authoritatively label
them as cash dividends.  Consequently this module never manufactures a DPS
series from the difference between adjusted and unadjusted prices.
"""

import datetime
import json
import math
from numbers import Integral

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from .._clock import tehran_now
from ..exceptions import (
    ConnectionError,
    DataParsingError,
    InvalidParameterError,
)
from ..http_client import safe_get
from ..settings import settings
from .conventions import coerce_financial_date
from .resolver import resolve_instrument

PRICE_ADJUSTMENT_COLUMNS = [
    "InsCode",
    "Symbol",
    "GregorianDate",
    "JalaliDate",
    "AdjustedClosingPrice",
    "UnadjustedClosingPrice",
    "AdjustmentAmount",
    "CorporateTypeCode",
    "CorporateActionType",
    "IsConfirmedDPS",
    "IdentityVerified",
    "Source",
    "FetchedAt",
]


def _typed_empty():
    frame = pd.DataFrame(columns=PRICE_ADJUSTMENT_COLUMNS)
    for column in (
        "InsCode",
        "Symbol",
        "JalaliDate",
        "CorporateTypeCode",
        "CorporateActionType",
        "Source",
    ):
        frame[column] = pd.Series(dtype="string")
    frame["GregorianDate"] = pd.Series(dtype="object")
    for column in (
        "AdjustedClosingPrice",
        "UnadjustedClosingPrice",
        "AdjustmentAmount",
    ):
        frame[column] = pd.Series(dtype="Float64")
    for column in ("IsConfirmedDPS", "IdentityVerified"):
        frame[column] = pd.Series(dtype="boolean")
    frame["FetchedAt"] = pd.Series(dtype="datetime64[ns, Asia/Tehran]")
    return frame


def _attrs(frame, *, identity, fetched_at):
    frame.attrs.update(
        {
            "source": "tsetmc_price_adjustment",
            "endpoint": "ClosingPrice/GetPriceAdjustList/{InsCode}",
            "ins_code": identity.ins_code,
            "symbol": identity.symbol,
            "identity_provenance": identity.provenance,
            "provenance": "tsetmc_server_history",
            "fetched_at": fetched_at,
            "dps_available": False,
            "dps_reason": "tsetmc_does_not_classify_adjustments_as_dividends",
            "no_backfill": False,
        }
    )
    return frame


def _date(value, name):
    if value is None:
        return None
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def _provider_date(value, context):
    if isinstance(value, bool) or isinstance(value, float):
        raise DataParsingError(
            "{}: dEven must be an exact YYYYMMDD integer".format(context)
        )
    if isinstance(value, Integral):
        text = str(int(value))
    else:
        text = "" if value is None else str(value).strip()
    if len(text) != 8 or not text.isascii() or not text.isdigit():
        raise DataParsingError(
            "{}: dEven must be an exact YYYYMMDD value".format(context)
        )
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise DataParsingError("{}: dEven is not a valid date".format(context)) from exc


def _row_ins_code(value, requested, context):
    if value is None or value is pd.NA:
        return requested, False
    if isinstance(value, bool) or isinstance(value, float):
        raise DataParsingError(
            "{}: insCode must be an exact decimal string".format(context)
        )
    if isinstance(value, Integral):
        text = str(int(value))
    else:
        text = str(value).strip()
    if text in {"", "0"}:
        return requested, False
    if not text.isascii() or not text.isdigit():
        raise DataParsingError(
            "{}: insCode must be an exact decimal string".format(context)
        )
    if text != requested:
        raise DataParsingError(
            "{}: response InsCode {!r} does not match requested {!r}".format(
                context, text, requested
            )
        )
    return text, True


def _price(value, field, context):
    if value is None or value is pd.NA or isinstance(value, bool):
        raise DataParsingError("{}: {} is missing or invalid".format(context, field))
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataParsingError("{}: {} must be numeric".format(context, field)) from exc
    if not math.isfinite(result) or result < 0:
        raise DataParsingError(
            "{}: {} must be finite and non-negative".format(context, field)
        )
    return result


def _corporate_code(value):
    if value is None or value is pd.NA:
        return pd.NA
    text = str(value).strip()
    return pd.NA if text in {"", "None", "nan"} else text


def _records(response):
    try:
        payload = response.json()
    except (ValueError, AttributeError, TypeError) as exc:
        raise DataParsingError("invalid TSETMC price-adjustment response") from exc
    if not isinstance(payload, dict) or not isinstance(
        payload.get("priceAdjust"), list
    ):
        raise DataParsingError("price-adjustment response has no priceAdjust list")
    return payload["priceAdjust"]


def _raw_fingerprint(record):
    """Return a stable identity for one complete provider record."""
    try:
        return json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataParsingError("price-adjustment record is not serializable") from exc


def _cast(rows):
    if not rows:
        return _typed_empty()
    result = pd.DataFrame(rows).reindex(columns=PRICE_ADJUSTMENT_COLUMNS)
    for column in (
        "InsCode",
        "Symbol",
        "JalaliDate",
        "CorporateTypeCode",
        "CorporateActionType",
        "Source",
    ):
        result[column] = result[column].astype("string")
    for column in (
        "AdjustedClosingPrice",
        "UnadjustedClosingPrice",
        "AdjustmentAmount",
    ):
        result[column] = pd.to_numeric(result[column], errors="raise").astype("Float64")
    for column in ("IsConfirmedDPS", "IdentityVerified"):
        result[column] = result[column].astype("boolean")
    result["FetchedAt"] = (
        pd.to_datetime(result["FetchedAt"], utc=True)
        .dt.tz_convert("Asia/Tehran")
        .astype("datetime64[ns, Asia/Tehran]")
    )
    return result


def get_price_adjustments(
    symbol=None,
    *,
    ins_code=None,
    start=None,
    end=None,
    progress=True,
):
    """Return TSETMC price-adjustment events for one exact instrument.

    Date bounds are inclusive and accept Gregorian or Jalali ISO dates.  A
    price discontinuity is not classified as DPS: ``IsConfirmedDPS`` is always
    false and ``CorporateActionType`` remains nullable unless TSETMC adds an
    authoritative classification to this endpoint.
    """
    if not isinstance(progress, bool):
        raise InvalidParameterError("progress must be bool")
    first, last = _date(start, "start"), _date(end, "end")
    if first is not None and last is not None and first > last:
        raise InvalidParameterError("start must be less than or equal to end")
    identity = resolve_instrument(
        symbol,
        ins_code=ins_code,
        asset_type="auto",
        require_active=False,
    )
    fetched_at = tehran_now()
    try:
        response = safe_get(settings.url_price_adjustments.format(identity.ins_code))
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        else:
            status_code = getattr(response, "status_code", 200)
            if isinstance(status_code, int) and status_code >= 400:
                raise requests.exceptions.HTTPError(
                    "TSETMC price-adjustment HTTP status {}".format(status_code),
                    response=response,
                )
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(
            "TSETMC price-adjustment request failed for {!r}".format(identity.ins_code)
        ) from exc
    rows = []
    for offset, record in enumerate(_records(response)):
        context = "priceAdjust[{}]".format(offset)
        if not isinstance(record, dict):
            raise DataParsingError("{} must be an object".format(context))
        event_date = _provider_date(record.get("dEven"), context)
        row_code, verified = _row_ins_code(
            record.get("insCode"), identity.ins_code, context
        )
        if first is not None and event_date < first:
            continue
        if last is not None and event_date > last:
            continue
        adjusted = _price(record.get("pClosing"), "pClosing", context)
        unadjusted = _price(
            record.get("pClosingNotAdjusted"), "pClosingNotAdjusted", context
        )
        instrument = record.get("instrument")
        provider_symbol = None
        if isinstance(instrument, dict):
            provider_symbol = instrument.get("lVal18AFC", instrument.get("lVal18"))
        rows.append(
            {
                "InsCode": row_code,
                "Symbol": identity.symbol or provider_symbol or pd.NA,
                "GregorianDate": event_date,
                "JalaliDate": JalaliDate.to_jalali(event_date).isoformat(),
                "AdjustedClosingPrice": adjusted,
                "UnadjustedClosingPrice": unadjusted,
                "AdjustmentAmount": unadjusted - adjusted,
                "CorporateTypeCode": _corporate_code(record.get("corporateTypeCode")),
                "CorporateActionType": pd.NA,
                "IsConfirmedDPS": False,
                "IdentityVerified": verified,
                "Source": "tsetmc_price_adjustment",
                "FetchedAt": fetched_at,
                "_RawFingerprint": _raw_fingerprint(record),
            }
        )
    if rows:
        raw_rows = pd.DataFrame(rows)
        # Only byte-for-byte-equivalent provider records are duplicates.  The
        # public date/price tuple is not an event identity: corporate-action
        # code, reported identity and nested provider fields may distinguish
        # legitimate same-day adjustments.
        raw_rows = raw_rows.drop_duplicates("_RawFingerprint", keep="first")
        raw_rows = raw_rows.sort_values("GregorianDate", kind="mergesort")
        result = _cast(
            raw_rows.drop(columns=["_RawFingerprint"]).to_dict(orient="records")
        ).reset_index(drop=True)
    else:
        result = _typed_empty()
    return _attrs(result, identity=identity, fetched_at=fetched_at)


def get_latest_price_adjustment(
    symbol=None,
    *,
    ins_code=None,
    start=None,
    end=None,
    progress=True,
):
    """Return the latest matching adjustment as a typed zero-or-one-row frame."""
    history = get_price_adjustments(
        symbol,
        ins_code=ins_code,
        start=start,
        end=end,
        progress=progress,
    )
    attrs = dict(history.attrs)
    result = history.tail(1).reset_index(drop=True)
    result.attrs.update(attrs)
    return result


__all__ = [
    "PRICE_ADJUSTMENT_COLUMNS",
    "get_price_adjustments",
    "get_latest_price_adjustment",
]
