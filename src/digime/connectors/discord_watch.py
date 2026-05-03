from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

import discord

from digime.agent.conversation import (
    ConversationState,
    analyze_conversation,
    build_conversation_brief,
    turns_from_records,
)
from digime.agent.meeting import parse_meeting_request
from digime.agent.proxy_reply import ProxyDraftRequest, ProxyReplyAgent
from digime.connectors.discord import DiscordMessage
from digime.connectors.google_calendar import GoogleCalendarConnector, GoogleCalendarError
from digime.llm.ollama import OllamaClient
from digime.memory.store import MessageStore


ApprovalFn = Callable[[str], str | None]


@dataclass(frozen=True)
class DiscordWatchConfig:
    token: str
    channel_ids: set[int]
    model: str
    ollama_base_url: str
    profile: str
    database_url: str
    context_limit: int = 25
    poll_seconds: int = 5
    auto_send: bool = True
    timezone: str = "America/New_York"
    google_calendar_id: str = "primary"
    google_oauth_client_file: str = "./config/google-oauth-client.json"
    google_oauth_token_file: str = "./config/google-token.json"


class DigiMeDiscordClient(discord.Client):
    def __init__(self, config: DiscordWatchConfig, approval_fn: ApprovalFn) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.config = config
        self.approval_fn = approval_fn
        self.store = MessageStore(config.database_url)
        self.agent = ProxyReplyAgent(
            OllamaClient(model=config.model, base_url=config.ollama_base_url)
        )
        self.calendar = GoogleCalendarConnector(
            credentials_path=config.google_oauth_client_file,
            token_path=config.google_oauth_token_file,
            calendar_id=config.google_calendar_id,
        )
        self.latest_seen_ids: dict[int, int] = {}

    async def on_ready(self) -> None:
        self.store.initialize()
        for channel_id in self.config.channel_ids:
            latest_stored = self.store.latest_discord_message_id(str(channel_id))
            self.latest_seen_ids[channel_id] = int(latest_stored) if latest_stored else 0
        watched = ", ".join(str(channel_id) for channel_id in sorted(self.config.channel_ids))
        print(f"DigiMe Discord watcher online as {self.user}. Watching: {watched}")
        self.loop.create_task(self._poll_channels())

    async def on_message(self, message: discord.Message) -> None:
        await self._process_message(message)

    async def _poll_channels(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            for channel_id in self.config.channel_ids:
                try:
                    await self._poll_channel(channel_id)
                except Exception as error:
                    print(f"Discord poll error for {channel_id}: {error}")
            await asyncio.sleep(self.config.poll_seconds)

    async def _poll_channel(self, channel_id: int) -> None:
        channel = self.get_channel(channel_id)
        if channel is None:
            channel = await self.fetch_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            return

        latest_seen_id = self.latest_seen_ids.get(channel_id, 0)
        after = discord.Object(id=latest_seen_id) if latest_seen_id else None
        messages = [message async for message in channel.history(limit=10, after=after)]
        for message in sorted(messages, key=lambda item: item.id):
            await self._process_message(message)

    async def _process_message(self, message: discord.Message) -> None:
        if message.channel.id not in self.config.channel_ids:
            return
        stored_message = self._discord_message_from_gateway(message)
        if stored_message.content.strip():
            self.store.upsert_discord_message(stored_message)

        if message.author.bot:
            return
        if not message.content.strip():
            return
        latest_seen_id = self.latest_seen_ids.get(message.channel.id, 0)
        if message.id <= latest_seen_id:
            return
        self.latest_seen_ids[message.channel.id] = message.id
        if self.store.has_handled_message("discord", str(message.id), "reply"):
            return

        state = self._conversation_state(message)
        if not state.needs_reply:
            self.store.mark_message_handled("discord", str(message.id), "skip")
            print(
                f"\nSkipping message from {message.author.display_name}: "
                f"{state.reason}\n{message.content}\n"
            )
            return

        meeting_reply = await asyncio.to_thread(self._handle_meeting_request, state)
        if meeting_reply is not None:
            handled = await self._send_proposed_reply(
                message=message,
                proposed_reply=meeting_reply,
                reason="meeting action",
            )
            if handled:
                self.store.mark_message_handled("discord", str(message.id), "reply")
            return

        action_reply = self._handle_deterministic_reply(state)
        if action_reply is not None:
            handled = await self._send_proposed_reply(
                message=message,
                proposed_reply=action_reply,
                reason=f"{state.intent} action",
            )
            if handled:
                self.store.mark_message_handled("discord", str(message.id), "reply")
            return

        package = await asyncio.to_thread(
            self.agent.draft,
            ProxyDraftRequest(
                message=f"{message.author.display_name}: {message.content}",
                platform="discord",
                profile=self.config.profile,
                additional_context=build_conversation_brief(state),
            ),
        )

        formatted_package = _format_package(
            author=message.author.display_name,
            content=message.content,
            analysis=build_conversation_brief(state),
            summary=package.summary,
            drafts=[draft.text for draft in package.drafts],
        )
        print(formatted_package)

        if self.config.auto_send and state.should_auto_send and not package.risk_checks.sensitive:
            reply = _select_auto_reply(package.drafts)
            print(f"Auto-sending:\n{reply}\n")
            await self._send_and_store(message.channel, reply)
            self.store.mark_message_handled("discord", str(message.id), "reply")
            return
        if self.config.auto_send:
            self.store.mark_message_handled("discord", str(message.id), "skip")
            print(
                "Auto-send skipped because the conversation state or model risk checks "
                f"were not strong enough.\nReason: {state.reason}\n"
            )
            return

        approved_reply = await asyncio.to_thread(self.approval_fn, formatted_package)
        if approved_reply:
            await self._send_and_store(message.channel, approved_reply)
            self.store.mark_message_handled("discord", str(message.id), "reply")

    def _handle_meeting_request(self, state: ConversationState) -> str | None:
        if state.intent not in {"meeting_request", "meeting_follow_up"}:
            return None

        meeting_context = "\n".join(turn.content for turn in state.relevant_turns)
        request = parse_meeting_request(meeting_context, self.config.timezone)
        if request.title == "DigiMe meeting":
            request = type(request)(
                platform=request.platform,
                start=request.start,
                duration_minutes=request.duration_minutes,
                title=f"Discord sync with {state.latest_author_name}",
                attendees=request.attendees,
                description=meeting_context,
                missing_fields=request.missing_fields,
            )
        if request.platform != "google_meet":
            return (
                "I saw the meeting request, but Zoom/other meeting creation is not wired yet. "
                "Google Meet is the default once Google Calendar OAuth is configured."
            )
        if not request.is_ready:
            missing = ", ".join(request.missing_fields)
            return f"I can set up a Google Meet, but I need the missing detail first: {missing}."
        if not self.calendar.is_configured():
            return (
                "I can create the Google Meet, but Google Calendar OAuth is not configured in "
                "this runtime yet. Add `config/google-oauth-client.json` and run "
                "`digime google auth`, then ask me again. Calendar setup: the one thing even "
                "bots cannot just import with vibes."
            )

        try:
            meeting = self.calendar.create_google_meet(request)
        except GoogleCalendarError as error:
            return f"I could not create the Google Meet yet: {error}"

        return (
            f"Google Meet is set for {meeting.start_iso}: {meeting.meeting_url} "
            f"(calendar event: {meeting.event_url})"
        )

    def _conversation_state(self, message: discord.Message) -> ConversationState:
        records = self.store.recent_discord_messages(
            str(message.channel.id),
            limit=self.config.context_limit,
            upto_message_id=str(message.id),
        )
        turns = list(reversed(turns_from_records(records)))
        bot_names = {
            self.user.display_name if self.user else "",
            self.user.name if self.user else "",
            "DigiMe",
        }
        return analyze_conversation(
            turns,
            latest_message_id=str(message.id),
            bot_user_id=str(self.user.id) if self.user else None,
            bot_names=bot_names,
        )

    def _handle_deterministic_reply(self, state: ConversationState) -> str | None:
        if state.intent == "weather_request":
            return (
                "I cannot check live weather from this local runtime yet. "
                "If you want, ask me again after wiring a weather data source."
            )
        if state.intent == "greeting":
            return f"Hey {state.latest_author_name}, I am here. What do you need?"
        if state.intent == "thanks":
            return "Any time."
        if state.intent in {"acknowledgement", "statement"}:
            return None
        if state.confidence == "low":
            return None
        return None

    async def _send_and_store(
        self,
        channel: discord.abc.Messageable,
        content: str,
    ) -> None:
        sent_message = await channel.send(content)
        self.store.upsert_discord_message(self._discord_message_from_gateway(sent_message))

    async def _send_proposed_reply(
        self,
        message: discord.Message,
        proposed_reply: str,
        reason: str,
    ) -> bool:
        print(
            f"\nProposed {reason} for {message.author.display_name}:\n"
            f"{message.content}\n\n{proposed_reply}\n"
        )
        if self.config.auto_send:
            await self._send_and_store(message.channel, proposed_reply)
            return True

        approved_reply = await asyncio.to_thread(
            self.approval_fn,
            (
                f"\nNew Discord message from {message.author.display_name}:\n{message.content}\n\n"
                f"Proposed action reply:\n{proposed_reply}\n"
            ),
        )
        if approved_reply:
            await self._send_and_store(message.channel, approved_reply)
            return True
        return False

    def _discord_message_from_gateway(self, message: discord.Message) -> DiscordMessage:
        return DiscordMessage(
            id=str(message.id),
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            author_name=message.author.display_name,
            content=message.content,
            timestamp=message.created_at.isoformat(),
            is_bot=bool(message.author.bot),
            raw={
                "id": str(message.id),
                "channel_id": str(message.channel.id),
                "author": {
                    "id": str(message.author.id),
                    "username": message.author.name,
                    "global_name": message.author.global_name,
                    "bot": bool(message.author.bot),
                },
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
            },
        )


def run_discord_watcher(config: DiscordWatchConfig, approval_fn: ApprovalFn) -> None:
    client = DigiMeDiscordClient(config=config, approval_fn=approval_fn)
    client.run(config.token)


def _format_package(
    author: str,
    content: str,
    analysis: str,
    summary: str,
    drafts: list[str],
) -> str:
    draft_lines = "\n".join(f"{index}. {draft}" for index, draft in enumerate(drafts, start=1))
    return (
        f"\nNew Discord message from {author}:\n{content}\n\n"
        f"{analysis}\n\n"
        f"Summary:\n{summary}\n\n"
        f"Drafts:\n{draft_lines}\n"
    )


def _select_auto_reply(drafts: list[object]) -> str:
    for draft in drafts:
        if getattr(draft, "label", "") == "natural":
            return str(getattr(draft, "text"))
    if drafts:
        return str(getattr(drafts[0], "text"))
    return "Got it."
