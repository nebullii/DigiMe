from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


SLACK_API_BASE = "https://slack.com/api"


class SlackApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class SlackConversation:
    id: str
    user_id: str | None
    is_im: bool
    raw: dict[str, Any]


class SlackConnector:
    """Fetches Slack direct messages through the Slack Web API."""

    def __init__(self, token: str, base_url: str = SLACK_API_BASE) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    def auth_test(self) -> dict[str, Any]:
        return self._post("auth.test")

    def list_direct_messages(self, limit: int = 200) -> list[SlackConversation]:
        conversations: list[SlackConversation] = []
        cursor: str | None = None

        while True:
            payload: dict[str, Any] = {
                "types": "im",
                "exclude_archived": True,
                "limit": limit,
            }
            if cursor:
                payload["cursor"] = cursor

            response = self._post("conversations.list", payload)
            for channel in response.get("channels", []):
                conversations.append(
                    SlackConversation(
                        id=channel["id"],
                        user_id=channel.get("user"),
                        is_im=bool(channel.get("is_im")),
                        raw=channel,
                    )
                )

            cursor = response.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                return conversations

    def conversation_history(
        self,
        conversation_id: str,
        limit: int = 200,
        oldest: str | None = None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            payload: dict[str, Any] = {
                "channel": conversation_id,
                "limit": limit,
            }
            if cursor:
                payload["cursor"] = cursor
            if oldest:
                payload["oldest"] = oldest

            response = self._post("conversations.history", payload)
            messages.extend(response.get("messages", []))

            cursor = response.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                return messages

    def _post(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{self.base_url}/{method}", headers=headers, json=payload or {})
            response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            raise SlackApiError(f"Slack API error for {method}: {data.get('error', 'unknown_error')}")
        return data
