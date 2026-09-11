import pandas as pd
import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


def test_recent_major_shareholder_source_contract_is_live():
    snapshots = att.get_major_shareholder_snapshots(
        days=1, enrich_identity=False, progress=False
    )
    assert snapshots.attrs["provider_window_max_sessions"] == 5
    assert snapshots.attrs["rolling_window"] is True
    assert snapshots["GregorianDate"].nunique() <= 1
    assert snapshots["Holdings"].dropna().ge(0).all()
    assert snapshots["InsCode"].str.fullmatch(r"[0-9]+").all()


def test_recent_shareholder_changes_and_activity_are_consistent():
    changes = att.get_major_shareholder_changes(
        days=5, enrich_identity=False, progress=False
    )
    active = att.get_active_shareholders(days=5, enrich_identity=False, progress=False)
    assert changes["ChangeShares"].ne(0).all()
    assert set(changes["Direction"].dropna()) <= {"increase", "decrease"}
    if not active.empty:
        assert active["ActiveDays"].ge(1).all()
        assert pd.to_numeric(active["GrossIncreaseShares"]).ge(0).all()
        assert pd.to_numeric(active["GrossDecreaseShares"]).ge(0).all()
