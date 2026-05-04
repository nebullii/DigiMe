from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
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
    weekday: int | None = None
    relative_day: str | None = None
    time_hour: int | None = None
    time_minute: int | None = None
    duration_explicit: bool = False

    @property
    def is_ready(self) -> bool:
        return self.start is not None and not self.missing_fields

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat() if self.start is not None else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MeetingRequest":
        start = data.get("start")
        return cls(
            platform=str(data["platform"]),
            start=datetime.fromisoformat(start) if start else None,
            duration_minutes=int(data["duration_minutes"]),
            title=str(data["title"]),
            attendees=[str(item) for item in data.get("attendees", [])],
            description=str(data.get("description", "")),
            missing_fields=[str(item) for item in data.get("missing_fields", [])],
            weekday=_optional_int(data.get("weekday")),
            relative_day=str(data["relative_day"]) if data.get("relative_day") else None,
            time_hour=_optional_int(data.get("time_hour")),
            time_minute=_optional_int(data.get("time_minute")),
            duration_explicit=bool(data.get("duration_explicit", False)),
        )


def looks_like_meeting_request(text: str) -> bool:
    normalized = text.lower()
    return any(word in normalized for word in MEETING_WORDS) and any(
        verb in normalized for verb in ["arrange", "create", "schedule", "set up", "setup", "book"]
    )


def parse_meeting_request(text: str, timezone_name: str) -> MeetingRequest:
    normalized = text.lower()
    platform = "zoom" if "zoom" in normalized else "google_meet"
    weekday, relative_day = _parse_day_reference(normalized)
    time_hour, time_minute = _parse_time_reference(normalized)
    start = _resolve_start(
        timezone_name=timezone_name,
        weekday=weekday,
        relative_day=relative_day,
        time_hour=time_hour,
        time_minute=time_minute,
    )
    missing_fields = []
    if start is None:
        missing_fields.append("date/time")
    duration_minutes, duration_explicit = _parse_duration_minutes(text)

    return MeetingRequest(
        platform=platform,
        start=start,
        duration_minutes=duration_minutes,
        title=_parse_title(text),
        attendees=sorted(set(EMAIL_PATTERN.findall(text))),
        description=text.strip(),
        missing_fields=missing_fields,
        weekday=weekday,
        relative_day=relative_day,
        time_hour=time_hour,
        time_minute=time_minute,
        duration_explicit=duration_explicit,
    )


def merge_meeting_requests(
    base: MeetingRequest | None,
    update: MeetingRequest,
    timezone_name: str,
) -> MeetingRequest:
    if base is None:
        return update

    platform = update.platform if update.platform != "google_meet" or base.platform == "google_meet" else base.platform
    weekday = update.weekday if update.weekday is not None else base.weekday
    relative_day = update.relative_day or base.relative_day
    time_hour = update.time_hour if update.time_hour is not None else base.time_hour
    time_minute = update.time_minute if update.time_minute is not None else base.time_minute
    start = _resolve_start(
        timezone_name=timezone_name,
        weekday=weekday,
        relative_day=relative_day,
        time_hour=time_hour,
        time_minute=time_minute,
    )
    missing_fields = []
    if start is None:
        missing_fields.append("date/time")

    title = update.title if update.title != "DigiMe meeting" else base.title
    description = "\n".join(part for part in [base.description, update.description] if part).strip()

    return MeetingRequest(
        platform=platform,
        start=start,
        duration_minutes=update.duration_minutes if update.duration_explicit else base.duration_minutes,
        title=title,
        attendees=sorted(set(base.attendees + update.attendees)),
        description=description,
        missing_fields=missing_fields,
        weekday=weekday,
        relative_day=relative_day,
        time_hour=time_hour,
        time_minute=time_minute,
        duration_explicit=base.duration_explicit or update.duration_explicit,
    )


def _resolve_start(
    timezone_name: str,
    weekday: int | None,
    relative_day: str | None,
    time_hour: int | None,
    time_minute: int | None,
) -> datetime | None:
    timezone = ZoneInfo(timezone_name)
    now = datetime.now(timezone)
    if time_hour is None or time_minute is None:
        return None

    day_offset = 0
    if relative_day == "tomorrow":
        day_offset = 1
    if weekday is None:
        target = now + timedelta(days=day_offset)
        if (time_hour, time_minute) <= (now.hour, now.minute):
            target = target + timedelta(days=1)
    else:
        days_ahead = (weekday - now.weekday()) % 7
        if relative_day == "next" and days_ahead == 0:
            days_ahead = 7
        if days_ahead == 0 and (time_hour, time_minute) <= (now.hour, now.minute):
            days_ahead = 7
        target = now + timedelta(days=days_ahead)

    return target.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)


def _parse_day_reference(normalized: str) -> tuple[int | None, str | None]:
    weekday = None
    relative_day = None
    for weekday_name, weekday_value in WEEKDAYS.items():
        if f"next {weekday_name}" in normalized:
            weekday = weekday_value
            relative_day = "next"
            return weekday, relative_day
        if weekday_name in normalized:
            weekday = weekday_value
            break
    if "tomorrow" in normalized:
        relative_day = "tomorrow"
    elif "today" in normalized:
        relative_day = "today"
    return weekday, relative_day


def _parse_time_reference(normalized: str) -> tuple[int | None, int | None]:
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", normalized)
    if not time_match:
        return None, None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or "0")
    meridiem = time_match.group(3)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour, minute


def _parse_duration_minutes(text: str) -> tuple[int, bool]:
    match = re.search(r"\b(\d{1,3})\s*(min|mins|minutes)\b", text.lower())
    if match:
        return int(match.group(1)), True
    return 30, False


def _parse_title(text: str) -> str:
    normalized = " ".join(text.strip().split())
    about_match = re.search(r"\b(?:about|for)\s+(.+)$", normalized, re.IGNORECASE)
    if about_match:
        candidate = about_match.group(1).strip(" .!?")
        if candidate and not re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", candidate, re.IGNORECASE):
            return candidate[:80]
    return "DigiMe meeting"


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
