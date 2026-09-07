"""Tests for the shared hanger matching rule (issue #1).

Contract under test (app.services.matching):
- the newest Excel row with entry time <= exit moment + 3h wins;
- an already matched row is never reused (old exit -> old row, new -> new);
- a row more than 3h after the exit is skipped;
- rows with unparseable dates fall back to file order.
"""
from app.services.matching import (
    event_exit_seconds,
    match_unload_events,
    select_latest_candidate,
)

DATE = "07.09.2026"


def _row(number, time, profile, date=DATE):
    return {
        "number": str(number),
        "date": date,
        "time": time,
        "profile": profile,
        "client": "Клиент",
        "color": "RAL9016",
        "lamels_qty": 1,
        "kpz_number": "1",
        "material_type": "Ал",
    }


def _event(hanger, time, date=DATE):
    return {"hanger": hanger, "date": date, "time": time}


def test_two_events_same_hanger_distributed_chronologically():
    """Two unloads of one hanger per shift: old exit -> old row, new -> new."""
    products = {
        "5": [
            _row(5, "10:00:00", "Профиль-новый"),
            _row(5, "08:00:00", "Профиль-старый"),
        ]
    }
    events = [_event(5, "12:00:00"), _event(5, "14:00:00")]

    pairs = match_unload_events(events, products)

    by_exit = {e["time"]: (p["profile"] if p else None) for e, p in pairs}
    assert by_exit["14:00:00"] == "Профиль-новый"
    assert by_exit["12:00:00"] == "Профиль-старый"


def test_old_row_not_matched_when_current_exists():
    """Single exit with stale + current rows present matches the current row."""
    candidates = [
        _row(7, "10:00:00", "Профиль-актуальный"),
        _row(7, "08:00:00", "Профиль-старый"),
    ]

    product = select_latest_candidate(
        candidates, exit_seconds=event_exit_seconds(_event(7, "14:00:00"))
    )

    assert product is not None
    assert product["profile"] == "Профиль-актуальный"


def test_entry_more_than_3h_after_exit_is_skipped():
    """Guard: a row loaded >3h after the unload cannot be its match."""
    candidates = [
        _row(9, "16:30:00", "Профиль-будущий"),
        _row(9, "08:00:00", "Профиль-верный"),
    ]

    product = select_latest_candidate(
        candidates, exit_seconds=event_exit_seconds(_event(9, "12:00:00"))
    )

    assert product is not None
    assert product["profile"] == "Профиль-верный"


def test_unparseable_dates_fallback_to_file_order():
    """Rows with unparseable dates keep file order instead of time math."""
    candidates = [
        _row(3, "10:00:00", "Профиль-первый-в-файле", date="???"),
        _row(3, "08:00:00", "Профиль-второй-в-файле", date=""),
    ]

    product = select_latest_candidate(
        candidates, exit_seconds=event_exit_seconds(_event(3, "14:00:00"))
    )

    assert product is not None
    assert product["profile"] == "Профиль-первый-в-файле"
