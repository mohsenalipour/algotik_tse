"""Small opt-in provider smoke; excluded from the default release gate."""

import pytest

from algotik_tse import list_listed_funds
from algotik_tse.http_client import safe_get
from algotik_tse.settings import settings

pytestmark = pytest.mark.online


def test_tsetmc_https_endpoint_responds_within_bound():
    response = safe_get(settings.url_market_watch_init, timeout=15)
    assert response.status_code == 200
    assert response.url.startswith("https://")


def test_fund_registry_types_and_identity_are_live_consistent():
    """Bounded observation: schemas and identities, never fixed row counts."""
    registrations = {}
    for category, type_id in settings.fund_type_ids.items():
        response = safe_get(settings.url_fund_list.format(type_id), timeout=15)
        rows = response.json().get("funds", [])
        for row in rows:
            raw_type = row.get("fixIncome")
            if raw_type not in (None, ""):
                assert int(raw_type) == type_id, (category, type_id, raw_type)
            reg_no = row.get("regNo")
            if reg_no:
                assert reg_no not in registrations, (
                    reg_no,
                    registrations[reg_no],
                    category,
                )
                registrations[reg_no] = category


def test_market_watch_still_exposes_both_listed_fund_types():
    funds = list_listed_funds(progress=False)
    observed = set(funds["InstrumentType"].dropna().astype(int))
    assert observed == {305, 380}
    assert funds.attrs.get("as_of") is not None
    assert funds.attrs.get("trade_date") is not None
    assert funds["commodity_underlyings"].map(lambda values: "gold" in values).any()
    assert funds["commodity_underlyings"].map(lambda values: "silver" in values).any()
