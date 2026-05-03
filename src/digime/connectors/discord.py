from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscordMessage:
    id: str
    channel_id: str
    author_id: str
    author_name: str
    content: str
    timestamp: str
    raw: dict[str, Any]


class DiscordConnector:
    """Reads and writes Discord channel messages using a bot token."""

    def __init__(self, token: str, base_url: str = DISCORD_API_BASE) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    def get_channel_messages(
        self,
        channel_id: str,
        limit: int = 25,
        after: str | None = None,
    ) -> list[DiscordMessage]:
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after

        data = self._request("GET", f"/channels/{channel_id}/messages", params=params)
        messages = [self._parse_message(channel_id, item) for item in data]
        return sorted(messages, key=lambda message: int(message.id))

    def create_message(self, channel_id: str, content: str) -> dict[str, Any]:
        return self._request("POST", f"/channels/{channel_id}/messages", json={"content": content})

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"Authorization": f"Bot {self.token}"}
        try:
            with httpx.Client(timeout=30) as client:
                response = client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    **kwargs,
                )
        except httpx.HTTPError as error:
            raise DiscordApiError(f"Could not reach Discord API: {error}") from error

        if response.status_code >= 400:
            raise DiscordApiError(
                f"Discord API error {response.status_code}: {response.text[:300]}"
            )
        return response.json()

    def _parse_message(self, channel_id: str, item: dict[str, Any]) -> DiscordMessage:
        author = item.get("author") or {}
        return DiscordMessage(
            id=item["id"],
            channel_id=item.get("channel_id") or channel_id,
            author_id=author.get("id", ""),
            author_name=author.get("global_name") or author.get("username") or "unknown",
            content=item.get("content") or "",
            timestamp=item.get("timestamp", ""),
            raw=item,
        )
