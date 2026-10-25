"""Bounded live verification for fund cash/deposit separation."""

import numpy as np
import pandas as pd
import pytest

import algotik_tse as att


@pytest.mark.online
def test_live_fixed_income_cash_is_exact_and_not_the_tsetmc_deposit_duplicate():
    funds = att.list_funds("fixed_income", progress=False)
    cash = pd.to_numeric(funds["pct_cash"], errors="coerce")
    deposit = pd.to_numeric(funds["pct_deposit"], errors="coerce")
    available = cash.notna() & deposit.notna()

    assert len(funds) >= 100
    assert int(cash.notna().sum()) >= 100
    assert int(available.sum()) >= 100
    assert int(np.isclose(cash[available], deposit[available]).sum()) < int(
        available.sum() * 0.1
    )

    khatam = funds.loc[funds["reg_no"].eq(11753)]
    assert len(khatam) == 1
    assert pd.notna(khatam.iloc[0]["record_date"])
    assert pd.notna(khatam.iloc[0]["pct_cash"])
    assert not np.isclose(
        float(khatam.iloc[0]["pct_cash"]),
        float(khatam.iloc[0]["pct_deposit"]),
    )

    assert funds.attrs["pct_cash_source"] == "fipiran_fund_compare_exact_reg_no"
    assert funds.attrs["pct_cash_source_status"] == "available"
    assert funds.attrs["pct_cash_inferred"] is False
    assert funds.attrs["pct_cash_values_available"] == int(cash.notna().sum())
