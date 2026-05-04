from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from digime.agent.meeting import MeetingRequest


class CalendarProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreatedMeeting:
    provider: str
    event_url: str
    meeting_url: str | None
    start_iso: str


class CalendarProvider(Protocol):
    provider_name: str

    def is_configured(self) -> bool:
        ...

    def supports_meeting_platform(self, platform: str) -> bool:
        ...

    def create_meeting(self, request: MeetingRequest) -> CreatedMeeting:
        ...


class UnconfiguredCalendarProvider:
    provider_name = "none"

    def is_configured(self) -> bool:
        return False

    def supports_meeting_platform(self, platform: str) -> bool:
        return False

    def create_meeting(self, request: MeetingRequest) -> CreatedMeeting:
        raise CalendarProviderError("No calendar provider is configured.")
