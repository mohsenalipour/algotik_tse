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


def test_derived_ownership_analytics_live_contracts():
    ranking = att.rank_shareholder_accumulation(
        days=1, top=5, enrich_identity=False, progress=False
    )
    network = att.get_shareholder_network(
        min_holdings=0, enrich_identity=False, progress=False
    )
    concentration = att.get_ownership_concentration("فولاد", progress=False)

    assert ranking.columns.tolist()[0] == "Rank"
    assert ranking.attrs["ranking_unit"] == "holder_instrument_pair"
    assert {"HolderNode", "InstrumentNode", "Holdings"}.issubset(network.columns)
    assert network.attrs["network_type"] == "bipartite_edge_list"
    assert len(concentration) == 1
    assert concentration.iloc[0]["MajorHolderCount"] > 0
    assert concentration.attrs["is_full_ownership_register"] is False
