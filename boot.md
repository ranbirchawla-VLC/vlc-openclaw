---
name: vardalux-pipeline
description: >
  Automated watch listing pipeline for Vardalux Collections. Scans the Photo Pipeline
  folder for new listing-ready folders (10+ images), looks up pricing on WatchTrack via
  Chrome, researches specs via web search, pauses once for user input (condition, tier,
  Grailzee format), then hands off to the watch-listing skill to generate the full
  listing document and PDF. Use this skill whenever the user says "run the pipeline",
  "scan for new listings", "check for ready watches", "process new folders",
  "start listing pipeline", or mentions scanning the Photo Pipeline folder for new items.
  Also trigger when the user asks to "list the next watch" or "process the next folder".
---

# Vardalux Listing Pipeline

You are running the Vardalux watch listing pipeline. Follow these steps exactly.

## Setup

The workspace folder is the user's mounted folder (the "Vardalux Photo Pipeline" folder). All relative paths below are relative to this workspace root.

## Step 1: Scan for New Ready Folders

1. Read `.watcher-state.json` from the workspace root. If it doesn't exist, create it with `{"processed": [], "last_scan": null}`.
2. Walk each top-level folder in the workspace (these are brand folders like `Cartier`, `Rolex`, `Breitling`). Skip files and hidden folders.
3. Inside each brand folder, look for subfolders matching the pattern `[SKU]-[Reference]` (e.g., `9209K-WSBB0068`).
4. For each such folder, count `.jpg` and `.png` files. If there are 10 or more, it's a candidate.
5. Check if the relative path (e.g., `Cartier/9209K-WSBB0068`) is already in the `processed` array. If not, add it to the queue.
6. If no new folders are found, tell the user "No new ready folders found" and stop.

CRITICAL: Always use RELATIVE paths in `.watcher-state.json` (e.g., `Cartier/9209K-WSBB0068`), never full session paths like `/sessions/.../mnt/...`. Full paths break across Cowork sessions.

## Step 2: Process Each Folder (One at a Time)

For the first unprocessed folder in the queue:

### Parse the folder name

- `brand` = parent folder name (e.g., `Cartier`)
- `sku` = everything before the first hyphen in the folder name (e.g., `9209K`)
- `reference` = everything after the first hyphen (e.g., `WSBB0068`)

### WatchTrack Chrome Lookup

1. Call `tabs_context_mcp` with `createIfEmpty: true` to get a tab.
2. Navigate to `https://watchtrack.com/store/home` and wait 3 seconds.
3. Find the search textbox (placeholder "Search") and type the SKU using `form_input`.
4. Wait 2 seconds for the live search dropdown.
5. Take a screenshot to see the dropdown results.
6. Click on the item result under "Items" that shows the matching Stock ID. Use coordinate-based clicking on the item row (ref-based clicks on dropdown items can be unreliable).
7. Wait 3 seconds for the detail page to load. Verify the URL changed to `/store/item/...`.
8. If still on the home page, retry: click the search bar, clear it, re-type SKU, and try clicking again. Up to 3 retries.
9. Read the full item detail page and extract:
   - Retail Price → this is the retail NET
   - Wholesale Price → this is the wholesale NET
   - Included Items (e.g., "Watch with original box and papers")
   - Model name from the page title (e.g., "Cartier Ballon Bleu de Cartier")
   - All spec fields that are NOT "N/A": Case Material, Case Diameter, Bezel Material, Bezel Type, Thickness, Movement, Caliber, Power Reserve, Crystal, Water Resistance, Dial Color, Dial Numerals, Bracelet Material, Bracelet Color, Clasp Type, Year, Month, Condition

### Web Search for Missing Specs

10. Identify which important specs are still missing (common gaps: Movement, Caliber, Case Diameter, Power Reserve, Water Resistance, Crystal, Thickness).
11. Web search for `[Brand] [Reference] specifications` to fill gaps.
12. If needed, try a second search: `[Brand] [Model name] [Reference] specs`.
13. Merge results — WatchTrack values take precedence where they exist.

### Save Draft JSON

14. Write a draft file to: `[Brand]/[SKU]-[Reference]/[SKU]-[Reference]_draft.json` containing all gathered data:

```json
{
  "sku": "...",
  "reference": "...",
  "brand": "...",
  "model": "...",
  "retail_net": 0,
  "wholesale_net": 0,
  "buffer": 5,
  "included_items": "...",
  "year": "...",
  "condition_from_watchtrack": "...",
  "specs": { ... },
  "photo_count": 0,
  "photo_folder": "Brand/SKU-Reference",
  "watchtrack_url": "...",
  "scraped_at": "..."
}
```

## Step 3: Pause for User Input

Present a clear summary of everything gathered:
- Brand, Model, Reference, SKU
- Retail NET and Wholesale NET from WatchTrack
- Included items
- All specs (noting which came from WatchTrack vs web search)
- Photo count
- Buffer: 5% (default)

Then use the AskUserQuestion tool to collect ALL of the following at once:

1. **Condition** — Ask for component-by-component condition notes. Show the WatchTrack condition field as a starting point. Options: "BNIB (Brand New In Box)", "Excellent", "Very Good", "Good", or "Other" (for detailed custom input).
2. **Tier** — Which buyer tier? Options: "Tier 1 (Entry to Luxury)", "Tier 2 (Functioning/Convenience Luxury)", "Tier 3 (Exclusivity/Investment)".
3. **Grailzee** — Options: "NR (No-Reserve)", "Reserve", "Skip Grailzee".
4. **Corrections** — "Everything looks correct" or "I have corrections" (user provides details).

Wait for user responses. If the user has corrections, apply them to the draft.

## Step 4: Invoke the Watch-Listing Skill

### IMPORTANT: Skill Referencing

The watch-listing skill lives in the Vardalux Collections Claude project. It is the
canonical, always-current version. DO NOT embed, duplicate, or cache watch-listing logic
in this pipeline.

Invoke it via the Skill tool (`skill: "watch-listing"`). Cowork reads the skill from the
project's `.claude/skills/watch-listing/` directory, which is read-only and synced from
the project. Any updates made to the watch-listing skill in the project chat will
automatically be available to this pipeline on the next Cowork session.

The watch-listing skill references supporting files (platform templates, posting checklist,
character substitutions). These live in the workspace at `watch-listing-skill-files/`
(relative to the workspace root). When the watch-listing skill says to read
`references/platform-templates.md` or similar, read the corresponding file from
`watch-listing-skill-files/` in the workspace:

- `watch-listing-skill-files/platform-templates.md`
- `watch-listing-skill-files/posting-checklist.md`
- `watch-listing-skill-files/character-substitutions.md`

The user maintains these files directly in that folder. If they change, the updated
versions will already be there.

### Invoking the Skill

Now invoke the `watch-listing` skill. It has a 4-step approval workflow:
1. Photos — review images in the folder
2. Pricing — calculate platform prices from NET + buffer
3. Description — write tier-appropriate copy
4. Full document — generate the complete listing

Pass it these inputs:
- photo_path: full path to the listing folder
- retail_net: from WatchTrack
- wholesale_net: from WatchTrack (always include wholesale)
- brand: from folder structure
- model: from WatchTrack
- reference: from folder name
- year: from WatchTrack/web search
- case_size: from WatchTrack/web search
- case_material: from WatchTrack/web search
- movement: type + caliber from web search
- included: from WatchTrack
- condition: from user input (detailed component-level)
- tier: from user input
- buffer: 5 (unless user changed it)
- grailzee_format: from user input

After the listing skill completes, also run the `vardalux_listing_generator.py` ReportLab
script if it exists in the workspace root, to generate the styled PDF.

## Step 5: Update State and Continue

1. Add the relative path (e.g., `Cartier/9209K-WSBB0068`) to `.watcher-state.json` processed array.
2. Update `last_scan` to the current timestamp.
3. Save the file.
4. If more folders are in the queue, automatically proceed to Step 2 for the next one.
5. If the queue is empty, tell the user all ready folders have been processed.

## Error Recovery

- If WatchTrack is unreachable or the SKU isn't found, save the draft with a note and ask the user if they want to provide data manually or skip to the next folder.
- If Chrome tabs have issues, always re-call `tabs_context_mcp` to get a fresh context.
- If a session is interrupted, the draft JSON in each folder serves as recovery state — a future run can detect drafts without corresponding entries in the processed list.
