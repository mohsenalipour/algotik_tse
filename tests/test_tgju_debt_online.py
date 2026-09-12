import pandas as pd
import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


@pytest.mark.parametrize(
    "name,unit",
    [
        ("gold-18k", "rial_per_gram"),
        ("gold-24k", "rial_per_gram"),
        ("silver-999", "rial_per_gram"),
        ("gold-ounce", "usd_per_troy_ounce"),
    ],
)
def test_tgju_new_asset_histories_live(name, unit):
    result = att.get_tgju_history(
        name, limit=3, date_format="gregorian", progress=False
    )
    assert len(result) == 3
    assert list(result.columns) == ["Open", "High", "Low", "Close"]
    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.attrs["unit"] == unit
    assert result.attrs["source"] == "tgju"


def test_erad_and_gam_current_universe_live():
    result = att.list_debt_instruments(["erad", "gam"], progress=False)
    assert not result.empty
    assert {"erad", "gam"}.issubset(set(result["DebtType"]))
    gam = result.loc[result["DebtType"].eq("gam")]
    assert not gam.empty
    assert gam["MaturityGregorian"].notna().all()
    assert gam["BondType"].eq("gam").all()
