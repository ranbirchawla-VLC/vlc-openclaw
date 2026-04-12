# GTD Agent Claude Implementation Packet v2

## Purpose

This document is the single consolidated implementation packet for building the GTD Agent system. It is intended to be fed directly to Claude so Claude can plan, generate, and structure the implementation work.

This is v2. It reflects a fundamental architectural shift: the system should use native Python tools for all deterministic work and invoke the LLM only for genuinely ambiguous reasoning tasks. This matches the pattern already proven in other Vardalux OpenClaw agents where replacing LLM skills with Python code reduced token cost and improved reliability.

The system also now integrates MNEMO for persistent memory, eliminating the need for the LLM to read raw storage files or re-derive user context on every call.

Use this as the authoritative build brief.

## Build objective

Build a GTD Agent system that supports low-friction capture and review for:
- defined tasks that are not yet calendar items,
- structured ideas that require regular review,
- and teammate-related follow-up items that remain personal reminders rather than collaborative assignments.

The system must be multi-user but personal. Each person has their own GTD workspace and must never share task state by default with another user.

## Architectural philosophy

### Python-first, LLM-minimal

The default path for every GTD operation should be deterministic Python. The LLM should be invoked only when a Python tool explicitly signals that it cannot handle the input with sufficient confidence.

This means:
- Normalization, validation, storage reads, storage writes, retrieval filtering, review scanning, and delegation grouping are all native Python tools.
- The LLM handles only ambiguous intent resolution, natural language title cleanup from messy transcriptions, novel domain inference for ideas that do not match any known pattern, and conversational clarification generation.
- No LLM call should occur on the hot capture path unless the Python normalizer returns a low-confidence or unclassifiable result.

### MNEMO for persistent memory

MNEMO is a Rust-based transparent HTTP proxy daemon that gives LLM agents persistent memory. It is already in the Vardalux OpenClaw tech stack.

In this system, MNEMO should:
- Maintain compact user profile and preference context so the LLM never re-reads profile.json.
- Retain recent capture history for conversational continuity without re-reading JSONL files.
- Persist the user's personal context taxonomy extensions.
- Track review state such as last review date, flagged items, and review cadence status.
- Inject only what the LLM needs when the LLM is actually called, keeping injected context minimal and relevant.

The LLM should never directly read or write raw storage files. Python tools handle all file I/O. MNEMO handles memory injection when the LLM is invoked.

## Core product model

### Identity model

The system is Telegram-first for identity.

Each person has:
- their own Telegram bot relationship and/or dedicated private bot chat,
- their own private `telegram_chat_id`,
- their own internal `user_id`,
- their own isolated workspace,
- and later may have Alexa linked to that same personal identity.

The primary alignment field for workspace routing is `telegram_chat_id`.

No normal operation may read from or write to another user's workspace.

Alexa and any future channels are secondary surfaces and must map into the same user record already anchored by Telegram identity.

### Product categories

The system manages three categories:

1. Tasks
2. Ideas
3. Delegation or waiting-for reminders

Tasks and ideas must remain distinct. Delegation items remain owned by the current user and are not reassigned to other GTD users automatically.

### Input model

The system is chat-first and capture-first.

Supported input surfaces:
- Telegram typed text
- Telegram voice notes converted to text before reasoning
- Alexa later, mapped into the same identity record

The product principle is ubiquitous capture with minimal interaction cost. The system should ask only short, necessary clarification questions and should separate capture from deeper organization.

## Deployment constraints

- This GTD system must not run in the default OpenClaw pipeline.
- It must be deployed as a separate agent family.
- It must use separate Telegram bot surfaces or separate GTD-specific routing from existing bots.
- It must have separate chats and dedicated OpenClaw workflow handling.
- It must not interfere with existing production bots already in place.

This is a hard requirement.

## Architecture layers

### Layer 1: Input adapters

Input adapters convert raw channel events into normalized text requests.

Responsibilities:
- Receive Telegram text or Telegram voice.
- Transcribe voice to text before any GTD logic runs.
- Later receive Alexa utterances and map them to the existing user record.
- Produce a normalized inbound event containing source, user identity, raw text, and timestamp.

### Layer 2: Python tool layer (deterministic, no LLM)

This is the core of the system. All of the following are native Python tools registered in OpenClaw:

#### `gtd_normalize`

Purpose: classify intent and extract structured fields from raw text.

Implementation approach:
- Keyword and regex pattern matching for intent detection.
- Known trigger phrases for explicit commands (`/task`, `/idea`, `/next`, `/review`, `/waiting`).
- Field extraction for context hints, priority markers, person names for delegation, and domain keywords for ideas.
- Confidence scoring based on match strength.
- Returns a structured result with intent, candidate fields, missing field flags, and a `needs_llm` boolean.

When `needs_llm` is false, the capture proceeds entirely in Python. When true, the system invokes the LLM fallback for ambiguous classification.

Must not: write storage records, invent missing values, or call the LLM directly.

#### `gtd_validate`

Purpose: validate a candidate record against the data contract before persistence.

Implementation approach:
- JSON schema validation for required fields, allowed enums, and type checks.
- Ownership field enforcement: every record must have `user_id` and `telegram_chat_id`.
- Context requirement enforcement: actionable tasks must have a context.
- Returns a structured validation result with pass/fail and specific field errors.

Must not: perform any reasoning, make workflow decisions, or call the LLM.

#### `gtd_write`

Purpose: append a validated record to the correct user-scoped JSONL file.

Implementation approach:
- Accepts a validated record and a record type.
- Resolves the correct file path from user identity.
- Generates a UUID for the record ID.
- Sets timestamps.
- Appends to the appropriate JSONL file.
- Returns confirmation or error.

Must not: skip validation, write to another user's path, or call the LLM.

#### `gtd_query`

Purpose: retrieve and rank records for operational queries.

Implementation approach:
- Read the user's JSONL files.
- Filter by status, context, priority, energy, duration, and record type as requested.
- Sort and rank.
- Return top N results (default 3 to 5).
- Exclude done, cancelled, and archived items by default.

Must not: call the LLM, mix idea records into task retrieval, or read other users' data.

#### `gtd_review`

Purpose: produce a structured review output.

Implementation approach:
- Scan the user's task, idea, delegation, and parking-lot files.
- Identify active tasks missing required metadata.
- Identify stale active tasks based on age thresholds.
- Identify ideas overdue for review based on `review_cadence` and `last_reviewed_at`.
- Identify waiting-for items that have not been touched recently.
- Identify parking-lot items needing classification.
- Return a structured review object with sections in priority order.

Must not: call the LLM for the structured scan. An optional LLM call may be made afterward to produce a conversational narrative summary if the user requests it.

#### `gtd_delegation`

Purpose: produce a grouped view of delegation and waiting-for items.

Implementation approach:
- Read delegation-relevant records for the current user.
- Group by `delegate_to` or `waiting_for`.
- Sort groups by oldest untouched item.
- Return a structured grouped result.

Must not: send external messages, create assignments in other systems, or call the LLM.

### Layer 3: MNEMO memory layer

MNEMO sits between OpenClaw and the LLM API as a transparent proxy.

Responsibilities in this system:
- Inject compact user profile context when the LLM is invoked.
- Inject recent capture history for conversational continuity.
- Inject the user's personal context taxonomy and domain extensions.
- Inject review state for review-related LLM calls.
- Observe all sessions passively to build and maintain its memory store.

MNEMO should not inject large file contents. Python tools handle file reads. MNEMO injects only compact, pre-summarized context relevant to the current LLM call.

### Layer 4: LLM reasoning (invoked only when needed)

The LLM should only be called when a Python tool explicitly requests it. These are the only LLM-facing capabilities needed:

#### `llm_ambiguous_classifier`

When to invoke: the Python normalizer returns `needs_llm: true` because the input does not match any known pattern with sufficient confidence.

Responsibility: determine whether the input is a task, idea, delegation item, or something else. Return a structured classification result.

#### `llm_title_rewriter`

When to invoke: voice transcription produced garbled, overly long, or unclear text that needs rewriting into a clean, concise, action-oriented title.

Responsibility: rewrite the raw text into a short task or idea title. Return only the rewritten title.

#### `llm_domain_inferrer`

When to invoke: an idea does not match any existing domain keyword and needs genuine reasoning to assign a domain.

Responsibility: suggest the most appropriate domain from the existing taxonomy, or propose a new domain name if none fits. Return a structured suggestion.

#### `llm_clarification_generator`

When to invoke: a required field is missing and a clarification question must be composed for the user.

Responsibility: generate one short, natural-language clarification question. Provide likely options when useful. Return structured clarification output.

#### `llm_review_narrative` (optional)

When to invoke: the user requests a conversational review summary rather than a structured list.

Responsibility: convert the structured review output from the Python review tool into a brief conversational summary. Return the narrative text.

### Layer 5: OpenClaw orchestration

OpenClaw is the orchestration layer. It should use deterministic routing for the primary branches, not LLM-based intent detection.

Responsibilities:
- Resolve user identity from the dedicated Telegram bot and private chat context.
- Route to the correct GTD branch using trigger-phrase matching and command detection, consistent with the existing vardalux-openclaw-router pattern.
- Call Python tools directly as the default path for every branch.
- Invoke the LLM only when a Python tool returns `needs_llm: true`.
- Enforce user isolation and storage ownership.
- Return concise user-facing responses.

#### Capture branch

Default flow (no LLM):
1. Resolve identity.
2. Call `gtd_normalize` on the input text.
3. If `needs_llm` is false, call `gtd_validate` on the candidate.
4. If valid, call `gtd_write`.
5. Return a short confirmation.

LLM fallback flow:
1. Resolve identity.
2. Call `gtd_normalize` — returns `needs_llm: true`.
3. Call `llm_ambiguous_classifier` and/or `llm_title_rewriter`.
4. Call `gtd_validate` on the refined candidate.
5. If a required field is still missing, call `llm_clarification_generator`.
6. Once complete, call `gtd_write`.
7. Return confirmation.

#### Retrieval branch

Flow (no LLM):
1. Resolve identity.
2. Call `gtd_query` with relevant filters.
3. Format and return.

#### Review branch

Flow (no LLM for structured output):
1. Resolve identity.
2. Call `gtd_review`.
3. Return structured review.
4. Optionally call `llm_review_narrative` if the user asks for a conversational summary.

#### Delegation branch

Flow (no LLM):
1. Resolve identity.
2. Call `gtd_delegation`.
3. Format and return.

### Layer 6: Storage and persistence

Storage lives on the shared Google Drive mount.

Path structure:

```text
gtd-agent/
  users/
    <user-id>/
      tasks.jsonl
      ideas.jsonl
      parking-lot.jsonl
      profile.json
```

All reads and writes are scoped to the current user path. No branch may read all users' data during normal operation. Python tools own all file I/O.

## Data contracts

All machine-facing outputs should be strict JSON validated by Python before persistence.

### User profile

```json
{
  "user_id": "string",
  "telegram_bot": "string",
  "telegram_chat_id": "string",
  "display_name": "string",
  "status": "active",
  "alexa_linked": false,
  "created_at": "iso8601",
  "updated_at": "iso8601"
}
```

### Task record

```json
{
  "id": "string",
  "record_type": "task",
  "user_id": "string",
  "telegram_chat_id": "string",
  "title": "string",
  "context": "string",
  "area": "string",
  "priority": "normal",
  "energy": "medium",
  "duration_minutes": null,
  "status": "active",
  "delegate_to": null,
  "waiting_for": null,
  "notes": null,
  "source": "telegram_text",
  "created_at": "iso8601",
  "updated_at": "iso8601",
  "completed_at": null
}
```

Rules:
- `record_type` must always be `task`.
- `title` must be action-oriented and concise.
- `context` is required for actionable tasks.
- `duration_minutes` is optional.
- `delegate_to` and `waiting_for` are optional but must be null when unused.
- `completed_at` must be null unless `status = done`.

### Idea record

```json
{
  "id": "string",
  "record_type": "idea",
  "user_id": "string",
  "telegram_chat_id": "string",
  "title": "string",
  "domain": "string",
  "context": "string",
  "review_cadence": "monthly",
  "promotion_state": "incubating",
  "spark_note": null,
  "status": "active",
  "source": "telegram_text",
  "created_at": "iso8601",
  "updated_at": "iso8601",
  "last_reviewed_at": null,
  "promoted_task_id": null
}
```

Rules:
- `record_type` must always be `idea`.
- `domain` is required.
- `context` is required.
- `review_cadence` is required.
- `promotion_state` tracks incubation lifecycle.
- `promoted_task_id` is null unless promoted.

### Parking-lot record

```json
{
  "id": "string",
  "record_type": "parking_lot",
  "user_id": "string",
  "telegram_chat_id": "string",
  "raw_text": "string",
  "source": "telegram_text",
  "reason": "ambiguous_capture",
  "status": "active",
  "created_at": "iso8601",
  "updated_at": "iso8601"
}
```

### Delegation modeling

Delegation or waiting-for items should be represented as task records with delegation-specific fields (`delegate_to`, `waiting_for`, `status = waiting` or `status = delegated`) rather than a fully separate primary entity type.

### Normalizer output contract

```json
{
  "status": "ok",
  "intent": "task_capture",
  "confidence": 0.93,
  "needs_llm": false,
  "candidate": {
    "title": "Call customs broker",
    "context_hint": "@phone",
    "priority_hint": "normal",
    "area_hint": "business",
    "missing_fields": []
  }
}
```

When `needs_llm` is true:

```json
{
  "status": "uncertain",
  "intent": "unknown",
  "confidence": 0.4,
  "needs_llm": true,
  "candidate": {
    "title": "raw transcribed text here",
    "context_hint": null,
    "priority_hint": null,
    "area_hint": null,
    "missing_fields": ["intent", "context"]
  }
}
```

### Clarification output contract (LLM-generated)

```json
{
  "status": "clarify",
  "question": "What context should this task use?",
  "missing_field": "context",
  "options": ["@phone", "@computer", "@errands"]
}
```

### Validation output contract

```json
{
  "status": "ok",
  "record_type": "task",
  "valid": true,
  "errors": []
}
```

Or:

```json
{
  "status": "error",
  "record_type": "task",
  "valid": false,
  "errors": [
    {
      "field": "context",
      "message": "Actionable task requires context"
    }
  ]
}
```

## Enums

### Source enum

```text
telegram_text
telegram_voice
alexa
manual
import
```

### Task status enum

```text
active
waiting
delegated
done
cancelled
archived
```

### Idea status enum

```text
active
on_hold
archived
promoted
```

### Priority enum

```text
low
normal
high
critical
```

### Energy enum

```text
low
medium
high
```

### Review cadence enum

```text
weekly
monthly
quarterly
```

### Promotion state enum

```text
raw
incubating
promoted_to_task
promoted_to_project
archived
```

### Parking-lot reason enum

```text
ambiguous_capture
missing_required_context
low_confidence_parse
```

## Starter taxonomy

### Contexts

```text
@phone
@computer
@errands
@home
@watch-desk
@ai-review
@team
```

### Areas

```text
business
personal
family
health
home
learning
operations
```

### Idea domains

```text
ai-automation
watch-business
business-improvement
meetings-to-schedule
home-life
learning
content
```

These are defaults. Each user may extend their personal taxonomy over time, and MNEMO should persist those extensions.

## Command surface

The system must support both explicit commands and natural-language requests.

### Explicit commands

```text
/start
/help
/capture
/task
/idea
/next
/review
/waiting
/settings
/privacy
```

### Command semantics

| Command | Meaning | Path |
|---|---|---|
| `/start` | Start or reconnect the GTD session | Python |
| `/help` | Show commands and usage examples | Python |
| `/capture` | Generic capture mode | Python → LLM if ambiguous |
| `/task` | Force task capture interpretation | Python |
| `/idea` | Force idea capture interpretation | Python |
| `/next` | Show the next best actions | Python |
| `/review` | Trigger structured review | Python → optional LLM narrative |
| `/waiting` | Show waiting-for and teammate follow-up | Python |
| `/settings` | Show user preferences | Python |
| `/privacy` | Show privacy and isolation rules | Python |

### Natural-language examples

- "Remind me to call the customs broker."
- "Idea: build an agent to scan watch buying opportunities."
- "What's next?"
- "Show calls I can make now."
- "What am I waiting on from Alex?"
- "Review my ideas."

The Python normalizer should handle these. LLM is only invoked if the normalizer cannot classify with confidence.

## Clarification rules

Ask only one clarification question at a time.

### Task clarification order

1. `context`
2. `title` if too vague
3. Task vs idea distinction if unclear

Do not ask for optional metadata unless it materially improves usefulness.

### Idea clarification order

1. `domain`
2. `context`
3. `review_cadence`

If these are strongly implied, infer them and proceed.

### Delegation clarification

Only ask if it is unclear whether the record is:
- a normal task mentioning a person,
- a waiting-for item,
- or a future assignment reminder.

## Retrieval behavior

### `/next`

- Return 3 to 5 items by default.
- Prefer context-matched actionable tasks.
- Use priority, energy, duration, and status when available.
- Exclude done, cancelled, and archived records.
- Do not mix ideas into next-action output.

### `/waiting`

- Return only waiting or delegation items owned by the current user.
- Group by person where possible.
- Highlight oldest untouched items first.

### `/review`

Review output order:
1. Active tasks missing metadata.
2. Stale active tasks.
3. Ideas overdue for review.
4. Waiting-for items needing follow-up.
5. Parking-lot items needing classification.

## Token budget expectations

The revised architecture should achieve near-zero LLM cost for the majority of daily operations.

| Scenario | LLM Cost |
|---|---|
| Clean task capture (clear intent, known context) | Zero |
| Ambiguous capture (messy voice, unclear intent) | One small LLM call |
| `/next` retrieval | Zero |
| `/waiting` retrieval | Zero |
| `/review` structured output | Zero |
| `/review` conversational narrative | One small LLM call |
| Weekly review | Zero for scan, optional small LLM for narrative |

The system should be designed so that the majority of daily interactions — clean captures, retrievals, and structured reviews — never touch the LLM at all.

## Install and setup expectations

### Telegram

- Use a dedicated GTD bot surface.
- Each user must start a private conversation with the GTD bot.
- Capture the user's private `telegram_chat_id`.
- Store the mapping in the GTD user registry.

### OpenClaw

- Create a dedicated GTD OpenClaw agent.
- Bind it to the GTD Telegram bot or GTD-specific routing branch.
- Do not attach this workflow to the default pipeline.
- Ensure existing bots remain untouched.
- Use deterministic trigger-phrase routing consistent with the vardalux-openclaw-router pattern.

### MNEMO

- Connect MNEMO as a transparent proxy for the GTD agent.
- Start in passive observation mode to build memory from initial sessions.
- Configure compact context injection for user profile, recent captures, taxonomy extensions, and review state.
- Do not inject large file dumps — Python tools handle file I/O.

### Python tools

- Register all six Python tools in the OpenClaw agent: `gtd_normalize`, `gtd_validate`, `gtd_write`, `gtd_query`, `gtd_review`, `gtd_delegation`.
- Each tool should be independently testable with known inputs.
- Tools should share a common utility module for file path resolution, user scoping, and JSONL read/write operations.

### Storage

- Create a dedicated GTD storage root on the shared Google Drive mount.
- Use per-user folders.
- Verify isolation with one-user and two-user tests before production.

### Alexa later

- Add Alexa only after Telegram identity and user-scoped storage are working.
- Map Alexa into the existing user record.
- Do not allow Alexa to bypass Telegram-anchored ownership.

## Recommended build order

1. **Python tools first.** Build `gtd_normalize`, `gtd_validate`, `gtd_write`, `gtd_query`, `gtd_review`, `gtd_delegation`. Write tests for each with known inputs. This is the foundation.

2. **Wire MNEMO.** Connect MNEMO passively to observe sessions and start building its memory store. Configure compact context injection for user profile and recent captures.

3. **Build the OpenClaw agent.** Deterministic router with trigger-phrase matching. Python tool calls as the default path. LLM invocation only on `needs_llm: true` from the normalizer.

4. **Build minimal LLM skills last.** Only `llm_ambiguous_classifier`, `llm_title_rewriter`, `llm_domain_inferrer`, `llm_clarification_generator`, and optionally `llm_review_narrative`. These should be tiny, focused, and rarely invoked.

5. **Test with one user.** Verify capture, retrieval, review, and delegation with a single user. Confirm zero LLM calls on clean captures.

6. **Test multi-user isolation.** Add a second user. Verify complete workspace separation.

7. **Add voice-to-text.** Connect Telegram voice-note ingestion. Confirm the same flows work with transcribed input. This is where `llm_title_rewriter` gets exercised more.

8. **Add Alexa later.** Only after Telegram identity and storage are solid.

## Build instructions for Claude

Use this packet to do the following work:

1. Produce a detailed implementation plan following the build order above.
2. Generate the Python tool implementations with tests.
3. Generate the OpenClaw agent configuration with deterministic routing.
4. Generate the minimal LLM skill definitions.
5. Generate MNEMO integration guidance.
6. Generate strict JSON schemas for all records and machine outputs.
7. Generate the installable repo structure.
8. Preserve separation from the default pipeline.
9. Preserve Telegram-first identity alignment.
10. Optimize for near-zero LLM cost on the daily capture and retrieval paths.

## Output expectations

Claude should produce:
- a plan,
- the proposed folder structure,
- the Python tool source files with tests,
- the OpenClaw agent prompt or config scaffolding,
- the minimal LLM skill files,
- MNEMO configuration notes,
- the data schemas,
- and setup steps,

while following this packet as the source of truth.
