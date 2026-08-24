import datetime

import pandas as pd
import pytest
import requests

import algotik_tse as att
from algotik_tse.core import price_adjustments as pa
from algotik_tse.core.resolver import InstrumentRef

CODE = "35425587644337450"


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class ErrorResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.json_called = False

    def raise_for_status(self):
        raise requests.exceptions.HTTPError("status {}".format(self.status_code))

    def json(self):
        self.json_called = True
        pytest.fail("HTTP error response reached JSON parser")


@pytest.fixture
def identity(monkeypatch):
    calls = []

    def resolve(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return InstrumentRef(
            ins_code=CODE,
            symbol="فملی",
            name="ملی صنایع مس ایران",
            asset_type="equity",
            is_active=False,
            provenance="fixture_exact",
        )

    monkeypatch.setattr(pa, "resolve_instrument", resolve)
    return calls


def _payload(rows):
    return {"priceAdjust": rows}


def _row(**changes):
    value = {
        "insCode": CODE,
        "dEven": 20240101,
        "pClosing": 8000,
        "pClosingNotAdjusted": 10000,
        "corporateTypeCode": None,
        "instrument": {"lVal18AFC": "فملی"},
    }
    value.update(changes)
    return value


def test_price_adjustments_retains_distinct_same_date_and_dedupes_exact(
    identity, monkeypatch
):
    calls = []
    rows = [
        _row(),
        _row(),
        _row(pClosing=8500, pClosingNotAdjusted=10500, corporateTypeCode=7),
        _row(insCode=None, dEven="20240201", pClosing=9000, pClosingNotAdjusted=9000),
    ]
    monkeypatch.setattr(
        pa,
        "safe_get",
        lambda url: calls.append(url) or Response(_payload(rows)),
    )

    result = att.get_price_adjustments("فملی")

    assert calls == [
        "https://cdn.tsetmc.com/api/ClosingPrice/GetPriceAdjustList/" + CODE
    ]
    assert identity == [
        (
            "فملی",
            {"ins_code": None, "asset_type": "auto", "require_active": False},
        )
    ]
    assert len(result) == 3
    assert result["GregorianDate"].tolist() == [
        datetime.date(2024, 1, 1),
        datetime.date(2024, 1, 1),
        datetime.date(2024, 2, 1),
    ]
    assert result["AdjustedClosingPrice"].tolist() == [8000, 8500, 9000]
    assert result["AdjustmentAmount"].tolist() == [2000, 2000, 0]
    assert result["IdentityVerified"].tolist() == [True, True, False]
    assert result["IsConfirmedDPS"].eq(False).all()
    assert result["CorporateActionType"].isna().all()
    assert result.attrs["dps_available"] is False
    assert (
        result.attrs["dps_reason"]
        == "tsetmc_does_not_classify_adjustments_as_dividends"
    )
    assert result.attrs["no_backfill"] is False


def test_same_date_and_prices_keep_distinguishing_provider_fields(
    identity, monkeypatch
):
    rows = [
        _row(corporateTypeCode=1),
        _row(corporateTypeCode=2),
        _row(insCode=None, corporateTypeCode=1),
        _row(corporateTypeCode=1, instrument={"lVal18AFC": "فملی", "rawTag": "x"}),
        _row(corporateTypeCode=1),
    ]
    monkeypatch.setattr(pa, "safe_get", lambda _: Response(_payload(rows)))
    result = att.get_price_adjustments("فملی")
    assert len(result) == 4
    assert result["CorporateTypeCode"].tolist() == ["1", "2", "1", "1"]
    assert result["IdentityVerified"].tolist() == [True, True, False, True]


@pytest.mark.parametrize("status", [404, 500])
def test_http_errors_become_typed_connection_error_before_parsing(
    identity, monkeypatch, status
):
    response = ErrorResponse(status)
    monkeypatch.setattr(pa, "safe_get", lambda _: response)
    with pytest.raises(att.ConnectionError) as caught:
        att.get_price_adjustments("فملی")
    assert isinstance(caught.value.__cause__, requests.exceptions.HTTPError)
    assert response.json_called is False


def test_http_status_fallback_for_minimal_response_fake(identity, monkeypatch):
    response = Response(_payload([_row()]))
    response.status_code = 503
    monkeypatch.setattr(pa, "safe_get", lambda _: response)
    with pytest.raises(att.ConnectionError) as caught:
        att.get_price_adjustments("فملی")
    assert isinstance(caught.value.__cause__, requests.exceptions.HTTPError)


def test_price_adjustment_dates_are_inclusive_and_accept_jalali(identity, monkeypatch):
    monkeypatch.setattr(
        pa,
        "safe_get",
        lambda _: Response(
            _payload(
                [
                    _row(dEven=20230320),
                    _row(dEven=20230321),
                    _row(dEven=20230322),
                ]
            )
        ),
    )
    result = att.get_price_adjustments("فملی", start="1402-01-01", end="2023-03-21")
    assert result["GregorianDate"].tolist() == [datetime.date(2023, 3, 21)]
    assert result["JalaliDate"].tolist() == ["1402-01-01"]


def test_latest_is_typed_zero_or_one_row_and_preserves_attrs(identity, monkeypatch):
    monkeypatch.setattr(
        pa,
        "safe_get",
        lambda _: Response(_payload([_row(dEven=20230101), _row(dEven=20240101)])),
    )
    latest = att.get_latest_price_adjustment("فملی")
    assert len(latest) == 1
    assert latest.loc[0, "GregorianDate"] == datetime.date(2024, 1, 1)
    assert str(latest["InsCode"].dtype) == "string"
    assert str(latest["IdentityVerified"].dtype) == "boolean"
    assert str(latest["FetchedAt"].dtype) == "datetime64[ns, Asia/Tehran]"
    assert latest.attrs["source"] == "tsetmc_price_adjustment"

    monkeypatch.setattr(pa, "safe_get", lambda _: Response(_payload([])))
    empty = att.get_latest_price_adjustment("فملی")
    assert empty.empty
    assert list(empty.columns) == pa.PRICE_ADJUSTMENT_COLUMNS
    assert str(empty["AdjustedClosingPrice"].dtype) == "Float64"
    assert str(empty["IdentityVerified"].dtype) == "boolean"
    assert empty.attrs["dps_available"] is False


@pytest.mark.parametrize(
    "bad_row,match",
    [
        (_row(insCode="99999999999999999"), "does not match requested"),
        (_row(insCode=float(CODE)), "exact decimal string"),
        (_row(dEven=20240101.0), "exact YYYYMMDD"),
        (_row(dEven="20241301"), "not a valid date"),
        (_row(pClosing=-1), "finite and non-negative"),
        (_row(pClosingNotAdjusted=float("inf")), "finite and non-negative"),
    ],
)
def test_provider_identity_date_and_price_validation(
    identity, monkeypatch, bad_row, match
):
    monkeypatch.setattr(pa, "safe_get", lambda _: Response(_payload([bad_row])))
    with pytest.raises(att.DataParsingError, match=match):
        att.get_price_adjustments("فملی")


@pytest.mark.parametrize("payload", [None, [], {}, {"priceAdjust": None}])
def test_malformed_envelope_is_rejected(identity, monkeypatch, payload):
    monkeypatch.setattr(pa, "safe_get", lambda _: Response(payload))
    with pytest.raises(att.DataParsingError, match="priceAdjust list"):
        att.get_price_adjustments("فملی")


def test_input_validation_happens_before_request(identity, monkeypatch):
    monkeypatch.setattr(pa, "safe_get", lambda _: pytest.fail("network called"))
    with pytest.raises(att.InvalidParameterError, match="less than or equal"):
        att.get_price_adjustments("فملی", start="2024-02-01", end="2024-01-01")
    with pytest.raises(att.InvalidParameterError, match="progress"):
        att.get_price_adjustments("فملی", progress=1)


def test_public_exports_are_present_and_no_dividend_api_is_invented():
    assert callable(att.get_price_adjustments)
    assert callable(att.get_latest_price_adjustment)
    assert not hasattr(att, "get_dividends")
    assert not hasattr(att, "get_dps")
