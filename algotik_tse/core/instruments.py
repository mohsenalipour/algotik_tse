"""Instrument-specific data functions for options, ETFs, bonds, and funds.

Provides enriched views of market data by combining ``market_watch()``
output with parsed instrument metadata (strike, expiry, NAV, maturity, etc.)
and optional per-instrument API calls for open interest.

Also provides ``list_funds()`` which fetches detailed fund information
(NAV, returns, portfolio composition, manager, etc.) from TSETMC Fund API.
"""

import json
import re
import time
from pathlib import Path
import numpy as np
import pandas as pd

from algotik_tse.settings import settings
from algotik_tse.http_client import safe_get
from algotik_tse.exceptions import InvalidParameterError
from algotik_tse.core.market_data import market_watch
from algotik_tse.core.resolver import normalize_instrument_text
from algotik_tse.core.parsers import (
    parse_option_name,
    parse_option_symbol,
    parse_bond_name,
    parse_treasury_name,
    _days_until,
)

LISTED_FUND_COLUMNS = [
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "InstrumentType",
    "Flow",
    "MarketCode",
    "Last",
    "Close",
    "Yesterday",
    "Volume",
    "Value",
    "TradeCount",
    "Low",
    "High",
    "NAV",
    "NAV_Discount",
    "Change",
    "ChangePct",
    "fund_category",
    "asset_exposure",
    "strategy_tags",
    "trading_mechanism",
    "unit_class",
    "commodity_profile",
    "commodity_underlyings",
    "primary_commodity",
    "classification_status",
    "classification_source",
    "classification_evidence",
    "taxonomy_version",
    "needs_review",
]

FUND_TAXONOMY_VERSION = "2026-09-11"
LISTED_FUND_INSTRUMENT_TYPES = frozenset({305, 380})
_FUND_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "fund_taxonomy.json"
)
_REGISTRY_ASSET_EXPOSURE = {
    "fixed_income": "fixed_income",
    "commodity": "commodity",
    "equity": "equity",
    "mixed": "mixed",
    "venture_capital": "venture",
    "project": "project",
    "private": "private_equity",
    "fund_of_funds": "fund_of_funds",
    "real_estate": "real_estate",
}
_REGISTRY_STRATEGIES = {
    "market_maker": ["market_making"],
    "sector": ["sector"],
    "leveraged": ["leveraged"],
    "index": ["index_tracking"],
    "capital_guaranteed": ["capital_guaranteed"],
    "supplementary_retirement": ["supplementary_retirement"],
}
_FUND_TYPE_ALIASES = {"venture": "venture_capital"}
_FUND_CATEGORIES = frozenset({*settings.fund_type_ids, "unknown"})
_FUND_STRATEGY_TAGS = frozenset(
    {
        "broad_market",
        "sector",
        "index_tracking",
        "leveraged",
        "market_making",
        "capital_guaranteed",
        "supplementary_retirement",
        "charity",
        "unknown",
    }
)
_COMMODITY_UNDERLYINGS = frozenset({"gold", "silver", "saffron", "other", "unknown"})
_CLASSIFICATION_STATUSES = frozenset(
    {
        "authoritative_field",
        "verified_exact_mapping",
        "explicit_official_name",
        "unknown",
    }
)


def _validate_fund_filter(name, value, allowed):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(f"{name} must be a non-empty string or None")
    normalized = value.strip()
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise InvalidParameterError(f"{name} must be one of {choices}; got {value!r}")
    return normalized


def _load_fund_taxonomy():
    """Load and validate the exact-identifier classification registry."""
    with _FUND_TAXONOMY_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("taxonomy_version") != FUND_TAXONOMY_VERSION:
        raise RuntimeError("fund taxonomy version does not match package contract")
    instruments = payload.get("instruments")
    if not isinstance(instruments, dict):
        raise RuntimeError("fund taxonomy instruments must be an object")
    return instruments


_EXACT_FUND_TAXONOMY = _load_fund_taxonomy()


def _normalized_official_name(value):
    text = normalize_instrument_text(value)
    text = re.sub(r"[\u060c\u061b\u061f،؛؟:;,_()\[\]{}\-/]+", " ", text)
    return " ".join(text.split())


def _exact_fund_classification(ins_code, isin):
    """Return an exact mapping only while both stable identifiers agree."""
    entry = _EXACT_FUND_TAXONOMY.get(str(ins_code))
    if not entry:
        return None
    expected_isin = str(entry.get("instrument_id", "")).strip()
    if not expected_isin or expected_isin != str(isin).strip():
        return None
    return entry


def _classify_listed_fund(row):
    instrument_type = int(row["InstrumentType"])
    normalized_name = _normalized_official_name(row.get("Name"))
    result = {
        "fund_category": "commodity" if instrument_type == 380 else "unknown",
        "asset_exposure": "commodity" if instrument_type == 380 else "unknown",
        "strategy_tags": [],
        "trading_mechanism": "exchange_traded",
        "unit_class": "unknown",
        "commodity_profile": "unknown",
        "commodity_underlyings": [],
        "primary_commodity": None,
        "classification_status": "unknown",
        "classification_source": "tsetmc_instrument_type",
        "classification_evidence": {
            "InstrumentType": instrument_type,
            "normalized_official_name": normalized_name,
        },
        "taxonomy_version": FUND_TAXONOMY_VERSION,
        "needs_review": True,
    }

    exact = _exact_fund_classification(row.get("InsCode"), row.get("ISIN"))
    if exact is not None:
        underlyings = list(exact.get("commodity_underlyings") or [])
        result.update(
            {
                "commodity_underlyings": underlyings,
                "primary_commodity": exact.get("primary_commodity"),
                "commodity_profile": (
                    "multi"
                    if len(underlyings) > 1
                    else "single" if underlyings else "unknown"
                ),
                "classification_status": "verified_exact_mapping",
                "classification_source": "versioned_exact_identifier_registry",
                "classification_evidence": {
                    "InstrumentType": instrument_type,
                    "evidence_type": exact.get("evidence_type"),
                    "evidence_url": exact.get("evidence_url"),
                    "evidence_date": exact.get("evidence_date"),
                },
                "needs_review": False,
            }
        )
        return result

    if instrument_type != 380:
        return result

    matched = []
    if re.search(r"(?:^| )طلا(?:ی)?(?: |$)", normalized_name):
        matched.append("gold")
    if re.search(r"(?:^| )نقره(?: |$)", normalized_name):
        matched.append("silver")
    if re.search(r"(?:^| )زعفران(?: |$)", normalized_name):
        matched.append("saffron")

    multi_named = "چند کالایی" in normalized_name
    if matched or multi_named:
        result.update(
            {
                "commodity_underlyings": matched,
                "primary_commodity": matched[0] if len(matched) == 1 else None,
                "commodity_profile": (
                    "multi" if multi_named or len(matched) > 1 else "single"
                ),
                "classification_status": "explicit_official_name",
                "classification_source": "tsetmc_official_instrument_name",
                "classification_evidence": {
                    "InstrumentType": instrument_type,
                    "normalized_official_name": normalized_name,
                    "matched_rule": "explicit_semantic_commodity_term",
                },
                "needs_review": False,
            }
        )
    return result


def _classify_registry_fund(raw, requested_type_id, requested_category):
    """Classify a registry row while preserving contradictory raw type data."""
    raw_type = raw.get("fixIncome")
    try:
        registry_type_id = (
            int(raw_type) if raw_type not in (None, "") else requested_type_id
        )
    except (TypeError, ValueError):
        registry_type_id = raw_type
    type_matches = registry_type_id == requested_type_id
    category = requested_category if type_matches else "unknown"
    classification = {
        "registry_type_id": registry_type_id,
        "registry_category": category,
        "asset_exposure": _REGISTRY_ASSET_EXPOSURE.get(category, "unknown"),
        "strategy_tags": list(_REGISTRY_STRATEGIES.get(category, [])),
        "commodity_underlyings": [],
        "primary_commodity": None,
        "classification_status": "authoritative_field" if type_matches else "unknown",
        "classification_source": "tsetmc_fund_registry_type",
        "classification_evidence": {
            "requested_type_id": requested_type_id,
            "raw_fixIncome": raw_type,
        },
        "taxonomy_version": FUND_TAXONOMY_VERSION,
        "record_date": raw.get("updateDate") or raw.get("modifyDate"),
        "needs_review": not type_matches,
    }
    if category == "commodity":
        named = _classify_listed_fund(
            {
                "InstrumentType": 380,
                "InsCode": "",
                "ISIN": "",
                "Name": raw.get("mfName", ""),
            }
        )
        classification["commodity_underlyings"] = named["commodity_underlyings"]
        classification["primary_commodity"] = named["primary_commodity"]
        if named["classification_status"] == "explicit_official_name":
            classification["classification_status"] = "explicit_official_name"
            classification["classification_source"] = "tsetmc_official_registry_name"
            classification["classification_evidence"].update(
                named["classification_evidence"]
            )
            classification["needs_review"] = False
        elif type_matches:
            classification["needs_review"] = True
    return classification


def _cast_listed_funds(frame):
    """Give the additive listed-fund API one stable empty/non-empty schema."""
    source_attrs = dict(frame.attrs)
    result = frame.reindex(columns=LISTED_FUND_COLUMNS).copy()
    for column in (
        "InsCode",
        "ISIN",
        "Symbol",
        "Name",
        "MarketCode",
        "fund_category",
        "asset_exposure",
        "trading_mechanism",
        "unit_class",
        "commodity_profile",
        "primary_commodity",
        "classification_status",
        "classification_source",
        "taxonomy_version",
    ):
        result[column] = result[column].astype("string")
    for column in (
        "InstrumentType",
        "Flow",
        "Last",
        "Close",
        "Yesterday",
        "Volume",
        "Value",
        "TradeCount",
        "Low",
        "High",
        "NAV",
        "Change",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("Int64")
    for column in ("NAV_Discount", "ChangePct"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "Float64"
        )
    for column in (
        "strategy_tags",
        "commodity_underlyings",
        "classification_evidence",
    ):
        result[column] = result[column].astype("object")
    result["needs_review"] = result["needs_review"].astype("boolean")
    result.attrs.update(source_attrs)
    return result.reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
#  Options
# ══════════════════════════════════════════════════════════════


def list_options(underlying=None, progress=True):
    """List all active option contracts with parsed metadata.

    Fetches ``market_watch()`` and filters to option instruments
    (InstrumentType 311=call, 312=put), then parses the Name field to
    extract underlying, strike price, and expiry date.

    Parameters
    ----------
    underlying : str, optional
        Filter by underlying symbol name (e.g. ``'اهرم'``).
        If ``None``, returns all options.
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code (str)
        - ``ISIN`` — International Securities ID
        - ``Symbol`` — Option symbol (e.g. ``'ضهرم1116'``)
        - ``Name`` — Full name
        - ``OptionType`` — ``'call'`` or ``'put'``
        - ``Underlying`` — Underlying asset name (e.g. ``'اهرم'``)
        - ``Strike`` — Strike price (int)
        - ``ExpiryJalali`` — Expiry date (Jalali string)
        - ``ExpiryGregorian`` — Expiry date (datetime.date)
        - ``DaysToExpiry`` — Days remaining to expiry (int)
        - ``Last`` — Last traded price (premium)
        - ``Close`` — Closing / weighted avg price
        - ``Yesterday`` — Yesterday reference price
        - ``Volume`` — Trading volume
        - ``Value`` — Trading value (Rials)
        - ``TradeCount`` — Number of trades
        - ``Change`` — Price change
        - ``ChangePct`` — Change percentage
        - ``MaxAllowed`` — Upper price limit
        - ``MinAllowed`` — Lower price limit

    Examples
    --------
    >>> import algotik_tse as att
    >>> options = att.list_options()                      # All options
    >>> calls = att.list_options(underlying='اهرم')       # Just اهرم options
    """
    if progress:
        print("Fetching market data...")

    data = market_watch()
    stocks_df = data["stocks"]

    # Filter to options only (311=call, 312=put)
    options_df = stocks_df[stocks_df["InstrumentType"].isin([311, 312])].copy()

    if options_df.empty:
        if progress:
            print("No options found in market data.")
        return pd.DataFrame()

    if progress:
        print(f"Found {len(options_df)} option contracts. Parsing metadata...")

    # Parse Name field for each option
    parsed_rows = []
    for _, row in options_df.iterrows():
        parsed = parse_option_name(row["Name"])
        if parsed:
            parsed_rows.append(
                {
                    "InsCode": row["InsCode"],
                    "ISIN": row["ISIN"],
                    "Symbol": row["Symbol"],
                    "Name": row["Name"],
                    "OptionType": parsed["option_type"],
                    "Underlying": parsed["underlying"],
                    "Strike": parsed["strike"],
                    "ExpiryJalali": parsed["expiry_jalali"],
                    "ExpiryGregorian": parsed["expiry_gregorian"],
                    "DaysToExpiry": (
                        _days_until(parsed["expiry_gregorian"])
                        if parsed["expiry_gregorian"]
                        else None
                    ),
                    "Last": row["Last"],
                    "Close": row["Close"],
                    "Yesterday": row["Yesterday"],
                    "Volume": row["Volume"],
                    "Value": row["Value"],
                    "TradeCount": row["TradeCount"],
                    "Change": row["Change"],
                    "ChangePct": row["ChangePct"],
                    "MaxAllowed": row["MaxAllowed"],
                    "MinAllowed": row["MinAllowed"],
                }
            )
        else:
            # Fallback: use symbol prefix for type detection
            opt_type = parse_option_symbol(row["Symbol"]) or "unknown"
            parsed_rows.append(
                {
                    "InsCode": row["InsCode"],
                    "ISIN": row["ISIN"],
                    "Symbol": row["Symbol"],
                    "Name": row["Name"],
                    "OptionType": opt_type,
                    "Underlying": None,
                    "Strike": None,
                    "ExpiryJalali": None,
                    "ExpiryGregorian": None,
                    "DaysToExpiry": None,
                    "Last": row["Last"],
                    "Close": row["Close"],
                    "Yesterday": row["Yesterday"],
                    "Volume": row["Volume"],
                    "Value": row["Value"],
                    "TradeCount": row["TradeCount"],
                    "Change": row["Change"],
                    "ChangePct": row["ChangePct"],
                    "MaxAllowed": row["MaxAllowed"],
                    "MinAllowed": row["MinAllowed"],
                }
            )

    result = pd.DataFrame(parsed_rows)

    # Filter by underlying if specified
    if underlying and not result.empty:
        result = result[result["Underlying"] == underlying].copy()
        if progress:
            print(f"Filtered to {len(result)} contracts for underlying '{underlying}'.")

    if progress:
        print(f"Done. {len(result)} options returned.")

    return result.reset_index(drop=True)


def get_options_chain(underlying, fetch_oi=False, progress=True):
    """Get a structured options chain for a specific underlying asset.

    Returns calls and puts separated, with the underlying's current price
    and all available expiry dates.

    Parameters
    ----------
    underlying : str
        Underlying symbol name (e.g. ``'اهرم'``, ``'شتران'``).
    fetch_oi : bool, default False
        If True, makes an additional API call per contract to fetch
        open interest (buyOP/sellOP), contract size, and date range.
        **Warning:** This is slow for many contracts due to rate limiting.
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    dict
        Keys:

        - ``calls`` — DataFrame of call options
        - ``puts`` — DataFrame of put options
        - ``underlying_name`` — str, underlying symbol name
        - ``underlying_price`` — int, current price of underlying (from market_watch)
        - ``expiry_dates`` — list of unique expiry dates (Jalali strings)
        - ``market_time`` — str, market time from snapshot

        If ``fetch_oi=True``, the DataFrames also contain:

        - ``OpenInterest`` — Open position count (buyOP)
        - ``ContractSize`` — Number of underlying shares per contract
        - ``BeginDate`` — Contract listing date (Gregorian int YYYYMMDD)
        - ``EndDate`` — Contract expiry date (Gregorian int YYYYMMDD)

    Examples
    --------
    >>> chain = att.get_options_chain('اهرم')
    >>> print(chain['calls'])
    >>> print(chain['puts'])
    >>> print(chain['underlying_price'])
    >>> print(chain['expiry_dates'])
    """
    # Get all options for this underlying
    all_options = list_options(underlying=underlying, progress=progress)

    if all_options.empty:
        return {
            "calls": pd.DataFrame(),
            "puts": pd.DataFrame(),
            "underlying_name": underlying,
            "underlying_price": None,
            "expiry_dates": [],
            "market_time": None,
        }

    # Get underlying price from market_watch
    data = market_watch()
    underlying_price = None
    market_time = data.get("market_time", "")

    # Search for underlying in stocks
    stocks_df = data["stocks"]
    # Try exact symbol match first
    match = stocks_df[stocks_df["Symbol"] == underlying]
    if match.empty:
        # Try partial match in Name
        match = stocks_df[stocks_df["Symbol"].str.contains(underlying, na=False)]
    if not match.empty:
        underlying_price = int(match.iloc[0]["Last"])

    # Fetch open interest if requested
    if fetch_oi:
        if progress:
            print(f"Fetching open interest for {len(all_options)} contracts...")
        oi_data = []
        for i, (_, row) in enumerate(all_options.iterrows()):
            oi = _fetch_option_info(row["ISIN"])
            oi_data.append(oi)
            if progress and (i + 1) % 10 == 0:
                print(f"  ... {i + 1}/{len(all_options)} contracts fetched")
        oi_df = pd.DataFrame(oi_data)
        all_options = pd.concat([all_options, oi_df], axis=1)

    # Split into calls and puts
    calls = all_options[all_options["OptionType"] == "call"].copy()
    puts = all_options[all_options["OptionType"] == "put"].copy()

    # Sort by strike then expiry
    for df in [calls, puts]:
        if not df.empty:
            df.sort_values(["ExpiryJalali", "Strike"], inplace=True)
            df.reset_index(drop=True, inplace=True)

    # Unique expiry dates
    expiry_dates = sorted(all_options["ExpiryJalali"].dropna().unique().tolist())

    return {
        "calls": calls,
        "puts": puts,
        "underlying_name": underlying,
        "underlying_price": underlying_price,
        "expiry_dates": expiry_dates,
        "market_time": market_time,
    }


def _fetch_option_info(isin):
    """Fetch option contract details (open interest, contract size, etc.).

    Calls ``GetInstrumentOptionByInstrumentID/{ISIN}`` on cdn.tsetmc.com.

    Parameters
    ----------
    isin : str
        The ISIN of the option instrument (e.g. ``'IRO9AHRM0631'``).

    Returns
    -------
    dict
        Keys: ``OpenInterest``, ``ContractSize``, ``StrikePrice``,
        ``UnderlyingInsCode``, ``BeginDate``, ``EndDate``.

    Example response from API::

        {
            "instrumentOption": {
                "buyOP": 55988,
                "sellOP": 55988,
                "contractSize": 1000,
                "strikePrice": 38000,
                "uaInsCode": "17914401175772326",
                "beginDate": 20251122,
                "endDate": 20260415
            }
        }
    """
    url = settings.url_option_info.format(isin)
    try:
        response = safe_get(url)
        if response is None or response.status_code != 200:
            return _empty_oi()
        data = response.json()
        opt = data.get("instrumentOption", {})
        return {
            "OpenInterest": opt.get("buyOP", 0),
            "ContractSize": opt.get("contractSize", 0),
            "StrikePrice_API": opt.get("strikePrice", 0),
            "UnderlyingInsCode": str(opt.get("uaInsCode", "")),
            "BeginDate": opt.get("beginDate", 0),
            "EndDate": opt.get("endDate", 0),
        }
    except Exception:
        return _empty_oi()


def _empty_oi():
    """Return an empty OI dict for failed fetches."""
    return {
        "OpenInterest": None,
        "ContractSize": None,
        "StrikePrice_API": None,
        "UnderlyingInsCode": None,
        "BeginDate": None,
        "EndDate": None,
    }


# ══════════════════════════════════════════════════════════════
#  ETFs
# ══════════════════════════════════════════════════════════════


def list_etfs(progress=True):
    """List legacy general listed funds with NAV and discount/premium.

    Fetches ``market_watch()`` and filters to ETF instruments
    (InstrumentType 305), then computes NAV discount or premium. Use
    :func:`list_listed_funds` for the complete classified 305+380 universe.

    Parameters
    ----------
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code
        - ``ISIN`` — International Securities ID
        - ``Symbol`` — Fund symbol
        - ``Name`` — Full name
        - ``Last`` — Last traded price
        - ``Close`` — Closing / weighted avg price
        - ``Yesterday`` — Yesterday reference price
        - ``Volume`` — Trading volume
        - ``Value`` — Trading value (Rials)
        - ``TradeCount`` — Number of trades
        - ``Low`` / ``High`` — Day's price range
        - ``NAV`` — Net Asset Value per unit
        - ``NAV_Discount`` — ``(Close - NAV) / NAV * 100``.
          Negative = trading at discount, Positive = at premium.
        - ``Change`` / ``ChangePct`` — Price change
        - ``MarketCode`` — Market identifier

    Examples
    --------
    >>> etfs = att.list_etfs()
    >>> discounted = etfs[etfs['NAV_Discount'] < -10]  # > 10% discount
    """
    if progress:
        print("Fetching market data...")

    data = market_watch()
    stocks_df = data["stocks"]

    # Filter to ETFs (InstrumentType == 305)
    etfs = stocks_df[stocks_df["InstrumentType"] == 305].copy()

    if etfs.empty:
        if progress:
            print("No ETFs found.")
        result = pd.DataFrame()
        result.attrs.update(
            {
                "source": "tsetmc_market_watch",
                "coverage": "legacy_general_listed_funds_type_305",
                "request_count": 1,
                "no_fuzzy_join": True,
                "no_backfill": True,
                "as_of": data.get("fetched_at"),
                "trade_date": data.get("trade_date"),
                "is_realtime_fresh": data.get("is_realtime_fresh", False),
                "is_stale": data.get("is_stale", True),
            }
        )
        return result

    # Compute NAV discount/premium
    etfs["NAV_Discount"] = np.nan
    mask = etfs["NAV"] > 0
    etfs.loc[mask, "NAV_Discount"] = (
        (etfs.loc[mask, "Close"] - etfs.loc[mask, "NAV"]) / etfs.loc[mask, "NAV"] * 100
    ).round(2)

    # Select and reorder columns
    cols = [
        "InsCode",
        "ISIN",
        "Symbol",
        "Name",
        "Last",
        "Close",
        "Yesterday",
        "Volume",
        "Value",
        "TradeCount",
        "Low",
        "High",
        "NAV",
        "NAV_Discount",
        "Change",
        "ChangePct",
        "MarketCode",
    ]
    available_cols = [c for c in cols if c in etfs.columns]
    result = etfs[available_cols].copy()

    if progress:
        nav_count = (result["NAV"] > 0).sum() if "NAV" in result.columns else 0
        print(f"Done. {len(result)} ETFs found ({nav_count} with NAV data).")

    result = result.reset_index(drop=True)
    result.attrs.update(
        {
            "source": "tsetmc_market_watch",
            "coverage": "legacy_general_listed_funds_type_305",
            "request_count": 1,
            "no_fuzzy_join": True,
            "no_backfill": True,
            "as_of": data.get("fetched_at"),
            "trade_date": data.get("trade_date"),
            "is_realtime_fresh": data.get("is_realtime_fresh", False),
            "is_stale": data.get("is_stale", True),
        }
    )
    return result


def list_listed_funds(
    progress=True,
    *,
    fund_category=None,
    strategy=None,
    commodity_underlying=None,
    classification_status=None,
    include_unknown=True,
):
    """Return classified exchange-listed funds from one MarketWatch snapshot.

    Both general listed funds (``InstrumentType=305``) and listed commodity
    funds (``InstrumentType=380``) are included. Classification uses structured
    TSETMC fields, an exact InsCode/ISIN registry, or explicit semantic terms in
    the official instrument name. Missing evidence remains ``unknown``.

    Parameters are keyword-only filters. For example,
    ``commodity_underlying='gold'`` returns only funds explicitly proved to
    hold gold; generic commodity names are not guessed. ``include_unknown=False``
    removes rows whose classification status is unknown.
    """
    if not isinstance(include_unknown, bool):
        raise InvalidParameterError("include_unknown must be bool")

    fund_category = _validate_fund_filter(
        "fund_category", fund_category, _FUND_CATEGORIES
    )
    strategy = _validate_fund_filter("strategy", strategy, _FUND_STRATEGY_TAGS)
    commodity_underlying = _validate_fund_filter(
        "commodity_underlying", commodity_underlying, _COMMODITY_UNDERLYINGS
    )
    classification_status = _validate_fund_filter(
        "classification_status", classification_status, _CLASSIFICATION_STATUSES
    )

    if progress:
        print("Fetching and classifying listed funds...")
    data = market_watch()
    stocks = data["stocks"]
    instrument_types = pd.to_numeric(stocks["InstrumentType"], errors="coerce")
    funds = stocks.loc[instrument_types.isin(LISTED_FUND_INSTRUMENT_TYPES)].copy()
    funds["NAV_Discount"] = np.nan
    nav_mask = pd.to_numeric(funds.get("NAV"), errors="coerce") > 0
    funds.loc[nav_mask, "NAV_Discount"] = (
        (funds.loc[nav_mask, "Close"] - funds.loc[nav_mask, "NAV"])
        / funds.loc[nav_mask, "NAV"]
        * 100
    ).round(2)

    classifications = [_classify_listed_fund(row) for _, row in funds.iterrows()]
    if classifications:
        classified = pd.DataFrame(classifications, index=funds.index)
        for column in classified.columns:
            funds[column] = classified[column]

    result = _cast_listed_funds(funds)
    if fund_category is not None:
        result = result.loc[result["fund_category"] == fund_category].copy()
    if strategy is not None:
        target = strategy
        result = result.loc[
            result["strategy_tags"].map(lambda values: target in (values or []))
        ].copy()
    if commodity_underlying is not None:
        target = commodity_underlying
        result = result.loc[
            result["commodity_underlyings"].map(lambda values: target in (values or []))
        ].copy()
    if classification_status is not None:
        result = result.loc[
            result["classification_status"] == classification_status
        ].copy()
    if not include_unknown:
        result = result.loc[result["classification_status"] != "unknown"].copy()

    result = result.reset_index(drop=True)
    result.attrs.update(
        {
            "source": "tsetmc_market_watch",
            "coverage": "current_listed_fund_universe_305_380",
            "request_count": 1,
            "no_fuzzy_join": True,
            "no_backfill": True,
            "as_of": data.get("fetched_at"),
            "trade_date": data.get("trade_date"),
            "is_realtime_fresh": data.get("is_realtime_fresh", False),
            "is_stale": data.get("is_stale", True),
            "taxonomy_version": FUND_TAXONOMY_VERSION,
            "classification_policy": "unknown_without_exact_or_explicit_evidence",
        }
    )
    result.attrs["api"] = "list_listed_funds"
    result.attrs["registry_joined"] = False
    if progress:
        print(f"Done. {len(result)} listed funds matched.")
    return result


# ══════════════════════════════════════════════════════════════
#  Bonds & Treasury
# ══════════════════════════════════════════════════════════════


def list_bonds(progress=True):
    """List all bond and treasury instruments with parsed maturity dates.

    Fetches ``market_watch()`` and identifies bond/treasury instruments
    by parsing their Name field for maturity date patterns.

    Parameters
    ----------
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``InsCode`` — Instrument code
        - ``ISIN`` — International Securities ID
        - ``Symbol`` — Symbol
        - ``Name`` — Full name
        - ``BondType`` — ``'murabaha'``, ``'treasury'``, ``'ijara'``, ``'salaf'``, ``'other'``
        - ``Ticker`` — Short ticker (e.g. ``'اراد1754'``, ``'اخزا4024'``)
        - ``MaturityJalali`` — Maturity date (Jalali string)
        - ``MaturityGregorian`` — Maturity as datetime.date
        - ``DaysToMaturity`` — Days remaining to maturity
        - ``Last`` — Last traded price
        - ``Close`` — Closing / weighted avg price
        - ``Yesterday`` — Yesterday reference price
        - ``Volume`` — Trading volume
        - ``Value`` — Trading value (Rials)
        - ``TradeCount`` — Number of trades
        - ``Change`` / ``ChangePct`` — Price change

    Examples
    --------
    >>> bonds = att.list_bonds()
    >>> treasury = bonds[bonds['BondType'] == 'treasury']
    >>> active = bonds[bonds['DaysToMaturity'] > 0]
    """
    if progress:
        print("Fetching market data...")

    data = market_watch()
    stocks_df = data["stocks"]

    if progress:
        print("Scanning for bonds and treasury instruments...")

    parsed_rows = []
    for _, row in stocks_df.iterrows():
        name = row["Name"]
        parsed = None

        # Try treasury first (اسناد خزانه / اخزا)
        if any(kw in name for kw in ["اسناد", "خزانه", "اخزا"]):
            parsed = parse_treasury_name(name)

        # Try bond (مرابحه, اجاره, etc.)
        if parsed is None and any(
            kw in name for kw in ["مرابحه", "اجاره", "سلف", "اراد", "ش.خ"]
        ):
            parsed = parse_bond_name(name)

        if parsed:
            days_to_mat = None
            if parsed.get("maturity_gregorian"):
                days_to_mat = _days_until(parsed["maturity_gregorian"])

            parsed_rows.append(
                {
                    "InsCode": row["InsCode"],
                    "ISIN": row["ISIN"],
                    "Symbol": row["Symbol"],
                    "Name": name,
                    "BondType": parsed["bond_type"],
                    "Ticker": parsed.get("ticker") or row["Symbol"],
                    "MaturityJalali": parsed["maturity_jalali"],
                    "MaturityGregorian": parsed["maturity_gregorian"],
                    "DaysToMaturity": days_to_mat,
                    "Last": row["Last"],
                    "Close": row["Close"],
                    "Yesterday": row["Yesterday"],
                    "Volume": row["Volume"],
                    "Value": row["Value"],
                    "TradeCount": row["TradeCount"],
                    "Change": row["Change"],
                    "ChangePct": row["ChangePct"],
                }
            )

    result = pd.DataFrame(parsed_rows)

    if progress:
        if result.empty:
            print("No bonds/treasury instruments found.")
        else:
            bond_types = result["BondType"].value_counts().to_dict()
            summary = ", ".join(f"{v} {k}" for k, v in bond_types.items())
            print(f"Done. {len(result)} instruments found ({summary}).")

    return result.reset_index(drop=True) if not result.empty else result


# ══════════════════════════════════════════════════════════════
#  Funds — detailed fund data from TSETMC Fund API
# ══════════════════════════════════════════════════════════════


def list_funds(
    fund_type=None,
    progress=True,
    *,
    listed_only=False,
    strategy=None,
    commodity_underlying=None,
    classification_status=None,
):
    """List investment funds with NAV, returns, portfolio composition and manager info.

    Fetches data from the TSETMC Fund API which provides rich information
    not available in ``market_watch()`` or ``list_etfs()``. By default this is
    a registry view: its rows are not guaranteed to be exchange-listed and do
    not carry a canonical ticker/InsCode. Use ``listed_only=True`` (or
    :func:`list_listed_funds`) for the exact current listed universe; the two
    sources are never fuzzy-joined by name.

    Parameters
    ----------
    fund_type : str or list of str, optional
        Filter by fund category. Valid values:

        - ``'equity'``       — صندوق سرمایه‌گذاری در سهام
        - ``'fixed_income'`` — صندوق درآمد ثابت
        - ``'mixed'``        — صندوق مختلط
        - ``'market_maker'`` — صندوق بازارگردانی
        - ``'venture_capital'`` — صندوق جسورانه (``'venture'`` نیز پذیرفته می‌شود)
        - ``'project'``      — صندوق پروژه
        - ``'real_estate'``  — صندوق زمین و ساختمان
        - ``'commodity'``    — صندوق کالایی (طلا، نقره، ...)
        - ``'private'``      — صندوق خصوصی
        - ``'fund_of_funds'``— صندوق در صندوق (ابر صندوق)
        - ``'sector'`` / ``'leveraged'`` / ``'index'``
        - ``'capital_guaranteed'`` / ``'supplementary_retirement'``

        If ``None`` (default), returns **all** fund types.
        If a string, returns only that type.
        If a list, returns the union of those types.

    progress : bool, default True
        Print progress messages.
    listed_only : bool, keyword-only, default False
        Return current exchange-listed funds from one MarketWatch snapshot.
        Cannot be combined with ``fund_type`` because the registry has no
        exact exchange identity suitable for that join.
    strategy : str, keyword-only, optional
        Exact strategy tag such as ``'sector'``, ``'leveraged'`` or
        ``'index_tracking'``.
    commodity_underlying : str, keyword-only, optional
        Explicit commodity subtype such as ``'gold'``, ``'silver'`` or
        ``'saffron'``. Rows without proof are not returned by this filter.
    classification_status : str, keyword-only, optional
        Auditable classification status to retain.

    Returns
    -------
    pd.DataFrame
        Columns (all funds):

        **Identity:**
        - ``fund_name``         — Fund name in Persian (e.g. ``'آرمان آتیه درخشان مس'``)
        - ``fund_type``         — Category label (e.g. ``'equity'``, ``'fixed_income'``)
        - ``reg_no``            — Registration number

        **NAV & Assets:**
        - ``nav_redemption``    — NAV for redemption (per unit)
        - ``nav_subscription``  — NAV for subscription (per unit)
        - ``nav_statistical``   — Statistical NAV (per unit)
        - ``net_asset``         — Total net asset value (Rials)
        - ``units``             — Outstanding units
        - ``inception_date``    — Fund start date (ISO string)

        **Returns (%):**
        - ``return_1d``         — 1-day return
        - ``return_7d``         — 7-day return
        - ``return_30d``        — 30-day return
        - ``return_90d``        — 90-day return (≈ quarterly)
        - ``return_180d``       — 180-day return (≈ semi-annual)
        - ``return_365d``       — 365-day return (≈ annual)
        - ``return_inception``  — Return since inception

        **Portfolio Composition (%):**
        - ``pct_stock``         — Equity allocation
        - ``pct_bond``          — Bond allocation
        - ``pct_deposit``       — Bank deposit allocation
        - ``pct_cash``          — Cash & equivalents
        - ``pct_other``         — Other assets
        - ``pct_top5``          — Top-5 holding concentration

        **Managers & Service Providers:**
        - ``manager``           — Fund manager
        - ``investment_manager``— Investment manager
        - ``custodian``         — Custodian / auditor
        - ``guarantor``         — Guarantor (if any)
        - ``market_maker``      — Market maker (if any)

    Examples
    --------
    >>> import algotik_tse as att
    >>> all_funds = att.list_funds()                             # All funds
    >>> equity = att.list_funds(fund_type='equity')              # Equity only
    >>> fixed = att.list_funds(fund_type='fixed_income')         # Fixed income
    >>> multi = att.list_funds(fund_type=['equity', 'mixed'])    # Equity + Mixed
    >>> commodity = att.list_funds(fund_type='commodity')        # All commodity
    >>> gold = att.list_funds(
    ...     fund_type='commodity', commodity_underlying='gold'
    ... )
    >>> top = all_funds.nlargest(10, 'return_365d')              # Best annual return
    """
    if not isinstance(listed_only, bool):
        raise InvalidParameterError("listed_only must be bool")
    strategy = _validate_fund_filter("strategy", strategy, _FUND_STRATEGY_TAGS)
    commodity_underlying = _validate_fund_filter(
        "commodity_underlying", commodity_underlying, _COMMODITY_UNDERLYINGS
    )
    classification_status = _validate_fund_filter(
        "classification_status", classification_status, _CLASSIFICATION_STATUSES
    )
    if listed_only:
        if fund_type is not None:
            raise InvalidParameterError(
                "fund_type cannot be combined with listed_only because the "
                "fund registry has no exact exchange identity"
            )
        return list_listed_funds(
            progress=progress,
            strategy=strategy,
            commodity_underlying=commodity_underlying,
            classification_status=classification_status,
        )

    # ── Determine which fund types to fetch ───────────────────
    all_type_ids = settings.fund_type_ids
    type_labels = settings.fund_type_labels

    if fund_type is None:
        types_to_fetch = list(dict.fromkeys(all_type_ids.values()))
    elif isinstance(fund_type, str):
        fund_type = _FUND_TYPE_ALIASES.get(fund_type, fund_type)
        if fund_type not in all_type_ids:
            valid = ", ".join(sorted(all_type_ids.keys()))
            print(f"Invalid fund_type '{fund_type}'. Valid types: {valid}")
            return None
        types_to_fetch = [all_type_ids[fund_type]]
    elif isinstance(fund_type, list):
        types_to_fetch = []
        for ft in fund_type:
            ft = _FUND_TYPE_ALIASES.get(ft, ft)
            if ft not in all_type_ids:
                valid = ", ".join(sorted(all_type_ids.keys()))
                print(f"Invalid fund_type '{ft}'. Valid types: {valid}")
                continue
            types_to_fetch.append(all_type_ids[ft])
        if not types_to_fetch:
            return None
    else:
        print("fund_type must be None, a string, or a list of strings.")
        return None

    # ── Fetch data from API ───────────────────────────────────
    all_rows = []
    fetched = 0
    total = len(types_to_fetch)

    for type_id in types_to_fetch:
        label = type_labels.get(type_id, str(type_id))
        if progress:
            fetched += 1
            print(f"  [{fetched}/{total}] Fetching {label} funds...", flush=True)

        url = settings.url_fund_list.format(type_id)
        try:
            resp = safe_get(url)
            data = resp.json()
            funds_list = data.get("funds", [])
        except Exception as e:
            if progress:
                print(f"    Warning: failed to fetch {label}: {e}")
            continue

        for f in funds_list:
            classification = _classify_registry_fund(f, type_id, label)
            all_rows.append(
                {
                    "fund_name": f.get("mfName", ""),
                    "fund_type": classification["registry_category"],
                    "reg_no": int(f["regNo"]) if f.get("regNo") else None,
                    **classification,
                    # NAV & Assets
                    "nav_redemption": f.get("navRed"),
                    "nav_subscription": f.get("navSub"),
                    "nav_statistical": f.get("navStat"),
                    "net_asset": f.get("netAsset"),
                    "units": f.get("units"),
                    "inception_date": (
                        f.get("initiationDate", "")[:10]
                        if f.get("initiationDate")
                        else None
                    ),
                    # Returns
                    "return_1d": f.get("day1Return"),
                    "return_7d": f.get("day7Return"),
                    "return_30d": f.get("day30Return"),
                    "return_90d": f.get("day90Return"),
                    "return_180d": f.get("day180Return"),
                    "return_365d": f.get("day365Return"),
                    "return_inception": f.get("dayFirstReturn"),
                    # Portfolio composition
                    "pct_stock": f.get("portfolioStock"),
                    "pct_bond": f.get("portfolioBond"),
                    "pct_deposit": f.get("portfolioDeposit"),
                    "pct_cash": f.get("portfolioCash"),
                    "pct_other": f.get("portfolioOther"),
                    "pct_top5": f.get("portfolioFiveBest"),
                    # Managers
                    "manager": f.get("manager"),
                    "investment_manager": f.get("investmentManager"),
                    "custodian": f.get("custodian"),
                    "guarantor": (
                        f.get("guarantor") if f.get("guarantor") != "----" else None
                    ),
                    "market_maker": f.get("marketMaker"),
                }
            )

        if progress and len(funds_list) > 0:
            print(f"    → {len(funds_list)} funds")

        # Rate-limit between requests
        if fetched < total:
            time.sleep(settings.rate_limit_delay)

    # ── Build DataFrame ───────────────────────────────────────
    if not all_rows:
        if progress:
            print("No funds found.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    if strategy is not None:
        target = strategy
        df = df.loc[df["strategy_tags"].map(lambda values: target in values)].copy()
    if commodity_underlying is not None:
        target = commodity_underlying
        df = df.loc[
            df["commodity_underlyings"].map(lambda values: target in values)
        ].copy()
    if classification_status is not None:
        df = df.loc[df["classification_status"] == classification_status].copy()

    # Sort by fund_type then fund_name
    df = df.sort_values(["fund_type", "fund_name"], ignore_index=True)

    if progress:
        type_counts = df["fund_type"].value_counts()
        summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        print(f"Done. {len(df)} funds total ({summary}).")

    df.attrs.update(
        {
            "source": "tsetmc_fund_registry",
            "taxonomy_version": FUND_TAXONOMY_VERSION,
            "no_fuzzy_join": True,
            "registry_joined": False,
            "discovery_signals": int((df["classification_status"] == "unknown").sum()),
        }
    )
    return df


# ══════════════════════════════════════════════════════════════
#  Indices
# ══════════════════════════════════════════════════════════════


def list_indices(progress=True):
    """Get all market indices with their current values.

    Fetches data from the TSETMC Index API and returns a DataFrame of
    all available indices (both industry-sector and general market indices).

    Parameters
    ----------
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``Name`` — Index name in Persian (e.g. ``'27-فلزات اساسی'``)
        - ``InsCode`` — Unique instrument code (str)
        - ``Value`` — Current index value
        - ``High`` — Highest value today
        - ``Low`` — Lowest value today
        - ``Change`` — Index change value
        - ``ChangePct`` — Change percentage

    Examples
    --------
    >>> import algotik_tse as att
    >>> indices = att.list_indices()
    >>> indices[indices['Name'].str.contains('فلزات')]
    """
    if progress:
        print("Fetching indices data...")

    try:
        resp = safe_get(settings.url_all_indices)
        data = resp.json()["indexB1"]
    except Exception as e:
        print("Error fetching indices: {}".format(e))
        return pd.DataFrame()

    rows = []
    for item in data:
        rows.append(
            {
                "Name": item.get("lVal30", ""),
                "InsCode": str(item.get("insCode", "")),
                "Value": item.get("xDrNivJIdx004", 0),
                "High": item.get("xPhNivJIdx004", 0),
                "Low": item.get("xPbNivJIdx004", 0),
                # TSETMC uses indexChange for the point move and
                # xVarIdxJRfV for the percentage move.  These fields were
                # accidentally reversed in algotik-tse <= 1.1.3.
                "Change": item.get("indexChange", 0),
                "ChangePct": item.get("xVarIdxJRfV", 0),
            }
        )

    df = pd.DataFrame(rows)

    if progress:
        print("Done. {} indices returned.".format(len(df)))

    return df


def get_index_companies(index_name, progress=True):
    """Get companies belonging to a specific index.

    Parameters
    ----------
    index_name : str
        Name of the index in Persian (e.g. ``'شاخص صنعت فلزات اساسی'``,
        ``'فلزات اساسی'``, ``'بانک'``) or InsCode directly (all digits).
    progress : bool, default True
        Print progress messages.

    Returns
    -------
    pd.DataFrame
        Columns:

        - ``Symbol`` — Stock symbol (e.g. ``'فولاد'``)
        - ``Name`` — Full company name
        - ``InsCode`` — Instrument code (str)
        - ``Close`` — Closing price
        - ``Yesterday`` — Yesterday's closing price
        - ``Last`` — Last traded price

    Examples
    --------
    >>> import algotik_tse as att
    >>> companies = att.get_index_companies('فلزات اساسی')
    >>> companies = att.get_index_companies('شاخص بانک')
    """
    from algotik_tse.core.search import (
        search_stock,
        _normalize_fa,
        _INDUSTRY_DICT,
    )

    # Resolve index name to web_id
    web_id = None

    # Check if it's already a web_id (all digits)
    if index_name.isdigit():
        web_id = index_name
    else:
        # Try industry lookup with normalization
        normalized = _normalize_fa(index_name)
        if normalized in _INDUSTRY_DICT:
            web_id = _INDUSTRY_DICT[normalized]
        else:
            # Try general index via search_stock
            result = search_stock(index_name)
            if result and result.endswith("industry"):
                web_id = result[:-8]
            elif result and result.endswith("index"):
                web_id = result[:-5]
            else:
                print("Index '{}' not found.".format(index_name))
                return pd.DataFrame()

    if progress:
        print("Fetching companies for index {}...".format(web_id))

    try:
        resp = safe_get(settings.url_index_companies.format(web_id))
        data = resp.json()
    except Exception as e:
        print("Error fetching index companies: {}".format(e))
        return pd.DataFrame()

    companies = data.get("indexCompany", [])

    rows = []
    for item in companies:
        inst = item.get("instrument") or {}
        rows.append(
            {
                "Symbol": inst.get("lVal18AFC", ""),
                "Name": inst.get("lVal30", ""),
                "InsCode": str(item.get("insCode", "")),
                "Close": item.get("pClosing", 0),
                "Yesterday": item.get("priceYesterday", 0),
                "Last": item.get("pDrCotVal", 0),
            }
        )

    df = pd.DataFrame(rows)

    if progress:
        print("Done. {} companies returned.".format(len(df)))

    return df
