from digime.connectors.slack import SlackConversation
from digime.memory.store import MessageStore


def test_build_slack_reply_examples(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()

    conversation = SlackConversation(
        id="D123",
        user_id="UOTHER",
        is_im=True,
        raw={"id": "D123", "user": "UOTHER", "is_im": True},
    )
    store.upsert_slack_conversation(conversation)
    store.upsert_slack_message(
        "D123",
        {"type": "message", "user": "UOTHER", "text": "Can you review this today?", "ts": "1.0"},
    )
    store.upsert_slack_message(
        "D123",
        {
            "type": "message",
            "user": "UME",
            "text": "Yep, I can take a look later this afternoon.",
            "ts": "2.0",
        },
    )

    inserted = store.build_slack_reply_examples(your_user_id="UME")

    assert inserted == 1
    assert store.counts()["reply_examples"] == 1


def test_build_slack_reply_examples_is_idempotent(tmp_path) -> None:
    store = MessageStore(f"sqlite:///{tmp_path / 'digime.sqlite3'}")
    store.initialize()

    conversation = SlackConversation(
        id="D123",
        user_id="UOTHER",
        is_im=True,
        raw={"id": "D123", "user": "UOTHER", "is_im": True},
    )
    store.upsert_slack_conversation(conversation)
    store.upsert_slack_message(
        "D123",
        {"type": "message", "user": "UOTHER", "text": "ping", "ts": "1.0"},
    )
    store.upsert_slack_message(
        "D123",
        {"type": "message", "user": "UME", "text": "pong", "ts": "2.0"},
    )

    assert store.build_slack_reply_examples(your_user_id="UME") == 1
    assert store.build_slack_reply_examples(your_user_id="UME") == 0
    assert store.counts()["reply_examples"] == 1

