from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MEETING_WORDS = {"meeting", "meet", "call", "sync", "standup", "zoom", "google meet"}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class MeetingRequest:
    platform: str
    start: datetime | None
    duration_minutes: int
    title: str
    attendees: list[str]
    description: str
    missing_fields: list[str]

    @property
    def is_ready(self) -> bool:
        return self.start is not None and not self.missing_fields


def looks_like_meeting_request(text: str) -> bool:
    normalized = text.lower()
    return any(word in normalized for word in MEETING_WORDS) and any(
        verb in normalized for verb in ["arrange", "create", "schedule", "set up", "setup", "book"]
    )


def parse_meeting_request(text: str, timezone_name: str) -> MeetingRequest:
    normalized = text.lower()
    platform = "zoom" if "zoom" in normalized else "google_meet"
    start = _parse_start(text, timezone_name)
    missing_fields = []
    if start is None:
        missing_fields.append("date/time")

    return MeetingRequest(
        platform=platform,
        start=start,
        duration_minutes=_parse_duration_minutes(text) or 30,
        title=_parse_title(text),
        attendees=sorted(set(EMAIL_PATTERN.findall(text))),
        description=text.strip(),
        missing_fields=missing_fields,
    )


def _parse_start(text: str, timezone_name: str) -> datetime | None:
    timezone = ZoneInfo(timezone_name)
    now = datetime.now(timezone)
    normalized = text.lower()

    day_offset = 0
    weekday = None
    for weekday_name, weekday_value in WEEKDAYS.items():
        if weekday_name in normalized:
            weekday = weekday_value
            break
    if "tomorrow" in normalized:
        day_offset = 1
    elif "today" in normalized:
        day_offset = 0

    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", normalized)
    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or "0")
    meridiem = time_match.group(3)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0

    if weekday is None:
        target = now + timedelta(days=day_offset)
        if (hour, minute) <= (now.hour, now.minute):
            target = target + timedelta(days=1)
    else:
        days_ahead = (weekday - now.weekday()) % 7
        if f"next {list(WEEKDAYS.keys())[weekday]}" in normalized and days_ahead == 0:
            days_ahead = 7
        if days_ahead == 0 and (hour, minute) <= (now.hour, now.minute):
            days_ahead = 7
        target = now + timedelta(days=days_ahead)

    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _parse_duration_minutes(text: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\s*(min|mins|minutes)\b", text.lower())
    if match:
        return int(match.group(1))
    return None


def _parse_title(text: str) -> str:
    normalized = " ".join(text.strip().split())
    about_match = re.search(r"\b(?:about|for)\s+(.+)$", normalized, re.IGNORECASE)
    if about_match:
        candidate = about_match.group(1).strip(" .!?")
        if candidate and not re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", candidate, re.IGNORECASE):
            return candidate[:80]
    return "DigiMe meeting"
