"""Offline contracts for the multi-axis Iranian fund taxonomy."""

import pandas as pd
import pytest

import algotik_tse as att
from algotik_tse.core import instruments
from algotik_tse.core.market_data import STOCK_COLUMNS
from algotik_tse.core.resolver import INSTRUMENT_TYPE_ASSET_MAP

EXPECTED_REGISTRY_TYPES = {
    "fixed_income": 4,
    "commodity": 5,
    "equity": 6,
    "mixed": 7,
    "market_maker": 11,
    "venture_capital": 12,
    "project": 13,
    "private": 16,
    "fund_of_funds": 17,
    "real_estate": 18,
    "sector": 21,
    "leveraged": 22,
    "index": 23,
    "capital_guaranteed": 24,
    "supplementary_retirement": 25,
}


def _market_snapshot():
    definitions = (
        ("10", "IRTK10", "سهامی", "صندوق سرمایه گذاری سهامی", 305),
        ("11", "IRTK11", "طلا", "صندوق پشتوانه طلای نمونه", 380),
        ("12", "IRTK12", "نقره", "صندوق کالایی نقره نمونه", 380),
        ("13", "IRTK13", "کالا", "صندوق سرمایه گذاری کالایی نمونه", 380),
        ("14", "IRTK14", "زرین", "صندوق زرین نمونه", 305),
    )
    rows = []
    for code, isin, symbol, name, instrument_type in definitions:
        row = {column: 0 for column in STOCK_COLUMNS}
        row.update(
            {
                "InsCode": code,
                "ISIN": isin,
                "Symbol": symbol,
                "Name": name,
                "InstrumentType": instrument_type,
                "Flow": 7,
                "MarketCode": "fund",
                "Close": 100,
                "Last": 101,
                "NAV": 110,
            }
        )
        rows.append(row)
    return {
        "stocks": pd.DataFrame(rows, columns=STOCK_COLUMNS),
        "fetched_at": "2026-09-11T12:00:00+03:30",
        "trade_date": "2026-09-09",
        "is_realtime_fresh": False,
        "is_stale": True,
    }


def test_registry_type_contract_and_resolver_coverage():
    assert att.settings.fund_type_ids == EXPECTED_REGISTRY_TYPES
    assert att.settings.fund_type_labels == {
        value: key for key, value in EXPECTED_REGISTRY_TYPES.items()
    }
    assert INSTRUMENT_TYPE_ASSET_MAP["305"] == "fund"
    assert INSTRUMENT_TYPE_ASSET_MAP["380"] == "fund"


def test_listed_funds_include_305_and_380_and_filter_proved_subtypes(monkeypatch):
    monkeypatch.setattr(instruments, "market_watch", _market_snapshot)
    all_funds = att.list_listed_funds(progress=False)
    assert set(all_funds["InstrumentType"].astype(int)) == {305, 380}
    assert list(all_funds.columns) == instruments.LISTED_FUND_COLUMNS
    assert all_funds.attrs["taxonomy_version"] == att.FUND_TAXONOMY_VERSION

    gold = att.list_listed_funds(commodity_underlying="gold", progress=False)
    silver = att.list_listed_funds(commodity_underlying="silver", progress=False)
    assert gold["InsCode"].tolist() == ["11"]
    assert silver["InsCode"].tolist() == ["12"]
    assert gold.iloc[0]["classification_status"] == "explicit_official_name"

    generic = all_funds.loc[all_funds["InsCode"] == "13"].iloc[0]
    assert generic["fund_category"] == "commodity"
    assert generic["commodity_underlyings"] == []
    assert generic["classification_status"] == "unknown"
    assert bool(generic["needs_review"]) is True


def test_brand_fragments_do_not_create_false_commodity_subtypes(monkeypatch):
    monkeypatch.setattr(instruments, "market_watch", _market_snapshot)
    result = att.list_listed_funds(progress=False)
    brand = result.loc[result["InsCode"] == "14"].iloc[0]
    assert brand["commodity_underlyings"] == []
    assert brand["primary_commodity"] is pd.NA


def test_exact_mapping_requires_matching_isin_and_supports_multi_commodity(monkeypatch):
    mapping = {
        "13": {
            "instrument_id": "IRTK13",
            "commodity_underlyings": ["gold", "silver"],
            "primary_commodity": None,
            "evidence_type": "official_exchange_notice",
            "evidence_url": "https://example.invalid/official-evidence",
            "evidence_date": "2026-09-11",
        }
    }
    monkeypatch.setattr(instruments, "_EXACT_FUND_TAXONOMY", mapping)
    exact = instruments._classify_listed_fund(
        {"InsCode": "13", "ISIN": "IRTK13", "InstrumentType": 380, "Name": "کالایی"}
    )
    mismatch = instruments._classify_listed_fund(
        {"InsCode": "13", "ISIN": "CHANGED", "InstrumentType": 380, "Name": "کالایی"}
    )
    assert exact["commodity_profile"] == "multi"
    assert exact["commodity_underlyings"] == ["gold", "silver"]
    assert exact["classification_status"] == "verified_exact_mapping"
    assert mismatch["classification_status"] == "unknown"
    assert mismatch["commodity_underlyings"] == []


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


def test_registry_rows_expose_auditable_axes_and_gold_filter(monkeypatch):
    def request(url):
        type_id = int(url.rsplit("/", 1)[-1])
        name = "صندوق پشتوانه طلای نمونه" if type_id == 5 else "صندوق نمونه"
        return _Response(
            {"funds": [{"mfName": name, "regNo": "1", "fixIncome": type_id}]}
        )

    monkeypatch.setattr(instruments, "safe_get", request)
    monkeypatch.setattr(
        instruments,
        "safe_post",
        lambda *args, **kwargs: _Response({"status": 200, "items": []}),
    )
    monkeypatch.setattr(instruments.time, "sleep", lambda _: None)
    result = att.list_funds("commodity", commodity_underlying="gold", progress=False)
    assert result["registry_type_id"].tolist() == [5]
    assert result["registry_category"].tolist() == ["commodity"]
    assert result["commodity_underlyings"].tolist() == [["gold"]]
    assert result.attrs["no_fuzzy_join"] is True


def test_registry_type_disagreement_fails_closed(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "safe_get",
        lambda _: _Response(
            {"funds": [{"mfName": "صندوق نمونه", "regNo": "1", "fixIncome": 999}]}
        ),
    )
    monkeypatch.setattr(
        instruments,
        "safe_post",
        lambda *args, **kwargs: _Response({"status": 200, "items": []}),
    )
    result = att.list_funds("equity", progress=False)
    row = result.iloc[0]
    assert row["registry_type_id"] == 999
    assert row["registry_category"] == "unknown"
    assert row["classification_status"] == "unknown"
    assert bool(row["needs_review"]) is True
    assert result.attrs["discovery_signals"] == 1


def test_registry_cash_uses_fipiran_exact_reg_no_and_preserves_deposit(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "safe_get",
        lambda _: _Response(
            {
                "funds": [
                    {
                        "mfName": "خاتم ایساتیس پویا",
                        "regNo": 11753.0,
                        "fixIncome": 4,
                        "recordDate": "2026-10-23T00:00:00",
                        "portfolioDeposit": 30.26,
                        "portfolioCash": 30.26,
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        instruments,
        "safe_post",
        lambda *args, **kwargs: _Response(
            {
                "status": 200,
                "items": [
                    {
                        "regNo": "11753",
                        "name": "خاتم ایساتیس پویا",
                        "cash": 0.05,
                        "deposit": 30.26,
                    }
                ],
            }
        ),
    )

    result = att.list_funds("fixed_income", progress=False)
    row = result.iloc[0]
    assert row["pct_deposit"] == pytest.approx(30.26)
    assert row["pct_cash"] == pytest.approx(0.05)
    assert row["record_date"] == "2026-10-23T00:00:00"
    assert result.attrs["pct_cash_source"] == "fipiran_fund_compare_exact_reg_no"
    assert result.attrs["pct_cash_source_status"] == "available"
    assert result.attrs["pct_cash_inferred"] is False
    assert result.attrs["pct_cash_registry_matches"] == 1
    assert result.attrs["pct_cash_values_available"] == 1
    assert result.attrs["pct_cash_missing"] == 0


def test_registry_cash_fails_closed_without_exact_fipiran_match(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "safe_get",
        lambda _: _Response(
            {
                "funds": [
                    {
                        "mfName": "نام تکراری",
                        "regNo": "1",
                        "fixIncome": 4,
                        "portfolioDeposit": 40,
                        "portfolioCash": 40,
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        instruments,
        "safe_post",
        lambda *args, **kwargs: _Response(
            {
                "status": 200,
                "items": [{"regNo": "2", "name": "نام تکراری", "cash": 3}],
            }
        ),
    )

    result = att.list_funds("fixed_income", progress=False)
    assert pd.isna(result.iloc[0]["pct_cash"])
    assert result.iloc[0]["pct_deposit"] == 40
    assert result.attrs["pct_cash_registry_matches"] == 0
    assert result.attrs["pct_cash_missing"] == 1


def test_registry_cash_is_missing_when_fipiran_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        instruments,
        "safe_get",
        lambda _: _Response(
            {
                "funds": [
                    {
                        "mfName": "صندوق نمونه",
                        "regNo": "1",
                        "fixIncome": 4,
                        "portfolioDeposit": 20,
                        "portfolioCash": 20,
                    }
                ]
            }
        ),
    )

    def unavailable(*args, **kwargs):
        raise OSError("provider unavailable")

    monkeypatch.setattr(instruments, "safe_post", unavailable)
    monkeypatch.setattr(instruments.time, "sleep", lambda _: None)
    result = att.list_funds("fixed_income", progress=False)
    assert pd.isna(result.iloc[0]["pct_cash"])
    assert result.attrs["pct_cash_source_status"] == "unavailable"
    assert result.attrs["pct_cash_inferred"] is False


def test_fipiran_cash_read_retries_transient_failure(monkeypatch):
    calls = []

    def request(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise OSError("temporary failure")
        return _Response({"status": 200, "items": [{"regNo": "11753", "cash": 0.05}]})

    delays = []
    monkeypatch.setattr(instruments, "safe_post", request)
    monkeypatch.setattr(instruments.time, "sleep", delays.append)
    result = instruments._fetch_fipiran_cash_allocations(max_attempts=2)
    assert result == {"11753": 0.05}
    assert len(calls) == 2
    assert len(delays) == 1


def test_filter_validation_is_typed(monkeypatch):
    monkeypatch.setattr(instruments, "market_watch", _market_snapshot)
    with pytest.raises(att.InvalidParameterError, match="include_unknown"):
        att.list_listed_funds(include_unknown="yes", progress=False)
    with pytest.raises(att.InvalidParameterError, match="commodity_underlying"):
        att.list_listed_funds(commodity_underlying="", progress=False)
    with pytest.raises(att.InvalidParameterError, match="commodity_underlying"):
        att.list_listed_funds(commodity_underlying="copper", progress=False)
