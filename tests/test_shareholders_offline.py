import datetime

import pandas as pd
import pytest

from algotik_tse import DataParsingError, InvalidParameterError
from algotik_tse.core import market_reference
from algotik_tse.core import shareholders as shareholders_module


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _row(name, date, shares, record_id, percentage=1.0, state=1):
    return {
        "shareHolderName": name,
        "numberOfShares": shares,
        "perOfShares": percentage,
        "change": state,
        "changeAmount": 0,
        "dEven": date,
        "shareHolderID": 0,
        "shareHolderShareID": record_id,
    }


def _dated_payload():
    return {
        "shareShareholder": [
            _row("شرکت الف", 20260912, 125, 201, 2.5, 2),
            _row("شرکت جدید", 20260912, 80, 202, 1.6, 2),
            _row("شركت الف", 20260909, 100, 101, 2.0),
            _row("شرکت خارج", 20260909, 50, 102, 1.0),
        ]
    }


def test_dated_shareholders_use_official_effective_date_and_exact_change(monkeypatch):
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        shareholders_module,
        "safe_get",
        lambda *_a, **_k: FakeResponse(_dated_payload()),
    )

    frame = shareholders_module.shareholders("نماد", date="1405-06-18", include_id=True)

    assert frame["date"].unique().tolist() == ["20260912"]
    assert frame["trade_date"].unique().tolist() == ["20260909"]
    assert frame["effective_date"].unique().tolist() == ["20260912"]
    assert frame["effective_date_jalali"].unique().tolist() == ["1405-06-21"]
    retained = frame.loc[frame["share_holder_name"] == "شرکت الف"].iloc[0]
    entered = frame.loc[frame["share_holder_name"] == "شرکت جدید"].iloc[0]
    assert retained["change_amount"] == 25
    assert retained["change_quality"] == "exact_normalized_name"
    assert pd.isna(entered["change_amount"])
    assert entered["change_quality"] == "unmatched_or_ambiguous"
    assert frame["share_holder_id"].tolist() == [201, 202]
    assert frame.attrs["requested_date"] == "2026-09-09"
    assert frame.attrs["effective_date"] == "2026-09-12"
    assert frame.attrs["change_includes_non_trade_transfers"] is True
    assert frame.attrs["is_authoritative_register"] is False
    assert frame.attrs["stable_shareholder_id_available"] is False


def test_latest_shareholders_keep_legacy_date_but_mark_client_date(monkeypatch):
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        shareholders_module,
        "safe_get",
        lambda *_a, **_k: FakeResponse({"shareHolder": [_row("سهامدار", 0, 100, 77)]}),
    )
    monkeypatch.setattr(
        shareholders_module, "tehran_today", lambda: datetime.date(2026, 9, 12)
    )

    frame = shareholders_module.shareholders("نماد", include_id=True)

    assert frame.iloc[0]["date"] == "20260912"
    assert frame.iloc[0]["share_holder_id"] == 77
    assert pd.isna(frame.iloc[0]["trade_date"])
    assert frame.attrs["date_is_provider_supplied"] is False


def _calendar(sessions):
    return pd.DataFrame(
        {
            "GregorianDate": sessions + sessions,
            "IsTradingDay": [True] * (2 * len(sessions)),
        }
    )


def test_history_pairs_six_sessions_into_three_requests(monkeypatch):
    sessions = [
        datetime.date(2026, 9, 2),
        datetime.date(2026, 9, 5),
        datetime.date(2026, 9, 6),
        datetime.date(2026, 9, 7),
        datetime.date(2026, 9, 8),
        datetime.date(2026, 9, 9),
    ]
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        market_reference, "get_trading_calendar", lambda **_k: _calendar(sessions)
    )
    calls = []

    def fake_get(url):
        query = int(url.rsplit("/", 1)[-1])
        calls.append(query)
        index = [int(value.strftime("%Y%m%d")) for value in sessions].index(query)
        dates = [sessions[index]]
        if index + 1 < len(sessions):
            dates.append(sessions[index + 1])
        return FakeResponse(
            {
                "shareShareholder": [
                    _row(
                        "سهامدار",
                        int(value.strftime("%Y%m%d")),
                        100 + sessions.index(value) * 10,
                        1000 + sessions.index(value),
                    )
                    for value in dates
                ]
            }
        )

    monkeypatch.setattr(shareholders_module, "safe_get", fake_get)
    frame = shareholders_module.get_shareholder_history(
        "نماد",
        start="2026-09-02",
        end="2026-09-09",
        max_requests=3,
        include_id=True,
        progress=False,
    )

    assert calls == [20260902, 20260906, 20260908]
    assert frame["effective_date"].unique().tolist() == [
        "20260902",
        "20260905",
        "20260906",
        "20260907",
        "20260908",
        "20260909",
    ]
    assert pd.isna(frame.iloc[0]["change_amount"])
    assert frame["change_amount"].tail(-1).tolist() == [10, 10, 10, 10, 10]
    assert frame.attrs["shareholder_requests_used"] == 3
    assert frame.attrs["requested_snapshot_count"] == 6
    assert frame.attrs["missing_effective_dates"] == ()
    assert frame.attrs["pair_request_optimization"] is True


def test_history_rejects_request_range_over_budget_before_fetch(monkeypatch):
    sessions = [datetime.date(2026, 9, day) for day in range(1, 7)]
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        market_reference, "get_trading_calendar", lambda **_k: _calendar(sessions)
    )
    monkeypatch.setattr(
        shareholders_module,
        "safe_get",
        lambda *_a, **_k: pytest.fail("shareholder endpoint must not be called"),
    )

    with pytest.raises(InvalidParameterError, match="exceeding max_requests=2"):
        shareholders_module.get_shareholder_history(
            "نماد",
            start="2026-09-01",
            end="2026-09-06",
            max_requests=2,
            progress=False,
        )


@pytest.mark.parametrize("frequency", ["weekly", "monthly"])
def test_history_sampling_uses_last_effective_session(monkeypatch, frequency):
    sessions = [
        datetime.date(2026, 8, 29),
        datetime.date(2026, 9, 1),
        datetime.date(2026, 9, 5),
        datetime.date(2026, 9, 9),
    ]
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        market_reference, "get_trading_calendar", lambda **_k: _calendar(sessions)
    )
    calls = []

    def fake_get(url):
        value = int(url.rsplit("/", 1)[-1])
        calls.append(value)
        return FakeResponse({"shareShareholder": [_row("سهامدار", value, 100, value)]})

    monkeypatch.setattr(shareholders_module, "safe_get", fake_get)
    frame = shareholders_module.get_shareholder_history(
        "نماد",
        start="2026-08-29",
        end="2026-09-09",
        frequency=frequency,
        max_requests=4,
        progress=False,
    )

    # Both Gregorian dates fall in Jalali Shahrivar, so monthly sampling keeps
    # only the last one. Weekly sampling keeps each exchange week's last day.
    expected = [20260909] if frequency == "monthly" else [20260901, 20260909]
    assert calls == expected
    assert frame["effective_date"].tolist() == [str(value) for value in expected]


def test_history_rejects_malformed_payload(monkeypatch):
    sessions = [datetime.date(2026, 9, 2)]
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        market_reference, "get_trading_calendar", lambda **_k: _calendar(sessions)
    )
    monkeypatch.setattr(
        shareholders_module,
        "safe_get",
        lambda *_a, **_k: FakeResponse({"unexpected": []}),
    )

    with pytest.raises(DataParsingError, match="lacks 'shareShareholder' envelope"):
        shareholders_module.get_shareholder_history(
            "نماد",
            start="2026-09-02",
            end="2026-09-02",
            progress=False,
        )


def test_legacy_shareholders_omits_snapshot_token_by_default(monkeypatch):
    monkeypatch.setattr(shareholders_module, "search_stock", lambda **_k: "11")
    monkeypatch.setattr(
        shareholders_module,
        "safe_get",
        lambda *_a, **_k: FakeResponse(_dated_payload()),
    )

    frame = shareholders_module.shareholders("نماد", date="2026-09-09")
    assert "share_holder_id" not in frame.columns
    assert frame.attrs["share_holder_id_scope"] == "provider snapshot/history token"
