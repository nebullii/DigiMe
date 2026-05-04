from digime.config import Settings


def test_discord_channel_ids_property_merges_list_and_default() -> None:
    settings = Settings(
        _env_file=None,
        discord_channel_ids_raw="123, 456",
        discord_default_channel_id="789",
    )

    assert settings.discord_channel_ids == ["123", "456", "789"]


def test_discord_channel_ids_property_avoids_duplicates() -> None:
    settings = Settings(
        _env_file=None,
        discord_channel_ids_raw="123,456",
        discord_default_channel_id="456",
    )

    assert settings.discord_channel_ids == ["123", "456"]
