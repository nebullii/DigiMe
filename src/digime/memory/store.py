from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def sqlite_path_from_url(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///"))
    if database_url.startswith("sqlite://"):
        return Path(database_url.removeprefix("sqlite://"))
    raise ValueError("Only sqlite database URLs are supported for the MVP.")


class MessageStore:
    """Persists raw messages, Slack DMs, reply examples, drafts, approvals, and edits."""

    def __init__(self, database_url: str) -> None:
        self.path = sqlite_path_from_url(database_url)
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                create table if not exists slack_conversations (
                    id text primary key,
                    user_id text,
                    is_im integer not null,
                    raw_json text not null,
                    synced_at text default current_timestamp
                );

                create table if not exists slack_messages (
                    id text primary key,
                    conversation_id text not null,
                    user_id text,
                    text text not null,
                    ts text not null,
                    raw_json text not null,
                    synced_at text default current_timestamp
                );

                create table if not exists reply_examples (
                    id integer primary key autoincrement,
                    platform text not null,
                    conversation_id text not null,
                    incoming_context text not null,
                    your_reply text not null,
                    sent_at text not null,
                    source_message_id text not null unique,
                    created_at text default current_timestamp
                );

                create table if not exists discord_messages (
                    id text primary key,
                    channel_id text not null,
                    author_id text not null,
                    author_name text not null,
                    content text not null,
                    timestamp text not null,
                    raw_json text not null,
                    synced_at text default current_timestamp
                );
                """
            )

    def upsert_slack_conversation(self, conversation: Any) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                insert into slack_conversations (id, user_id, is_im, raw_json, synced_at)
                values (?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    user_id = excluded.user_id,
                    is_im = excluded.is_im,
                    raw_json = excluded.raw_json,
                    synced_at = current_timestamp
                """,
                (
                    conversation.id,
                    conversation.user_id,
                    int(conversation.is_im),
                    json.dumps(conversation.raw),
                ),
            )

    def upsert_slack_message(self, conversation_id: str, message: dict[str, Any]) -> bool:
        message_id = f"{conversation_id}:{message['ts']}"
        user_id = message.get("user") or message.get("bot_id")
        text = message.get("text") or ""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                insert into slack_messages (id, conversation_id, user_id, text, ts, raw_json, synced_at)
                values (?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    user_id = excluded.user_id,
                    text = excluded.text,
                    raw_json = excluded.raw_json,
                    synced_at = current_timestamp
                """,
                (message_id, conversation_id, user_id, text, message["ts"], json.dumps(message)),
            )
            return cursor.rowcount > 0

    def build_slack_reply_examples(
        self,
        your_user_id: str,
        context_window: int = 3,
    ) -> int:
        inserted = 0
        with self.connect() as connection:
            conversations = connection.execute("select id from slack_conversations").fetchall()
            for conversation in conversations:
                rows = connection.execute(
                    """
                    select id, conversation_id, user_id, text, ts
                    from slack_messages
                    where conversation_id = ?
                      and text != ''
                    order by cast(ts as real) asc
                    """,
                    (conversation["id"],),
                ).fetchall()

                for index, row in enumerate(rows):
                    if row["user_id"] != your_user_id:
                        continue

                    context_rows = [
                        previous
                        for previous in rows[max(0, index - context_window) : index]
                        if previous["user_id"] != your_user_id and previous["text"].strip()
                    ]
                    if not context_rows or not row["text"].strip():
                        continue

                    connection.execute(
                        """
                        insert or ignore into reply_examples (
                            platform,
                            conversation_id,
                            incoming_context,
                            your_reply,
                            sent_at,
                            source_message_id
                        )
                        values (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "slack",
                            row["conversation_id"],
                            json.dumps([context["text"] for context in context_rows]),
                            row["text"],
                            row["ts"],
                            row["id"],
                        ),
                    )
                    if connection.execute("select changes()").fetchone()[0] == 1:
                        inserted += 1
        return inserted

    def latest_discord_message_id(self, channel_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                select id
                from discord_messages
                where channel_id = ?
                order by cast(id as integer) desc
                limit 1
                """,
                (channel_id,),
            ).fetchone()
        return str(row["id"]) if row else None

    def upsert_discord_message(self, message: Any) -> bool:
        with self.connect() as connection:
            connection.execute(
                """
                insert into discord_messages (
                    id,
                    channel_id,
                    author_id,
                    author_name,
                    content,
                    timestamp,
                    raw_json,
                    synced_at
                )
                values (?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    channel_id = excluded.channel_id,
                    author_id = excluded.author_id,
                    author_name = excluded.author_name,
                    content = excluded.content,
                    timestamp = excluded.timestamp,
                    raw_json = excluded.raw_json,
                    synced_at = current_timestamp
                """,
                (
                    message.id,
                    message.channel_id,
                    message.author_id,
                    message.author_name,
                    message.content,
                    message.timestamp,
                    json.dumps(message.raw),
                ),
            )
            return connection.execute("select changes()").fetchone()[0] == 1

    def recent_discord_context(self, channel_id: str, limit: int = 25) -> str:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select author_name, content, timestamp
                from discord_messages
                where channel_id = ?
                  and content != ''
                order by cast(id as integer) desc
                limit ?
                """,
                (channel_id, limit),
            ).fetchall()

        ordered_rows = list(reversed(rows))
        return "\n".join(
            f"{row['author_name']} [{row['timestamp']}]: {row['content']}"
            for row in ordered_rows
        )

    def counts(self) -> dict[str, int]:
        tables = ["slack_conversations", "slack_messages", "discord_messages", "reply_examples"]
        with self.connect() as connection:
            return {
                table: int(connection.execute(f"select count(*) from {table}").fetchone()[0])
                for table in tables
            }
