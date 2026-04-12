# Purchase Intake — OpenClaw Skill

Vardalux Collections purchase intake bot. Parses shorthand Telegram messages
about watch deals into structured JSON for WatchTrack Writer.

## What It Does

1. Ranbir sends a deal message via Telegram (e.g., "tudor pepsi 79830RB 2750 from mike johnson zelle full kit excellent")
2. Agent extracts all fields, asks for anything missing one at a time
3. Shows confirmation summary
4. On confirm, writes canonical JSON to Google Drive
5. WatchTrack Writer picks it up from there

## Required Fields

Every deal needs all seven before confirmation:
seller name, watch brand, model, reference, condition, set completeness, price.

## Setup

### 1. Create Google Drive folders

If not already created by the bootstrap script:

```
VardaluxAgents/
  incoming/      # Partial deals (future use)
  confirmed/     # Confirmed deals for WatchTrack Writer
```

These live on the Vardalux Shared Drive, mounted locally via Google Drive for Desktop.

### 2. Create the Telegram bot

In Telegram, message @BotFather:

```
/newbot
Name: Vardalux Purchase Intake
Username: VardaluxPurchaseBot (or VardaluxPurchaseIntakeBot if taken)
```

Save the token.

Configure the bot profile:
```
/setdescription → Vardalux Collections purchase intake. Send watch deal details here.
/setabouttext → Purchase intake for Vardalux Collections.
```

### 3. Install the skill

Copy the `purchase-intake/` folder to your OpenClaw workspace skills directory:

```bash
cp -r purchase-intake/ ~/.openclaw/workspace/skills/purchase-intake/
```

Or wherever your agent's workspace skills live.

### 4. Configure the agent

In your OpenClaw agent config, add the Telegram bot token and point the
agent at this skill. The agent should use this skill as the sole handler
for the purchase intake bot's Telegram channel.

### 5. Verify the Drive path

The SKILL.md contains a hardcoded DRIVE_ROOT path. Verify it matches your
Google Drive for Desktop mount:

```
/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/VardaluxAgents
```

If your mount path differs, update the DRIVE_ROOT in SKILL.md.

### 6. Test

Send a test message to the bot:

```
tudor pepsi 79830RB 2750 from mike johnson zelle full kit excellent
```

Expected: agent shows confirmation summary with all fields populated.
Confirm with "yes" and verify JSON appears in the confirmed/ folder.

## File Structure

```
purchase-intake/
  SKILL.md                                    # Agent instructions (the skill)
  README.md                                   # This file
  schemas/
    canonical-transaction.schema.json          # JSON output schema
```

## Canonical JSON Output

Confirmed deals write to `VardaluxAgents/confirmed/{DEAL_ID}.json`.

Deal ID format: `purchase-{YYYYMMDD}-{seller}-{brand}` (lowercase, hyphens).

See `schemas/canonical-transaction.schema.json` for the full schema.

## Downstream

WatchTrack Writer reads from `confirmed/` and creates client + purchase
records in WatchTrack via browser automation. That agent is a separate
build step.

## What This Replaces

This single SKILL.md replaces the entire Node.js `vardalux-agents` codebase
(Steps 1-6: schemas, shared skills, transport, Claude skills, conversation
infra, agent assembly, webhook server, intake orchestrator). OpenClaw handles
Telegram I/O, session history, and Claude API calls natively.
