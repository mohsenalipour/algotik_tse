"""Iran Energy Exchange and Iran Mercantile Exchange market data.

The module uses only public first-party feeds published by TSETMC and IME.
Provider categories and units are kept explicit: no contract type, maturity or
monetary scale is inferred from a Persian instrument name.
"""

import datetime
import json
import math
import re
from collections.abc import Mapping

import pandas as pd
import requests
from persiantools.jdatetime import JalaliDate

from .._clock import tehran_now, tehran_today
from ..exceptions import ConnectionError, DataParsingError, InvalidParameterError
from ..http_client import safe_get, safe_post
from ..settings import settings
from .conventions import coerce_financial_date
from .resolver import validate_ins_code

ENERGY_AUCTION_COLUMNS = [
    "AuctionID",
    "InstrumentID",
    "Title",
    "Description",
    "ProductTypeCode",
    "ProductSubtypeCode",
    "ProductDescription",
    "Volume",
    "MaximumVolume",
    "TradeType",
    "BasePrice",
    "BasePriceMin",
    "BasePriceMax",
    "AuctionDateTime",
    "GregorianDate",
    "JalaliDate",
    "Producer",
    "SupplierCode",
    "PaymentTerms",
    "DeliveryTerms",
    "Packaging",
    "TargetMarket",
    "AuthorizedPriceMin",
    "AuthorizedPriceMax",
    "VolumeUnitCode",
    "VolumeUnit",
    "MinimumPurchase",
    "MinimumPriceDiscoveryVolume",
    "TickSize",
    "MaximumPurchase",
    "PriceUnitCode",
    "PriceUnit",
    "StepCode",
    "Status",
    "NextTransition",
    "EnergySymbol",
    "MaximumBuyVolume",
    "LotSize",
    "DivisionType",
    "TraderID",
    "DeliveryPlace",
    "ParallelTrade",
    "Notes",
    "BoardID",
    "DiscoveredPrice",
    "BaseVolumeUnit",
    "TradedVolume",
    "SurplusTradedVolume",
    "VWAP",
    "Board",
    "RequestedStatus",
    "Source",
]

AUCTION_TRADE_COLUMNS = [
    "AuctionID",
    "TradeDateTime",
    "GregorianDate",
    "JalaliDate",
    "Price",
    "Volume",
    "TradeScope",
    "Source",
]

ENERGY_OVERVIEW_COLUMNS = [
    "Market",
    "Flow",
    "GregorianDate",
    "JalaliDate",
    "Time",
    "TradeCount",
    "Volume",
    "Value",
    "ValueUnit",
    "StateCode",
    "State",
    "Source",
]

MARKET_INSTRUMENT_COLUMNS = [
    "Market",
    "Segment",
    "Active",
    "InsCode",
    "Symbol",
    "Name",
    "GregorianDate",
    "JalaliDate",
    "Close",
    "Last",
    "PreviousClose",
    "Open",
    "Low",
    "High",
    "Change",
    "ChangePct",
    "TradeCount",
    "Volume",
    "Value",
    "ValueUnit",
    "UnitsOutstanding",
    "ExpiryDate",
    "ExpiryJalali",
    "ContractSize",
    "ContractUnit",
    "SettlementPrice",
    "OpenInterest",
    "Source",
]

ENERGY_FUTURE_COLUMNS = [
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "BaseAsset",
    "ContractDescription",
    "ContractSize",
    "ContractUnit",
    "CurrencyPriceCode",
    "TradeCurrencyCode",
    "StartDate",
    "StartDateJalali",
    "ExpiryDate",
    "ExpiryDateJalali",
    "DeliveryDate",
    "DeliveryDateJalali",
    "PreparationDate",
    "PreparationTime",
    "SettlementPrice",
    "Last",
    "PreviousClose",
    "Open",
    "Low",
    "High",
    "TradeCount",
    "Volume",
    "Value",
    "InitialMarginRatio",
    "ActiveInitialMarginRatio",
    "MaintenanceMarginRatio",
    "ActiveMaintenanceMarginRatio",
    "AdditionalMargin",
    "BuyFeeRatio",
    "SellFeeRatio",
    "CashSettlementFeeRatio",
    "PhysicalSettlementFeeRatio",
    "PenaltyRatio",
    "MinimumSettlement",
    "MaxBrokerOpenPositions",
    "MaxClientOpenPositions",
    "MaxMarketOpenPositions",
    "TradingHours",
    "SettlementDetails",
    "BuyPrepayment",
    "SellPrepayment",
    "CurrencyReference",
    "Notes",
    "Source",
]

COMMODITY_LIVE_COLUMNS = [
    "Market",
    "Segment",
    "InsCode",
    "ISIN",
    "Symbol",
    "Name",
    "EnglishName",
    "Time",
    "StatusCode",
    "TradeCount",
    "Volume",
    "Value",
    "ValueUnit",
    "Close",
    "Last",
    "PreviousClose",
    "Open",
    "Low",
    "High",
    "Change",
    "ChangePct",
    "IndividualBuyCount",
    "LegalBuyCount",
    "IndividualBuyVolume",
    "LegalBuyVolume",
    "IndividualSellCount",
    "LegalSellCount",
    "IndividualSellVolume",
    "LegalSellVolume",
    "ExpiryJalali",
    "SettlementPrice",
    "OpenInterest",
    "ContractSize",
    "ContractUnit",
    "LastUpdate",
    "Source",
] + [
    value
    for level in range(1, 6)
    for value in (
        "BidPrice{}".format(level),
        "BidCount{}".format(level),
        "BidVolume{}".format(level),
        "AskPrice{}".format(level),
        "AskCount{}".format(level),
        "AskVolume{}".format(level),
    )
]

PHYSICAL_HISTORY_COLUMNS = [
    "GregorianDate",
    "JalaliDate",
    "Volume",
    "Value",
    "ValueUnit",
    "Source",
]

PHYSICAL_SUMMARY_COLUMNS = [
    "HallID",
    "Hall",
    "Volume",
    "OfferVolume",
    "TradeToOfferRatio",
    "Value",
    "ValueUnit",
    "StartDate",
    "EndDate",
    "Source",
]

COMMODITY_ACTIVITY_COLUMNS = [
    "MarketID",
    "Market",
    "Volume",
    "Value",
    "ValueUnit",
    "StartDate",
    "EndDate",
    "Source",
]

FUTURES_CURVE_COLUMNS = [
    "Market",
    "Segment",
    "InsCode",
    "Symbol",
    "Name",
    "Underlying",
    "ValuationDate",
    "ExpiryDate",
    "ExpiryJalali",
    "DaysToExpiry",
    "Price",
    "PriceSource",
    "SpotPrice",
    "AbsoluteBasis",
    "BasisPct",
    "AnnualizedBasis",
    "ValueUnit",
    "Source",
]


_AUCTION_STATUSES = {
    "upcoming": "ready",
    "ready": "ready",
    "آماده": "ready",
    "active": "active",
    "فعال": "active",
    "surplus": "mazad",
    "mazad": "mazad",
    "مازاد": "mazad",
    "ended": "ended",
    "closed": "ended",
    "پایان": "ended",
}

_AUCTION_BOARDS = {
    "physical": (0, "physical"),
    "فیزیکی": (0, "physical"),
    "power": (1, "power"),
    "electricity": (1, "power"),
    "برق": (1, "power"),
    "special": (2, "special"),
    "special_auction": (2, "special"),
    "green": (4, "green_power"),
    "green_power": (4, "green_power"),
    "سبز": (4, "green_power"),
    "free": (5, "free_power"),
    "free_power": (5, "free_power"),
    "آزاد": (5, "free_power"),
}

_ENERGY_FLOWS = {
    "free_power": (60, "free_power"),
    "power": (62, "power_total"),
    "standard_salaf": (63, "standard_salaf"),
    "standard_power": (64, "standard_power"),
    "securities": (65, "other_securities"),
    "future": (67, "energy_future"),
    "deposit_certificate": (68, "energy_deposit_certificate"),
    "green_power": (69, "green_power"),
}

_POWER_MARKETS = {
    "free": ("EnergyPowerTrade", 60, "free_power"),
    "standard": ("EnergyPowerTrade", 64, "standard_power"),
    "green": ("EnergyPowerTrade", 69, "green_power"),
}

_ENERGY_SECURITIES = {
    "standard_salaf": (("StandardSalaf", "StandardSalafExpired"), 6),
    "capacity_certificate": (("IRBZ",), 6),
    "energy_saving_certificate": (("IRBS", "IRBSExpired"), 6),
    "deposit_certificate": (("EngDepContinuous", "EngDepContinuousExpired "), 68),
    "future": (("EnergyFuture",), 67),
}

_IME_FINANCIAL_KINDS = {
    "certificate": "gavahi",
    "deposit_certificate": "gavahi",
    "گواهی": "gavahi",
    "standard_salaf": "salaf",
    "salaf": "salaf",
    "سلف": "salaf",
    "fund": "sandoq",
    "funds": "sandoq",
    "صندوق": "sandoq",
}


def _empty(columns, **attrs):
    frame = pd.DataFrame(columns=columns)
    frame.attrs.update(attrs)
    return frame


def _clean_text(value):
    if value is None:
        return pd.NA
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else pd.NA


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return result if math.isfinite(result) else float("nan")


def _integer(value):
    result = _number(value)
    return pd.NA if math.isnan(result) else int(result)


def _pct_change(last, previous):
    last, previous = _number(last), _number(previous)
    if math.isnan(last) or math.isnan(previous) or previous == 0:
        return float("nan")
    return (last / previous - 1.0) * 100.0


def _provider_date(value):
    if value in (None, "", 0, "0"):
        return None
    text = str(_integer(value))
    if len(text) != 8 or not text.isdigit() or not 1900 <= int(text[:4]) <= 2200:
        return None
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except (TypeError, ValueError) as exc:
        raise DataParsingError("provider returned an invalid YYYYMMDD date") from exc


def _date_pair(value):
    date = _provider_date(value)
    if date is None:
        return pd.NaT, pd.NA
    return pd.Timestamp(date), JalaliDate.to_jalali(date).isoformat()


def _jalali_to_date(value, name="date"):
    if (
        value is None
        or value is pd.NA
        or (isinstance(value, str) and not value.strip())
    ):
        return None
    text = str(value).strip().replace("-", "/")
    try:
        parts = [int(part) for part in text.split("/")]
        if len(parts) != 3:
            raise ValueError
        if parts[0] >= 1700:
            return datetime.date(*parts)
        return JalaliDate(*parts).to_gregorian()
    except (TypeError, ValueError) as exc:
        raise DataParsingError(
            "{} returned by provider is invalid".format(name)
        ) from exc


def _positive_int(value, name, maximum=1000):
    if isinstance(value, bool):
        raise InvalidParameterError("{} must be a positive integer".format(name))
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(
            "{} must be a positive integer".format(name)
        ) from exc
    if result <= 0 or result != float(value) or result > maximum:
        raise InvalidParameterError("{} must be between 1 and {}".format(name, maximum))
    return result


def _response_json(response, context):
    try:
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise ConnectionError("{} request failed".format(context)) from exc
    except (TypeError, ValueError) as exc:
        raise DataParsingError("{} returned invalid JSON".format(context)) from exc


def _rows(payload, key, context):
    if not isinstance(payload, Mapping) or not isinstance(payload.get(key), list):
        raise DataParsingError("{} response is missing {!r}".format(context, key))
    return payload[key]


def _finalize(frame, columns, attrs, sort=None):
    frame = frame.reindex(columns=columns)
    if sort and not frame.empty:
        frame = frame.sort_values(sort, ignore_index=True, na_position="last")
    metadata = dict(attrs)
    metadata.setdefault("fetched_at", tehran_now().isoformat())
    metadata.setdefault("row_count", len(frame))
    metadata.setdefault("coverage", "complete_provider_response")
    metadata.setdefault("quality_flags", ())
    frame.attrs.update(metadata)
    return frame


def _auction_record(raw, auction_id=None, board=None, requested_status=None):
    date_time = pd.to_datetime(raw.get("auctionDate"), errors="coerce")
    date = date_time.date() if not pd.isna(date_time) else None
    return {
        "AuctionID": auction_id if auction_id is not None else _integer(raw.get("idn")),
        "InstrumentID": _integer(raw.get("instrumentID")),
        "Title": _clean_text(raw.get("auctionTitle")),
        "Description": _clean_text(raw.get("auctionDesc")),
        "ProductTypeCode": _integer(raw.get("productTypeCode")),
        "ProductSubtypeCode": _integer(raw.get("productsubTypeCode")),
        "ProductDescription": _clean_text(raw.get("productDesc")),
        "Volume": _number(raw.get("auctionVol")),
        "MaximumVolume": _number(raw.get("auctionMaxVol")),
        "TradeType": _clean_text(raw.get("tradeType")),
        "BasePrice": _number(raw.get("basePrice")),
        "BasePriceMin": _number(raw.get("basePriceMin")),
        "BasePriceMax": _number(raw.get("basePriceMax")),
        "AuctionDateTime": date_time,
        "GregorianDate": pd.Timestamp(date) if date else pd.NaT,
        "JalaliDate": JalaliDate.to_jalali(date).isoformat() if date else pd.NA,
        "Producer": _clean_text(raw.get("producerName")),
        "SupplierCode": _clean_text(raw.get("supplierName")),
        "PaymentTerms": _clean_text(raw.get("termsOfPayment")),
        "DeliveryTerms": _clean_text(raw.get("termsOfDelivery")),
        "Packaging": _clean_text(
            raw.get("typeOfPackaging") or raw.get("packagingTitle")
        ),
        "TargetMarket": _clean_text(raw.get("targetMarket")),
        "AuthorizedPriceMin": _number(raw.get("authorizedPriceMin")),
        "AuthorizedPriceMax": _number(raw.get("authorizedPriceMax")),
        "VolumeUnitCode": _integer(raw.get("volUnitCode")),
        "VolumeUnit": _clean_text(raw.get("volUnitTitle")),
        "MinimumPurchase": _number(raw.get("minimumPurchase")),
        "MinimumPriceDiscoveryVolume": _number(
            raw.get("minimumPurchaseForPriceDiscovery")
        ),
        "TickSize": _number(raw.get("tickSize")),
        "MaximumPurchase": _number(raw.get("maximumPurchase")),
        "PriceUnitCode": _integer(raw.get("priceUnitCode")),
        "PriceUnit": _clean_text(raw.get("priceUnitTitle")),
        "StepCode": _integer(raw.get("stepCode")),
        "Status": _clean_text(raw.get("stepTitle")),
        "NextTransition": pd.to_datetime(raw.get("nextTransition"), errors="coerce"),
        "EnergySymbol": _clean_text(raw.get("energySymbol")),
        "MaximumBuyVolume": _number(raw.get("maxBuyVol")),
        "LotSize": _number(raw.get("lotSize")),
        "DivisionType": _integer(raw.get("divisionType")),
        "TraderID": _clean_text(raw.get("traderID")),
        "DeliveryPlace": _clean_text(raw.get("placeOfDelivery")),
        "ParallelTrade": _clean_text(raw.get("parallelInductorTrade")),
        "Notes": _clean_text(raw.get("adminDesc")),
        "BoardID": _integer(raw.get("boardId")),
        "DiscoveredPrice": _number(raw.get("discoveredPrice")),
        "BaseVolumeUnit": _clean_text(raw.get("baseVolUnitTitle")),
        "TradedVolume": _number(raw.get("tradedQuantity")),
        "SurplusTradedVolume": _number(raw.get("mazadTradedQuantity")),
        "VWAP": _number(raw.get("wap")),
        "Board": board if board is not None else pd.NA,
        "RequestedStatus": requested_status if requested_status is not None else pd.NA,
        "Source": "tsetmc_energy_auction",
    }


def get_energy_auctions(status="upcoming", board="physical", top=100):
    """Return official Iran Energy Exchange auction notices.

    ``status='all'`` and ``board='all'`` request every verified provider
    category. The result retains delivery, payment, price-band, lot-size and
    discovery fields required to evaluate an auction.
    """
    top = _positive_int(top, "top")
    status_key = str(status).strip().lower()
    board_key = str(board).strip().lower()
    statuses = (
        list(dict.fromkeys(_AUCTION_STATUSES.values()))
        if status_key in {"all", "همه"}
        else [_AUCTION_STATUSES.get(status_key)]
    )
    boards = (
        list(dict.fromkeys(_AUCTION_BOARDS.values()))
        if board_key in {"all", "همه"}
        else [_AUCTION_BOARDS.get(board_key)]
    )
    if None in statuses:
        raise InvalidParameterError(
            "status must be upcoming, active, surplus, ended, or all"
        )
    if None in boards:
        raise InvalidParameterError(
            "board must be physical, power, special, green, free, or all"
        )
    records = []
    for provider_status in statuses:
        for board_id, board_name in boards:
            payload = _response_json(
                safe_get(
                    settings.url_energy_auction_list.format(
                        provider_status, top, board_id
                    )
                ),
                "TSETMC energy auction list",
            )
            for raw in _rows(payload, "auctionListItem", "TSETMC energy auction list")[
                :top
            ]:
                records.append(
                    _auction_record(
                        raw, board=board_name, requested_status=provider_status
                    )
                )
    return _finalize(
        pd.DataFrame(records),
        ENERGY_AUCTION_COLUMNS,
        {
            "source": "tsetmc_energy_auction",
            "request_count": len(statuses) * len(boards),
            "board": board_key,
            "status": status_key,
            "is_partial": False,
        },
        ["AuctionDateTime", "AuctionID"],
    )


def _auction_trades(auction_id, url, trade_scope):
    payload = _response_json(
        safe_get(url.format(auction_id)), "TSETMC energy auction trades"
    )
    records = []
    for raw in _rows(payload, "auctionTrade", "TSETMC energy auction trades"):
        stamp = pd.to_datetime(raw.get("tradeDate"), errors="coerce")
        date = stamp.date() if not pd.isna(stamp) else None
        records.append(
            {
                "AuctionID": auction_id,
                "TradeDateTime": stamp,
                "GregorianDate": pd.Timestamp(date) if date else pd.NaT,
                "JalaliDate": JalaliDate.to_jalali(date).isoformat() if date else pd.NA,
                "Price": _number(raw.get("tradedPrice")),
                "Volume": _number(raw.get("tradedQuantity")),
                "TradeScope": trade_scope,
                "Source": "tsetmc_energy_auction",
            }
        )
    return _finalize(
        pd.DataFrame(records),
        AUCTION_TRADE_COLUMNS,
        {
            "source": "tsetmc_energy_auction",
            "auction_id": auction_id,
            "trade_scope": trade_scope,
            "is_partial": False,
        },
        ["TradeDateTime"],
    )


def get_energy_auction(
    auction_id, include_trades=True, include_instrument_history=False
):
    """Return one auction plus its own trades and optional instrument history.

    ``include_instrument_history`` is opt-in because TSETMC's second trade feed
    contains earlier auctions of the same instrument, not trades of this single
    auction. The return value is a dictionary of DataFrames.
    """
    auction_id = _positive_int(auction_id, "auction_id", maximum=10**12)
    if not isinstance(include_trades, bool) or not isinstance(
        include_instrument_history, bool
    ):
        raise InvalidParameterError(
            "include_trades and include_instrument_history must be bool"
        )
    payload = _response_json(
        safe_get(settings.url_energy_auction_detail.format(auction_id)),
        "TSETMC energy auction detail",
    )
    raw = payload.get("auction") if isinstance(payload, Mapping) else None
    if not isinstance(raw, Mapping):
        raise DataParsingError("TSETMC energy auction detail is missing 'auction'")
    auction = _finalize(
        pd.DataFrame([_auction_record(raw, auction_id=auction_id)]),
        ENERGY_AUCTION_COLUMNS,
        {
            "source": "tsetmc_energy_auction",
            "auction_id": auction_id,
            "is_partial": False,
        },
    )
    result = {"auction": auction}
    if include_trades:
        result["auction_trades"] = _auction_trades(
            auction_id, settings.url_energy_auction_trades, "auction"
        )
    if include_instrument_history:
        result["instrument_history"] = _auction_trades(
            auction_id,
            settings.url_energy_instrument_auction_trades,
            "instrument_history",
        )
    return result


def get_energy_market_overview(market="all"):
    """Return official daily activity for verified energy-market flows."""
    key = str(market).strip().lower()
    selected = (
        list(_ENERGY_FLOWS.values())
        if key in {"all", "همه"}
        else [_ENERGY_FLOWS.get(key)]
    )
    if None in selected:
        raise InvalidParameterError(
            "unknown energy market; use one of {} or all".format(
                ", ".join(_ENERGY_FLOWS)
            )
        )
    records = []
    for flow, label in selected:
        payload = _response_json(
            safe_get(settings.url_market_overview.format(flow)),
            "TSETMC energy overview",
        )
        raw = payload.get("marketOverview") if isinstance(payload, Mapping) else None
        if not isinstance(raw, Mapping):
            raise DataParsingError("TSETMC energy overview is missing 'marketOverview'")
        date, jalali = _date_pair(raw.get("marketActivityDEven"))
        records.append(
            {
                "Market": label,
                "Flow": flow,
                "GregorianDate": date,
                "JalaliDate": jalali,
                "Time": (
                    str(_integer(raw.get("marketActivityHEven"))).zfill(6)
                    if raw.get("marketActivityHEven")
                    else pd.NA
                ),
                "TradeCount": _integer(raw.get("marketActivityZTotTran")),
                "Volume": _number(raw.get("marketActivityQTotTran")),
                "Value": _number(raw.get("marketActivityQTotCap")),
                "ValueUnit": "rial",
                "StateCode": _clean_text(raw.get("marketState")),
                "State": _clean_text(raw.get("marketStateTitle")),
                "Source": "tsetmc_energy_market_overview",
            }
        )
    return _finalize(
        pd.DataFrame(records),
        ENERGY_OVERVIEW_COLUMNS,
        {
            "source": "tsetmc_energy_market_overview",
            "request_count": len(selected),
            "market": key,
            "is_partial": False,
        },
        ["Flow"],
    )


def _trade_top(provider_type, flow, segment, market, top, active=True):
    payload = _response_json(
        safe_get(settings.url_energy_trade_top.format(provider_type, flow, top)),
        "TSETMC trade-top",
    )
    records = []
    for raw in _rows(payload, "tradeTop", "TSETMC trade-top"):
        instrument = raw.get("instrument") or {}
        date, jalali = _date_pair(raw.get("dEven"))
        last, previous = raw.get("pDrCotVal"), raw.get("priceYesterday")
        records.append(
            {
                "Market": market,
                "Segment": segment,
                "Active": bool(active),
                "InsCode": _clean_text(raw.get("insCode") or instrument.get("insCode")),
                "Symbol": _clean_text(instrument.get("lVal18AFC")),
                "Name": _clean_text(instrument.get("lVal30")),
                "GregorianDate": date,
                "JalaliDate": jalali,
                "Close": _number(raw.get("pClosing")),
                "Last": _number(last),
                "PreviousClose": _number(previous),
                "Open": _number(raw.get("priceFirst")),
                "Low": _number(raw.get("priceMin")),
                "High": _number(raw.get("priceMax")),
                "Change": _number(raw.get("priceChange")),
                "ChangePct": _pct_change(last, previous),
                "TradeCount": _integer(raw.get("zTotTran")),
                "Volume": _number(raw.get("qTotTran5J")),
                "Value": _number(raw.get("qTotCap")),
                "ValueUnit": "rial",
                "UnitsOutstanding": _number(instrument.get("zTitad")),
                "Source": "tsetmc_trade_top",
            }
        )
    return records


def list_power_instruments(market="all", top=100):
    """List standard, green and free-electricity contracts from TSETMC."""
    top = _positive_int(top, "top")
    key = str(market).strip().lower()
    selected = (
        list(_POWER_MARKETS.values())
        if key in {"all", "همه"}
        else [_POWER_MARKETS.get(key)]
    )
    if None in selected:
        raise InvalidParameterError("market must be standard, green, free, or all")
    records = []
    for provider_type, flow, label in selected:
        records.extend(_trade_top(provider_type, flow, label, "energy", top))
    return _finalize(
        pd.DataFrame(records),
        MARKET_INSTRUMENT_COLUMNS,
        {
            "source": "tsetmc_trade_top",
            "market": key,
            "request_count": len(selected),
            "is_partial": False,
        },
        ["Segment", "Symbol"],
    )


def list_energy_securities(kind="all", active=True, top=100, enrich_futures=True):
    """List energy salaf, certificates and futures by exact provider category."""
    top = _positive_int(top, "top")
    key = str(kind).strip().lower()
    if not isinstance(active, bool) or not isinstance(enrich_futures, bool):
        raise InvalidParameterError("active and enrich_futures must be bool")
    selected = (
        list(_ENERGY_SECURITIES.items())
        if key in {"all", "همه"}
        else [(key, _ENERGY_SECURITIES.get(key))]
    )
    if any(spec is None for _, spec in selected):
        raise InvalidParameterError(
            "unknown kind; use one of {} or all".format(", ".join(_ENERGY_SECURITIES))
        )
    records, requests_made = [], 0
    for label, (provider_types, flow) in selected:
        types = provider_types if not active else provider_types[:1]
        for index, provider_type in enumerate(types):
            records.extend(
                _trade_top(provider_type, flow, label, "energy", top, active=index == 0)
            )
            requests_made += 1
    if enrich_futures:
        for record in records:
            if record["Segment"] == "future" and record["InsCode"] is not pd.NA:
                detail = get_energy_future_contract(record["InsCode"])
                requests_made += 1
                if not detail.empty:
                    item = detail.iloc[0]
                    record.update(
                        {
                            "ExpiryDate": item["ExpiryDate"],
                            "ExpiryJalali": item["ExpiryDateJalali"],
                            "ContractSize": item["ContractSize"],
                            "ContractUnit": item["ContractUnit"],
                            "SettlementPrice": item["SettlementPrice"],
                        }
                    )
    return _finalize(
        pd.DataFrame(records),
        MARKET_INSTRUMENT_COLUMNS,
        {
            "source": "tsetmc_trade_top",
            "kind": key,
            "active": active,
            "request_count": requests_made,
            "is_partial": False,
        },
        ["Segment", "ExpiryDate", "Symbol"],
    )


def get_energy_future_contract(ins_code):
    """Return the official specification and margins of one energy future."""
    code = validate_ins_code(ins_code)
    payload = _response_json(
        safe_get(settings.url_energy_future_detail.format(code)),
        "TSETMC energy future detail",
    )
    raw = (
        payload.get("instrumentEnergyFuture") if isinstance(payload, Mapping) else None
    )
    if not isinstance(raw, Mapping):
        raise DataParsingError(
            "TSETMC energy future detail is missing 'instrumentEnergyFuture'"
        )
    start, start_j = _date_pair(raw.get("beginDate"))
    expiry, expiry_j = _date_pair(raw.get("endDate"))
    delivery, delivery_j = _date_pair(raw.get("stlmntDlvryDate"))
    preparation, _ = _date_pair(raw.get("prepareDate"))
    record = {
        "InsCode": code,
        "ISIN": _clean_text(raw.get("cisin")),
        "Symbol": _clean_text(raw.get("cCode")),
        "Name": _clean_text(raw.get("desc")),
        "BaseAsset": _clean_text(raw.get("baseAsset")),
        "ContractDescription": _clean_text(raw.get("edsContract")),
        "ContractSize": _number(raw.get("quantity")),
        "ContractUnit": _clean_text(raw.get("unitName")),
        "CurrencyPriceCode": _integer(raw.get("currenciesPrice")),
        "TradeCurrencyCode": _integer(raw.get("currencyTrade")),
        "StartDate": start,
        "StartDateJalali": start_j,
        "ExpiryDate": expiry,
        "ExpiryDateJalali": expiry_j,
        "DeliveryDate": delivery,
        "DeliveryDateJalali": delivery_j,
        "PreparationDate": preparation,
        "PreparationTime": (
            str(_integer(raw.get("prepareTime"))).zfill(6)
            if raw.get("prepareTime")
            else pd.NA
        ),
        "SettlementPrice": _number(raw.get("closingPrice") or raw.get("editedPrice")),
        "Last": _number(raw.get("pDrCotVal")),
        "PreviousClose": _number(raw.get("priceYesterday")),
        "Open": _number(raw.get("priceFirst")),
        "Low": _number(raw.get("priceMin")),
        "High": _number(raw.get("priceMax")),
        "TradeCount": _integer(raw.get("zTotTran")),
        "Volume": _number(raw.get("qTotTran5J")),
        "Value": _number(raw.get("qTotCap")),
        "InitialMarginRatio": _number(raw.get("imaValue")),
        "ActiveInitialMarginRatio": _number(raw.get("imaValueAct")),
        "MaintenanceMarginRatio": _number(raw.get("rmbValue")),
        "ActiveMaintenanceMarginRatio": _number(raw.get("rmbValueAct")),
        "AdditionalMargin": _number(
            raw.get("dExtraMarginAct") or raw.get("dExtraMargin")
        ),
        "BuyFeeRatio": _number(raw.get("buyFeeRatio")),
        "SellFeeRatio": _number(raw.get("sellFeeRatio")),
        "CashSettlementFeeRatio": _number(raw.get("cashFeeRatio")),
        "PhysicalSettlementFeeRatio": _number(raw.get("physFeeRatio")),
        "PenaltyRatio": _number(raw.get("penaltyRatio")),
        "MinimumSettlement": _number(raw.get("minSettelment")),
        "MaxBrokerOpenPositions": _integer(
            raw.get("maxBrockerOPAct") or raw.get("maxBrockerOP")
        ),
        "MaxClientOpenPositions": _integer(
            raw.get("maxClientOPAct") or raw.get("maxClientOP")
        ),
        "MaxMarketOpenPositions": _integer(
            raw.get("maxMarketOPAct") or raw.get("maxMarketOP")
        ),
        "TradingHours": _clean_text(raw.get("tradingTimeDate")),
        "SettlementDetails": _clean_text(raw.get("settlementDetails")),
        "BuyPrepayment": _clean_text(raw.get("prePaidBuy")),
        "SellPrepayment": _clean_text(raw.get("prePaidSell")),
        "CurrencyReference": _clean_text(raw.get("currExRef")),
        "Notes": _clean_text(raw.get("descryption")),
        "Source": "tsetmc_energy_future_detail",
    }
    return _finalize(
        pd.DataFrame([record]),
        ENERGY_FUTURE_COLUMNS,
        {
            "source": "tsetmc_energy_future_detail",
            "ins_code": code,
            "is_partial": False,
        },
    )


def _ime_headers(host="cdn"):
    origin = "https://cdn.ime.co.ir" if host == "cdn" else "https://www.ime.co.ir"
    return {
        **settings.headers,
        "Accept": "application/json, text/plain, */*",
        "Referer": origin + "/",
        "Origin": origin,
        "X-Requested-With": "XMLHttpRequest",
    }


def _ime_financial_record(raw, segment):
    last, previous = raw.get("LastPrice"), raw.get("YesterdayPrice")
    match = re.search(r"-?\d+", str(raw.get("ModifyDate", "")))
    update = (
        pd.to_datetime(int(match.group()), unit="ms", errors="coerce")
        if match
        else pd.NaT
    )
    record = {
        "Market": "commodity",
        "Segment": segment,
        "InsCode": _clean_text(raw.get("InsCode")),
        "ISIN": _clean_text(raw.get("Code")),
        "Symbol": _clean_text(raw.get("Symbol")),
        "Name": _clean_text(raw.get("Name")),
        "EnglishName": _clean_text(raw.get("EnName")),
        "Time": _clean_text(raw.get("Time")),
        "StatusCode": _integer(raw.get("Status")),
        "TradeCount": _integer(raw.get("Quantity")),
        "Volume": _number(raw.get("Volume")),
        "Value": _number(raw.get("Value")),
        "ValueUnit": "thousand_rial",
        "Close": _number(raw.get("FinalPrice")),
        "Last": _number(last),
        "PreviousClose": _number(previous),
        "Open": _number(raw.get("FirstPrice")),
        "Low": _number(raw.get("MinPrice")),
        "High": _number(raw.get("MaxPrice")),
        "Change": _number(raw.get("PriceChange")),
        "ChangePct": _pct_change(last, previous),
        "IndividualBuyCount": _integer(raw.get("Buy_Count_ClientI")),
        "LegalBuyCount": _integer(raw.get("Buy_Count_ClientN")),
        "IndividualBuyVolume": _number(raw.get("Buy_I_Volume")),
        "LegalBuyVolume": _number(raw.get("Buy_N_Volume")),
        "IndividualSellCount": _integer(raw.get("Sell_Count_ClientI")),
        "LegalSellCount": _integer(raw.get("Sell_Count_ClientN")),
        "IndividualSellVolume": _number(raw.get("Sell_I_Volume")),
        "LegalSellVolume": _number(raw.get("Sell_N_Volume")),
        "LastUpdate": update,
        "Source": "ime_trading_board",
    }
    for level in range(1, 6):
        record.update(
            {
                "BidPrice{}".format(level): _number(
                    raw.get("DemandPrice{}".format(level))
                ),
                "BidCount{}".format(level): _integer(
                    raw.get("DemandQuantity{}".format(level))
                ),
                "BidVolume{}".format(level): _number(
                    raw.get("DemandVolume{}".format(level))
                ),
                "AskPrice{}".format(level): _number(
                    raw.get("OfferPrice{}".format(level))
                ),
                "AskCount{}".format(level): _integer(
                    raw.get("OfferQuantity{}".format(level))
                ),
                "AskVolume{}".format(level): _number(
                    raw.get("OfferVolume{}".format(level))
                ),
            }
        )
    return record


def _ime_future_record(raw):
    expiry_j = _clean_text(raw.get("PesrsianLastTradingDate"))
    return {
        "Market": "commodity",
        "Segment": "future",
        "InsCode": _clean_text(raw.get("InsCode")),
        "ISIN": _clean_text(raw.get("ContractCode")),
        "Symbol": _clean_text(raw.get("ContractCode")),
        "Name": _clean_text(raw.get("ContractCode")),
        "EnglishName": pd.NA,
        "Time": _clean_text(raw.get("LastTradedPriceTime")),
        "TradeCount": _integer(raw.get("TradeCount")),
        "Volume": _number(raw.get("TradesVolume")),
        "Value": _number(raw.get("TradesValue")),
        "ValueUnit": "thousand_rial",
        "Close": _number(raw.get("TodayLiveSettlement")),
        "Last": _number(raw.get("LastTradedPrice")),
        "PreviousClose": _number(raw.get("LastSettlementPrice")),
        "Open": _number(raw.get("FirstTradedPrice")),
        "Low": _number(raw.get("LowTradedPrice")),
        "High": _number(raw.get("HighTradedPrice")),
        "Change": _number(raw.get("LastTradedPriceChanges")),
        "ChangePct": _number(raw.get("LastTradedPriceChangesPercent")),
        "ExpiryJalali": expiry_j,
        "SettlementPrice": _number(
            raw.get("TodayLiveSettlement") or raw.get("LastSettlementPrice")
        ),
        "OpenInterest": _number(raw.get("OpenInterests")),
        "ContractSize": _number(raw.get("ContractSize")),
        "ContractUnit": _clean_text(raw.get("ContractSizeUnitFaDesc")),
        "Source": "ime_trading_board",
    }


def get_commodity_market(kind="all"):
    """Return IME's live certificates, salaf, funds and futures board.

    Monetary ``Value`` is published by IME in thousand rials and is therefore
    never silently rescaled; ``ValueUnit`` records that unit on every row.
    """
    key = str(kind).strip().lower()
    kinds = [
        ("certificate", "gavahi"),
        ("standard_salaf", "salaf"),
        ("fund", "sandoq"),
        ("future", "future"),
    ]
    if key not in {"all", "همه"}:
        if key in {"future", "futures", "آتی"}:
            kinds = [("future", "future")]
        elif key in _IME_FINANCIAL_KINDS:
            provider = _IME_FINANCIAL_KINDS[key]
            label = {
                "gavahi": "certificate",
                "salaf": "standard_salaf",
                "sandoq": "fund",
            }[provider]
            kinds = [(label, provider)]
        else:
            raise InvalidParameterError(
                "kind must be certificate, standard_salaf, fund, future, or all"
            )
    records = []
    for label, provider in kinds:
        url = (
            settings.url_ime_futures_market
            if provider == "future"
            else settings.url_ime_financial_market.format(provider)
        )
        payload = _response_json(
            safe_get(url, headers=_ime_headers()), "IME trading board"
        )
        if not isinstance(payload, list):
            raise DataParsingError("IME trading board must return a list")
        records.extend(
            (
                _ime_future_record(raw)
                if provider == "future"
                else _ime_financial_record(raw, label)
            )
            for raw in payload
        )
    return _finalize(
        pd.DataFrame(records),
        COMMODITY_LIVE_COLUMNS,
        {
            "source": "ime_trading_board",
            "kind": key,
            "request_count": len(kinds),
            "value_unit": "thousand_rial",
            "is_partial": False,
        },
        ["Segment", "Symbol"],
    )


def _ime_range(start, end):
    try:
        start_date = coerce_financial_date(start, "start")
        end_date = coerce_financial_date(end, "end")
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc
    if start_date > end_date:
        raise InvalidParameterError("start must be on or before end")
    return (
        start_date,
        end_date,
        JalaliDate.to_jalali(start_date).strftime("%Y/%m/%d"),
        JalaliDate.to_jalali(end_date).strftime("%Y/%m/%d"),
    )


def _ime_home(operation, start, end):
    start_date, end_date, start_j, end_j = _ime_range(start, end)
    payload = _response_json(
        safe_post(
            settings.url_ime_home_service.format(operation),
            json={
                "Language": 8,
                "GregorianFromDate": start_j,
                "GregorianToDate": end_j,
            },
            headers=_ime_headers("www"),
        ),
        "IME historical market service",
    )
    raw = payload.get("d") if isinstance(payload, Mapping) else None
    try:
        while isinstance(raw, str):
            raw = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise DataParsingError(
            "IME historical market service returned invalid embedded JSON"
        ) from exc
    if not isinstance(raw, list):
        raise DataParsingError("IME historical market service must return a list")
    return raw, start_date, end_date


def get_commodity_physical_history(start, end=None):
    """Return daily physical-market volume and value for an explicit range."""
    if end is None:
        end = tehran_today()
    rows, start_date, end_date = _ime_home("GetHajmArzeshMoamelatDateGrid", start, end)
    records = []
    for raw in rows:
        date = _jalali_to_date(raw.get("TradeDate"), "TradeDate")
        records.append(
            {
                "GregorianDate": pd.Timestamp(date),
                "JalaliDate": JalaliDate.to_jalali(date).isoformat(),
                "Volume": _number(raw.get("TradeVolume")),
                "Value": _number(raw.get("TradeValue")),
                "ValueUnit": "million_rial",
                "Source": "ime_physical_history",
            }
        )
    return _finalize(
        pd.DataFrame(records),
        PHYSICAL_HISTORY_COLUMNS,
        {
            "source": "ime_physical_history",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "value_unit": "million_rial",
            "is_partial": False,
        },
        ["GregorianDate"],
    )


def get_commodity_physical_summary(start, end=None, hall="all"):
    """Aggregate physical-market value, volume and offer coverage by hall."""
    if end is None:
        end = tehran_today()
    rows, start_date, end_date = _ime_home("GetHomeFizikiWithDateGrid", start, end)
    key = str(hall).strip()
    records = []
    for raw in rows:
        hall_name = _clean_text(raw.get("xRingName"))
        if key.lower() not in {"all", "همه"} and key not in {
            str(raw.get("ID")),
            str(hall_name),
        }:
            continue
        volume, offer = _number(raw.get("Volume")), _number(raw.get("OfferVolume"))
        ratio = (
            volume / offer
            if not math.isnan(volume) and not math.isnan(offer) and offer
            else float("nan")
        )
        records.append(
            {
                "HallID": _integer(raw.get("ID")),
                "Hall": hall_name,
                "Volume": volume,
                "OfferVolume": offer,
                "TradeToOfferRatio": ratio,
                "Value": _number(raw.get("Value")),
                "ValueUnit": "million_rial",
                "StartDate": start_date,
                "EndDate": end_date,
                "Source": "ime_physical_summary",
            }
        )
    return _finalize(
        pd.DataFrame(records),
        PHYSICAL_SUMMARY_COLUMNS,
        {
            "source": "ime_physical_summary",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "hall": key,
            "value_unit": "million_rial",
            "is_partial": False,
        },
        ["HallID"],
    )


def get_commodity_market_activity(start, end=None, market="all"):
    """Aggregate IME activity across physical, future, option and financial markets."""
    if end is None:
        end = tehran_today()
    rows, start_date, end_date = _ime_home("GetHomeNamaWithDateGrid", start, end)
    key = str(market).strip()
    records = []
    for raw in rows:
        name, market_id = _clean_text(raw.get("name")), str(raw.get("Id"))
        if key.lower() not in {"all", "همه"} and key not in {market_id, str(name)}:
            continue
        records.append(
            {
                "MarketID": _integer(raw.get("Id")),
                "Market": name,
                "Volume": _number(raw.get("TradeVolume")),
                "Value": _number(raw.get("TradeValue")),
                "ValueUnit": "million_rial",
                "StartDate": start_date,
                "EndDate": end_date,
                "Source": "ime_market_activity",
            }
        )
    return _finalize(
        pd.DataFrame(records),
        COMMODITY_ACTIVITY_COLUMNS,
        {
            "source": "ime_market_activity",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "market": key,
            "value_unit": "million_rial",
            "is_partial": False,
        },
        ["MarketID"],
    )


def _date_value(value, name):
    if isinstance(value, pd.Timestamp):
        return value.date()
    try:
        return coerce_financial_date(value, name)
    except ValueError as exc:
        raise InvalidParameterError(str(exc)) from exc


def get_futures_curve(
    contracts, underlying=None, valuation_date=None, price="settlement", spot_price=None
):
    """Build a maturity-sorted futures curve from explicit contract rows."""
    if not isinstance(contracts, pd.DataFrame):
        contracts = pd.DataFrame(contracts)
    price_key = str(price).strip().lower()
    candidates = {
        "settlement": ("SettlementPrice", "Close", "Last"),
        "close": ("Close", "SettlementPrice", "Last"),
        "last": ("Last", "Close", "SettlementPrice"),
    }
    if price_key not in candidates:
        raise InvalidParameterError("price must be settlement, close, or last")
    expiry_column = next(
        (
            name
            for name in ("ExpiryDate", "Expiry", "MaturityDate")
            if name in contracts
        ),
        None,
    )
    if expiry_column is None:
        raise InvalidParameterError(
            "contracts must contain ExpiryDate, Expiry, or MaturityDate"
        )
    price_columns = [name for name in candidates[price_key] if name in contracts]
    if not price_columns:
        raise InvalidParameterError(
            "contracts do not contain a usable {} price".format(price_key)
        )
    valuation = (
        tehran_today()
        if valuation_date is None
        else _date_value(valuation_date, "valuation_date")
    )
    if spot_price is not None:
        spot_price = float(spot_price)
        if not math.isfinite(spot_price) or spot_price <= 0:
            raise InvalidParameterError("spot_price must be positive and finite")
    default_value_unit = contracts.attrs.get("value_unit", pd.NA)
    records = []
    for _, raw in contracts.iterrows():
        if underlying is not None:
            base = raw.get("BaseAsset", raw.get("Underlying", raw.get("Name", "")))
            if str(underlying).strip() not in str(base):
                continue
        expiry_raw = raw.get(expiry_column)
        if pd.isna(expiry_raw):
            continue
        expiry = _date_value(expiry_raw, expiry_column)
        days = (expiry - valuation).days
        price_column, contract_price = None, float("nan")
        for candidate in price_columns:
            candidate_price = _number(raw.get(candidate))
            if not math.isnan(candidate_price):
                price_column, contract_price = candidate, candidate_price
                break
        absolute = (
            contract_price - spot_price
            if spot_price is not None and not math.isnan(contract_price)
            else float("nan")
        )
        basis_pct = (
            absolute / spot_price * 100.0
            if spot_price is not None and not math.isnan(absolute)
            else float("nan")
        )
        annual = (
            basis_pct * 365.0 / days
            if days > 0 and not math.isnan(basis_pct)
            else float("nan")
        )
        records.append(
            {
                "Market": raw.get("Market", pd.NA),
                "Segment": raw.get("Segment", "future"),
                "InsCode": raw.get("InsCode", pd.NA),
                "Symbol": raw.get("Symbol", pd.NA),
                "Name": raw.get("Name", pd.NA),
                "Underlying": raw.get("BaseAsset", raw.get("Underlying", underlying)),
                "ValuationDate": valuation,
                "ExpiryDate": expiry,
                "ExpiryJalali": JalaliDate.to_jalali(expiry).isoformat(),
                "DaysToExpiry": days,
                "Price": contract_price,
                "PriceSource": price_column,
                "SpotPrice": spot_price,
                "AbsoluteBasis": absolute,
                "BasisPct": basis_pct,
                "AnnualizedBasis": annual,
                "ValueUnit": raw.get("ValueUnit", default_value_unit),
                "Source": "calculated_from_explicit_contracts",
            }
        )
    frame = pd.DataFrame(records)
    value_units = (
        frame["ValueUnit"].dropna().astype(str).str.strip().replace("", pd.NA).dropna()
        if "ValueUnit" in frame
        else pd.Series(dtype="object")
    )
    unique_units = tuple(sorted(value_units.unique()))
    if len(unique_units) > 1:
        raise InvalidParameterError(
            "contracts must use one ValueUnit before curve calculations"
        )
    return _finalize(
        frame,
        FUTURES_CURVE_COLUMNS,
        {
            "source": "calculated_from_explicit_contracts",
            "valuation_date": valuation.isoformat(),
            "price_priority": price_key,
            "available_price_columns": tuple(price_columns),
            "spot_price": spot_price,
            "value_unit": unique_units[0] if unique_units else None,
            "is_partial": False,
        },
        ["ExpiryDate", "Symbol"],
    )


def get_calendar_spreads(curve):
    """Calculate adjacent-expiry spreads from a futures curve."""
    if not isinstance(curve, pd.DataFrame):
        curve = pd.DataFrame(curve)
    required = {"ExpiryDate", "Price"}
    if not required <= set(curve.columns):
        raise InvalidParameterError("curve must contain ExpiryDate and Price")
    ordered = curve.copy().sort_values("ExpiryDate", ignore_index=True)
    records = []
    for index in range(len(ordered) - 1):
        near, far = ordered.iloc[index], ordered.iloc[index + 1]
        near_price, far_price = _number(near["Price"]), _number(far["Price"])
        near_expiry, far_expiry = _date_value(
            near["ExpiryDate"], "ExpiryDate"
        ), _date_value(far["ExpiryDate"], "ExpiryDate")
        days = (far_expiry - near_expiry).days
        spread = far_price - near_price
        finite_prices = not math.isnan(near_price) and not math.isnan(far_price)
        if not finite_prices:
            spread = float("nan")
        near_unit, far_unit = near.get("ValueUnit", pd.NA), far.get("ValueUnit", pd.NA)
        if pd.notna(near_unit) and pd.notna(far_unit) and near_unit != far_unit:
            raise InvalidParameterError(
                "adjacent contracts must use the same ValueUnit"
            )
        value_unit = near_unit if pd.notna(near_unit) else far_unit
        records.append(
            {
                "NearSymbol": near.get("Symbol", pd.NA),
                "FarSymbol": far.get("Symbol", pd.NA),
                "NearExpiry": near_expiry,
                "FarExpiry": far_expiry,
                "ExpiryGapDays": days,
                "NearPrice": near_price,
                "FarPrice": far_price,
                "Spread": spread,
                "SpreadPct": (
                    spread / near_price * 100.0
                    if finite_prices and near_price
                    else float("nan")
                ),
                "AnnualizedSpreadPct": (
                    spread / near_price * 365.0 / days * 100.0
                    if finite_prices and near_price and days > 0
                    else float("nan")
                ),
                "ValueUnit": value_unit,
                "Structure": (
                    (
                        "contango"
                        if spread > 0
                        else "backwardation" if spread < 0 else "flat"
                    )
                    if finite_prices
                    else pd.NA
                ),
                "Source": "calculated_from_futures_curve",
            }
        )
    frame = pd.DataFrame(
        records,
        columns=[
            "NearSymbol",
            "FarSymbol",
            "NearExpiry",
            "FarExpiry",
            "ExpiryGapDays",
            "NearPrice",
            "FarPrice",
            "Spread",
            "SpreadPct",
            "AnnualizedSpreadPct",
            "ValueUnit",
            "Structure",
            "Source",
        ],
    )
    value_units = (
        frame["ValueUnit"].dropna().astype(str).str.strip().replace("", pd.NA).dropna()
    )
    unique_units = tuple(sorted(value_units.unique()))
    frame.attrs.update(
        {
            "source": "calculated_from_futures_curve",
            "pairing": "adjacent_expiries",
            "value_unit": unique_units[0] if unique_units else None,
            "is_partial": False,
        }
    )
    return frame


def analyze_cash_and_carry(curve, annual_rate, storage_rate=0.0, convenience_yield=0.0):
    """Compare futures prices with explicit cost-of-carry assumptions."""
    if not isinstance(curve, pd.DataFrame):
        curve = pd.DataFrame(curve)
    required = {"SpotPrice", "Price", "DaysToExpiry"}
    if not required <= set(curve.columns):
        raise InvalidParameterError(
            "curve must contain SpotPrice, Price, and DaysToExpiry"
        )
    rates = []
    for name, value in (
        ("annual_rate", annual_rate),
        ("storage_rate", storage_rate),
        ("convenience_yield", convenience_yield),
    ):
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("{} must be finite".format(name)) from exc
        if not math.isfinite(number):
            raise InvalidParameterError("{} must be finite".format(name))
        rates.append(number)
    annual_rate, storage_rate, convenience_yield = rates
    if 1.0 + annual_rate + storage_rate - convenience_yield <= 0:
        raise InvalidParameterError(
            "1 + annual_rate + storage_rate - convenience_yield must be positive"
        )
    result = curve.copy()
    tenor = pd.to_numeric(result["DaysToExpiry"], errors="coerce") / 365.0
    spot = pd.to_numeric(result["SpotPrice"], errors="coerce")
    futures = pd.to_numeric(result["Price"], errors="coerce")
    result["FairValue"] = spot * (
        (1.0 + annual_rate + storage_rate - convenience_yield) ** tenor
    )
    result["Mispricing"] = futures - result["FairValue"]
    result["MispricingPct"] = result["Mispricing"] / result["FairValue"] * 100.0
    result["Signal"] = result["Mispricing"].map(
        lambda value: (
            pd.NA
            if pd.isna(value)
            else (
                "cash_and_carry"
                if value > 0
                else "reverse_cash_and_carry" if value < 0 else "fair"
            )
        )
    )
    result["AnnualRate"] = annual_rate
    result["StorageRate"] = storage_rate
    result["ConvenienceYield"] = convenience_yield
    result["Source"] = "calculated_from_explicit_assumptions"
    result.attrs.update(
        {
            "source": "calculated_from_explicit_assumptions",
            "annual_rate": annual_rate,
            "storage_rate": storage_rate,
            "convenience_yield": convenience_yield,
            "compounding": "annual_effective",
            "is_partial": False,
        }
    )
    return result
