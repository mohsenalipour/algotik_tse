import datetime

import pandas as pd
import pytest

from algotik_tse import DataParsingError, InvalidParameterError
from algotik_tse.core import ownership
from algotik_tse.core import shareholders as shareholders_module
from algotik_tse.core.resolver import InstrumentRef


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def _payload():
    return {
        "dates": [20260906, 20260907, 20260908, 20260909, 20260912],
        "shareHoldersChanges": [
            {
                "name": "سهامدار نمونه",
                "insList": [
                    {
                        "insCode": "11",
                        "name": "شرکت نمونه",
                        "firstDay": 100,
                        "secondDay": 120,
                        "thirdDay": 120,
                        "fourthDay": 90,
                        "fifthDay": 110,
                    }
                ],
            },
            {
                "name": "شخص حقيقي",
                "insList": [
                    {
                        "insCode": "22",
                        "name": "شرکت دوم",
                        "firstDay": 50,
                        "secondDay": 50,
                        "thirdDay": 40,
                        "fourthDay": 40,
                        "fifthDay": 40,
                    }
                ],
            },
        ],
    }


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    monkeypatch.setattr(
        ownership, "safe_get", lambda *_a, **_k: FakeResponse(_payload())
    )


def test_snapshots_preserve_five_date_window_and_source_limits():
    frame = ownership.get_major_shareholder_snapshots(
        days=5, enrich_identity=False, progress=False
    )

    assert len(frame) == 10
    assert frame["GregorianDate"].nunique() == 5
    assert frame["Holdings"].dtype == "Int64"
    assert frame.attrs["provider_window_max_sessions"] == 5
    assert frame.attrs["rolling_window"] is True
    assert frame.attrs["no_backfill"] is True
    assert frame.attrs["is_complete_major_shareholder_list"] is False
    assert frame.attrs["stable_shareholder_id_available"] is False


def test_snapshot_date_accepts_jalali_and_rejects_outside_window():
    frame = ownership.get_major_shareholder_snapshots(
        date="1405-06-21", enrich_identity=False, progress=False
    )
    assert frame["GregorianDate"].unique().tolist() == [datetime.date(2026, 9, 12)]

    with pytest.raises(InvalidParameterError, match="outside the five-date"):
        ownership.get_major_shareholder_snapshots(
            date="2026-09-01", enrich_identity=False, progress=False
        )


def test_changes_are_consecutive_deltas_and_exclude_unchanged_by_default():
    frame = ownership.get_major_shareholder_changes(
        days=5, enrich_identity=False, progress=False
    )

    sample = frame.loc[frame["InsCode"] == "11"]
    assert sample["ChangeShares"].tolist() == [20, -30, 20]
    assert sample["Direction"].tolist() == ["increase", "decrease", "increase"]
    assert frame["PreviousHoldings"].dtype == "Int64"
    assert frame.attrs["oldest_snapshot_has_no_prior_comparison"] is True


def test_changes_days_one_uses_previous_published_snapshot():
    frame = ownership.get_major_shareholder_changes(
        days=1, enrich_identity=False, progress=False
    )
    assert frame["GregorianDate"].unique().tolist() == [datetime.date(2026, 9, 12)]
    assert frame["ChangeShares"].tolist() == [20]
    assert frame.iloc[0]["PreviousGregorianDate"] == datetime.date(2026, 9, 9)


def test_unchanged_direction_is_explicit():
    frame = ownership.get_major_shareholder_changes(
        days=2,
        direction="unchanged",
        enrich_identity=False,
        progress=False,
    )
    assert not frame.empty
    assert frame["ChangeShares"].eq(0).all()
    assert frame["Direction"].eq("unchanged").all()


def test_active_shareholders_aggregate_net_and_gross_activity():
    frame = ownership.get_active_shareholders(
        days=5, enrich_identity=False, progress=False
    )
    sample = frame.loc[frame["InsCode"] == "11"].iloc[0]
    assert sample["InitialHoldings"] == 100
    assert sample["LatestHoldings"] == 110
    assert sample["NetChangeShares"] == 10
    assert sample["GrossIncreaseShares"] == 40
    assert sample["GrossDecreaseShares"] == 30
    assert sample["ActiveDays"] == 3
    assert sample["ActivityDirection"] == "accumulation"


def test_exact_holder_filter_normalizes_persian_characters():
    frame = ownership.get_major_shareholder_snapshots(
        holder="شخص حقیقی", enrich_identity=False, progress=False
    )
    assert frame["HolderName"].unique().tolist() == ["شخص حقیقی"]
    assert frame["InsCode"].unique().tolist() == ["22"]


def test_identity_enrichment_is_exact_inscode_join(monkeypatch):
    monkeypatch.setattr(
        ownership,
        "_identity_map",
        lambda: {"11": ("نماد", "نام رسمی"), "999": ("غلط", "غلط")},
    )
    frame = ownership.get_major_shareholder_snapshots(days=1, progress=False)
    row = frame.loc[frame["InsCode"] == "11"].iloc[0]
    assert row["Symbol"] == "نماد"
    assert row["InstrumentName"] == "نام رسمی"
    assert pd.isna(frame.loc[frame["InsCode"] == "22", "Symbol"]).all()
    assert frame.attrs["unmatched_identity_count"] == 1


def test_same_display_name_is_not_treated_as_stable_holder_identity(monkeypatch):
    payload = _payload()
    payload["shareHoldersChanges"] = [
        {
            "name": "شخص حقیقی",
            "insList": [
                {
                    "insCode": "11",
                    "name": "شرکت نمونه",
                    "firstDay": 100,
                    "secondDay": 110,
                    "thirdDay": 110,
                    "fourthDay": 110,
                    "fifthDay": 110,
                }
            ],
        },
        {
            "name": "شخص حقیقی",
            "insList": [
                {
                    "insCode": "11",
                    "name": "شرکت نمونه",
                    "firstDay": 200,
                    "secondDay": 180,
                    "thirdDay": 180,
                    "fourthDay": 180,
                    "fifthDay": 180,
                }
            ],
        },
    ]
    monkeypatch.setattr(ownership, "safe_get", lambda *_a, **_k: FakeResponse(payload))

    frame = ownership.get_active_shareholders(
        days=5, enrich_identity=False, progress=False
    )
    assert len(frame) == 2
    assert frame["HolderRecord"].nunique() == 2
    assert sorted(frame["NetChangeShares"].tolist()) == [-20, 10]
    assert frame.attrs["stable_shareholder_id_available"] is False


@pytest.mark.parametrize("days", [0, 6, 1.5, True, "bad"])
def test_days_must_be_one_to_five(days):
    with pytest.raises(InvalidParameterError, match="between 1 and 5"):
        ownership.get_major_shareholder_snapshots(
            days=days, enrich_identity=False, progress=False
        )


@pytest.mark.parametrize("holder", ["", "   ", 123, False])
def test_holder_filter_must_be_a_non_empty_string(holder):
    with pytest.raises(InvalidParameterError, match="holder"):
        ownership.get_major_shareholder_snapshots(
            holder=holder, enrich_identity=False, progress=False
        )


def test_malformed_provider_contract_fails_closed(monkeypatch):
    monkeypatch.setattr(
        ownership,
        "safe_get",
        lambda *_a, **_k: FakeResponse(
            {"dates": [20260912] * 6, "shareHoldersChanges": []}
        ),
    )
    with pytest.raises(DataParsingError, match="1 to 5 dates"):
        ownership.get_major_shareholder_snapshots(enrich_identity=False, progress=False)


def test_empty_filter_has_stable_typed_schema():
    frame = ownership.get_major_shareholder_changes(
        holder="وجود ندارد", enrich_identity=False, progress=False
    )
    assert frame.empty
    assert frame.columns.tolist() == ownership.MAJOR_SHAREHOLDER_CHANGE_COLUMNS
    assert frame["ChangeShares"].dtype == "Int64"
    assert str(frame["FetchedAt"].dtype) == "datetime64[ns, Asia/Tehran]"


def test_accumulation_ranking_uses_relative_change_per_instrument():
    frame = ownership.rank_shareholder_accumulation(
        days=5,
        metric="percent",
        top=2,
        enrich_identity=False,
        progress=False,
    )

    assert frame["Rank"].tolist() == [1, 2]
    assert frame["InsCode"].tolist() == ["22", "11"]
    assert frame["NetChangePercent"].tolist() == [-20.0, 10.0]
    assert frame.attrs["ranking_unit"] == "holder_instrument_pair"
    assert frame.attrs["cross_instrument_share_counts_are_not_summed"] is True


def test_accumulation_ranking_filters_direction_and_validates_metric():
    frame = ownership.rank_shareholder_accumulation(
        direction="distribution",
        metric="shares",
        enrich_identity=False,
        progress=False,
    )
    assert frame["ActivityDirection"].tolist() == ["distribution"]
    assert frame["Score"].tolist() == [10.0]

    with pytest.raises(InvalidParameterError, match="metric"):
        ownership.rank_shareholder_accumulation(
            metric="value", enrich_identity=False, progress=False
        )


def test_shareholder_network_is_latest_bipartite_edge_list(monkeypatch):
    payload = _payload()
    payload["shareHoldersChanges"][0]["insList"].append(
        {
            "insCode": "33",
            "name": "شرکت سوم",
            "firstDay": 10,
            "secondDay": 20,
            "thirdDay": 30,
            "fourthDay": 40,
            "fifthDay": 50,
        }
    )
    monkeypatch.setattr(ownership, "safe_get", lambda *_a, **_k: FakeResponse(payload))

    frame = ownership.get_shareholder_network(
        min_holdings=45, enrich_identity=False, progress=False
    )

    assert frame["GregorianDate"].nunique() == 1
    assert frame["InsCode"].tolist() == ["11", "33"]
    assert frame["HolderInstrumentCount"].tolist() == [2, 2]
    assert frame["HolderNode"].nunique() == 1
    assert frame.attrs["network_type"] == "bipartite_edge_list"
    assert frame.attrs["holder_node_scope"] == "current provider response only"


def test_ownership_concentration_reports_both_hhi_bases(monkeypatch):
    snapshot = pd.DataFrame(
        {
            "percentage_of_shares": pd.array([20.0, 10.0, 5.0], dtype="Float64"),
            "trade_date": ["20260909"] * 3,
            "effective_date": ["20260912"] * 3,
            "effective_date_jalali": ["1405-06-21"] * 3,
        }
    )
    snapshot.attrs["source"] = "fixture_shareholders"
    monkeypatch.setattr(
        ownership,
        "resolve_instrument",
        lambda *_a, **_k: InstrumentRef("11", "نماد", "شرکت نمونه", "equity"),
    )
    monkeypatch.setattr(shareholders_module, "shareholders", lambda *_a, **_k: snapshot)

    frame = ownership.get_ownership_concentration("نماد", top_n=2, progress=False)
    row = frame.iloc[0]

    assert row["MajorHolderCount"] == 3
    assert row["DisclosedOwnershipPercent"] == 35.0
    assert row["UndisclosedOrBelowThresholdPercent"] == 65.0
    assert row["TopNPercent"] == 30.0
    assert row["MajorHolderHHI"] == 525.0
    assert row["NormalizedDisclosedHHI"] == pytest.approx(4285.7142857)
    assert frame.attrs["is_full_ownership_register"] is False
    assert frame.attrs["unreported_remainder_is_not_assumed_to_be_one_holder"] is True
    assert frame.attrs["major_holder_hhi_is_lower_bound_on_full_hhi"] is True


def test_ownership_concentration_rejects_impossible_percentages(monkeypatch):
    snapshot = pd.DataFrame(
        {
            "percentage_of_shares": [70.0, 31.0],
            "trade_date": ["20260909"] * 2,
            "effective_date": ["20260912"] * 2,
            "effective_date_jalali": ["1405-06-21"] * 2,
        }
    )
    monkeypatch.setattr(
        ownership,
        "resolve_instrument",
        lambda *_a, **_k: InstrumentRef("11", "نماد", "شرکت نمونه", "equity"),
    )
    monkeypatch.setattr(shareholders_module, "shareholders", lambda *_a, **_k: snapshot)

    with pytest.raises(DataParsingError, match="cannot materially exceed 100"):
        ownership.get_ownership_concentration("نماد", progress=False)


@pytest.mark.parametrize(
    "function, kwargs",
    [
        (ownership.rank_shareholder_accumulation, {"top": 0}),
        (ownership.get_shareholder_network, {"min_holdings": -1}),
        (ownership.get_ownership_concentration, {"top_n": True}),
    ],
)
def test_derived_ownership_inputs_fail_closed(function, kwargs):
    with pytest.raises(InvalidParameterError):
        function(progress=False, **kwargs)
