---
name: vardalux-pipeline
description: >
  Watches the Vardalux Photo Pipeline folder for new listing-ready folders
  (10+ images). OpenClaw handles WatchTrack lookup directly using the browser
  tool. Claude Code handles listing content generation only.
---

# Vardalux Listing Pipeline

## What OpenClaw Does

1. Scan for new folders with 10+ photos
2. Notify Ranbir on Telegram with Start / Skip buttons
3. When Start is tapped: OpenClaw (main agent) uses the browser tool to look up WatchTrack, writes watchtrack.json, confirms with Ranbir
4. When WatchTrack confirmed: spawn Claude Code with watch-listing-content skill for Steps 1–4
5. Post completed listing to Slack when done

## What OpenClaw Does NOT Do
- Generate listing copy, descriptions, pricing calculations, or PDFs
- Those belong to Claude Code using the watch-listing-content skill

---

## Configuration

| Setting | Value |
|---------|-------|
| Pipeline root | `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Photo Pipeline` |
| Telegram chat ID | `8712103657` |
| Slack channel | `C0APPJX0FGC` |
| Watcher state | `{pipeline_root}/.watcher-state.json` |
| WatchTrack URL | `https://watchtrack.com/store/inventory` |

---

## Step 1: Scan

1. Read `.watcher-state.json`. If missing, create `{"processed": [], "last_scan": null}`.
2. Walk brand folders: `Rolex/` `Tudor/` `Omega/` `Cartier/` `IWC/` `Breitling/` `Hublot/`
3. For each subfolder with 10+ `.jpg`/`.png` files, check if relative path is in `processed`.
4. Collect unprocessed folders as the queue.
5. If queue is empty, update last_scan and stop.

**Always use RELATIVE paths in `.watcher-state.json`** (e.g. `Cartier/821QW-WSSA0089`).

---

## Step 2: Notify

For each new folder found, send one Telegram message with buttons:

```
openclaw message send --channel telegram --target "8712103657" \
  --message "🆕 New listing ready: [brand] [folder_name]\n[N] photos" \
  --buttons '[[{"text":"▶️ Start Listing","callback_data":"start:[relative_path]"},{"text":"⏭ Skip","callback_data":"skip:[relative_path]"}]]'
```

Update `last_scan` timestamp. Wait for button tap.

---

## Step 3: WatchTrack Lookup (OpenClaw does this directly)

When "start:[relative_path]" button tap is received:

1. Parse `internal_ref` from folder name (first segment before the hyphen, e.g. `821QW` from `821QW-WSSA0089`)
2. Use the **browser tool** to navigate to `https://watchtrack.com/store/inventory`
3. Search for the SKU in the inventory search bar
4. Extract all fields: brand, model, reference, serial, condition, included items, retail price, wholesale price, item cost, sub_status, sale_channel, owner, notes
5. Write extracted data as `watchtrack.json` to the listing folder
6. Send Telegram summary with buttons:

```
openclaw message send --channel telegram --target "8712103657" \
  --message "✅ WatchTrack: [brand] [model] ([sku])\nRetail: $X | Cost: $X | [condition]\n[included]" \
  --buttons '[[{"text":"✅ Looks Good","callback_data":"wt_ok:[relative_path]"},{"text":"✏️ Correct This","callback_data":"wt_fix:[relative_path]"}]]'
```

**watchtrack.json schema** (write to listing folder):
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

---

## Step 4: Listing Generation (spawn Claude Code)

When "wt_ok:[relative_path]" is received, spawn Claude Code:

```
sessions_spawn({
  runtime: "acp",
  agentId: "claude",
  mode: "run",
  streamTo: "parent",
  sandbox: "inherit",
  task: `
Run Steps 1–4 of the Vardalux listing pipeline.

Folder: {full_folder_path}
WatchTrack data is already in: {full_folder_path}/watchtrack.json

Read and follow:
- ~/.openclaw/workspace/skills/watch-listing-content/SKILL.md
- ~/.openclaw/workspace/skills/watch-listing-content/prompt.md

Follow the exact step sequence from prompt.md. Do NOT skip any approval gate.
All user interaction via Telegram: openclaw message send --channel telegram --target "8712103657" --message "..." --buttons '[...]'

After PDF is generated and confirmed:
1. Delete generate_pdf.py from the folder
2. Post completion to Slack: openclaw message send --channel slack --target "C0APPJX0FGC" --message "..."
3. Return confirmation
  `
})
```

When Claude Code confirms completion, mark folder as processed in `.watcher-state.json`.

---

## Step 5: Update WatchTrack Sub Status

After listing is confirmed complete, use the browser tool to:
1. Navigate to `https://watchtrack.com/store/inventory`
2. Search for the SKU
3. Open the item and set Sub Status to "Ready for Listing"
4. Confirm to Ranbir via Telegram

---

## Error Handling

- If browser tool fails or WatchTrack is not logged in: send error to Telegram, ask Ranbir to paste data manually
- If Claude Code errors: post error to Telegram with folder path
- Never mark a folder processed unless listing is confirmed complete
