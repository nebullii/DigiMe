from digime.connectors.discord import DiscordMessage
from digime.memory.store import MessageStore


def test_upsert_discord_message_and_context(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()

    inserted = store.upsert_discord_message(
        DiscordMessage(
            id="100",
            channel_id="C1",
            author_id="U1",
            author_name="Alex",
            content="Can someone help with the demo?",
            timestamp="2026-05-03T10:00:00.000000+00:00",
            is_bot=False,
            raw={"id": "100"},
        )
    )

    assert inserted is True
    assert store.latest_discord_message_id("C1") == "100"
    assert "Alex" in store.recent_discord_context("C1")
    assert "Can someone help with the demo?" in store.recent_discord_context("C1")


def test_upsert_discord_message_updates_existing_record(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()
    message = DiscordMessage(
        id="100",
        channel_id="C1",
        author_id="U1",
        author_name="Alex",
        content="ping",
        timestamp="2026-05-03T10:00:00.000000+00:00",
        is_bot=False,
        raw={"id": "100"},
    )

    assert store.upsert_discord_message(message) is True
    assert store.upsert_discord_message(message) is True
    assert store.counts()["discord_messages"] == 1


def test_handled_messages_are_idempotent(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()

    assert not store.has_handled_message("discord", "100", "reply")
    assert store.mark_message_handled("discord", "100", "reply") is True
    assert store.mark_message_handled("discord", "100", "reply") is False
    assert store.has_handled_message("discord", "100", "reply")
