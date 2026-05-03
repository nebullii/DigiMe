# DigiMe

DigiMe is a local-first communication proxy. It watches approved sources, summarizes recent context, drafts replies with a local model, and waits for human approval before sending.

The current working path is Discord + Ollama:

```text
Discord channel
  -> DigiMe local watcher
  -> SQLite message store
  -> Qwen via Ollama
  -> terminal approval
  -> approved Discord reply
```

## Current Status

Working:

- local Ollama inference with `qwen3:latest`
- one-off proxy drafting from copied text
- Discord channel polling through a bot token
- live Discord watcher that keeps the bot online
- terminal approval before sending
- local SQLite storage for Slack and Discord messages

Not built yet:

- desktop/menu-bar approval UI
- browser extension capture for Slack/Discord/Teams/Gmail web
- automatic style retrieval from prior replies
- multi-channel Discord watchlist
- Slack live watcher

## Architecture

```text
Communication apps
  Discord now; Slack/Teams/Gmail later
        |
Capture / monitor layer
  Discord bot watcher, polling fallback, future browser extension
        |
Local inbox / memory
  SQLite message store, future vector memory
        |
Reply engine
  prompt builder, risk checks, local Ollama model
        |
Human approval
  terminal now, desktop UI later
        |
Output
  approved Discord send now, clipboard/app-specific send later
```

The model does not directly inspect apps. DigiMe captures controlled context, then passes only that context to the model.

## Repo Layout

```text
src/digime/
  agent/       prompt building and reply package parsing
  connectors/ Discord, Slack, WhatsApp adapters
  ingest/      parsers, normalization, redaction
  llm/         Ollama/local model adapters
  memory/      SQLite message store and future vector retrieval
  style/       style profile generation
  api/         future local API

data/
  raw/         ignored local exports and API dumps
  processed/   ignored normalized datasets
```

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Install the default local model:

```bash
ollama pull qwen3:latest
```

Useful checks:

```bash
digime doctor
ollama list
```

## Local Proxy Drafting

This works without any app integration:

```bash
digime proxy-draft \
  --platform discord \
  --profile discord \
  "Hey DigiMe, can you help me test a reply?"
```

Output includes:

- summary
- risk checks
- draft options

## Discord Setup

DigiMe uses a Discord bot token. The bot can only read channels where it has access.

Required bot/channel permissions:

- View Channel
- Read Message History
- Send Messages
- Message Content Intent enabled in Discord Developer Portal

Set `.env`:

```bash
DISCORD_BOT_TOKEN=...
DISCORD_DEFAULT_CHANNEL_ID=...
```

Get the channel ID from Discord:

```text
User Settings -> Advanced -> Developer Mode -> right-click channel -> Copy Channel ID
```

## Discord Commands

Fetch recent messages once:

```bash
digime discord sync --limit 25
```

Summarize stored channel context:

```bash
digime discord summarize
```

Draft from stored channel context:

```bash
digime discord draft-needed --profile discord
```

Send an already-approved reply:

```bash
digime discord send-approved "Approved reply text" --yes
```

Run the live watcher:

```bash
digime discord watch --poll-seconds 3
```

The watcher:

- keeps the bot online
- listens to Discord Gateway events
- also polls the channel as a fallback
- stores new messages locally
- summarizes recent channel context
- drafts replies with local Qwen
- waits for terminal approval

Approval options:

```text
1, 2, 3  send one of the drafts
e        type your own approved reply
Enter    skip
```

## Slack Status

Slack ingestion exists but is not the core path right now.

For personal Slack DM history, configure a Slack token with:

- `im:read`
- `im:history`
- `users:read`

Then:

```bash
digime slack auth-check
digime slack sync-dms --max-conversations 3
digime slack build-examples
digime slack stats
```

Slack live reply automation is intentionally deferred until the local proxy loop is solid.

## Privacy Principles

- Keep tokens in `.env`; never commit them.
- Store messages locally.
- Watch only explicitly configured channels.
- Do not send without human approval.
- Treat generated replies as drafts until approved.
- Use app APIs only where permissions are explicit.
