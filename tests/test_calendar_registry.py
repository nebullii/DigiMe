from digime.connectors.calendar_provider import UnconfiguredCalendarProvider
from digime.connectors.calendar_registry import CalendarProviderConfig, build_calendar_provider
from digime.connectors.google_calendar import GoogleCalendarProvider


def test_build_calendar_provider_returns_google_provider() -> None:
    provider = build_calendar_provider(
        CalendarProviderConfig(
            provider="google",
            calendar_id="primary",
            oauth_client_file="./config/google-oauth-client.json",
            oauth_token_file="./config/google-token.json",
        )
    )

    assert isinstance(provider, GoogleCalendarProvider)
    assert provider.provider_name == "google"


def test_build_calendar_provider_returns_unconfigured_provider() -> None:
    provider = build_calendar_provider(CalendarProviderConfig(provider="none"))

    assert isinstance(provider, UnconfiguredCalendarProvider)
    assert provider.provider_name == "none"
    assert provider.is_configured() is False


def test_build_calendar_provider_rejects_unknown_provider() -> None:
    try:
        build_calendar_provider(CalendarProviderConfig(provider="outlook"))
    except ValueError as error:
        assert "Unsupported calendar provider" in str(error)
    else:
        raise AssertionError("Expected unknown provider to raise ValueError.")
