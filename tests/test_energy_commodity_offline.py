import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import energy_commodity as ec


class Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("failed")


def auction_row():
    return {
        "idn": 94812,
        "instrumentID": 260,
        "auctionTitle": "  عرضه آزمون  ",
        "auctionDesc": "نیروگاه نمونه",
        "productTypeCode": 152,
        "productsubTypeCode": 928,
        "auctionVol": 150,
        "basePrice": 135000,
        "auctionDate": "2026-09-13T10:00:00",
        "producerName": "تولیدکننده",
        "termsOfPayment": "نقدی",
        "termsOfDelivery": "1405/06/30",
        "volUnitTitle": "تن",
        "priceUnitTitle": "ریال",
        "minimumPurchase": 10,
        "tickSize": 1,
        "stepTitle": "آماده عرضه",
        "energySymbol": "TEST",
        "lotSize": 10,
        "tradedQuantity": 25,
        "wap": 136000,
    }


def trade_top_row(ins_code="13758785995633713"):
    return {
        "instrument": {
            "insCode": ins_code,
            "lVal30": "آتی میعانات گازی",
            "lVal18AFC": "جمعیعا511",
            "zTitad": 1,
        },
        "insCode": ins_code,
        "dEven": 20260912,
        "pClosing": 85,
        "pDrCotVal": 90,
        "priceYesterday": 80,
        "priceFirst": 82,
        "priceMin": 81,
        "priceMax": 91,
        "priceChange": 10,
        "zTotTran": 3,
        "qTotTran5J": 7,
        "qTotCap": 620,
    }


def future_detail():
    return {
        "instrumentEnergyFuture": {
            "cisin": "IROPMY0005B1",
            "cCode": "جمعیعا511",
            "desc": "گواهی سپرده میعانات گازی",
            "insCode": 13758785995633713,
            "quantity": 1,
            "unitName": "بشکه",
            "beginDate": 20260808,
            "endDate": 20270203,
            "stlmntDlvryDate": 20270203,
            "prepareDate": 20270203,
            "prepareTime": 150000,
            "priceYesterday": 85,
            "pClosing": 85,
            "baseAsset": "میعانات گازی",
            "edsContract": "قرارداد آتی میعانات گازی",
            "imaValue": 0.2,
            "imaValueAct": 0.2,
            "rmbValue": 0.7,
            "rmbValueAct": 0.7,
            "buyFeeRatio": 0.00068,
            "sellFeeRatio": 0.00068,
        }
    }


def ime_row():
    row = {
        "InsCode": "55294951106810711",
        "Symbol": "زعفر0510پ20",
        "Code": "IRK1A12405A1",
        "Name": "زعفران نگین",
        "EnName": "Saffron",
        "Quantity": 142,
        "Volume": 78262,
        "Value": 222048246.746,
        "FinalPrice": 2837242,
        "LastPrice": 2850000,
        "YesterdayPrice": 2817207,
        "PriceChange": 32793,
        "MinPrice": 2816001,
        "MaxPrice": 2850000,
        "FirstPrice": 2842000,
        "Time": "17:57:15",
        "Status": 0,
        "Buy_Count_ClientI": 32,
        "Buy_I_Volume": 52388,
        "Sell_Count_ClientI": 44,
        "Sell_I_Volume": 52288,
        "ModifyTime": "18:00:22",
    }
    for level in range(1, 6):
        row.update(
            {
                f"DemandPrice{level}": 100 - level,
                f"DemandQuantity{level}": level,
                f"DemandVolume{level}": level * 10,
                f"OfferPrice{level}": 100 + level,
                f"OfferQuantity{level}": level + 1,
                f"OfferVolume{level}": level * 20,
            }
        )
    return row


def test_energy_auctions_maps_full_contract(monkeypatch):
    monkeypatch.setattr(
        ec, "safe_get", lambda *_a, **_k: Response({"auctionListItem": [auction_row()]})
    )
    frame = att.get_energy_auctions(status="upcoming", board="physical", top=5)
    assert list(frame.columns) == ec.ENERGY_AUCTION_COLUMNS
    assert frame.loc[0, "AuctionID"] == 94812
    assert frame.loc[0, "Title"] == "عرضه آزمون"
    assert frame.loc[0, "JalaliDate"] == "1405-06-22"
    assert frame.loc[0, "Board"] == "physical"
    assert frame.attrs["request_count"] == 1


def test_energy_auctions_validates_before_network(monkeypatch):
    monkeypatch.setattr(ec, "safe_get", lambda *_a, **_k: pytest.fail("network called"))
    with pytest.raises(att.InvalidParameterError):
        att.get_energy_auctions(status="bad")
    with pytest.raises(att.InvalidParameterError):
        att.get_energy_auctions(top=0)


def test_energy_auction_separates_auction_and_instrument_trades(monkeypatch):
    def request(url, **_kwargs):
        if "GetAuctionById" in url:
            return Response({"auction": auction_row()})
        return Response(
            {
                "auctionTrade": [
                    {
                        "tradeDate": "2026-09-12T11:52:17",
                        "tradedPrice": 12,
                        "tradedQuantity": 3,
                    }
                ]
            }
        )

    monkeypatch.setattr(ec, "safe_get", request)
    result = att.get_energy_auction(94812, include_instrument_history=True)
    assert set(result) == {"auction", "auction_trades", "instrument_history"}
    assert result["auction_trades"].attrs["trade_scope"] == "auction"
    assert result["instrument_history"].attrs["trade_scope"] == "instrument_history"


def test_energy_market_overview(monkeypatch):
    payload = {
        "marketOverview": {
            "marketActivityDEven": 20260912,
            "marketActivityHEven": 123000,
            "marketActivityZTotTran": 55,
            "marketActivityQTotCap": 1000,
            "marketActivityQTotTran": 200,
            "marketState": "F",
            "marketStateTitle": "بسته",
        }
    }
    monkeypatch.setattr(ec, "safe_get", lambda *_a, **_k: Response(payload))
    frame = att.get_energy_market_overview("standard_power")
    assert frame.loc[0, "Flow"] == 64
    assert frame.loc[0, "TradeCount"] == 55
    assert frame.attrs["request_count"] == 1


def test_power_and_energy_security_lists(monkeypatch):
    monkeypatch.setattr(
        ec, "safe_get", lambda *_a, **_k: Response({"tradeTop": [trade_top_row()]})
    )
    power = att.list_power_instruments("green", top=2)
    assert power.loc[0, "Segment"] == "green_power"
    assert power.loc[0, "ValueUnit"] == "rial"
    securities = att.list_energy_securities("future", top=2, enrich_futures=False)
    assert securities.loc[0, "Segment"] == "future"
    assert securities.loc[0, "ChangePct"] == pytest.approx(12.5)


def test_energy_future_detail_and_enrichment(monkeypatch):
    def request(url, **_kwargs):
        if "GetInstrumentEnergyFuture" in url:
            return Response(future_detail())
        return Response({"tradeTop": [trade_top_row()]})

    monkeypatch.setattr(ec, "safe_get", request)
    detail = att.get_energy_future_contract("13758785995633713")
    assert detail.loc[0, "ExpiryDate"] == pd.Timestamp("2027-02-03")
    assert detail.loc[0, "ContractUnit"] == "بشکه"
    listed = att.list_energy_securities("future", enrich_futures=True)
    assert listed.loc[0, "ExpiryJalali"] == "1405-11-14"
    assert listed.attrs["request_count"] == 2


def test_commodity_market_keeps_ime_value_unit_and_depth(monkeypatch):
    monkeypatch.setattr(ec, "safe_get", lambda *_a, **_k: Response([ime_row()]))
    frame = att.get_commodity_market("certificate")
    assert list(frame.columns) == ec.COMMODITY_LIVE_COLUMNS
    assert frame.loc[0, "ValueUnit"] == "thousand_rial"
    assert frame.loc[0, "BidPrice5"] == 95
    assert frame.loc[0, "AskVolume5"] == 100
    assert frame.attrs["request_count"] == 1


def test_commodity_future_empty_is_valid(monkeypatch):
    monkeypatch.setattr(ec, "safe_get", lambda *_a, **_k: Response([]))
    frame = att.get_commodity_market("future")
    assert frame.empty
    assert list(frame.columns) == ec.COMMODITY_LIVE_COLUMNS
    assert frame.attrs["is_partial"] is False


@pytest.mark.parametrize(
    ("function", "operation", "payload", "expected"),
    [
        (
            att.get_commodity_physical_history,
            "GetHajmArzeshMoamelatDateGrid",
            [{"TradeDate": "1405/06/01", "TradeValue": 10, "TradeVolume": 2}],
            "Volume",
        ),
        (
            att.get_commodity_physical_summary,
            "GetHomeFizikiWithDateGrid",
            [
                {
                    "ID": 3,
                    "xRingName": "پتروشیمی",
                    "Value": 10,
                    "Volume": 2,
                    "OfferVolume": 4,
                }
            ],
            "TradeToOfferRatio",
        ),
        (
            att.get_commodity_market_activity,
            "GetHomeNamaWithDateGrid",
            [
                {
                    "Id": "3",
                    "name": "بازار اختیار معامله",
                    "TradeValue": 10,
                    "TradeVolume": 2,
                }
            ],
            "MarketID",
        ),
    ],
)
def test_ime_historical_contracts(monkeypatch, function, operation, payload, expected):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response({"d": __import__("json").dumps(payload, ensure_ascii=False)})

    monkeypatch.setattr(ec, "safe_post", post)
    frame = function("1405-06-01", "1405-06-22")
    assert operation in calls[0][0]
    assert calls[0][1]["json"]["GregorianFromDate"] == "1405/06/01"
    assert expected in frame.columns
    assert frame.attrs["value_unit"] == "million_rial"
    if expected == "TradeToOfferRatio":
        assert frame.loc[0, expected] == 0.5


def test_ime_date_range_validates_before_network(monkeypatch):
    monkeypatch.setattr(
        ec, "safe_post", lambda *_a, **_k: pytest.fail("network called")
    )
    with pytest.raises(att.InvalidParameterError):
        att.get_commodity_physical_history("1405-06-22", "1405-06-01")


def test_futures_curve_spreads_and_cash_and_carry():
    contracts = pd.DataFrame(
        [
            {
                "Market": "energy",
                "Symbol": "F1",
                "BaseAsset": "گاز",
                "ExpiryDate": "2027-01-01",
                "SettlementPrice": 110,
                "ValueUnit": "thousand_rial",
            },
            {
                "Market": "energy",
                "Symbol": "F2",
                "BaseAsset": "گاز",
                "ExpiryDate": "2027-04-01",
                "SettlementPrice": 125,
                "ValueUnit": "thousand_rial",
            },
        ]
    )
    curve = att.get_futures_curve(
        contracts, underlying="گاز", valuation_date="2026-10-01", spot_price=100
    )
    assert list(curve["Symbol"]) == ["F1", "F2"]
    assert curve.loc[0, "AbsoluteBasis"] == 10
    assert curve.loc[0, "AnnualizedBasis"] > 0
    assert list(curve["ValueUnit"]) == ["thousand_rial", "thousand_rial"]
    assert curve.attrs["value_unit"] == "thousand_rial"
    spreads = att.get_calendar_spreads(curve)
    assert spreads.loc[0, "Spread"] == 15
    assert spreads.loc[0, "Structure"] == "contango"
    assert spreads.loc[0, "ValueUnit"] == "thousand_rial"
    carry = att.analyze_cash_and_carry(curve, annual_rate=0.2, storage_rate=0.01)
    assert {"FairValue", "Mispricing", "Signal"} <= set(carry)
    assert carry.attrs["compounding"] == "annual_effective"


def test_futures_analytics_reject_ambiguous_inputs():
    with pytest.raises(att.InvalidParameterError):
        att.get_futures_curve([{"Price": 1}])
    with pytest.raises(att.InvalidParameterError):
        att.get_calendar_spreads(pd.DataFrame({"Price": [1]}))
    with pytest.raises(att.InvalidParameterError):
        att.analyze_cash_and_carry(pd.DataFrame({"Price": [1]}), annual_rate=0.2)
    with pytest.raises(att.InvalidParameterError):
        att.get_futures_curve([{"ExpiryDate": "2027-01-01", "Last": 1}], spot_price=-1)
    with pytest.raises(att.InvalidParameterError):
        att.get_futures_curve(
            [
                {
                    "ExpiryDate": "2027-01-01",
                    "Last": 1,
                    "ValueUnit": "rial",
                },
                {
                    "ExpiryDate": "2027-02-01",
                    "Last": 2,
                    "ValueUnit": "thousand_rial",
                },
            ]
        )


def test_public_phase_exports_are_present():
    expected = {
        "get_energy_auctions",
        "get_energy_auction",
        "get_energy_market_overview",
        "list_power_instruments",
        "list_energy_securities",
        "get_energy_future_contract",
        "get_commodity_market",
        "get_commodity_physical_history",
        "get_commodity_physical_summary",
        "get_commodity_market_activity",
        "get_futures_curve",
        "get_calendar_spreads",
        "analyze_cash_and_carry",
    }
    assert expected <= set(att.__all__)
