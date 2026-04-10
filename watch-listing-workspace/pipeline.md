# Vardalux Listing Pipeline

## How It Works

You are triggered manually by Ranbir via Telegram. When asked to look for new folders,
scan the pipeline root for unprocessed listing-ready folders. Work ONE folder at a time,
start to finish, before stopping. Never process multiple folders in parallel.

## Configuration

| Setting | Value |
|---------|-------|
| Pipeline root | `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Photo Pipeline` |
| Telegram chat ID | `8712103657` |
| Slack channel | `C0APPJX0FGC` |
| Watcher state | `{pipeline_root}/.watcher-state.json` |
| WatchTrack URL | `https://watchtrack.com/store/inventory` |

## Trigger

Ranbir messages the bot on Telegram. Examples:
- "check for new folders"
- "any new listings?"
- "look for listings"
- "scan pipeline"

On trigger: run Step 1 below.

## Step 1: Scan

1. Read `{pipeline_root}/.watcher-state.json`. If missing, create `{"processed": [], "last_scan": null}`.
2. Walk ALL subdirectories in the pipeline root (ignore files, ignore `Archive/`). Do not use a hardcoded brand list — new brands may be added at any time.
3. For each subfolder with 10+ `.jpg`/`.png` files, check if relative path is in `processed`.
4. Collect unprocessed folders as the queue.
5. If queue is empty: reply "No new listing folders found." and stop.
6. Take the FIRST unprocessed folder only. Ignore the rest for now.

**Always use RELATIVE paths in `.watcher-state.json`** (e.g. `Cartier/821QW-WSSA0089`).

## Step 2: Notify

Send one Telegram message with buttons for the folder found:

```
🆕 New listing ready: [brand] [folder_name]
[N] photos
```

Buttons: `▶️ Start Listing` / `⏭ Skip`

- If **Skip**: add folder to `processed` in `.watcher-state.json`, update `last_scan`, stop.
- If **Start**: proceed to Step 3.

## Step 3: WatchTrack Lookup

Use the native browser tool directly (never exec, never CLI):

1. Parse `internal_ref` from folder name (first segment before hyphen, e.g. `821QW` from `821QW-WSSA0089`)
2. Navigate to `https://watchtrack.com/store/home` using the browser tool
3. Search for the SKU, open the item, extract all fields:
   brand, model, reference, serial, condition, included items, retail price,
   wholesale price, item cost, sub_status, sale_channel, owner, notes, comps
4. Write `watchtrack.json` to the listing folder (schema below)
5. Send Telegram summary with buttons: `✅ Looks Good` / `✏️ Correct This`
6. If `Correct This`: prompt for corrections, update `watchtrack.json`, re-confirm

**watchtrack.json schema:**
```json
{
  "sku": "821QW",
  "extracted_at": "ISO-8601",
  "source_url": "https://watchtrack.com/store/item/{uuid}",
  "item": {
    "brand": "Cartier",
    "model": "Santos de Cartier Large",
    "reference": "WSSA0089",
    "serial": "string or null",
    "condition": "Pre-owned",
    "included": "Watch with original box and papers",
    "sub_status": "Needs Photos",
    "sale_channel": "Retail Listings, Social Push",
    "owner": "Vardalux Collections"
  },
  "pricing": {
    "retail_price": 12600.00,
    "wholesale_price": null,
    "item_cost": 9250.00
  },
  "item_notes": "string or null"
}
```

## Step 1.5: Title Research

Immediately after WatchTrack confirmed — before listing generation:

1. Read `watchtrack.json` for watch identity
2. Run title research using web search tools (eBay, Chrono24, Google)
3. Write `title-research.json` to the listing folder
4. Silent — no approval gate, do NOT notify Ranbir unless catastrophic
5. Continue to Step 4 regardless of success/failure

Expected: 60–90 seconds. Skip any single research step that exceeds 30 seconds.

## Step 4: Listing Generation

Run the full listing pipeline natively. Follow `skills/watch-listing/SKILL.md` exactly:

- Step 0: WatchTrack already done — load from `watchtrack.json`
- Step 1: Photo review → Telegram approval
- Step 2: Pricing → Telegram approval
- Step 3: Descriptions → Telegram approval
- Step 3.5: Grailzee gate
- Step 4: Generate PDF via `exec` (ReportLab Python script in listing folder)
  - Delete `generate_pdf.py` after PDF confirmed
  - Post completion to Telegram
  - Post notification to Slack `C0APPJX0FGC`

**One step at a time. Hard approval gate at every step. Never skip. Never combine.**

## Step 5: WatchTrack Sub-Status Update

Use the native browser tool to set Sub Status to "Ready for Listing":

1. Navigate to `https://watchtrack.com/store/inventory`
2. Search for the SKU
3. Open item, set Sub Status → "Ready for Listing"
4. Confirm to Ranbir via Telegram

## Step 6: Mark Complete

Add folder relative path to `processed` in `.watcher-state.json`. Update `last_scan`.

Reply to Ranbir: "✅ [brand] [model] ([internal_ref]) — listing complete and WatchTrack updated."

---

## Rules

- **One at a time.** Never process multiple folders simultaneously.
- **No cron, no auto-scan.** Only runs when Ranbir asks.
- **Never spawn subagents or Claude Code.** Do all work natively in this session.
- **Browser tool only for WatchTrack.** Never use exec or CLI for browser actions.
- **All approvals via Telegram inline buttons.** Never poll for free-text when a button is appropriate.
- **Slack for completed notifications only.** Never use Slack for approvals or mid-pipeline updates.
