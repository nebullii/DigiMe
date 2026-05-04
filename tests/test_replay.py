from digime.agent.conversation import ConversationTurn, analyze_conversation
from digime.agent.meeting import merge_meeting_requests, parse_meeting_request


def test_replay_meeting_request_then_time_follow_up_becomes_schedulable() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="DigiMe, can you set up a meeting Tuesday for design review?",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
        ConversationTurn(
            id="2",
            author_id="u2",
            author_name="Nevi",
            content="2pm works for me",
            timestamp="2026-05-03T10:02:00+00:00",
        ),
    ]

    first_state = analyze_conversation(turns[:1], latest_message_id="1", bot_names={"DigiMe"})
    assert first_state.intent == "meeting_request"

    pending = parse_meeting_request(turns[0].content, "America/New_York")
    assert pending.is_ready is False

    second_state = analyze_conversation(turns, latest_message_id="2", bot_names={"DigiMe"})
    assert second_state.intent == "meeting_follow_up"

    merged = merge_meeting_requests(
        pending,
        parse_meeting_request(turns[1].content, "America/New_York"),
        "America/New_York",
    )

    assert merged.is_ready is True
    assert merged.start is not None
    assert merged.start.hour == 14


def test_replay_noisy_channel_acknowledgement_stays_skip() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Alex",
            content="I deployed the patch.",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
        ConversationTurn(
            id="2",
            author_id="u2",
            author_name="Jamie",
            content="nice",
            timestamp="2026-05-03T10:01:00+00:00",
        ),
    ]

    state = analyze_conversation(turns, latest_message_id="2", bot_names={"DigiMe"})

    assert state.needs_reply is False
    assert state.should_auto_send is False
