# DigiMe

DigiMe is a local-first communication proxy. It watches approved sources, summarizes recent context, and replies with a local model.

The current working path is Discord + Ollama:

```text
Discord channel
  -> DigiMe local watcher
  -> SQLite message store
  -> Qwen via Ollama
  -> autonomous Discord reply
```

## Current Status

Working:

- local Ollama inference with `qwen3:latest`
- one-off proxy drafting from copied text
- Discord channel polling through a bot token
- live Discord watcher that keeps the bot online
- autonomous Discord replies by default
- optional terminal approval mode for testing
- deterministic meeting-request handling before the LLM path
- local SQLite storage for Slack and Discord messages
- default personality: efficient software engineer, light puns, detailed when useful, honest about limits

Not built yet:

- browser extension capture for Slack/Discord/Teams/Gmail web
- automatic style retrieval from prior replies
- multi-channel Discord watchlist
- Slack live watcher
- Zoom meeting-link creation integration

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
Autonomous reply policy
  auto-send now, optional approval mode for testing
        |
Output
  Discord send now, clipboard/app-specific send later
```

The model does not directly inspect apps. DigiMe captures controlled context, then passes only that context to the model.

## Personality

DigiMe currently replies as an efficient software engineer:

- clear, practical, and human-like
- detailed when details help
- lightly playful with software puns when natural
- honest about uncertainty and missing context
- privacy-aware and unwilling to invent facts or pretend actions happened
- defaults to Google Meet for meeting requests unless Zoom or another platform is specified
- only claims a meeting link was created when the calendar action layer actually created it

## Calendar Provider Layer

DigiMe routes meeting actions through a calendar provider layer. Google is the current implemented provider, and it creates real Google Meet links through Google Calendar API when OAuth is configured.

Current provider config:

```bash
DIGIME_CALENDAR_PROVIDER=google
```

Future providers such as Outlook or CalDAV should plug into the same action layer without changing the Discord watcher.

## Google Meet Setup

Required Google setup:

1. Go to Google Cloud > Search for Google Calendar API > Enable Google Calendar API.
2. Once enabled, click on Credentials > Create Credentials > Create OAuth client ID > Application Type (Desktop App) Permissions
3. Create an OAuth client in Google Cloud Console.
4. Download the OAuth client JSON.
5. Save it locally as:

```text
config/google-oauth-client.json
```

5. Confirm `.env`:

```bash
GOOGLE_CALENDAR_ID=primary
GOOGLE_OAUTH_CLIENT_FILE=./config/google-oauth-client.json
GOOGLE_OAUTH_TOKEN_FILE=./config/google-token.json
DIGIME_TIMEZONE=America/New_York
```

6. Run OAuth:

```bash
digime google auth
```

Check status:

```bash
digime google status
```

Once configured, a Discord message like:

```text
Can you arrange a meeting on Monday 11 am?
```

will create a Google Calendar event with a Google Meet link and send that link to the channel.

If Google OAuth is not configured, DigiMe will say setup is required instead of pretending it created a meeting.

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
DISCORD_CHANNEL_IDS=123456789,987654321
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

Or watch multiple channels with one process:

```bash
digime discord watch --channel-id 123456789 --channel-id 987654321
```

The watcher:

- keeps the bot online
- listens to Discord Gateway events
- also polls the channel as a fallback
- stores new messages locally
- skips messages it has already handled
- persists pending meeting state so follow-up messages like time confirmations can complete an earlier request
- routes meeting requests through the configured calendar provider before using the LLM
- summarizes recent channel context
- drafts replies with local Qwen
- auto-sends the `natural` draft by default

Run with terminal approval instead:

```bash
digime discord watch --poll-seconds 3 --approval
```

Approval mode options:

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
- Default Discord watch mode sends autonomously.
- Use `--approval` while testing risky channels.
- Use app APIs only where permissions are explicit.
