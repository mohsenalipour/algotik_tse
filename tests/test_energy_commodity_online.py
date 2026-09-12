import pandas as pd
import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


def test_energy_auction_and_overview_live_contracts():
    auctions = att.get_energy_auctions(status="upcoming", board="physical", top=2)
    overview = att.get_energy_market_overview("standard_power")
    assert len(auctions) <= 2
    assert {
        "AuctionID",
        "PaymentTerms",
        "DeliveryTerms",
        "VolumeUnit",
        "PriceUnit",
    } <= set(auctions)
    assert len(overview) == 1
    assert overview.loc[0, "Flow"] == 64
    assert overview.loc[0, "ValueUnit"] == "rial"


def test_energy_contract_lists_and_future_detail_live():
    power = att.list_power_instruments("standard", top=3)
    futures = att.list_energy_securities("future", top=3, enrich_futures=True)
    assert len(power) <= 3
    assert len(futures) <= 3
    assert {"InsCode", "Close", "Last", "ValueUnit"} <= set(power)
    if not futures.empty:
        assert futures["ExpiryDate"].notna().all()
        code = futures.iloc[0]["InsCode"]
        detail = att.get_energy_future_contract(code)
        assert detail.loc[0, "InsCode"] == code
        assert detail.loc[0, "ExpiryDate"] is not pd.NaT


def test_ime_live_and_historical_contracts():
    certificates = att.get_commodity_market("certificate")
    history = att.get_commodity_physical_history("1405-06-01", "1405-06-03")
    summary = att.get_commodity_physical_summary("1405-06-01", "1405-06-22")
    activity = att.get_commodity_market_activity("1405-06-01", "1405-06-22")
    assert certificates.attrs["value_unit"] == "thousand_rial"
    assert {"BidPrice1", "AskPrice1", "IndividualBuyVolume", "LegalSellVolume"} <= set(
        certificates
    )
    assert not history.empty and history.attrs["value_unit"] == "million_rial"
    assert not summary.empty and summary["TradeToOfferRatio"].notna().any()
    assert not activity.empty
    assert 3 in set(activity["MarketID"].dropna())  # official aggregate options market


def test_ime_futures_empty_snapshot_remains_a_valid_schema():
    futures = att.get_commodity_market("future")
    assert {"ExpiryJalali", "SettlementPrice", "OpenInterest", "ContractSize"} <= set(
        futures
    )
    assert futures.attrs["is_partial"] is False
