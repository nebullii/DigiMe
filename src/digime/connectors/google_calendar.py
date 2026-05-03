from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from digime.agent.meeting import MeetingRequest


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleCalendarError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreatedMeeting:
    event_url: str
    meeting_url: str
    start_iso: str


class GoogleCalendarConnector:
    def __init__(
        self,
        credentials_path: str,
        token_path: str,
        calendar_id: str = "primary",
    ) -> None:
        self.credentials_path = Path(credentials_path).expanduser()
        self.token_path = Path(token_path).expanduser()
        self.calendar_id = calendar_id

    def is_configured(self) -> bool:
        return self.credentials_path.exists()

    def create_google_meet(self, request: MeetingRequest) -> CreatedMeeting:
        if request.start is None:
            raise GoogleCalendarError("Meeting request is missing a start time.")
        if not self.credentials_path.exists():
            raise GoogleCalendarError(
                f"Google OAuth client file not found: {self.credentials_path}"
            )

        service = self._service()
        end = request.start + timedelta(minutes=request.duration_minutes)
        event_body = {
            "summary": request.title,
            "description": request.description,
            "start": {
                "dateTime": request.start.isoformat(),
                "timeZone": str(request.start.tzinfo),
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": str(end.tzinfo),
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        if request.attendees:
            event_body["attendees"] = [{"email": email} for email in request.attendees]
        event = (
            service.events()
            .insert(
                calendarId=self.calendar_id,
                body=event_body,
                conferenceDataVersion=1,
            )
            .execute()
        )
        meeting_url = event.get("hangoutLink") or _conference_uri(event)
        if not meeting_url:
            raise GoogleCalendarError("Google Calendar did not return a Meet link.")
        return CreatedMeeting(
            event_url=event.get("htmlLink", ""),
            meeting_url=meeting_url,
            start_iso=request.start.isoformat(),
        )

    def _service(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as error:
            raise GoogleCalendarError(
                "Google Calendar dependencies are not installed. Run pip install -e '.[dev]'."
            ) from error

        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path),
                    SCOPES,
                )
                credentials = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(credentials.to_json())
        return build("calendar", "v3", credentials=credentials)


def _conference_uri(event: dict) -> str | None:
    for entry_point in event.get("conferenceData", {}).get("entryPoints", []):
        if entry_point.get("entryPointType") == "video":
            return entry_point.get("uri")
    return None
