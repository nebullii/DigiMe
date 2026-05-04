from __future__ import annotations

from dataclasses import dataclass

from digime.connectors.calendar_provider import CalendarProvider, UnconfiguredCalendarProvider
from digime.connectors.google_calendar import GoogleCalendarProvider


@dataclass(frozen=True)
class CalendarProviderConfig:
    provider: str = "google"
    calendar_id: str = "primary"
    oauth_client_file: str = "./config/google-oauth-client.json"
    oauth_token_file: str = "./config/google-token.json"


def build_calendar_provider(config: CalendarProviderConfig) -> CalendarProvider:
    provider = config.provider.strip().lower()
    if provider in {"", "none", "disabled"}:
        return UnconfiguredCalendarProvider()
    if provider == "google":
        return GoogleCalendarProvider(
            credentials_path=config.oauth_client_file,
            token_path=config.oauth_token_file,
            calendar_id=config.calendar_id,
        )
    raise ValueError(
        f"Unsupported calendar provider '{config.provider}'. "
        "Supported providers: google, none."
    )
