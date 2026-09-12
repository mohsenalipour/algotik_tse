import pandas as pd
import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


def test_dated_shareholders_follow_effective_date_contract():
    frame = att.get_shareholders(
        date="2026-09-07",
        ins_code="2161110547458064",
        include_id=True,
    )

    assert frame is not None and not frame.empty
    assert frame["trade_date"].unique().tolist() == ["20260907"]
    assert frame["effective_date"].unique().tolist() == ["20260908"]
    assert frame["share_holder_id"].fillna(0).ne(0).all()
    changed = frame.loc[
        frame["share_holder_name"].str.contains("ETFکدرزرو", regex=False)
    ].iloc[0]
    assert changed["change_amount"] == 225000000
    assert changed["change_quality"] == "exact_normalized_name"
    assert frame.attrs["change_includes_non_trade_transfers"] is True


def test_shareholder_history_pair_optimization_is_live():
    frame = att.get_shareholder_history(
        "فولاد",
        start="2026-09-02",
        end="2026-09-09",
        max_requests=3,
        include_id=True,
        progress=False,
    )

    assert not frame.empty
    assert frame["effective_date"].nunique() == 6
    assert frame.attrs["shareholder_requests_used"] == 3
    assert frame.attrs["missing_effective_dates"] == ()
    assert frame["share_holder_id"].fillna(0).ne(0).all()
    assert pd.isna(frame.iloc[0]["change_amount"])
