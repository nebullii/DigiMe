from digime.agent.conversation import (
    ConversationTurn,
    analyze_conversation,
    build_conversation_brief,
)


def test_analyze_conversation_detects_meeting_follow_up() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="Can someone arrange a meeting for next Tuesday?",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
        ConversationTurn(
            id="2",
            author_id="u2",
            author_name="Nevi",
            content="Tuesday 2pm works for me",
            timestamp="2026-05-03T10:01:00+00:00",
        ),
    ]

    state = analyze_conversation(turns, latest_message_id="2", bot_names={"DigiMe"})

    assert state.intent == "meeting_follow_up"
    assert state.needs_reply is True
    assert state.should_auto_send is True
    assert state.confidence == "medium"


def test_analyze_conversation_skips_short_acknowledgement() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="I pushed the latest draft.",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
        ConversationTurn(
            id="2",
            author_id="u2",
            author_name="Nevi",
            content="ok",
            timestamp="2026-05-03T10:01:00+00:00",
        ),
    ]

    state = analyze_conversation(turns, latest_message_id="2", bot_names={"DigiMe"})

    assert state.intent == "acknowledgement"
    assert state.needs_reply is False
    assert state.should_auto_send is False


def test_analyze_conversation_detects_direct_weather_request() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="DigiMe, can you check the weather in Boston?",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
    ]

    state = analyze_conversation(turns, latest_message_id="1", bot_names={"DigiMe"})

    assert state.intent == "weather_request"
    assert state.direct_addressed is True
    assert state.should_auto_send is True


def test_analyze_conversation_detects_whats_up_as_greeting() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="What's up DigiMe?",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
    ]

    state = analyze_conversation(turns, latest_message_id="1", bot_names={"DigiMe"})

    assert state.intent == "greeting"
    assert state.needs_reply is True
    assert state.should_auto_send is True


def test_analyze_conversation_detects_welcome_as_greeting() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="Welcome <@1500599346876645406>",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
    ]

    state = analyze_conversation(
        turns,
        latest_message_id="1",
        bot_user_id="1500599346876645406",
        bot_names={"DigiMe"},
    )

    assert state.intent == "greeting"
    assert state.needs_reply is True


def test_build_conversation_brief_contains_routing_flags() -> None:
    turns = [
        ConversationTurn(
            id="1",
            author_id="u1",
            author_name="Lilian",
            content="Hey DigiMe",
            timestamp="2026-05-03T10:00:00+00:00",
        ),
    ]

    state = analyze_conversation(turns, latest_message_id="1", bot_names={"DigiMe"})
    brief = build_conversation_brief(state)

    assert "Intent: greeting" in brief
    assert "Needs reply: true" in brief
    assert "Relevant recent turns" in brief
