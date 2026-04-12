# Pipeline — GTD Agent

## Config

```
pipeline_root:   ~/.openclaw/workspace/gtd-workspace/
telegram_chat:   (set after bootstrap)
slack_channel:   (set after bootstrap)
task_store:      (set after bootstrap)
```

## Trigger

Ranbir messages on Telegram. Read the message, route to a branch, execute.

---

## Routing Table

| Message Intent | Branch | Matched By |
|---------------|--------|-----------|
| "Add", "capture", "remember", pasted thought, voice transcript | **capture** | Action verb or unstructured noun phrase |
| "What do I have", "show me", "list", "anything for @context" | **retrieval** | Query verb + optional filter |
| "Review", "weekly", "daily review", "what's stale" | **review** | Review keyword |
| "Delegate", "follow up on", "waiting for", "did X get back to me" | **delegation** | Delegate verb or contact name + task reference |

When intent is ambiguous: ask one question, route after answer.

---

## Branch: Capture

**Purpose:** Take raw input and persist it as a validated task, idea, or parking lot item.

**Steps:**
1. Read raw input from Telegram message
2. Run `gtd_normalize.py` → produces candidate JSON with inferred type
3. If type is ambiguous, send Telegram: "Is this a task, idea, or parking lot?" → button selection
4. Run `gtd_validate.py` against appropriate schema
5. If validation fails: surface missing fields, ask for them one at a time
6. Run `gtd_write.py` to persist
7. Confirm to Telegram: type + title + context (one line)

**Rules:**
- Never skip normalization — raw text is not a task
- A task must have: title, context, next_action. Ask for any that are missing.
- An idea must have: title, domain. Ask if missing.
- Parking lot items require only title.
- Do not infer next_action — ask if not present.

---

## Branch: Retrieval

**Purpose:** Surface stored items matching the user's query.

**Steps:**
1. Parse query intent: extract context, area, status, type filters from message
2. Run `gtd_query.py` with extracted filters
3. Format results as numbered list: `N. [context] Title (status)`
4. Send to Telegram
5. If 0 results: confirm filters used, suggest broadening

**Rules:**
- Never return more than 20 items in one message — paginate with "Show more?" button
- Do not modify any items during retrieval
- If the user says "do that one" after retrieval, route to capture or delegation — do not act on ambiguity

---

## Branch: Review

**Purpose:** Run daily or weekly review; surface actionable items, flag stale ones.

| Mode | Scope |
|------|-------|
| daily | Active tasks with today context; overdue items |
| weekly | All active + waiting + someday; items with no update in >7 days |

**Steps:**
1. Run `gtd_review.py --mode <daily|weekly>`
2. Send summary to Telegram:
   - Active next actions count
   - Overdue count
   - Waiting-for count
   - Stale items (weekly only)
3. For each stale item: title + last updated + "Keep / Drop / Someday" buttons
4. Apply user decisions via `gtd_write.py`
5. Send completion: "Review complete. N items processed."

**Rules:**
- Weekly review does not auto-close anything — all decisions require explicit approval
- Daily review is read-only unless the user explicitly acts on an item
- Never surface delegated items in group channels

---

## Branch: Delegation

**Purpose:** Track tasks delegated to others; manage follow-up cadence; record resolution.

**Steps — list:**
1. Run `gtd_delegation.py --action list --status pending`
2. Format as table: Contact | Task | Delegated | Due | Days waiting
3. Send to Telegram

**Steps — follow up:**
1. User identifies item (by number from list)
2. Confirm: "Send follow-up to [name] via [channel]?" → Yes/No button
3. On Yes: draft message, send for user approval, then dispatch

**Steps — resolve:**
1. User marks item resolved
2. Run `gtd_write.py` to update status → done
3. Confirm: "[Task] resolved. Removed from waiting list."

**Rules:**
- Never auto-send follow-up messages — always gate on user approval
- Record follow-up date and channel on every follow-up action
- Delegation items are tasks — they live in the task store with status: waiting

---

## Error Handling

| Condition | Action |
|-----------|--------|
| Schema validation fails | Surface missing fields, ask one at a time |
| gtd_query returns 0 results | Confirm filters used, suggest broadening |
| Ambiguous routing | Ask one question to resolve |
| Python tool exits non-zero | Surface stdout to Telegram, halt branch |
