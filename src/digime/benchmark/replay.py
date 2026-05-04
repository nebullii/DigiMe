from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from digime.agent.conversation import ConversationTurn, analyze_conversation, build_conversation_brief
from digime.agent.meeting import merge_meeting_requests, parse_meeting_request
from digime.agent.proxy_reply import ProxyDraftRequest, ProxyReplyAgent


@dataclass(frozen=True)
class ReplayCase:
    name: str
    platform: str
    turns: list[ConversationTurn]
    latest_message_id: str
    expected_intent: str
    expected_behavior: str
    notes: str = ""


@dataclass(frozen=True)
class ReplayCaseResult:
    case: ReplayCase
    actual_intent: str
    actual_behavior: str
    passed: bool
    model_latency_ms: float | None = None
    model_error: str | None = None


def load_replay_cases(path: str | Path) -> list[ReplayCase]:
    raw_cases = json.loads(Path(path).read_text())
    cases: list[ReplayCase] = []
    for raw_case in raw_cases:
        turns = [
            ConversationTurn(
                id=str(turn.get("id", index + 1)),
                author_id=str(turn.get("author_id", f"user-{index + 1}")),
                author_name=str(turn["author_name"]),
                content=str(turn["content"]),
                timestamp=str(turn.get("timestamp", f"2026-05-03T10:{index:02d}:00+00:00")),
                is_bot=bool(turn.get("is_bot", False)),
            )
            for index, turn in enumerate(raw_case["turns"])
        ]
        latest_message_id = str(raw_case.get("latest_message_id", turns[-1].id))
        cases.append(
            ReplayCase(
                name=str(raw_case["name"]),
                platform=str(raw_case.get("platform", "discord")),
                turns=turns,
                latest_message_id=latest_message_id,
                expected_intent=str(raw_case["expected_intent"]),
                expected_behavior=str(raw_case["expected_behavior"]),
                notes=str(raw_case.get("notes", "")),
            )
        )
    return cases


def run_replay_benchmark(
    cases: list[ReplayCase],
    *,
    timezone_name: str = "America/New_York",
    with_model: bool = False,
    agent: ProxyReplyAgent | None = None,
) -> list[ReplayCaseResult]:
    results: list[ReplayCaseResult] = []
    for case in cases:
        state = analyze_conversation(
            case.turns,
            latest_message_id=case.latest_message_id,
            bot_names={"DigiMe"},
        )
        actual_behavior = classify_behavior(case, state, timezone_name=timezone_name)
        passed = (
            state.intent == case.expected_intent and actual_behavior == case.expected_behavior
        )

        model_latency_ms: float | None = None
        model_error: str | None = None
        if with_model and actual_behavior == "draft_reply":
            if agent is None:
                raise ValueError("run_replay_benchmark(with_model=True) requires an agent.")
            started_at = time.perf_counter()
            try:
                agent.draft(
                    ProxyDraftRequest(
                        message=f"{state.latest_author_name}: {state.latest_text}",
                        platform=case.platform,
                        profile=case.platform,
                        additional_context=build_conversation_brief(state),
                    )
                )
            except Exception as error:  # pragma: no cover - exercised by CLI usage, not unit tests
                model_error = str(error)
            finally:
                model_latency_ms = (time.perf_counter() - started_at) * 1000

        results.append(
            ReplayCaseResult(
                case=case,
                actual_intent=state.intent,
                actual_behavior=actual_behavior,
                passed=passed,
                model_latency_ms=model_latency_ms,
                model_error=model_error,
            )
        )
    return results


def classify_behavior(case: ReplayCase, state: Any, *, timezone_name: str) -> str:
    if not state.needs_reply:
        return "skip"
    if state.intent in {"meeting_request", "meeting_follow_up"}:
        request = _resolve_replay_meeting_request(case, state, timezone_name=timezone_name)
        if request.platform != "google_meet":
            return "unsupported_meeting_platform"
        if not request.is_ready:
            return "meeting_clarify"
        return "meeting_create"
    if state.intent in {"weather_request", "greeting", "thanks"}:
        return "deterministic_reply"
    if state.should_auto_send:
        return "draft_reply"
    return "skip"


def _resolve_replay_meeting_request(case: ReplayCase, state: Any, *, timezone_name: str):
    latest_turn = next(turn for turn in case.turns if turn.id == case.latest_message_id)
    if state.intent == "meeting_follow_up":
        prior_text = "\n".join(
            turn.content for turn in case.turns if turn.id != case.latest_message_id and not turn.is_bot
        )
        base = parse_meeting_request(prior_text, timezone_name)
        update = parse_meeting_request(latest_turn.content, timezone_name)
        return merge_meeting_requests(base, update, timezone_name)
    meeting_text = "\n".join(turn.content for turn in state.relevant_turns if not turn.is_bot)
    return parse_meeting_request(meeting_text, timezone_name)
