from __future__ import annotations

import re
from dataclasses import dataclass

from digime.agent.meeting import MEETING_WORDS, looks_like_meeting_request


QUESTION_WORDS = {
    "can",
    "could",
    "would",
    "will",
    "should",
    "do",
    "does",
    "did",
    "is",
    "are",
    "anyone",
}
REQUEST_WORDS = {
    "please",
    "need",
    "help",
    "review",
    "check",
    "arrange",
    "create",
    "schedule",
    "set up",
    "setup",
    "book",
    "send",
    "share",
    "join",
}
GREETING_WORDS = {"hi", "hello", "hey", "yo"}
THANKS_WORDS = {"thanks", "thank you", "thx", "ty"}
ACK_WORDS = {
    "ok",
    "okay",
    "cool",
    "sounds good",
    "works",
    "that works",
    "sure",
    "yep",
    "yes",
    "got it",
}
WEATHER_WORDS = {"weather", "forecast", "temperature", "rain", "snow", "wind"}
SENSITIVE_WORDS = {
    "password",
    "secret",
    "token",
    "api key",
    "salary",
    "medical",
    "diagnosis",
    "lawsuit",
    "legal",
    "confidential",
    "private",
    "social security",
    "ssn",
}
TIME_REFERENCE_PATTERN = re.compile(
    r"\b("
    r"today|tonight|tomorrow|next week|next monday|next tuesday|next wednesday|"
    r"next thursday|next friday|next saturday|next sunday|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{1,2}(:\d{2})?\s*(am|pm)"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConversationTurn:
    id: str
    author_id: str
    author_name: str
    content: str
    timestamp: str
    is_bot: bool = False


@dataclass(frozen=True)
class ConversationState:
    latest_message_id: str
    latest_author_id: str
    latest_author_name: str
    latest_text: str
    intent: str
    confidence: str
    needs_reply: bool
    direct_addressed: bool
    missing_context: bool
    sensitive: bool
    should_auto_send: bool
    reason: str
    recent_turns: list[ConversationTurn]
    relevant_turns: list[ConversationTurn]


def analyze_conversation(
    messages: list[ConversationTurn],
    latest_message_id: str | None = None,
    bot_user_id: str | None = None,
    bot_names: set[str] | None = None,
) -> ConversationState:
    non_empty_messages = [message for message in messages if message.content.strip()]
    if not non_empty_messages:
        raise ValueError("Conversation analysis needs at least one non-empty message.")

    if latest_message_id is None:
        latest = non_empty_messages[-1]
        latest_index = len(non_empty_messages) - 1
    else:
        latest_index = next(
            index for index, message in enumerate(non_empty_messages) if message.id == latest_message_id
        )
        latest = non_empty_messages[latest_index]

    names = {name.lower() for name in (bot_names or set()) if name}
    names.add("digime")
    direct_addressed = _is_direct_addressed(latest.content, bot_user_id, names)
    relevant_turns = _select_relevant_turns(non_empty_messages, latest_index)
    prior_text = "\n".join(turn.content for turn in relevant_turns[:-1])
    meeting_context_active = any(word in prior_text.lower() for word in MEETING_WORDS)

    intent = _classify_intent(latest.content, meeting_context_active=meeting_context_active)
    missing_context = _is_missing_context(latest.content, intent)
    sensitive = _is_sensitive(latest.content)
    needs_reply = _needs_reply(intent, direct_addressed)
    confidence = _confidence(intent, latest.content, direct_addressed, missing_context, relevant_turns)
    should_auto_send = needs_reply and confidence != "low" and not sensitive
    reason = _reason(
        intent=intent,
        direct_addressed=direct_addressed,
        missing_context=missing_context,
        sensitive=sensitive,
        confidence=confidence,
    )

    return ConversationState(
        latest_message_id=latest.id,
        latest_author_id=latest.author_id,
        latest_author_name=latest.author_name,
        latest_text=latest.content,
        intent=intent,
        confidence=confidence,
        needs_reply=needs_reply,
        direct_addressed=direct_addressed,
        missing_context=missing_context,
        sensitive=sensitive,
        should_auto_send=should_auto_send,
        reason=reason,
        recent_turns=non_empty_messages,
        relevant_turns=relevant_turns,
    )


def build_conversation_brief(state: ConversationState) -> str:
    turns = "\n".join(
        f"- {turn.author_name}: {turn.content}"
        for turn in state.relevant_turns
    )
    return (
        "Conversation state:\n"
        f"- Intent: {state.intent}\n"
        f"- Confidence: {state.confidence}\n"
        f"- Needs reply: {str(state.needs_reply).lower()}\n"
        f"- Directly addressed to DigiMe: {str(state.direct_addressed).lower()}\n"
        f"- Missing context: {str(state.missing_context).lower()}\n"
        f"- Sensitive: {str(state.sensitive).lower()}\n"
        f"- Auto-send allowed: {str(state.should_auto_send).lower()}\n"
        f"- Reason: {state.reason}\n"
        "Relevant recent turns:\n"
        f"{turns}"
    )


def turns_from_records(records: list[dict[str, str]]) -> list[ConversationTurn]:
    return [
        ConversationTurn(
            id=str(record["id"]),
            author_id=str(record.get("author_id", "")),
            author_name=str(record["author_name"]),
            content=str(record["content"]),
            timestamp=str(record["timestamp"]),
            is_bot=bool(record.get("is_bot", False)),
        )
        for record in records
        if str(record.get("content", "")).strip()
    ]


def _select_relevant_turns(messages: list[ConversationTurn], latest_index: int, max_turns: int = 8) -> list[ConversationTurn]:
    start = max(0, latest_index - (max_turns - 1))
    window = messages[start : latest_index + 1]
    latest = messages[latest_index]
    if len(window) < max_turns:
        return window

    # Keep a closer window when the latest message is explicit; widen slightly for short follow-ups.
    if len(latest.content.split()) <= 4 or TIME_REFERENCE_PATTERN.search(latest.content):
        return window
    return window[-6:]


def _classify_intent(text: str, meeting_context_active: bool) -> str:
    normalized = text.lower().strip()
    if looks_like_meeting_request(normalized):
        return "meeting_request"
    if meeting_context_active and TIME_REFERENCE_PATTERN.search(normalized):
        return "meeting_follow_up"
    if _looks_like_weather_request(normalized):
        return "weather_request"
    if _looks_like_greeting(normalized):
        return "greeting"
    if _looks_like_thanks(normalized):
        return "thanks"
    if _looks_like_question(normalized):
        return "question"
    if _looks_like_request(normalized):
        return "request"
    if _looks_like_ack(normalized):
        return "acknowledgement"
    return "statement"


def _needs_reply(intent: str, direct_addressed: bool) -> bool:
    if intent in {"meeting_request", "meeting_follow_up", "weather_request", "question", "request"}:
        return True
    if intent in {"greeting", "thanks"}:
        return direct_addressed
    return direct_addressed and intent != "statement"


def _confidence(
    intent: str,
    text: str,
    direct_addressed: bool,
    missing_context: bool,
    relevant_turns: list[ConversationTurn],
) -> str:
    if intent in {"meeting_request", "weather_request"}:
        return "high"
    if intent in {"greeting", "thanks"}:
        return "high"
    if intent in {"question", "request"} and not missing_context:
        return "high"
    if intent == "meeting_follow_up":
        return "medium"
    if intent in {"question", "request"} and missing_context:
        return "medium"
    if direct_addressed and len(text.split()) > 4:
        return "medium"
    if _multiple_human_topics(relevant_turns):
        return "low"
    return "low"


def _reason(
    *,
    intent: str,
    direct_addressed: bool,
    missing_context: bool,
    sensitive: bool,
    confidence: str,
) -> str:
    if sensitive:
        return "Sensitive content should not be auto-sent without stronger controls."
    if intent == "meeting_request":
        return "Explicit meeting request detected."
    if intent == "meeting_follow_up":
        return "Scheduling follow-up detected from recent meeting context."
    if intent == "weather_request":
        return "External real-time request detected."
    if missing_context:
        return "A clarifying reply is safer because the message depends on missing context."
    if direct_addressed:
        return "The latest message appears directed at DigiMe."
    if confidence == "low":
        return "The latest message looks informational or ambiguous, so replying is risky."
    return "The latest message is a direct social or task-oriented prompt."


def _is_direct_addressed(
    text: str,
    bot_user_id: str | None,
    bot_names: set[str],
) -> bool:
    normalized = text.lower()
    mention_patterns = {f"<@{bot_user_id}>"} if bot_user_id else set()
    if any(pattern in text for pattern in mention_patterns):
        return True
    if any(name in normalized for name in bot_names):
        return True
    return False


def _is_missing_context(text: str, intent: str) -> bool:
    normalized = text.lower().strip()
    short = len(normalized.split()) <= 4
    if intent == "meeting_follow_up":
        return False
    if short and any(token in normalized for token in {"that", "this", "it", "works", "fine"}):
        return True
    if intent == "statement" and short:
        return True
    return False


def _is_sensitive(text: str) -> bool:
    normalized = text.lower()
    return any(word in normalized for word in SENSITIVE_WORDS)


def _looks_like_question(text: str) -> bool:
    return "?" in text or any(text.startswith(f"{word} ") for word in QUESTION_WORDS)


def _looks_like_request(text: str) -> bool:
    return any(word in text for word in REQUEST_WORDS)


def _looks_like_greeting(text: str) -> bool:
    return len(text.split()) <= 8 and any(text.startswith(word) for word in GREETING_WORDS)


def _looks_like_thanks(text: str) -> bool:
    return any(word in text for word in THANKS_WORDS)


def _looks_like_ack(text: str) -> bool:
    return any(word == text or text.startswith(f"{word} ") for word in ACK_WORDS)


def _looks_like_weather_request(text: str) -> bool:
    return any(word in text for word in WEATHER_WORDS) and (
        _looks_like_question(text) or _looks_like_request(text)
    )


def _multiple_human_topics(turns: list[ConversationTurn]) -> bool:
    actionable = [
        turn
        for turn in turns
        if not turn.is_bot and (
            _looks_like_question(turn.content.lower())
            or _looks_like_request(turn.content.lower())
            or looks_like_meeting_request(turn.content.lower())
        )
    ]
    authors = {turn.author_id for turn in actionable}
    return len(actionable) >= 3 and len(authors) >= 2
