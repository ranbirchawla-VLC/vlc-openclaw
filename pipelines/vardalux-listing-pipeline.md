---
name: vardalux-pipeline
description: >
  Watches the Vardalux Photo Pipeline folder for new listing-ready folders
  (10+ images) and forwards them to Claude Code for processing. OpenClaw's
  job is folder detection and Telegram notification only. Claude Code does
  all the actual work (WatchTrack, photos, pricing, descriptions, PDF).
---

# Vardalux Listing Pipeline

## What OpenClaw Does

1. Scan for new folders
2. Notify Ranbir on Telegram
3. Spawn Claude Code with the folder path when he says go
4. Post completed listing to Slack when Claude Code is done

That's it. OpenClaw does NOT do WatchTrack lookups, photo reviews, pricing,
descriptions, or PDF generation. Claude Code handles all of that.

---

## Configuration

| Setting | Value |
|---------|-------|
| Pipeline root | `/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Photo Pipeline` |
| Telegram chat ID | `8712103657` |
| Slack channel | `C0APPJX0FGC` |
| Watcher state | `{pipeline_root}/.watcher-state.json` |

---

## Step 1: Scan

1. Read `.watcher-state.json`. If missing, create `{"processed": [], "last_scan": null}`.
2. Walk brand folders: `Rolex/` `Tudor/` `Omega/` `Cartier/` `IWC/` `Breitling/`
3. For each subfolder with 10+ `.jpg`/`.png` files, check if relative path is in `processed`.
4. Collect unprocessed folders as the queue.
5. If queue is empty, do nothing and stop.

**Always use RELATIVE paths in `.watcher-state.json`** (e.g. `IWC/164WU-IW371446-1`).

---

## Step 2: Notify

For each new folder found, send one Telegram message with buttons:

```
openclaw message send --channel telegram --target "8712103657" \
  --message "🆕 New listing ready: [brand] [model] ([folder_name])\n[N] photos" \
  --buttons '[[{"text":"▶️ Start Listing","callback_data":"start:[relative_path]"},{"text":"⏭ Skip","callback_data":"skip:[relative_path]"}]]'
```

Wait for button response before processing.

---

## Step 3: Spawn Claude Code

When user taps "Start Listing", spawn Claude Code via ACP:

```
sessions_spawn({
  runtime: "acp",
  agentId: "claude",
  mode: "run",
  streamTo: "parent",
  task: "
    Run the full Vardalux watch listing pipeline for:
    Folder: {full_folder_path}
    
    You have full access to the browser and are already logged into WatchTrack.
    Follow the existing Co-Work pipeline:
    1. WatchTrack lookup for SKU {internal_ref}
       - Extract: Retail Price (retail_net), Wholesale Price (wholesale_net),
         Included Items, Model name, Serial number, Cost basis, Transaction ID,
         all spec fields that are not N/A
       - IMPORTANT: Also read the Notes field on the WatchTrack item page.
         Pricing targets are sometimes stored there as free text
         (e.g. 'Retail NET $5,411' or 'List at $5,850'). Capture everything
         in the Notes field verbatim and flag it as '(from Notes field)'.
    2. Photo review
    3. Collect condition/tier/Grailzee/pricing via Telegram (chat ID: 8712103657)
    4. Generate full listing document
    5. Generate PDF
    6. Post completed listing to Slack channel C0APPJX0FGC
    7. Return confirmation when done
  "
})
```

Wait for Claude Code to return. When done, update `.watcher-state.json` to mark
the folder as processed.

---

## Step 4: Confirm

When Claude Code completes, post to Telegram:
```
✅ Listing complete: [brand] [model] — posted to #listings-bot
```

---

## Error Handling

- If Claude Code errors out: post error to Telegram with the folder path so
  Ranbir can open it manually in Co-Work
- Never mark a folder as processed unless Claude Code confirms completion
- If Google Drive isn't mounted: post warning to Telegram and stop
