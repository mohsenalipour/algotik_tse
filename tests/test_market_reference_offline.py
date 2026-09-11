import datetime

import pandas as pd
import pytest

from algotik_tse import InvalidParameterError
from algotik_tse.core import market_reference as mr


class FakeResponse:
    def __init__(self, payload=None, text="", content=b""):
        self._payload = payload
        self.text = text
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_trading_calendar_expands_closed_days(monkeypatch):
    payload = {"indexB2": [{"dEven": 20260905}, {"dEven": 20260907}]}
    monkeypatch.setattr(mr, "safe_get", lambda *_a, **_k: FakeResponse(payload))

    frame = mr.get_trading_calendar(
        start="2026-09-05", end="2026-09-07", market="tse", include_closed=True
    )

    assert frame["GregorianDate"].tolist() == [
        datetime.date(2026, 9, 5),
        datetime.date(2026, 9, 6),
        datetime.date(2026, 9, 7),
    ]
    assert frame["IsTradingDay"].tolist() == [True, False, True]
    assert frame.attrs["calendar_semantics"] == "published_reference_index_sessions"


def test_market_value_history_computes_changes(monkeypatch):
    payload = {
        "marketValue": [
            {"deven": 20260907, "marketCap": 100},
            {"deven": 20260908, "marketCap": 110},
        ]
    }
    monkeypatch.setattr(mr, "safe_get", lambda *_a, **_k: FakeResponse(payload))

    frame = mr.get_market_value_history(market="tse", limit=2)

    assert frame["MarketValue"].tolist() == [100.0, 110.0]
    assert frame.iloc[1]["Change"] == 10
    assert frame.iloc[1]["ChangePct"] == pytest.approx(10)
    assert frame.attrs["unit"] == "rial"


def test_index_impact_sorts_filters_and_calculates_share(monkeypatch):
    payload = {
        "instEffect": [
            {
                "insCode": "1",
                "instrument": {"lVal18AFC": "الف", "lVal30": "الف نمونه"},
                "pClosing": 100,
                "instEffectValue": 20,
            },
            {
                "insCode": "2",
                "instrument": {"lVal18AFC": "ب", "lVal30": "ب نمونه"},
                "pClosing": 90,
                "instEffectValue": -5,
            },
        ]
    }
    monkeypatch.setattr(mr, "safe_get", lambda *_a, **_k: FakeResponse(payload))

    frame = mr.get_index_impact("2026-09-09", market="tse", top=10)

    assert frame["InsCode"].tolist() == ["1", "2"]
    assert frame["Direction"].tolist() == ["positive", "negative"]
    assert frame["AbsSharePct"].tolist() == pytest.approx([80, 20])
    negative = mr.get_index_impact(
        "2026-09-09", market="tse", top=10, direction="negative"
    )
    assert negative["InsCode"].tolist() == ["2"]


def _daily_payload():
    return {
        "closingPriceDailyHistoryWithInstDetails": [
            {
                "instrumentID": "IRO1TEST0001",
                "insCode": 11,
                "lVal18AFC": "تست",
                "lVal30": "شرکت تست",
                "zTotTran": 2,
                "qTotTran5J": 50,
                "qTotCap": 6000,
                "priceFirst": 100,
                "priceMax": 125,
                "priceMin": 95,
                "pClosing": 120,
                "pDrCotVal": 121,
                "priceYesterday": 100,
                "priceChange": 20,
            },
            {
                "instrumentID": "IRB3BOND0001",
                "insCode": 22,
                "lVal18AFC": "اخزا",
                "lVal30": "اسناد خزانه",
                "zTotTran": 0,
                "qTotTran5J": 0,
                "qTotCap": 0,
                "priceYesterday": 1000,
                "pClosing": 1000,
            },
        ]
    }


def test_market_trades_is_daily_summary_and_filters_market(monkeypatch):
    monkeypatch.setattr(
        mr, "safe_get", lambda *_a, **_k: FakeResponse(_daily_payload())
    )

    all_rows = mr.get_market_trades("2026-09-09", progress=False)
    tse = mr.get_market_trades("2026-09-09", market="tse", progress=False)

    assert all_rows["AssetType"].tolist() == ["bond", "stock"]
    assert tse["Symbol"].tolist() == ["تست"]
    assert tse.iloc[0]["ChangePct"] == pytest.approx(20)
    assert all_rows.attrs["transaction_level"] is False


def test_isin_families_do_not_mislabel_other_flows_as_tse_or_ifb():
    assert mr._market_from_isin("IRO9OPTION01") == "other"
    assert mr._asset_type_from_isin("IRO9OPTION01") == "option"
    assert mr._market_from_isin("IRO4FUTURE01") == "other"
    assert mr._asset_type_from_isin("IRO4FUTURE01") == "future"
    assert mr._market_from_isin("IRTKCOMMFUND") == "commodity"
    assert mr._asset_type_from_isin("IRTKCOMMFUND") == "fund"


def test_market_activity_aggregates_daily_frame(monkeypatch):
    calendar = pd.DataFrame(
        {
            "GregorianDate": [datetime.date(2026, 9, 9)],
            "IsTradingDay": [True],
        }
    )
    daily = pd.DataFrame({"TradeCount": [2, 0], "Volume": [50, 0], "Value": [6000, 0]})
    monkeypatch.setattr(mr, "get_trading_calendar", lambda **_k: calendar)
    monkeypatch.setattr(mr, "get_market_trades", lambda *_a, **_k: daily)

    frame = mr.get_market_activity(
        "2026-09-09", "2026-09-09", market="all", progress=False
    )

    row = frame.iloc[0]
    assert row["InstrumentCount"] == 2
    assert row["TradedInstrumentCount"] == 1
    assert row["AverageTradeValue"] == 3000


def test_market_activity_honours_request_budget(monkeypatch):
    calendar = pd.DataFrame(
        {
            "GregorianDate": [
                datetime.date(2026, 9, 8),
                datetime.date(2026, 9, 9),
            ],
            "IsTradingDay": [True, True],
        }
    )
    monkeypatch.setattr(mr, "get_trading_calendar", lambda **_k: calendar)
    with pytest.raises(InvalidParameterError, match="exceeding max_requests"):
        mr.get_market_activity(
            "2026-09-08", "2026-09-09", max_requests=1, progress=False
        )


def _master_table():
    return pd.DataFrame(
        {
            "نماد [Name]": [
                ("شرکت تست (تست)", "/Loader.aspx?ParTree=151311&i=11"),
                ("صندوق نمونه (صندوق)", "/Loader.aspx?ParTree=151311&i=22"),
            ],
            "کد 12 رقمی نماد [Instrument ISIN]": [
                ("IRO1TEST0001", None),
                ("IRT3FUND0001", None),
            ],
            "نام انگلیسی [English Name]": [("Test", None), ("Fund", None)],
            "کد 4 رقمی شرکت [Company Code]": [("TEST", None), ("FUND", None)],
            "کد 12 رقمی شرکت [Company ISIN]": [
                ("IRO1TEST0000", None),
                ("IRT3FUND0000", None),
            ],
            "بازار": [("بورس اوراق بهادار تهران", None), ("فرابورس ایران", None)],
            "گروه صنعت": [("محصولات شیمیایی", None), ("صندوق سرمایه گذاری", None)],
            "نوع [Type]": [("فعال", None), ("فعال", None)],
        }
    )


def test_instrument_master_parses_links_and_filters(monkeypatch):
    monkeypatch.setattr(mr, "safe_get", lambda *_a, **_k: FakeResponse(text="table"))
    monkeypatch.setattr(pd, "read_html", lambda *_a, **_k: [_master_table()])

    frame = mr.get_instrument_master(asset_type="fund", progress=False)

    assert frame["InsCode"].tolist() == ["22"]
    assert frame.iloc[0]["MarketGroup"] == "ifb"
    assert frame.iloc[0]["Symbol"] == "صندوق"


def test_instrument_master_active_filter_uses_live_snapshot(monkeypatch):
    monkeypatch.setattr(mr, "safe_get", lambda *_a, **_k: FakeResponse(text="table"))
    monkeypatch.setattr(pd, "read_html", lambda *_a, **_k: [_master_table()])
    import algotik_tse.core.market_data as market_data

    monkeypatch.setattr(
        market_data,
        "market_watch",
        lambda: {"stocks": pd.DataFrame({"InsCode": ["11"]})},
    )
    frame = mr.get_instrument_master(active=True, progress=False)
    assert frame["InsCode"].tolist() == ["11"]
    assert frame["Active"].tolist() == [True]


def test_instrument_changes_reports_added_removed_and_field_changes():
    previous = pd.DataFrame(
        {"InsCode": ["1", "2"], "Symbol": ["الف", "ب"], "Name": ["قدیم", "ب"]}
    )
    current = pd.DataFrame(
        {"InsCode": ["1", "3"], "Symbol": ["الف", "ج"], "Name": ["جدید", "ج"]}
    )
    frame = mr.get_instrument_changes(previous, current, progress=False)
    assert set(frame["ChangeType"]) == {"added", "removed", "changed"}
    changed = frame.loc[frame["ChangeType"] == "changed"].iloc[0]
    assert (changed["Field"], changed["OldValue"], changed["NewValue"]) == (
        "Name",
        "قدیم",
        "جدید",
    )


def test_instrument_changes_rejects_invalid_or_duplicate_identity():
    current = pd.DataFrame({"InsCode": ["2"], "Symbol": ["ب"]})
    with pytest.raises(InvalidParameterError, match="invalid InsCode"):
        mr.get_instrument_changes(
            pd.DataFrame({"InsCode": [pd.NA], "Symbol": ["الف"]}),
            current,
            progress=False,
        )
    with pytest.raises(InvalidParameterError, match="duplicate InsCode"):
        mr.get_instrument_changes(
            pd.DataFrame({"InsCode": ["1", "1"], "Symbol": ["الف", "الف"]}),
            current,
            progress=False,
        )


SOAP_RESPONSE = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body><TOPResponse xmlns="http://tsetmc.com/"><TOPResult>
    <diffgr:diffgram xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
      <NewDataSet><Table>
        <NInsCode>11</NInsCode><LVal30>شرکت تست</LVal30><LVal18AFC>تست</LVal18AFC>
        <DEven>20260909</DEven><HEven>84501</HEven><PTeoOvJ>105</PTeoOvJ>
        <QXtePTeoOvj>300</QXtePTeoOvj><CSensQNrepOv>B</CSensQNrepOv><QNrepOv>25</QNrepOv>
        <QTitMeLimSimAc>400</QTitMeLimSimAc><PMeLimSimAcVal>105</PMeLimSimAcVal>
        <PMeLimSimVtVal>106</PMeLimSimVtVal><QTitMeLimSimVt>100</QTitMeLimSimVt>
        <XQVarPJDrPRf>5</XQVarPJDrPRf>
      </Table></NewDataSet>
    </diffgr:diffgram>
  </TOPResult></TOPResponse></soap:Body>
</soap:Envelope>""".encode("utf-8")


def test_top_requires_credentials():
    with pytest.raises(InvalidParameterError, match="username"):
        mr.get_theoretical_opening_price(progress=False)


def test_top_rejects_invalid_timeout_before_network():
    with pytest.raises(InvalidParameterError, match="timeout"):
        mr.get_theoretical_opening_price(
            username="member", password="secret", timeout=0, progress=False
        )


def test_top_parses_official_subscriber_response(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(content=SOAP_RESPONSE)

    monkeypatch.setattr(mr.requests, "post", fake_post)
    frame = mr.get_theoretical_opening_price(
        username="member", password="secret", market="tse", progress=False
    )

    assert frame.iloc[0]["TheoreticalOpeningPrice"] == 105
    assert frame.iloc[0]["Time"] == "08:45:01"
    assert frame.attrs["credentials_stored"] is False
    sent = calls[0][1]
    assert b"<ns1:UserName>member</ns1:UserName>" in sent["data"]
    assert sent["headers"]["SOAPAction"].endswith("/TOP")


def test_preopen_imbalance_is_transparent_and_does_not_mutate_input():
    top = pd.DataFrame(
        {"TheoreticalBuyVolume": [400, 0], "TheoreticalSellVolume": [100, 0]}
    )
    result = mr.get_preopen_imbalance(top)
    assert "ImbalanceVolume" not in top
    assert result["ImbalanceVolume"].tolist() == [300, 0]
    assert result.iloc[0]["ImbalanceRatio"] == pytest.approx(0.6)
    assert result["ImbalanceSide"].tolist() == ["buy", "unavailable"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: mr.get_trading_calendar(market="invalid"),
        lambda: mr.get_index_impact("2026-09-09", direction="up"),
        lambda: mr.get_market_trades("2026-09-09", progress="yes"),
        lambda: mr.get_instrument_master(active="yes"),
    ],
)
def test_new_api_rejects_invalid_parameters(call):
    with pytest.raises(InvalidParameterError):
        call()
