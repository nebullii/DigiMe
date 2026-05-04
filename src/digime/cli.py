import typer

from digime.agent.conversation import (
    ConversationState,
    analyze_conversation,
    build_conversation_brief,
    turns_from_records,
)
from digime.benchmark.replay import load_replay_cases, run_replay_benchmark
from digime.connectors.calendar_registry import CalendarProviderConfig, build_calendar_provider
from digime.agent.proxy_reply import ProxyDraftRequest, ProxyReplyAgent
from digime.connectors.discord import DiscordApiError, DiscordConnector
from digime.connectors.discord_watch import DiscordWatchConfig, run_discord_watcher
from digime.connectors.google_calendar import GoogleCalendarError
from digime.connectors.slack import SlackApiError, SlackConnector
from digime.config import settings
from digime.llm.ollama import OllamaClient, OllamaError
from digime.memory.store import MessageStore

app = typer.Typer(help="DigiMe local personal reply agent.")
slack_app = typer.Typer(help="Slack DM ingestion commands.")
discord_app = typer.Typer(help="Discord bot-token polling commands.")
google_app = typer.Typer(help="Google Calendar / Meet commands.")
benchmark_app = typer.Typer(help="Replay benchmark commands.")
app.add_typer(slack_app, name="slack")
app.add_typer(discord_app, name="discord")
app.add_typer(google_app, name="google")
app.add_typer(benchmark_app, name="benchmark")


@app.command()
def doctor() -> None:
    """Print the active local configuration."""
    typer.echo(f"env: {settings.env}")
    typer.echo(f"draft_only: {settings.draft_only}")
    typer.echo(f"llm_provider: {settings.llm_provider}")
    typer.echo(f"llm_model: {settings.llm_model}")
    typer.echo(f"llm_base_url: {settings.llm_base_url}")
    typer.echo(f"database_url: {settings.database_url}")
    typer.echo(f"slack_token_configured: {bool(settings.slack_token)}")
    typer.echo(f"slack_your_user_id: {settings.slack_your_user_id or ''}")
    typer.echo(f"discord_token_configured: {bool(settings.discord_bot_token)}")
    typer.echo(f"discord_default_channel_id: {settings.discord_default_channel_id or ''}")
    typer.echo(f"discord_channel_ids: {','.join(settings.discord_channel_ids)}")
    typer.echo(f"calendar_provider: {settings.calendar_provider}")
    typer.echo(f"google_calendar_id: {settings.google_calendar_id}")
    typer.echo(f"google_oauth_client_file: {settings.google_oauth_client_file}")
    typer.echo(f"google_oauth_token_file: {settings.google_oauth_token_file}")
    typer.echo(f"timezone: {settings.timezone}")


@app.command()
def draft(message: str, platform: str = "slack", profile: str = "work_slack") -> None:
    """Placeholder command for drafting a reply."""
    typer.echo("Drafting is not implemented yet.")
    typer.echo(f"platform: {platform}")
    typer.echo(f"profile: {profile}")
    typer.echo(f"message: {message}")


@app.command("proxy-draft")
def proxy_draft(
    message: str = typer.Argument(..., help="Copied message/context to draft a reply for."),
    platform: str = typer.Option("unknown", help="Source app, such as slack, gmail, teams."),
    profile: str = typer.Option("default", help="Style profile name."),
    model: str | None = typer.Option(None, help="Override local Ollama model."),
) -> None:
    """Draft an approval-ready reply package with a local Ollama model."""
    agent = ProxyReplyAgent(_ollama(model))
    try:
        package = agent.draft(
            ProxyDraftRequest(
                message=message,
                platform=platform,
                profile=profile,
            )
        )
    except (OllamaError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    _print_proxy_package(package)


@slack_app.command("auth-check")
def slack_auth_check() -> None:
    """Verify that the configured Slack token works."""
    connector = _slack_connector()
    data = connector.auth_test()
    typer.echo(f"ok: {data.get('ok')}")
    typer.echo(f"user_id: {data.get('user_id')}")
    typer.echo(f"team: {data.get('team')}")


@slack_app.command("init-db")
def slack_init_db() -> None:
    """Initialize the local SQLite database tables."""
    store = _store()
    store.initialize()
    typer.echo(f"initialized: {store.path}")


@slack_app.command("sync-dms")
def slack_sync_dms(
    max_conversations: int | None = typer.Option(
        None,
        help="Optional cap for testing with a small number of DMs.",
    ),
    history_limit: int = typer.Option(200, help="Slack page size for history fetches."),
    oldest: str | None = typer.Option(
        None,
        help="Optional Slack timestamp. Only fetch messages after this ts.",
    ),
) -> None:
    """Fetch 1:1 Slack DMs and store them locally."""
    connector = _slack_connector()
    store = _store()
    store.initialize()

    conversations = connector.list_direct_messages()
    if max_conversations is not None:
        conversations = conversations[:max_conversations]

    message_count = 0
    for conversation in conversations:
        store.upsert_slack_conversation(conversation)
        messages = connector.conversation_history(
            conversation.id,
            limit=history_limit,
            oldest=oldest,
        )
        for message in messages:
            if message.get("type") == "message" and "ts" in message:
                store.upsert_slack_message(conversation.id, message)
                message_count += 1

    typer.echo(f"synced_conversations: {len(conversations)}")
    typer.echo(f"synced_messages: {message_count}")


@slack_app.command("build-examples")
def slack_build_examples(
    your_user_id: str | None = typer.Option(
        None,
        help="Your Slack user ID. Defaults to SLACK_YOUR_USER_ID or auth.test user_id.",
    ),
    context_window: int = typer.Option(3, help="Number of prior messages to consider."),
) -> None:
    """Build reply examples from stored Slack DMs."""
    store = _store()
    store.initialize()

    resolved_user_id = your_user_id or settings.slack_your_user_id
    if not resolved_user_id:
        resolved_user_id = _slack_connector().auth_test().get("user_id")
    if not resolved_user_id:
        raise typer.BadParameter("Could not resolve your Slack user ID.")

    inserted = store.build_slack_reply_examples(
        your_user_id=resolved_user_id,
        context_window=context_window,
    )
    typer.echo(f"your_user_id: {resolved_user_id}")
    typer.echo(f"inserted_reply_examples: {inserted}")


@slack_app.command("stats")
def slack_stats() -> None:
    """Show local Slack ingestion counts."""
    store = _store()
    store.initialize()
    for name, count in store.counts().items():
        typer.echo(f"{name}: {count}")


@discord_app.command("sync")
def discord_sync(
    channel_id: str | None = typer.Option(
        None,
        help="Discord channel ID. Defaults to DISCORD_DEFAULT_CHANNEL_ID.",
    ),
    limit: int = typer.Option(25, min=1, max=100, help="Messages to fetch from Discord."),
    only_new: bool = typer.Option(True, help="Fetch only messages after the last stored message."),
) -> None:
    """Poll recent Discord channel messages into the local store."""
    resolved_channel_id = _discord_channel_id(channel_id)
    store = _store()
    store.initialize()
    after = store.latest_discord_message_id(resolved_channel_id) if only_new else None
    messages = _discord_connector().get_channel_messages(
        resolved_channel_id,
        limit=limit,
        after=after,
    )

    inserted = 0
    for message in messages:
        if store.upsert_discord_message(message):
            inserted += 1

    typer.echo(f"channel_id: {resolved_channel_id}")
    typer.echo(f"fetched_messages: {len(messages)}")
    typer.echo(f"inserted_messages: {inserted}")


@discord_app.command("summarize")
def discord_summarize(
    channel_id: str | None = typer.Option(
        None,
        help="Discord channel ID. Defaults to DISCORD_DEFAULT_CHANNEL_ID.",
    ),
    limit: int = typer.Option(25, help="Stored messages to include."),
    model: str | None = typer.Option(None, help="Override local Ollama model."),
) -> None:
    """Summarize recent stored Discord channel messages with local Ollama."""
    state = _discord_state(channel_id, limit)
    prompt = (
        "Summarize this Discord channel context for the human. "
        "Mention key topics, decisions, direct asks, and whether a reply seems needed.\n\n"
        f"{build_conversation_brief(state)}"
    )
    typer.echo(_ollama(model).generate(prompt))


@discord_app.command("draft-needed")
def discord_draft_needed(
    channel_id: str | None = typer.Option(
        None,
        help="Discord channel ID. Defaults to DISCORD_DEFAULT_CHANNEL_ID.",
    ),
    limit: int = typer.Option(25, help="Stored messages to include."),
    profile: str = typer.Option("discord", help="Style profile name."),
    model: str | None = typer.Option(None, help="Override local Ollama model."),
) -> None:
    """Draft a reply package for recent stored Discord context."""
    resolved_channel_id = _discord_channel_id(channel_id)
    state = _discord_state(resolved_channel_id, limit)
    retrieved_examples = _store().find_similar_reply_examples(
        platform="discord",
        conversation_id=resolved_channel_id,
        query_text="\n".join(turn.content for turn in state.relevant_turns),
        limit=3,
    )
    agent = ProxyReplyAgent(_ollama(model))
    package = agent.draft(
        ProxyDraftRequest(
            message=f"{state.latest_author_name}: {state.latest_text}",
            platform="discord",
            profile=profile,
            additional_context=build_conversation_brief(state),
            retrieved_examples=_format_retrieved_examples(retrieved_examples),
        )
    )
    _print_proxy_package(package)


@discord_app.command("logs")
def discord_logs(
    channel_id: str | None = typer.Option(
        None,
        help="Discord channel ID. Defaults to DISCORD_DEFAULT_CHANNEL_ID.",
    ),
    limit: int = typer.Option(20, help="Messages to show."),
) -> None:
    """Show recent locally stored Discord messages."""
    resolved_channel_id = _discord_channel_id(channel_id)
    store = _store()
    store.initialize()
    for message in store.recent_discord_messages(resolved_channel_id, limit=limit):
        content = message["content"] or "[empty]"
        typer.echo(
            f"{message['timestamp']} | {message['author_name']} | {message['id']} | {content}"
        )


@discord_app.command("send-approved")
def discord_send_approved(
    content: str = typer.Argument(..., help="Approved message content to send."),
    channel_id: str | None = typer.Option(
        None,
        help="Discord channel ID. Defaults to DISCORD_DEFAULT_CHANNEL_ID.",
    ),
    yes: bool = typer.Option(False, "--yes", help="Required explicit approval flag."),
) -> None:
    """Send an already-approved Discord message."""
    if not yes:
        raise typer.BadParameter("Refusing to send without --yes.")

    resolved_channel_id = _discord_channel_id(channel_id)
    result = _discord_connector().create_message(resolved_channel_id, content)
    typer.echo(f"sent_message_id: {result.get('id')}")


@discord_app.command("watch")
def discord_watch(
    channel_id: list[str] | None = typer.Option(
        None,
        "--channel-id",
        help="Discord channel ID. Repeat the option for multiple channels. Defaults to DISCORD_CHANNEL_IDS or DISCORD_DEFAULT_CHANNEL_ID.",
    ),
    model: str | None = typer.Option(None, help="Override local Ollama model."),
    profile: str = typer.Option("discord", help="Style profile name."),
    context_limit: int = typer.Option(25, help="Stored messages to include in each draft."),
    poll_seconds: int = typer.Option(5, help="Polling fallback interval in seconds."),
    approval: bool = typer.Option(
        False,
        "--approval",
        help="Require terminal approval before sending. Default is autonomous auto-send.",
    ),
) -> None:
    """Run a live Discord watcher that drafts and sends replies."""
    resolved_channel_ids = _discord_channel_ids(channel_id)
    if not settings.discord_bot_token:
        raise typer.BadParameter("Set DISCORD_BOT_TOKEN in .env.")

    config = DiscordWatchConfig(
        token=settings.discord_bot_token,
        channel_ids={int(item) for item in resolved_channel_ids},
        model=model or settings.llm_model,
        ollama_base_url=settings.llm_base_url,
        profile=profile,
        database_url=settings.database_url,
        context_limit=context_limit,
        poll_seconds=poll_seconds,
        auto_send=not approval,
        timezone=settings.timezone,
        calendar_provider=settings.calendar_provider,
        google_calendar_id=settings.google_calendar_id,
        google_oauth_client_file=settings.google_oauth_client_file,
        google_oauth_token_file=settings.google_oauth_token_file,
    )
    run_discord_watcher(config=config, approval_fn=_terminal_approval)


@google_app.command("status")
def google_status() -> None:
    """Show whether Google Calendar OAuth files are configured."""
    connector = _google_calendar_connector()
    typer.echo(f"provider: {settings.calendar_provider}")
    typer.echo(f"calendar_id: {settings.google_calendar_id}")
    typer.echo(f"oauth_client_file_exists: {connector.credentials_path.exists()}")
    typer.echo(f"oauth_token_file_exists: {connector.token_path.exists()}")


@google_app.command("auth")
def google_auth() -> None:
    """Run Google OAuth by creating a tiny test client and building credentials."""
    if settings.calendar_provider != "google":
        raise typer.BadParameter(
            f"Google auth is only valid when DIGIME_CALENDAR_PROVIDER=google, got {settings.calendar_provider!r}."
        )
    connector = _google_calendar_connector()
    if not connector.credentials_path.exists():
        raise typer.BadParameter(
            f"Google OAuth client file not found: {connector.credentials_path}"
        )
    try:
        connector._service()
    except GoogleCalendarError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"authorized: {connector.token_path}")


@benchmark_app.command("replay")
def benchmark_replay(
    cases_path: str = typer.Argument(
        "benchmarks/replay_cases.json",
        help="Path to the replay benchmark JSON file.",
    ),
    with_model: bool = typer.Option(
        False,
        "--with-model",
        help="Also run local model drafting on draft-reply cases and report latency.",
    ),
    model: str | None = typer.Option(None, help="Override local Ollama model for --with-model."),
) -> None:
    """Run the replay benchmark against DigiMe's current routing behavior."""
    cases = load_replay_cases(cases_path)
    agent = ProxyReplyAgent(_ollama(model)) if with_model else None
    results = run_replay_benchmark(
        cases,
        timezone_name=settings.timezone,
        with_model=with_model,
        agent=agent,
    )

    passed = 0
    model_runs = 0
    model_failures = 0
    total_model_latency_ms = 0.0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        typer.echo(
            f"[{status}] {result.case.name} "
            f"(intent: {result.actual_intent}, behavior: {result.actual_behavior})"
        )
        if not result.passed:
            typer.echo(
                f"  expected intent={result.case.expected_intent}, "
                f"behavior={result.case.expected_behavior}"
            )
        if result.model_latency_ms is not None:
            model_runs += 1
            total_model_latency_ms += result.model_latency_ms
            if result.model_error:
                model_failures += 1
                typer.echo(f"  model error: {result.model_error}")
            else:
                typer.echo(f"  model latency: {result.model_latency_ms:.1f} ms")
        if result.passed:
            passed += 1

    typer.echo("")
    typer.echo(f"cases: {len(results)}")
    typer.echo(f"passed: {passed}")
    typer.echo(f"failed: {len(results) - passed}")
    if model_runs:
        typer.echo(f"model_runs: {model_runs}")
        typer.echo(f"model_failures: {model_failures}")
        typer.echo(f"avg_model_latency_ms: {total_model_latency_ms / model_runs:.1f}")
    if passed != len(results):
        raise typer.Exit(code=1)


def _store() -> MessageStore:
    return MessageStore(settings.database_url)


def _slack_connector() -> SlackConnector:
    if not settings.slack_token:
        raise typer.BadParameter("Set SLACK_USER_TOKEN or SLACK_BOT_TOKEN in .env.")
    try:
        return SlackConnector(settings.slack_token)
    except SlackApiError as error:
        raise typer.BadParameter(str(error)) from error


def _discord_connector() -> DiscordConnector:
    if not settings.discord_bot_token:
        raise typer.BadParameter("Set DISCORD_BOT_TOKEN in .env.")
    try:
        return DiscordConnector(settings.discord_bot_token)
    except DiscordApiError as error:
        raise typer.BadParameter(str(error)) from error


def _discord_channel_id(channel_id: str | None) -> str:
    resolved_channel_id = channel_id or settings.discord_default_channel_id
    if not resolved_channel_id:
        raise typer.BadParameter("Pass --channel-id or set DISCORD_DEFAULT_CHANNEL_ID in .env.")
    return resolved_channel_id


def _discord_channel_ids(channel_ids: list[str] | None) -> list[str]:
    if channel_ids:
        resolved_channel_ids = [item for item in channel_ids if item]
    else:
        resolved_channel_ids = settings.discord_channel_ids
    if not resolved_channel_ids:
        raise typer.BadParameter(
            "Pass one or more --channel-id values or set DISCORD_CHANNEL_IDS / DISCORD_DEFAULT_CHANNEL_ID in .env."
        )
    return resolved_channel_ids


def _discord_state(channel_id: str | None, limit: int) -> ConversationState:
    resolved_channel_id = _discord_channel_id(channel_id)
    store = _store()
    store.initialize()
    messages = store.recent_discord_messages(resolved_channel_id, limit=limit)
    if not messages:
        raise typer.BadParameter("No stored Discord messages found. Run digime discord sync first.")
    turns = list(reversed(turns_from_records(messages)))
    latest_human = next((turn for turn in reversed(turns) if not turn.is_bot), None)
    if latest_human is None:
        raise typer.BadParameter("No human Discord messages found in the stored context.")
    return analyze_conversation(turns, latest_message_id=latest_human.id, bot_names={"DigiMe"})


def _format_retrieved_examples(matches: list[object]) -> str | None:
    if not matches:
        return None
    lines: list[str] = []
    for index, match in enumerate(matches, start=1):
        lines.append(f"Example {index}:")
        lines.append(f"Incoming context: {match.incoming_context}")
        lines.append(f"Approved reply: {match.your_reply}")
    return "\n".join(lines)


def _ollama(model: str | None) -> OllamaClient:
    return OllamaClient(
        model=model or settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _google_calendar_connector():
    provider = build_calendar_provider(
        CalendarProviderConfig(
            provider="google",
            calendar_id=settings.google_calendar_id,
            oauth_client_file=settings.google_oauth_client_file,
            oauth_token_file=settings.google_oauth_token_file,
        )
    )
    return provider


def _print_proxy_package(package: object) -> None:
    typer.echo("Summary:")
    typer.echo(package.summary)
    typer.echo("")
    typer.echo("Risk checks:")
    typer.echo(f"- makes_commitment: {package.risk_checks.makes_commitment}")
    typer.echo(f"- missing_context: {package.risk_checks.missing_context}")
    typer.echo(f"- sensitive: {package.risk_checks.sensitive}")
    typer.echo(f"- reason: {package.risk_checks.reason}")
    typer.echo("")
    typer.echo("Drafts:")
    for index, draft_option in enumerate(package.drafts, start=1):
        typer.echo(f"{index}. [{draft_option.label}] {draft_option.text}")


def _terminal_approval(formatted_package: str) -> str | None:
    typer.echo(formatted_package)
    drafts = _extract_numbered_drafts(formatted_package)
    typer.echo("Approve reply:")
    if drafts:
        available = ", ".join(str(index) for index in range(1, len(drafts) + 1))
        typer.echo(f"- enter {available} to send that draft")
    typer.echo("- enter e to type your own reply")
    typer.echo("- press Enter to skip")
    choice = typer.prompt("Choice", default="", show_default=False).strip()

    if not choice:
        typer.echo("Skipped.")
        return None

    if choice.isdigit():
        index = int(choice) - 1
        if index < len(drafts):
            return drafts[index]
        typer.echo("Draft choice was unavailable. Skipped.")
        return None

    if choice.lower() == "e":
        edited = typer.prompt("Type approved reply", default="", show_default=False).strip()
        return edited or None

    typer.echo("Unknown choice. Skipped.")
    return None


def _extract_numbered_drafts(formatted_package: str) -> list[str]:
    drafts: list[str] = []
    for line in formatted_package.splitlines():
        stripped = line.strip()
        if not stripped or ". " not in stripped:
            continue
        prefix, remainder = stripped.split(". ", 1)
        if prefix.isdigit():
            drafts.append(remainder)
    return drafts


if __name__ == "__main__":
    app()
