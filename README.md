# DigiMe

DigiMe is a local-first personal reply agent. It learns from your past Slack and WhatsApp replies through prompting, retrieval, and feedback rather than model training.

## Goal

Build a private assistant that drafts replies in your style while keeping you in control.

The first version should:

- ingest Slack history and WhatsApp exports
- extract your replies with surrounding context
- generate platform-specific style profiles
- retrieve similar past examples
- draft replies with a local Qwen model
- require approval before anything is sent
- learn from your edits over time

## High-Level Architecture

```text
Data sources
  Slack API, WhatsApp exports
        |
Ingestion
  parse, normalize, redact, identify your replies
        |
Memory
  SQLite for records, vector DB for similar examples
        |
Style
  platform and relationship-specific style profiles
        |
Reply agent
  prompt builder, retrieval, local Qwen generation
        |
Interfaces
  local approval UI, Slack app, optional WhatsApp Business API
```

## Repo Layout

```text
src/digime/
  agent/       reply orchestration
  api/         future local HTTP API
  connectors/ Slack and WhatsApp integrations
  ingest/      parsers, normalization, redaction
  llm/         local Qwen adapter
  memory/      message store and vector retrieval
  style/       style profile generation

data/
  raw/         ignored local exports and API dumps
  processed/   ignored normalized datasets

config/
  profiles.example.yaml

scripts/
  development entrypoints
```

## Suggested MVP

1. Import a small WhatsApp export manually.
2. Fetch Slack history through the Slack API.
3. Normalize both into conversation/reply pairs.
4. Generate a style profile using local Qwen.
5. Store examples in local memory.
6. Draft replies in a local CLI or web UI.
7. Save your edited final replies as feedback.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Privacy Principles

- Store raw exports locally only.
- Redact secrets before embedding or prompting.
- Keep separate style profiles for work, friends, family, and sensitive contexts.
- Start in draft-only mode.
- Log every generated draft and your final edited version.

