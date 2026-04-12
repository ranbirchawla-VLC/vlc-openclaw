# SETUP — GTD Agent

End-to-end deployment guide. Start here before anything else.

---

## Prerequisites

- Python 3.12.10 via pyenv (`.python-version` in `gtd-workspace/` pins this)
- OpenClaw daemon running
- MNEMO proxy running (or skipped for initial dev)
- Google Drive mounted at its standard path
- A Telegram account with access to BotFather

Verify Python version:

```bash
cd gtd-workspace/
python --version
# Python 3.12.10
```

---

## 1. Telegram Bot Setup

### Create a dedicated bot

The GTD agent **must use its own bot** — separate from any existing Vardalux production bots. Do not attach it to the watch-listing bot or any shared surface.

1. Open Telegram. Start a chat with `@BotFather`.
2. Send `/newbot`. Follow the prompts.
   - Choose a display name: e.g. `Ranbir GTD`
   - Choose a username: e.g. `ranbir_gtd_bot` (must end in `bot`)
3. BotFather returns a bot token in the form `123456789:ABCdefGHI...`
4. Store the token immediately — it is shown only once.

### Store the token

```bash
export TELEGRAM_GTD_BOT_TOKEN="123456789:ABCdefGHI..."
```

For production, add this to your OpenClaw environment config (not to `.env` files in the repo).

### Set bot commands

Send `/setcommands` to BotFather, select your new bot, then paste:

```
start - Start or reconnect your GTD session
help - Show available commands
capture - Generic capture (task, idea, or parking lot)
task - Capture a task directly
idea - Capture an idea directly
next - Show your best next actions
review - Run a structured review
waiting - Show delegation and waiting-for items
settings - View your preferences
privacy - View data isolation and privacy rules
```

### Webhook vs polling

| Mode | When to use |
|------|-------------|
| Polling (`getUpdates`) | Local development — no public URL needed |
| Webhook | Production — lower latency, no idle polling |

For production, set a webhook:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-host>/gtd/webhook
```

For local dev, configure OpenClaw's Telegram adapter to use polling mode.

### How `telegram_chat_id` is captured

When a user sends any message to the bot (including `/start`), Telegram delivers an update containing `message.chat.id`. This integer is the user's permanent `telegram_chat_id` for that bot.

The onboarding flow (see [User Onboarding](#5-user-onboarding) below) reads this value from the first update and writes it to the user's `profile.json`.

---

## 2. Environment Setup

### Python path

The tools directory must be on `PYTHONPATH` when running tools outside tests. From the project root:

```bash
export PYTHONPATH="$(pwd)/gtd-workspace/tools:$PYTHONPATH"
```

Alternatively, run tools from inside `gtd-workspace/` where `conftest.py` handles path insertion automatically.

### Required environment variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GTD_STORAGE_ROOT` | Root of all GTD JSONL storage | `/Volumes/GoogleDrive/My Drive/gtd-storage` |
| `TELEGRAM_GTD_BOT_TOKEN` | Token for the dedicated GTD bot | `123456789:ABCdef...` |

For local development without Google Drive:

```bash
export GTD_STORAGE_ROOT="/tmp/gtd-dev"
```

If `GTD_STORAGE_ROOT` is unset, tools default to `gtd-workspace/storage/` relative to the tools directory. **Do not rely on this default in production.**

---

## 3. Storage Setup

### Google Drive mount path

The GTD storage root lives on the shared Google Drive mount. Create the directory structure:

```bash
mkdir -p "$GTD_STORAGE_ROOT/gtd-agent/users"
```

### Per-user directory structure

`user_path()` in `common.py` creates this on first write:

```
$GTD_STORAGE_ROOT/
  gtd-agent/
    users/
      <user_id>/
        tasks.jsonl
        ideas.jsonl
        parking-lot.jsonl
        profile.json        ← created during onboarding
```

Files are created on first write. An empty user directory with no JSONL files is a valid state (new user, no records yet).

### Isolation verification

After creating a second user, run:

```bash
cd gtd-workspace/
python -m pytest tests/test_e2e_isolation.py -v
```

All 9 isolation tests must pass before any production traffic.

### user_id and path safety

`user_path()` rejects any `user_id` containing `/`, `\`, or `..`. Use the Telegram chat ID (as a string) or a stable alphanumeric identifier.

Set `user_id = str(telegram_chat_id)` during onboarding. This is the required approach — deterministic, requires no mapping table, and keeps identity anchored to the Telegram private chat.

---

## 4. OpenClaw Wiring

### Create a dedicated GTD agent family

The GTD agent must be a **separate agent family** from `watch-listing`. It must not load the watch-listing pipeline, skills, or tools.

In your OpenClaw configuration:
- Agent family name: `gtd`
- Pipeline: `gtd-workspace/pipeline.md`
- AGENTS identity: `gtd-workspace/AGENTS.md`
- Do not set this as the default agent for any existing bot surface.

### Bind to the dedicated Telegram bot

Map the GTD bot token to the GTD agent family only. No other agent should receive messages from this bot.

### Tool registration

The current `gtd-workspace/openclaw.json` is a reference stub. The correct CLI signatures (from `TOOLS.md`) are:

| Tool | CLI signature |
|------|--------------|
| `gtd_router.py` | `python3 tools/gtd_router.py '<raw_input>' <user_id> <telegram_chat_id>` |
| `gtd_normalize.py` | `python3 tools/gtd_normalize.py '<raw_input>'` |
| `gtd_validate.py` | `python3 tools/gtd_validate.py <record_type> <file.json>` |
| `gtd_write.py` | `python3 tools/gtd_write.py <record_type> <file.json>` |
| `gtd_query.py` | `python3 tools/gtd_query.py <user_id> [--context @computer] [--priority high] [--limit 5]` |
| `gtd_review.py` | `python3 tools/gtd_review.py <user_id>` |
| `gtd_delegation.py` | `python3 tools/gtd_delegation.py <user_id>` |

**Primary entry point for OpenClaw:** `gtd_router.py` handles the full flow — normalisation, routing, and writing — in a single call. The individual tools remain independently runnable for testing and debugging.

Update `openclaw.json` to use `gtd_router.py` as the primary registered tool before going to production. Individual tools may also be registered for direct debugging access.

### Deterministic trigger-phrase routing

Consistent with the `vardalux-openclaw-router` pattern, routing is deterministic:

1. Check message text against the explicit command list (`/task`, `/idea`, `/next`, `/review`, `/waiting`, `/start`, `/help`, `/settings`, `/privacy`, `/capture`).
2. If no explicit command, pass raw text to `gtd_router.py`.
3. The router returns `{ branch, result, needs_llm }`.
4. If `needs_llm: false`, format and return the result directly.
5. If `needs_llm: true`, invoke the appropriate LLM skill from `skills/gtd/` per the SKILL.md invocation rules.

**Never use LLM-based intent detection for routing.** The Python normaliser handles all classification deterministically.

### Separation from existing bots

Checklist:
- [ ] GTD bot token is not registered in the watch-listing agent config
- [ ] Watch-listing bot token is not registered in the GTD agent config
- [ ] Default OpenClaw pipeline does not include GTD tools
- [ ] GTD `openclaw.json` does not reference watch-listing skills or tools

---

## 5. MNEMO Setup

MNEMO is the transparent HTTP proxy that provides persistent memory. The GTD agent uses it only when the LLM is actually called.

### Connection

Configure OpenClaw to route the GTD agent's LLM API calls through MNEMO:

```
LLM call path:  GTD agent → MNEMO proxy → Anthropic API
```

No code changes are required in the Python tools. MNEMO intercepts at the HTTP layer.

### Start in passive observation mode

MNEMO builds its memory store from observed sessions automatically. No explicit write calls are needed from the agent side. See `gtd-workspace/memory/MNEMO.md` for the full configuration.

### Memory keys configured

| Key pattern | Contents | Injected on |
|-------------|----------|-------------|
| `gtd:user:{user_id}:profile` | display_name, status, telegram_chat_id, alexa_linked | Every LLM call |
| `gtd:user:{user_id}:recent_captures` | Last 10 captures (title, record_type, captured_at) | Ambiguous capture LLM calls |
| `gtd:user:{user_id}:taxonomy_extensions` | Custom contexts, areas, domains | Ambiguous capture LLM calls |
| `gtd:user:{user_id}:review_state` | last_reviewed_at, total_items_flagged, section_counts | Review narrative LLM calls |

MNEMO injects nothing on zero-LLM paths (clean capture, retrieval, structured review, delegation).

### Degradation

If MNEMO is unavailable, LLM calls proceed without context injection — the agent still functions, but the LLM has no memory of prior sessions. Zero-LLM paths (clean capture, retrieval, review, delegation) are unaffected.

### What MNEMO must not inject

- Raw JSONL file contents
- Full task or idea lists
- Context on zero-LLM paths

---

## 6. User Onboarding

### First-contact flow

When a new user sends `/start` to the GTD bot:

1. Telegram delivers an update with `message.from.id` (Telegram user ID) and `message.chat.id` (private chat ID).
2. The `telegram_chat_id` is `str(message.chat.id)`.
3. Set `user_id = telegram_chat_id` (simplest deterministic mapping).
4. `user_path(user_id)` creates `$GTD_STORAGE_ROOT/gtd-agent/users/<user_id>/`.
5. Write `profile.json` to that directory:

```json
{
  "user_id": "<telegram_chat_id>",
  "telegram_bot": "<bot_username>",
  "telegram_chat_id": "<telegram_chat_id>",
  "display_name": "<user's first name from Telegram>",
  "status": "active",
  "alexa_linked": false,
  "created_at": "<iso8601>",
  "updated_at": "<iso8601>"
}
```

6. Reply: "Your GTD workspace is ready. Send `/help` to see commands."

### Profile creation is out-of-band

`gtd_write.py` does not support writing `profile` records (`profile` is excluded from `_FILE_MAP` by design). Profile creation must happen in a dedicated onboarding step outside the standard capture flow.

### Identity model

All channels anchor to the Telegram identity:

```
Telegram private chat → telegram_chat_id → user_id → workspace
Alexa (future)        → linked to existing user_id → same workspace
```

The Telegram private chat is the source of truth for user identity. Alexa and any future channels must look up the existing `user_id` — they must not create a new workspace.

---

## Quick-start checklist

See the pre-production checklist in `TESTING.md`.
