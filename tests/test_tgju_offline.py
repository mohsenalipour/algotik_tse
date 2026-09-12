import pandas as pd
import pytest
import requests

import algotik_tse as att
from algotik_tse.core import currency
from algotik_tse.settings import settings


class _Response:
    status_code = 200

    def __init__(self, data=None):
        self._data = data

    def json(self):
        return {"data": self._data}


ROWS = [
    ["100", "90", "110", "105", "0", "0", "2026/09/12", "1405/06/21"],
    ["105", "95", "115", "110", "0", "0", "2026/09/13", "1405/06/22"],
]


def test_tgju_catalog_is_unique_complete_and_filterable():
    catalog = att.list_tgju_assets(include_aliases=True)
    assert len(catalog) == 87
    assert catalog["Name"].is_unique
    assert catalog["Slug"].is_unique
    assert set(catalog["Category"]) == {
        "currency",
        "official_rate",
        "gold",
        "silver",
        "coin",
        "coin_bubble",
        "global_metal",
    }
    gold = att.list_tgju_assets("gold")
    assert {"gold-18k", "gold-24k", "gold-mesghal"}.issubset(gold["Name"])
    assert set(gold["Unit"]) == {"rial_per_gram", "rial_per_mesghal"}
    selected = att.list_tgju_assets(["silver", "global_metal"])
    assert set(selected["Category"]) == {"silver", "global_metal"}
    assert catalog.attrs["source"] == "tgju"


def test_tgju_catalog_rejects_bad_filters():
    with pytest.raises(att.InvalidParameterError, match="category"):
        att.list_tgju_assets("crypto")
    with pytest.raises(att.InvalidParameterError, match="include_aliases"):
        att.list_tgju_assets(include_aliases=1)


def test_get_tgju_history_resolves_english_persian_and_slug(monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        return _Response(ROWS)

    monkeypatch.setattr(currency, "safe_get", fake_get)
    english = att.get_tgju_history(
        "gold-18k", limit=1, output_type="full", progress=False
    )
    persian = att.get_currency("طلای ۲۴ عیار", limit=1, progress=False)
    slug = att.currency_coin("silver_999", limit=1, progress=False)
    assert english["Ticker"].iloc[0] == "طلای 18 عیار"
    assert english.attrs["slug"] == "geram18"
    assert english.attrs["unit"] == "rial_per_gram"
    assert persian.attrs["asset"] == "gold-24k"
    assert slug.attrs["asset"] == "silver-999"
    assert any(url.endswith("/geram18") for url in seen)
    assert any(url.endswith("/geram24") for url in seen)
    assert any(url.endswith("/silver_999") for url in seen)


def test_get_tgju_history_preserves_legacy_names_and_settings(monkeypatch):
    monkeypatch.setattr(currency, "safe_get", lambda url: _Response(ROWS))
    legacy = att.currency_coin(currency_coin_name="ربع سکه", values=1, progress=False)
    assert legacy.attrs["asset"] == "rob-seke"
    assert settings.currency_web_word["dollar"]["web_word"] == "price_dollar_rl"
    assert settings.currency_persian["سکه"] == "seke"


def test_get_tgju_history_multi_asset_and_typed_failures(monkeypatch):
    monkeypatch.setattr(currency, "safe_get", lambda url: _Response(ROWS))
    result = att.get_tgju_history(["gold-18k", "طلای ۲۴ عیار"], limit=1, progress=False)
    assert isinstance(result.columns, pd.MultiIndex)
    assert set(result.columns.get_level_values(1)) == {"gold-18k", "gold-24k"}
    with pytest.raises(att.InvalidParameterError, match="list_tgju_assets"):
        att.get_tgju_history("not-an-asset", progress=False)

    monkeypatch.setattr(currency, "safe_get", lambda url: _Response({"bad": True}))
    with pytest.raises(att.DataParsingError, match="unexpected schema"):
        att.get_tgju_history("gold-18k", progress=False)


def test_get_tgju_history_connection_error_is_typed(monkeypatch):
    response = _Response(ROWS)
    response.status_code = 503
    monkeypatch.setattr(currency, "safe_get", lambda url: response)
    with pytest.raises(att.ConnectionError, match="503"):
        att.get_tgju_history("gold-18k", progress=False)

    def timeout(url):
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(currency, "safe_get", timeout)
    with pytest.raises(att.ConnectionError, match="could not be fetched"):
        att.get_tgju_history("gold-18k", progress=False)
