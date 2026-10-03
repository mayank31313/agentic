"""Unit tests for agentic.agentic_mcp.gcalendar.tools helpers.

These target the pure event-body/date-range helpers in isolation, since
``GCalendarTool`` itself requires Google OAuth credentials and network
access to construct.
"""

import datetime

from agentic.agentic_mcp.gcalendar.tools import (
    _build_event_body,
    _to_event_time,
    _todays_bounds,
)


def test_to_event_time_uses_date_for_all_day_events():
    assert _to_event_time("2026-09-03") == {"date": "2026-09-03"}


def test_to_event_time_uses_date_time_for_timestamps():
    assert _to_event_time("2026-09-03T10:00:00-07:00") == {
        "dateTime": "2026-09-03T10:00:00-07:00"
    }


def test_build_event_body_minimal():
    body = _build_event_body(
        "Standup", "2026-09-03T09:00:00Z", "2026-09-03T09:30:00Z"
    )
    assert body == {
        "summary": "Standup",
        "start": {"dateTime": "2026-09-03T09:00:00Z"},
        "end": {"dateTime": "2026-09-03T09:30:00Z"},
    }


def test_build_event_body_includes_optional_fields():
    body = _build_event_body(
        "Planning",
        "2026-09-03T09:00:00Z",
        "2026-09-03T10:00:00Z",
        description="Quarterly planning",
        location="Room 1",
        attendees=["a@example.com", "b@example.com"],
    )
    assert body["description"] == "Quarterly planning"
    assert body["location"] == "Room 1"
    assert body["attendees"] == [
        {"email": "a@example.com"},
        {"email": "b@example.com"},
    ]


def test_build_event_body_all_day():
    body = _build_event_body("Vacation", "2026-09-03", "2026-09-04")
    assert body["start"] == {"date": "2026-09-03"}
    assert body["end"] == {"date": "2026-09-04"}


def test_todays_bounds_span_exactly_one_day():
    start_str, end_str = _todays_bounds("UTC")
    start = datetime.datetime.fromisoformat(start_str)
    end = datetime.datetime.fromisoformat(end_str)
    assert end - start == datetime.timedelta(days=1)
    assert start.hour == 0 and start.minute == 0 and start.second == 0


def test_todays_bounds_matches_current_date():
    start_str, _ = _todays_bounds("UTC")
    start = datetime.datetime.fromisoformat(start_str)
    assert start.date() == datetime.datetime.now(datetime.timezone.utc).date()

