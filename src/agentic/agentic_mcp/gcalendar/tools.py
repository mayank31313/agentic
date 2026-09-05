import datetime
import logging
import os.path
from pathlib import Path
from zoneinfo import ZoneInfo

from fastmcp.tools import ToolResult, tool
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Local timezone used to compute "today"'s start/end bounds for the
# day-planning tool. Mirrors the pattern of other env-overridable defaults
# in this package (see agentic_mcp/gmail/tools.py's DEFAULT_ATTACHMENT_DIR).
DEFAULT_TIMEZONE = os.environ.get("AGENTIC_TIMEZONE", "UTC")


def _build_event_body(
    summary: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
) -> dict:
    """Build a Google Calendar event resource body.

    ``start``/``end`` must already be RFC3339 timestamps (e.g.
    ``2026-09-03T10:00:00-07:00``) or plain ``YYYY-MM-DD`` dates for
    all-day events. No conferencing/Meet-link data is attached.
    """
    body: dict = {
        "summary": summary,
        "start": _to_event_time(start),
        "end": _to_event_time(end),
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": email} for email in attendees]
    return body


def _to_event_time(value: str) -> dict:
    """Wrap a timestamp/date string into the Calendar API's start/end shape."""
    if len(value) == 10:  # YYYY-MM-DD -> all-day event
        return {"date": value}
    return {"dateTime": value}


def _todays_bounds(tz_name: str | None = None) -> tuple[str, str]:
    """Return RFC3339 (start-of-day, end-of-day) timestamps for "today"."""
    tz = ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    now = datetime.datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=1)
    return start.isoformat(), end.isoformat()


class GCalendarTool:
    def __init__(self, credentials_path: str):
        self._creds = None
        self._creds_path = credentials_path
        self._token_path = str(
            Path(credentials_path).with_name("google_calendar_token.json")
        )
        self._init_credentials()

    def _init_credentials(self):
        if os.path.exists(self._token_path):
            self._creds = Credentials.from_authorized_user_file(self._token_path, SCOPES)
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._creds_path, SCOPES
                )
                self._creds = flow.run_local_server(port=0)
            with open(self._token_path, "w") as token:
                token.write(self._creds.to_json())

    def list_events(self, time_min: str, time_max: str, calendar_id: str = "primary"):
        """List events on a calendar within [time_min, time_max)."""
        try:
            service = build("calendar", "v3", credentials=self._creds)
            events_result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return events_result.get("items", [])
        except HttpError as error:
            logger.error(f"An error occurred listing events: {error}")
            return []

    def get_todays_events(self, calendar_id: str = "primary", tz_name: str | None = None):
        """List today's events on a calendar, used for day-planning."""
        time_min, time_max = _todays_bounds(tz_name)
        return self.list_events(time_min, time_max, calendar_id=calendar_id)

    def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ):
        """Create a calendar event/meeting and return the created event resource."""
        service = build("calendar", "v3", credentials=self._creds)
        body = _build_event_body(summary, start, end, description, location, attendees)
        return service.events().insert(calendarId=calendar_id, body=body).execute()

    def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ):
        """Patch an existing event, only sending fields that were provided."""
        service = build("calendar", "v3", credentials=self._creds)
        body: dict = {}
        if summary is not None:
            body["summary"] = summary
        if start is not None:
            body["start"] = _to_event_time(start)
        if end is not None:
            body["end"] = _to_event_time(end)
        if description is not None:
            body["description"] = description
        if location is not None:
            body["location"] = location
        if attendees is not None:
            body["attendees"] = [{"email": email} for email in attendees]
        return (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )

    def delete_event(self, event_id: str, calendar_id: str = "primary"):
        """Delete an event from a calendar."""
        service = build("calendar", "v3", credentials=self._creds)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def get_calendar_tools(google_credentials_path: str):
    calendar_tool = GCalendarTool(google_credentials_path)

    @tool
    def list_calendar_events(
        time_min: str, time_max: str, calendar_id: str = "primary"
    ):
        """List calendar events between two RFC3339 timestamps (e.g. 2026-09-03T00:00:00Z).

        Use this for arbitrary date ranges; use ``get_todays_schedule`` for
        planning the current day specifically.
        """
        try:
            events = calendar_tool.list_events(time_min, time_max, calendar_id)
            return ToolResult(content=events)
        except Exception as error:
            logger.error(f"Error listing calendar events: {error}")
            return ToolResult(content={"error": str(error)})

    @tool
    def get_todays_schedule(calendar_id: str = "primary", timezone: str | None = None):
        """Get today's schedule (all events for the current day) for day planning.

        Args:
            calendar_id: Calendar to query, defaults to the primary calendar.
            timezone: IANA timezone name (e.g. "America/Los_Angeles") to use
                when computing "today"'s start/end bounds. Defaults to the
                ``AGENTIC_TIMEZONE`` environment variable, or UTC.
        """
        try:
            events = calendar_tool.get_todays_events(calendar_id, timezone)
            return ToolResult(content=events)
        except Exception as error:
            logger.error(f"Error fetching today's schedule: {error}")
            return ToolResult(content={"error": str(error)})

    @tool
    def create_calendar_event(
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ):
        """Create/schedule a calendar meeting or event.

        Args:
            summary: Event title.
            start: Start time as RFC3339 (e.g. "2026-09-03T10:00:00-07:00")
                or a plain "YYYY-MM-DD" date for an all-day event.
            end: End time, same format rules as ``start``.
            description: Optional event description/agenda.
            location: Optional event location.
            attendees: Optional list of attendee email addresses to invite.
            calendar_id: Calendar to create the event on, defaults to primary.
        """
        try:
            event = calendar_tool.create_event(
                summary, start, end, description, location, attendees, calendar_id
            )
            return ToolResult(
                content={"event_id": event.get("id"), "html_link": event.get("htmlLink")}
            )
        except Exception as error:
            logger.error(f"Error creating calendar event '{summary}': {error}")
            return ToolResult(content={"error": str(error)})

    @tool
    def update_calendar_event(
        event_id: str,
        calendar_id: str = "primary",
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
    ):
        """Update an existing calendar event/meeting. Only provided fields are changed."""
        try:
            event = calendar_tool.update_event(
                event_id,
                calendar_id,
                summary,
                start,
                end,
                description,
                location,
                attendees,
            )
            return ToolResult(
                content={"event_id": event.get("id"), "html_link": event.get("htmlLink")}
            )
        except Exception as error:
            logger.error(f"Error updating calendar event '{event_id}': {error}")
            return ToolResult(content={"error": str(error)})

    @tool
    def delete_calendar_event(event_id: str, calendar_id: str = "primary"):
        """Delete/cancel a calendar event/meeting."""
        try:
            calendar_tool.delete_event(event_id, calendar_id)
            return ToolResult(content={"deleted": True, "event_id": event_id})
        except Exception as error:
            logger.error(f"Error deleting calendar event '{event_id}': {error}")
            return ToolResult(content={"error": str(error)})

    return [
        list_calendar_events,
        get_todays_schedule,
        create_calendar_event,
        update_calendar_event,
        delete_calendar_event,
    ]

