import datetime

import pandas as pd
import pytest

from algotik_tse import InvalidParameterError
from algotik_tse.core import symbol_events
from algotik_tse.core.resolver import InstrumentRef


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


@pytest.fixture(autouse=True)
def exact_identity(monkeypatch):
    monkeypatch.setattr(
        symbol_events,
        "resolve_instrument",
        lambda *_a, **_k: InstrumentRef(
            ins_code="11",
            symbol="نماد",
            name="شرکت نمونه",
            provenance="test_exact_inscode",
        ),
    )


def _fake_get(url):
    if "GetMsgByInsCode" in url:
        return FakeResponse(
            {
                "msg": [
                    {
                        "tseMsgIdn": 7,
                        "dEven": 20260909,
                        "hEven": 90102,
                        "tseTitle": "بازگشايي نماد",
                        "tseDesc": "توضيح ناظر",
                    }
                ]
            }
        )
    return FakeResponse(
        {
            "instrumentShareChange": [
                {
                    "dEven": 20260908,
                    "numberOfShareOld": 100,
                    "numberOfShareNew": 150,
                },
                {
                    "dEven": 20260908,
                    "numberOfShareOld": 100,
                    "numberOfShareNew": 150,
                },
            ]
        }
    )


def _adjustments(*_args, **_kwargs):
    return pd.DataFrame(
        {
            "GregorianDate": [datetime.date(2026, 9, 7)],
            "UnadjustedClosingPrice": [120.0],
            "AdjustedClosingPrice": [100.0],
            "CorporateTypeCode": [pd.NA],
        }
    )


def test_symbol_events_unifies_native_sources(monkeypatch):
    monkeypatch.setattr(symbol_events, "safe_get", _fake_get)
    monkeypatch.setattr(symbol_events, "get_price_adjustments", _adjustments)

    frame = symbol_events.get_symbol_events(progress=False, limit=0, ascending=True)

    assert frame["EventType"].tolist() == [
        "price_adjustment",
        "capital_change",
        "supervisor_message",
    ]
    assert frame.loc[frame["EventType"] == "capital_change", "ChangeValue"].iat[0] == 50
    assert frame["EventID"].is_unique
    assert frame.attrs["codal_included"] is False
    assert frame.attrs["price_adjustment_is_not_confirmed_dps"] is True


def test_symbol_events_filters_dates_and_kinds(monkeypatch):
    monkeypatch.setattr(symbol_events, "safe_get", _fake_get)
    frame = symbol_events.get_symbol_events(
        start="1405-06-18",
        end="1405-06-18",
        kinds="messages",
        progress=False,
    )
    assert frame["EventType"].tolist() == ["supervisor_message"]
    assert frame.iloc[0]["GregorianDate"] == datetime.date(2026, 9, 9)
    assert frame.iloc[0]["Timestamp"].hour == 9


def test_symbol_events_request_budget_fails_before_resolution(monkeypatch):
    called = False

    def resolver(*_a, **_k):
        nonlocal called
        called = True

    monkeypatch.setattr(symbol_events, "resolve_instrument", resolver)
    with pytest.raises(InvalidParameterError, match="exceeding max_requests"):
        symbol_events.get_symbol_events(max_requests=2, progress=False)
    assert called is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kinds": []},
        {"kinds": ["codal"]},
        {"limit": -1},
        {"ascending": "yes"},
        {"progress": 1},
        {"start": "2026-09-10", "end": "2026-09-01"},
    ],
)
def test_symbol_events_rejects_invalid_contract(kwargs):
    with pytest.raises(InvalidParameterError):
        symbol_events.get_symbol_events(**kwargs)


def test_empty_timeline_has_stable_schema(monkeypatch):
    monkeypatch.setattr(
        symbol_events, "safe_get", lambda *_a, **_k: FakeResponse({"msg": []})
    )
    frame = symbol_events.get_symbol_events(kinds="messages", progress=False)
    assert frame.empty
    assert frame.columns.tolist() == symbol_events.SYMBOL_EVENT_COLUMNS
    assert frame["ChangeValue"].dtype == "Float64"
    assert str(frame["Timestamp"].dtype) == "datetime64[ns, Asia/Tehran]"
