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

## Step 3: WatchTrack Lookup (LLM — step0-watchtrack)

Load `skills/step0-watchtrack/SKILL.md`. This skill handles:

1. Parse `internal_ref` from folder name (first segment before hyphen)
2. Navigate to WatchTrack using browser tool
3. Extract all fields → write to `_draft.json`
4. Send Telegram summary with buttons: `✅ Looks Good` / `✏️ Correct This`
5. If corrections needed: update `_draft.json`, re-confirm

**Context loaded: ~3K.** Only browser nav + data extraction instructions.

## Step 3.5: Title Research

Immediately after WatchTrack confirmed — before listing generation:

1. Read `_draft.json` for watch identity
2. Run title research using web search tools (eBay, Chrono24, Google)
3. Write `title-research.json` to the listing folder
4. Silent — no approval gate, do NOT notify Ranbir unless catastrophic
5. Continue regardless of success/failure

Expected: 60–90 seconds. Skip any single research step that exceeds 30 seconds.

## Step 4: Photo Review (LLM — step1-photos)

Load `skills/step1-photos/SKILL.md`. This skill handles:

1. Read images from listing folder
2. Assess quality, composition, lighting, completeness
3. Post review to Telegram with at least one full paragraph of feedback
4. Buttons: `✅ Approve` / `🔄 Request Changes`
5. After approval: collect condition, tier, pricing inputs (retail_net, wholesale_net, etc.)
6. Save everything to `_draft.json`

**Context loaded: ~4K.** Only photo review criteria + input collection.

## Step 5: Pricing (Python — run_pricing)

Exact exec command:
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_pricing.py "<folder_path>"
```

Capture stdout — that is the pricing table. Post it to Telegram.
If output starts with `{"ok": false`, post the error and stop.

Posts pricing table to Telegram for approval:
Buttons: `✅ Approve Pricing` / `✏️ Adjust`

On Adjust: ask what to change. Update `inputs.*` via `draft_save.py`, re-run `run_pricing.py`, re-post.

## Step 6: Canonical Description (LLM — step3a-canonical)

Load `skills/step3a-canonical/SKILL.md`. This skill handles:

1. Read `_draft.json` for condition, tier, brand, model, specs
2. Read `skills/step3a-canonical/references/voice-tone.md` for writing rules
3. Write: one canonical description paragraph + one condition line + one Grailzee description
4. Save to `_draft.json`
5. Post to Telegram for approval
6. Buttons: `✅ Approve` / `✏️ Request Changes`

**Context loaded: ~5K.** Only voice-tone + tier rules.

## Step 6.5: Grailzee Gate (Python — run_grailzee_gate)

Exact exec command:
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_grailzee_gate.py "<folder_path>"
```

Capture stdout. Post recommendation to Telegram.
If data unavailable, tool returns a manual-check message — does NOT block pipeline.

Buttons: `✅ Proceed` / `⏭ Skip Grailzee`

## Step 7: Assembly + PDF (Python — run_phase_b + generate_listing_pdf)

Exact exec commands (run in sequence):
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_phase_b.py "<folder_path>"
```
If output is `{"ok": true, ...}`, then:
```
python3 /Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/generate_listing_pdf.py "<folder_path>/_Listing.md"
```

If either returns `{"ok": false, ...}`: post the error to Telegram and stop.

On success, post to Telegram:
> ✅ Listing complete — [Brand] [Model]
> _Listing.md and PDF ready in [folder_name]

Then post to Slack `C0APPJX0FGC`:
> ✅ Listing complete: [Brand] [Model] ([internal_ref])

**No LLM needed. All formatting, substitutions, and checklists are handled internally.**

## Step 8: WatchTrack Sub-Status Update

Use the native browser tool to set Sub Status to "Ready for Listing":

1. Navigate to `https://watchtrack.com/store/inventory`
2. Search for the SKU
3. Open item, set Sub Status → "Ready for Listing"
4. Confirm to Ranbir via Telegram

## Step 9: Mark Complete

Add folder relative path to `processed` in `.watcher-state.json`. Update `last_scan`.

Reply to Ranbir: "✅ [brand] [model] ([internal_ref]) — listing complete and WatchTrack updated."

---

## Resume Logic

If `_draft.json` exists in the folder with a `step` value:
- Offer Telegram buttons: `▶️ Resume from Step [N+1]` / `🔄 Start Over`
- Resume picks up from the next step after the last completed one
- Start Over deletes `_draft.json` and begins at Step 3

## Step ↔ Tool Mapping

```
step = None → Create draft, load step0-watchtrack skill      (LLM)
step = 0    → Load step1-photos skill                        (LLM)
step = 1    → Call run_pricing tool                          (Python)
step = 2    → Load step3a-canonical skill                    (LLM)
step = 3    → Call run_grailzee_gate tool                    (Python)
step = 3.5  → Call run_phase_b tool → generate_listing_pdf   (Python)
step = 4    → WatchTrack update → mark complete              (Browser)
```

## Rules

- **One at a time.** Never process multiple folders simultaneously.
- **No cron, no auto-scan.** Only runs when Ranbir asks.
- **Never spawn subagents or Claude Code.** Do all work natively in this session.
- **Browser tool only for WatchTrack.** Never use exec or CLI for browser actions.
- **All approvals via Telegram inline buttons.** Never poll for free-text when a button is appropriate.
- **Slack for completed notifications only.** Never use Slack for approvals or mid-pipeline updates.
- **LLM skills load only what they need.** Never load the full monolith. Each micro-skill is 3-5K context max.
- **Python tools are deterministic.** Pricing, templates, substitutions, checklists — never send these to the LLM.
- **Shared state travels through `_draft.json`.** Every tool reads from it and writes back to it. Validate against `schema/draft_schema.json` before every operation.
