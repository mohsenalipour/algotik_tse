"""Exact, type-aware TSETMC instrument resolution.

The search endpoint is intentionally used only as a source of candidates.  A
candidate must still match the normalized ticker or full name exactly; fuzzy
ordering returned by TSETMC is never treated as identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

VALID_ASSET_TYPES = frozenset(
    {"auto", "equity", "index", "industry", "fund", "bond", "option"}
)

_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_instrument_text(value: Any) -> str:
    """Return one canonical comparison form for Persian instrument text."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).translate(_DIGIT_TRANSLATION)
    text = text.replace("\u0643", "\u06a9").replace("\u064a", "\u06cc")
    text = text.replace("\u0649", "\u06cc")
    text = text.replace("\u200c", " ").replace("\u200d", " ")
    text = text.replace("\ufeff", " ").replace("\u00a0", " ")
    return " ".join(text.split())


@dataclass(frozen=True)
class InstrumentRef:
    """Immutable canonical identity returned by :func:`resolve_instrument`."""

    ins_code: str
    symbol: str | None = None
    name: str | None = None
    asset_type: str = "unknown"
    is_active: bool | None = None
    provenance: str = ""
    selector: str | None = None

    @property
    def web_id(self) -> str:
        """Backward-friendly alias for the canonical TSETMC InsCode."""
        return self.ins_code


# The order matches the long-standing public aliases in ``settings.index_names``.
_INDEX_CODES = (
    "32097828799138957",
    "67130298613737946",
    "67130298613737946",
    "67130298613737946",
    "67130298613737946",
    "67130298613737946",
    "5798407779416661",
    "8384385859414435",
    "8384385859414435",
    "8384385859414435",
    "49579049405614711",
    "49579049405614711",
    "62752761908615603",
    "71704845530629737",
    "43754960038275285",
    "10523825119011581",
    "10523825119011581",
    "10523825119011581",
    "46342955726788357",
    "46342955726788357",
    "46342955726788357",
    "46342955726788357",
    "46342955726788357",
    "46342955726788357",
)

# Verified TSETMC ``yVal``/MarketWatch ``InstrumentType`` values used by this
# package. Codes not listed here deliberately remain ``unknown``.
INSTRUMENT_TYPE_ASSET_MAP = {
    "300": "equity",
    "303": "equity",
    "309": "equity",
    "305": "fund",
    "306": "bond",
    "311": "option",
    "312": "option",
    "706": "bond",
}

MAX_TYPE_ENRICHMENT_CANDIDATES = 8


def _index_registry() -> dict[str, tuple[str, str]]:
    return {
        normalize_instrument_text(name): (str(code), str(name))
        for name, code in zip(settings.index_names, _INDEX_CODES)
    }


def _industry_registry() -> dict[str, tuple[str, str]]:
    # Imported lazily to keep ``search.py``'s public registries compatible
    # without creating a module-import cycle.
    from .search import _INDUSTRY_DICT, INDUSTRY_NAMES

    result = {}
    for alias, code in _INDUSTRY_DICT.items():
        result[normalize_instrument_text(alias)] = (
            str(code),
            INDUSTRY_NAMES.get(str(code), alias),
        )
    return result


def _validate_asset_type(asset_type: str) -> str:
    normalized = str(asset_type).strip().lower()
    if normalized not in VALID_ASSET_TYPES:
        allowed = ", ".join(sorted(VALID_ASSET_TYPES))
        raise InvalidParameterError(
            f"asset_type must be one of {allowed}; got {asset_type!r}"
        )
    return normalized


def validate_ins_code(value: Any) -> str:
    """Validate and return one canonical ASCII TSETMC ``InsCode``.

    The public resolver deliberately does not translate Persian/Arabic digits
    for identifiers: an identifier is an opaque provider key, not display
    text.  Zero, signs, whitespace within the value, and values longer than 20
    digits are rejected with :class:`InvalidParameterError`.
    """
    code = "" if value is None else str(value).strip()
    if not code or not code.isascii() or not code.isdigit():
        raise InvalidParameterError("ins_code must contain only decimal digits")
    # TSETMC uses numeric identifiers.  Reject pathological/accidental values
    # while retaining legacy short fixture identifiers used by callers/tests.
    if len(code) > 20 or int(code) <= 0:
        raise InvalidParameterError(f"invalid TSETMC ins_code: {value!r}")
    return code


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    if missing is pd.NA:
        return True
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _row_value(row: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(row, pd.Series) and key in row.index:
            value = row[key]
        elif isinstance(row, dict) and key in row:
            value = row[key]
        else:
            continue
        if not _is_missing(value):
            return value
    return None


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if _is_missing(value):
        return None
    text = normalize_instrument_text(value).lower()
    if text in {"1", "true", "active", "فعال", "open", "listed"}:
        return True
    if text in {"0", "false", "inactive", "غیرفعال", "بسته", "delisted"}:
        return False
    return None


def _active_from_row(row: Any, *, snapshot: bool = False) -> bool | None:
    if snapshot:
        return True
    for key in (
        "isActive",
        "is_active",
        "active",
        "instrumentIsActive",
        "listed",
        "lastDate",
        "last_date",
    ):
        parsed = _parse_bool(_row_value(row, key))
        if parsed is not None:
            return parsed
    status = _row_value(row, "status", "instrumentStatus", "state")
    return _parse_bool(status)


def _asset_type_from_row(row: Any) -> str:
    keys = (
        "asset_type",
        "AssetType",
        "InstrumentType",
        "instrumentType",
        "instrumentTypeName",
        "type",
        "typeName",
        "securityType",
        "yVal",
    )
    for key in keys:
        explicit = _row_value(row, key)
        text = normalize_instrument_text(explicit).lower()
        if not text:
            continue
        if text in INSTRUMENT_TYPE_ASSET_MAP:
            return INSTRUMENT_TYPE_ASSET_MAP[text]
        if text in VALID_ASSET_TYPES - {"auto"}:
            return text
        if any(token in text for token in ("اختیار", "option")):
            return "option"
        if any(token in text for token in ("صندوق", "fund", "etf")):
            return "fund"
        if any(
            token in text
            for token in (
                "اوراق",
                "اخزا",
                "اسناد خزانه",
                "صکوک",
                "bond",
                "debt",
            )
        ):
            return "bond"
        if any(token in text for token in ("شاخص صنعت", "industry index")):
            return "industry"
        if any(token in text for token in ("شاخص", "index")):
            return "index"
        if any(token in text for token in ("سهام", "equity", "stock")):
            return "equity"
    return "unknown"


def _candidate(row: Any, provenance: str, *, snapshot: bool = False) -> dict:
    code = normalize_instrument_text(_row_value(row, "InsCode", "insCode"))
    return {
        "ins_code": code,
        "symbol": _row_value(row, "Symbol", "lVal18AFC", "lVal18"),
        "name": _row_value(row, "Name", "lVal30", "instrumentName"),
        "asset_type": _asset_type_from_row(row),
        "is_active": _active_from_row(row, snapshot=snapshot),
        "provenance": provenance,
    }


def _snapshot_rows(snapshot: Any) -> list[Any]:
    if isinstance(snapshot, dict):
        snapshot = snapshot.get("stocks")
    if not isinstance(snapshot, pd.DataFrame) or snapshot.empty:
        return []
    return [row for _, row in snapshot.iterrows()]


def _response_json(response, endpoint: str) -> dict:
    try:
        payload = response.json()
    except (ValueError, AttributeError, TypeError) as exc:
        raise DataParsingError(f"invalid {endpoint} response") from exc
    if not isinstance(payload, dict):
        raise DataParsingError(f"unexpected {endpoint} response shape")
    return payload


def _search_rows(selector: str, cache: dict) -> list[dict]:
    key = ("search", selector)
    if key in cache:
        return cache[key]
    try:
        response = safe_get(settings.url_search.format(selector))
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"instrument search failed for {selector!r}") from exc
    payload = _response_json(response, "instrument search")
    rows = payload.get("instrumentSearch") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise DataParsingError(
            "instrument search response has no instrumentSearch list"
        )
    cache[key] = rows
    return rows


def _instrument_info(ins_code: str, cache: dict) -> dict:
    key = ("instrument_info", ins_code)
    if key in cache:
        return cache[key]
    try:
        response = safe_get(settings.url_instrument_information.format(ins_code))
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f"instrument info failed for {ins_code!r}") from exc
    payload = _response_json(response, "instrument info")
    row = payload.get("instrumentInfo")
    if not isinstance(row, dict):
        raise DataParsingError("instrument info response has no instrumentInfo object")
    row = dict(row)
    reported_value = _row_value(row, "InsCode", "insCode")
    if _is_missing(reported_value) or str(reported_value).strip() in {"", "0"}:
        reported = None
    else:
        try:
            reported = validate_ins_code(reported_value)
        except InvalidParameterError as exc:
            raise DataParsingError(
                "instrument info returned a non-canonical InsCode"
            ) from exc
    if reported is None:
        raise DataParsingError("instrument info response has no authoritative InsCode")
    if reported != ins_code:
        raise DataParsingError(
            f"instrument info InsCode {reported!r} does not match requested "
            f"{ins_code!r}"
        )
    cache[key] = row
    return row


def _select_unique(candidates: list[dict], selector: str, require_active: bool) -> dict:
    unique = {}
    for item in candidates:
        if item["ins_code"]:
            code = item["ins_code"]
            if code not in unique:
                unique[code] = dict(item)
                continue
            current = unique[code]
            for field in ("symbol", "name"):
                if _is_missing(current.get(field)) and not _is_missing(item.get(field)):
                    current[field] = item[field]
            if (
                current.get("asset_type") == "unknown"
                and item.get("asset_type") != "unknown"
            ):
                current["asset_type"] = item["asset_type"]
            states = {current.get("is_active"), item.get("is_active")}
            current["is_active"] = (
                True if True in states else False if False in states else None
            )
            provenance = [
                value
                for value in (
                    current.get("provenance", ""),
                    item.get("provenance", ""),
                )
                if value
            ]
            current["provenance"] = "+".join(dict.fromkeys(provenance))
    values = list(unique.values())
    if require_active:
        usable = [item for item in values if item["is_active"] is not False]
        if usable:
            values = usable
        else:
            raise StockNotFoundError(f"No active instrument matched {selector!r}")
        confirmed = [item for item in values if item["is_active"] is True]
        if confirmed:
            values = confirmed
    if not values:
        raise StockNotFoundError(f"No exact instrument matched {selector!r}")
    if len(values) != 1:
        public_candidates = [
            {
                "ins_code": item["ins_code"],
                "symbol": item["symbol"],
                "name": item["name"],
                "asset_type": item["asset_type"],
                "is_active": item["is_active"],
            }
            for item in values
        ]
        raise AmbiguousSymbolError(
            f"Selector {selector!r} matched {len(values)} same-rank instruments: "
            f"{public_candidates}"
        )
    return values[0]


def _make_ref(item: dict, selector: Any) -> InstrumentRef:
    return InstrumentRef(
        ins_code=item["ins_code"],
        symbol=None if _is_missing(item.get("symbol")) else str(item["symbol"]),
        name=None if _is_missing(item.get("name")) else str(item["name"]),
        asset_type=item.get("asset_type", "unknown"),
        is_active=item.get("is_active"),
        provenance=item.get("provenance", ""),
        selector=None if selector is None else str(selector),
    )


def _enrich_selected(item: dict, requested_type: str, cache: dict) -> dict:
    """Enrich one already-selected identity without introducing N+1 calls."""
    needs_identity = _is_missing(item.get("symbol")) or _is_missing(item.get("name"))
    needs_type = item.get("asset_type", "unknown") == "unknown"
    if not (needs_identity or needs_type):
        enriched = dict(item)
    else:
        row = _instrument_info(item["ins_code"], cache)
        reported_code = normalize_instrument_text(_row_value(row, "InsCode", "insCode"))
        if reported_code and reported_code != item["ins_code"]:
            raise DataParsingError(
                "instrument info returned an identity different from requested InsCode"
            )
        info = _candidate(row, "instrument_info")
        enriched = dict(item)
        for field in ("symbol", "name"):
            if _is_missing(enriched.get(field)) and not _is_missing(info.get(field)):
                enriched[field] = info[field]
        if enriched.get("asset_type", "unknown") == "unknown":
            enriched["asset_type"] = info.get("asset_type", "unknown")
        # InstrumentInfo is the authoritative point record for an explicit
        # identity.  Preserve a previously observed status only when that
        # endpoint genuinely omits status information.
        if info.get("is_active") is not None:
            enriched["is_active"] = info["is_active"]
        enriched["provenance"] = "+".join(
            dict.fromkeys(
                value
                for value in (
                    enriched.get("provenance", ""),
                    info.get("provenance", ""),
                )
                if value
            )
        )
    if requested_type != "auto":
        resolved_type = enriched.get("asset_type", "unknown")
        if resolved_type == "unknown":
            raise InvalidParameterError(
                f"asset_type={requested_type!r} could not be verified for "
                f"InsCode {item['ins_code']}"
            )
        if resolved_type != requested_type:
            raise StockNotFoundError(
                f"InsCode {item['ins_code']} is {resolved_type!r}, not "
                f"requested {requested_type!r}"
            )
    return enriched


def _verify_requested_type_candidates(
    candidates: list[dict], requested_type: str, cache: dict
) -> list[dict]:
    """Verify every unknown exact rival before applying a requested type.

    Silently preferring a known typed candidate is unsafe because another
    exact active identity may have the same requested type.  Candidate
    enrichment is bounded to prevent a malformed provider response from
    creating an unbounded sequence of point calls.
    """
    if requested_type == "auto":
        return candidates
    unknown = [item for item in candidates if item.get("asset_type") == "unknown"]
    if len(unknown) > MAX_TYPE_ENRICHMENT_CANDIDATES:
        raise AmbiguousSymbolError(
            f"Too many untyped exact candidates ({len(unknown)}) to verify safely"
        )
    verified = [item for item in candidates if item.get("asset_type") == requested_type]
    for item in unknown:
        try:
            verified.append(_enrich_selected(item, requested_type, cache))
        except StockNotFoundError:
            # InstrumentInfo authoritatively proved a different asset type.
            continue
    return verified


def _local_registry_ref(ins_code: str, requested_type: str, selector: Any):
    """Resolve known local index/industry codes without a provider call."""
    for local_type, registry in (
        ("index", _index_registry()),
        ("industry", _industry_registry()),
    ):
        for alias, (code, name) in registry.items():
            if code != ins_code:
                continue
            if requested_type not in {"auto", local_type}:
                raise StockNotFoundError(
                    f"InsCode {ins_code} is {local_type!r}, not requested "
                    f"{requested_type!r}"
                )
            return InstrumentRef(
                ins_code=code,
                symbol=alias,
                name=name,
                asset_type=local_type,
                is_active=True,
                provenance=f"{local_type}_registry_ins_code",
                selector=None if selector is None else str(selector),
            )
    return None


def _exact_candidates(rows: list[dict], selector_text: str) -> list[dict]:
    ticker = [
        item
        for item in rows
        if normalize_instrument_text(item.get("symbol")) == selector_text
    ]
    if ticker:
        return ticker
    return [
        item
        for item in rows
        if normalize_instrument_text(item.get("name")) == selector_text
    ]


def resolve_instrument(
    selector=None,
    *,
    ins_code=None,
    asset_type="auto",
    snapshot=None,
    require_active=True,
) -> InstrumentRef:
    """Resolve one selector to an exact, canonical instrument identity.

    Priority is: a validated explicit ``ins_code`` (including local index and
    industry registries), an explicit ``شاخص ...`` selector, an exact active
    normalized ticker, an exact normalized full name, then a legacy industry
    alias only when no exact instrument exists.  Substring/fuzzy first hits are
    never identities.  A supplied ``snapshot`` is authoritative, including an
    empty one, so no InstrumentSearch request is made for snapshot misses.

    Without a snapshot the resolver makes at most two cached InstrumentSearch
    calls (the raw selector and one full-name alternate). InstrumentInfo calls
    are bounded and used only to verify selected identity/type or exact unknown
    rivals. ``InstrumentRef.provenance`` records the successful source.

    Raises ``InvalidParameterError`` for invalid/conflicting inputs,
    ``StockNotFoundError`` for no usable exact match, ``AmbiguousSymbolError``
    for same-rank identities, and ``DataParsingError`` when provider identity
    cannot be verified.
    """
    requested_type = _validate_asset_type(asset_type)
    if not isinstance(require_active, bool):
        raise InvalidParameterError("require_active must be bool")
    raw_selector = "" if selector is None else str(selector).strip()
    selector_text = normalize_instrument_text(raw_selector)
    request_cache = {}

    explicit_code = None if ins_code is None else validate_ins_code(ins_code)
    if not selector_text and explicit_code is None:
        raise InvalidParameterError("selector or ins_code is required")

    if selector_text.isascii() and selector_text.isdigit():
        selector_code = validate_ins_code(raw_selector)
        if explicit_code is not None and selector_code != explicit_code:
            raise InvalidParameterError(
                "selector and ins_code refer to different instruments"
            )
        explicit_code = selector_code

    if explicit_code is not None and (
        not selector_text or selector_text == explicit_code
    ):
        local_ref = _local_registry_ref(explicit_code, requested_type, selector)
        if local_ref is not None:
            return local_ref

    snapshot_is_authoritative = snapshot is not None
    snapshot_candidates = [
        _candidate(row, "market_watch_exact", snapshot=True)
        for row in _snapshot_rows(snapshot)
    ]

    if explicit_code is not None and (
        not selector_text or selector_text == explicit_code
    ):
        matches = [
            item for item in snapshot_candidates if item["ins_code"] == explicit_code
        ]
        if matches:
            item = _select_unique(matches, explicit_code, require_active)
            if requested_type != "auto" and item.get("asset_type") == "unknown":
                item = _enrich_selected(item, requested_type, request_cache)
            elif requested_type != "auto" and item.get("asset_type") != requested_type:
                raise StockNotFoundError(
                    f"InsCode {explicit_code} does not match requested asset_type"
                )
            if require_active and item.get("is_active") is False:
                raise StockNotFoundError(
                    f"No active instrument matched InsCode {explicit_code!r}"
                )
            return _make_ref(item, selector)
        if snapshot_is_authoritative:
            if requested_type != "auto":
                raise InvalidParameterError(
                    f"asset_type={requested_type!r} cannot be verified for an "
                    "InsCode absent from the authoritative snapshot"
                )
            return InstrumentRef(
                ins_code=explicit_code,
                asset_type="unknown",
                is_active=None,
                provenance="explicit_ins_code_absent_from_snapshot",
                selector=None if selector is None else str(selector),
            )
        seed = {
            "ins_code": explicit_code,
            "symbol": None,
            "name": None,
            "asset_type": "unknown",
            "is_active": None,
            "provenance": "explicit_ins_code",
        }
        item = _enrich_selected(seed, requested_type, request_cache)
        if require_active and item.get("is_active") is False:
            raise StockNotFoundError(
                f"No active instrument matched InsCode {explicit_code!r}"
            )
        return _make_ref(item, selector)

    indices = _index_registry()
    industries = _industry_registry()

    # An explicit index phrase is authoritative and intentionally outranks a
    # same-text security search result.
    if selector_text.startswith("شاخص "):
        if selector_text in indices and requested_type in {"auto", "index"}:
            code, name = indices[selector_text]
            ref = InstrumentRef(
                code,
                symbol=str(selector),
                name=name,
                asset_type="index",
                is_active=True,
                provenance="index_registry_exact",
                selector=str(selector),
            )
            if explicit_code is not None and explicit_code != ref.ins_code:
                raise InvalidParameterError(
                    "selector and ins_code refer to different instruments"
                )
            return ref
        if selector_text in industries and requested_type in {"auto", "industry"}:
            code, name = industries[selector_text]
            ref = InstrumentRef(
                code,
                symbol=str(selector),
                name=name,
                asset_type="industry",
                is_active=True,
                provenance="industry_registry_explicit",
                selector=str(selector),
            )
            if explicit_code is not None and explicit_code != ref.ins_code:
                raise InvalidParameterError(
                    "selector and ins_code refer to different instruments"
                )
            return ref

    if requested_type == "industry" and selector_text in industries:
        code, name = industries[selector_text]
        ref = InstrumentRef(
            code,
            symbol=str(selector),
            name=name,
            asset_type="industry",
            is_active=True,
            provenance="industry_registry_requested",
            selector=str(selector),
        )
        if explicit_code is not None and explicit_code != ref.ins_code:
            raise InvalidParameterError(
                "selector and ins_code refer to different instruments"
            )
        return ref

    if selector_text in indices and requested_type in {"auto", "index"}:
        code, name = indices[selector_text]
        ref = InstrumentRef(
            code,
            symbol=str(selector),
            name=name,
            asset_type="index",
            is_active=True,
            provenance="index_registry_exact",
            selector=str(selector),
        )
        if explicit_code is not None and explicit_code != ref.ins_code:
            raise InvalidParameterError(
                "selector and ins_code refer to different instruments"
            )
        return ref

    rows = list(snapshot_candidates)
    foreign_exact_seen = bool(_exact_candidates(rows, selector_text))
    if explicit_code is not None:
        rows = [item for item in rows if item["ins_code"] == explicit_code]
    candidates = _exact_candidates(rows, selector_text)
    if not snapshot_is_authoritative:
        all_search_rows = [
            _candidate(row, "tsetmc_search_exact")
            for row in _search_rows(raw_selector, request_cache)
        ]
        foreign_exact_seen = foreign_exact_seen or bool(
            _exact_candidates(all_search_rows, selector_text)
        )
        rows = all_search_rows
        if explicit_code is not None:
            rows = [item for item in rows if item["ins_code"] == explicit_code]
        candidates = _exact_candidates(rows, selector_text)
        if not candidates:
            tokens = selector_text.split()
            alternate = tokens[-1] if len(tokens) > 1 else ""
            if alternate and normalize_instrument_text(
                alternate
            ) != normalize_instrument_text(raw_selector):
                all_alternate_rows = [
                    _candidate(row, "tsetmc_search_exact_alternate")
                    for row in _search_rows(alternate, request_cache)
                ]
                foreign_exact_seen = foreign_exact_seen or bool(
                    _exact_candidates(all_alternate_rows, selector_text)
                )
                alternate_rows = all_alternate_rows
                if explicit_code is not None:
                    alternate_rows = [
                        item
                        for item in alternate_rows
                        if item["ins_code"] == explicit_code
                    ]
                candidates = _exact_candidates(alternate_rows, selector_text)

    if explicit_code is not None and not candidates and foreign_exact_seen:
        raise InvalidParameterError(
            "selector and ins_code refer to different instruments"
        )

    # An explicit canonical code disambiguates identity before any type
    # enrichment. Unrelated exact rivals must not trigger point calls, caps, or
    # provider errors for the identity the caller explicitly selected.
    if explicit_code is not None and candidates:
        candidates = [item for item in candidates if item["ins_code"] == explicit_code]
        if not candidates:
            raise InvalidParameterError(
                "selector and ins_code refer to different instruments"
            )

    if requested_type != "auto" and candidates:
        candidates = _verify_requested_type_candidates(
            candidates, requested_type, request_cache
        )

    if candidates:
        if explicit_code is not None:
            item = _select_unique(candidates, selector_text, require_active)
            item = dict(item)
            item["provenance"] += "+explicit_ins_code_match"
        else:
            item = _select_unique(candidates, selector_text, require_active)
        if item.get("asset_type") == "unknown" and (
            requested_type != "auto" or explicit_code is not None
        ):
            if requested_type != "auto" or not snapshot_is_authoritative:
                item = _enrich_selected(item, requested_type, request_cache)
        elif requested_type != "auto" and item.get("asset_type") != requested_type:
            raise StockNotFoundError(
                f"Selector {selector!r} is not asset_type={requested_type!r}"
            )
        if require_active and item.get("is_active") is False:
            raise StockNotFoundError(f"No active instrument matched {selector!r}")
        return _make_ref(item, selector)

    # Bare industry aliases remain backward compatible only after proving that
    # no exact ticker/full-name instrument exists.
    if selector_text in industries and requested_type in {"auto", "industry"}:
        code, name = industries[selector_text]
        if explicit_code is not None and explicit_code != code:
            raise InvalidParameterError(
                "selector and ins_code refer to different instruments"
            )
        return InstrumentRef(
            code,
            symbol=str(selector),
            name=name,
            asset_type="industry",
            is_active=True,
            provenance="industry_registry_legacy_fallback",
            selector=str(selector),
        )

    raise StockNotFoundError(f"No exact instrument matched {selector!r}")


__all__ = [
    "InstrumentRef",
    "VALID_ASSET_TYPES",
    "normalize_instrument_text",
    "resolve_instrument",
    "validate_ins_code",
]
