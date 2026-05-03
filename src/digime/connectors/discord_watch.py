from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

import discord

from digime.agent.proxy_reply import ProxyDraftRequest, ProxyReplyAgent
from digime.connectors.discord import DiscordMessage
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
        if message.author.bot:
            return
        if message.channel.id not in self.config.channel_ids:
            return
        latest_seen_id = self.latest_seen_ids.get(message.channel.id, 0)
        if message.id <= latest_seen_id:
            return
        self.latest_seen_ids[message.channel.id] = message.id

        self.store.upsert_discord_message(
            DiscordMessage(
                id=str(message.id),
                channel_id=str(message.channel.id),
                author_id=str(message.author.id),
                author_name=message.author.display_name,
                content=message.content,
                timestamp=message.created_at.isoformat(),
                raw={
                    "id": str(message.id),
                    "channel_id": str(message.channel.id),
                    "author": {
                        "id": str(message.author.id),
                        "username": message.author.name,
                        "global_name": message.author.global_name,
                    },
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                },
            )
        )

        context = self.store.recent_discord_context(
            str(message.channel.id),
            limit=self.config.context_limit,
        )
        package = await asyncio.to_thread(
            self.agent.draft,
            ProxyDraftRequest(
                message=context,
                platform="discord",
                profile=self.config.profile,
            ),
        )

        formatted_package = _format_package_for_approval(
            author=message.author.display_name,
            content=message.content,
            summary=package.summary,
            drafts=[draft.text for draft in package.drafts],
        )
        approved_reply = await asyncio.to_thread(self.approval_fn, formatted_package)
        if approved_reply:
            await message.channel.send(approved_reply)


def run_discord_watcher(config: DiscordWatchConfig, approval_fn: ApprovalFn) -> None:
    client = DigiMeDiscordClient(config=config, approval_fn=approval_fn)
    client.run(config.token)


def _format_package_for_approval(
    author: str,
    content: str,
    summary: str,
    drafts: list[str],
) -> str:
    draft_lines = "\n".join(f"{index}. {draft}" for index, draft in enumerate(drafts, start=1))
    return (
        f"\nNew Discord message from {author}:\n{content}\n\n"
        f"Summary:\n{summary}\n\n"
        f"Drafts:\n{draft_lines}\n"
    )
