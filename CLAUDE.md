# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
ollama pull qwen3:latest
```

## Commands

```bash
# Lint
ruff check src tests

# Run all tests
pytest

# Run a single test file
pytest tests/test_proxy_reply.py

# Check config/token status
digime doctor
```

## Architecture

DigiMe is a local-first communication proxy that watches messaging platforms, drafts replies with a local LLM (Qwen via Ollama), and requires human approval before sending anything.

**Data flow:**
```
Platform (Discord/Slack) → Connector → SQLite store → ProxyReplyAgent (Ollama) → terminal approval → send
```

**Key packages under `src/digime/`:**

- `config.py` — `Settings` (pydantic-settings), loaded once as `settings` singleton; reads from `.env`. All env vars use `DIGIME_` prefix except platform tokens.
- `cli.py` — Typer app with two sub-apps: `slack` and `discord`. Entry point for all user-facing commands.
- `agent/` — `ProxyReplyAgent.draft()` builds a prompt via `proxy_prompt.py`, calls Ollama, and parses the JSON response into `ProxyDraftPackage` (summary + risk checks + 3 draft options).
- `connectors/` — `DiscordConnector` (REST polling), `discord_watch.py` (Gateway + polling loop), `SlackConnector` (DM history). Connectors are thin HTTP wrappers; they don't touch the store.
- `ingest/` — message normalization and PII redaction.
- `memory/store.py` — `MessageStore` wraps SQLite directly (no ORM). Call `store.initialize()` before any reads/writes to ensure tables exist.
- `llm/ollama.py` — `OllamaClient.generate(prompt)` → raw string. Model and base URL come from settings.
- `style/profile.py` — loads `config/profiles.example.yaml` for style context passed to the prompt.

**Approval flow (Discord watcher):** `run_discord_watcher` in `discord_watch.py` drives an async discord.py client. On new messages it calls `ProxyReplyAgent`, formats the package, then calls the injected `approval_fn` (terminal in CLI; replaceable for future UI). Only sends if `approval_fn` returns a non-None string.

**LLM response contract:** The model must return a single JSON object with keys `summary`, `risk_checks` (`makes_commitment`, `missing_context`, `sensitive`, `reason`), and `drafts` (list of `{label, text}`). Parsing is in `agent/proxy_reply.py:parse_proxy_draft_response`.

## Environment Variables

| Variable | Purpose |
|---|---|
| `DISCORD_BOT_TOKEN` | Discord bot token (needs Message Content Intent) |
| `DISCORD_DEFAULT_CHANNEL_ID` | Default channel to watch/poll |
| `SLACK_USER_TOKEN` / `SLACK_BOT_TOKEN` | Slack token (user token preferred) |
| `SLACK_YOUR_USER_ID` | Your Slack user ID for reply-example extraction |
| `DIGIME_LLM_MODEL` | Ollama model name (default: `qwen3:latest`) |
| `DIGIME_DATABASE_URL` | SQLite path (default: `sqlite:///./digime.sqlite3`) |
| `DIGIME_DRAFT_ONLY` | When `true`, skip sends (default: `true`) |
