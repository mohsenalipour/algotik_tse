import pytest

import algotik_tse as att

pytestmark = pytest.mark.online


def test_symbol_messages_contract_is_live():
    frame = att.get_symbol_events("وبملت", kinds="messages", limit=3, progress=False)
    assert 0 < len(frame) <= 3
    assert frame["InsCode"].eq("778253364357513").all()
    assert frame["EventType"].eq("supervisor_message").all()
    assert frame["EventID"].is_unique
    assert frame.attrs["codal_included"] is False


def test_capital_and_adjustment_events_are_not_labeled_dps():
    frame = att.get_symbol_events(
        "وبملت",
        kinds=("capital_changes", "price_adjustments"),
        limit=0,
        progress=False,
    )
    assert set(frame["EventType"]) <= {"capital_change", "price_adjustment"}
    assert frame.attrs["price_adjustment_is_not_confirmed_dps"] is True
