from digime.connectors.discord import DiscordMessage
from digime.memory.store import MessageStore
from digime.agent.meeting import parse_meeting_request


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


def test_meeting_state_roundtrip(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()
    request = parse_meeting_request(
        "Arrange a meeting tomorrow at 3pm for design review",
        "America/New_York",
    )

    store.save_meeting_state("C1", request, status="pending", last_message_id="123")
    loaded = store.get_meeting_state("C1")

    assert loaded is not None
    assert loaded.request.title == request.title
    assert loaded.request.start == request.start
    assert loaded.status == "pending"
    assert store.clear_meeting_state("C1") is True
    assert store.get_meeting_state("C1") is None


def test_reply_example_similarity_prefers_same_channel(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()
    store.save_reply_example(
        platform="discord",
        conversation_id="C1",
        incoming_context="Alex: can you review the API change today?",
        your_reply="Yep, I can take a look this afternoon.",
        sent_at="2026-05-03T10:05:00+00:00",
        source_message_id="m1",
    )
    store.save_reply_example(
        platform="discord",
        conversation_id="C2",
        incoming_context="Jamie: can you review the design doc?",
        your_reply="Sure, I'll review it later today.",
        sent_at="2026-05-03T10:06:00+00:00",
        source_message_id="m2",
    )

    matches = store.find_similar_reply_examples(
        platform="discord",
        conversation_id="C1",
        query_text="can you review this API change?",
        limit=2,
    )

    assert len(matches) == 2
    assert matches[0].conversation_id == "C1"
    assert "take a look this afternoon" in matches[0].your_reply
