import datetime

import pandas as pd
import pytest

from algotik_tse import DataParsingError, InvalidParameterError
from algotik_tse.core import ownership


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
