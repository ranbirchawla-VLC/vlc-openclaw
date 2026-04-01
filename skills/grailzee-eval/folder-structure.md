# Grailzee Analyzer — Local Folder Structure

## Location

```
/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/
  Shared drives/Vardalux Shared Drive/GrailzeeData/
```

Short reference: `GrailzeeData/` on the Vardalux Shared Drive.

This lives on Google Drive alongside the Photo Pipeline. Both Claude Chat
(via the grailzee-analyzer skill) and OpenClaw (via the evaluate_deal function)
read and write here. Marissa and the team can access the output spreadsheet
directly from Drive or their synced desktop.

## Layout

```
GrailzeeData/
├── .grailzee-meta.json          ← Schema version, creation date. Do not edit.
│
├── reports/                     ← Grailzee Pro Excel files
│   ├── Grailzee_Pro_BiWeekly_Report__February_W1.xlsx
│   ├── Grailzee_Pro_BiWeekly_Report__March_W1.xlsx
│   └── ...
│
├── output/                      ← Human-readable deliverables
│   ├── Vardalux_Grailzee_Buy_Targets_March2026.xlsx
│   ├── Vardalux_Buy_Targets_Summary_2026-03-30.pdf
│   └── ...
│
├── state/                       ← Machine-readable state (both interfaces read this)
│   ├── analysis_cache.json      ← Flattened reference lookup. THE BRIDGE FILE.
│   └── run_history.json         ← Timestamped log of analysis runs
│
└── backup/                      ← Auto-rotated previous cache files
    ├── analysis_cache_20260330_141500.json
    └── ...  (last 10 kept, older auto-deleted)
```

## How Each Interface Uses This

### Claude Chat (full analyzer skill)
- **Reads from:** `reports/` (raw Grailzee Pro Excel files)
- **Writes to:** `output/` (spreadsheet + PDF), `state/analysis_cache.json`
- **Workflow:** User uploads or points to a new report → skill parses it →
  builds spreadsheet in `output/` → writes cache to `state/` → presents
  summary in conversation → Q&A

### OpenClaw (deal evaluator)
- **Reads from:** `state/analysis_cache.json` (only)
- **Writes:** Nothing. Pure read-only consumer.
- **Workflow:** Receives brand + ref + price → calls Claude with skill context →
  Claude runs evaluate_deal.py against the cache → returns structured JSON →
  OpenClaw routes to Telegram

### Human (Ranbir, Marissa, team)
- **Reads from:** `output/` — open the spreadsheet directly
- **Drops into:** `reports/` — new Grailzee Pro reports go here
- The `output/` folder is the canonical location for the current buy targets
  spreadsheet. Open it in Excel, take it on your phone, reference it in
  sourcing conversations.

## analysis_cache.json Format

This is the bridge file. Both interfaces depend on its structure.

```json
{
  "schema_version": 1,
  "generated_at": "2026-03-30T14:15:00",
  "source_report": "Grailzee_Pro_BiWeekly_Report__March_W1.xlsx",

  "references": {
    "Tudor|BB GMT Pepsi": {
      "brand": "Tudor",
      "model": "BB GMT Pepsi",
      "reference": "79830RB",
      "section": "core",
      "alternate_refs": ["M79830RB", "M79830RB-0001"],

      "median": 3150,
      "floor": 2700,
      "ceiling": 3600,
      "volume": 18,
      "quality_count": 12,
      "st_pct": 0.73,

      "max_buy_nr": 2860,
      "max_buy_res": 2810,
      "breakeven_nr": 3009,
      "breakeven_res": 3009,

      "risk_nr": 8.3,
      "risk_res": 0.0,
      "recommend_reserve": false,
      "signal": "Strong",

      "profit_nr": 141,
      "profit_res": 141,

      "trend_signal": "Stable",
      "trend_median_change": 50,
      "trend_median_pct": 1.6
    }
  },

  "dj_configs": {
    "Black/Oyster": { "...same shape..." },
    "Slate/Jubilee": { "...same shape..." }
  },

  "discoveries": {
    "SOME_REF": { "...same shape + sale_count..." }
  },

  "summary": {
    "total_references": 22,
    "strong_count": 8,
    "normal_count": 6,
    "reserve_count": 4,
    "pass_count": 1,
    "discoveries_count": 3,
    "dj_configs_count": 5
  }
}
```

## Setup (One Time)

The folder structure is created automatically on first run by write_cache.py.
If you want to set it up manually, navigate to the Vardalux Shared Drive and
create a `GrailzeeData` folder with four subfolders:

```bash
cd "/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive"
mkdir -p GrailzeeData/reports
mkdir -p GrailzeeData/output
mkdir -p GrailzeeData/state
mkdir -p GrailzeeData/backup
```

Then copy any existing Grailzee Pro report files into `GrailzeeData/reports/`.

## Backup Behavior

Every time the analyzer writes a new cache:
1. The existing `analysis_cache.json` is copied to `backup/` with a timestamp
2. The new cache overwrites the file in `state/`
3. Backups older than the 10 most recent are auto-deleted

To restore a previous cache (e.g., if a bad report was processed):
```bash
cp ".../GrailzeeData/backup/analysis_cache_YYYYMMDD_HHMMSS.json" \
   ".../GrailzeeData/state/analysis_cache.json"
```

## Schema Versioning

`.grailzee-meta.json` and `analysis_cache.json` both carry `schema_version`.
If the evaluator sees a version it doesn't recognize, it returns an error
asking for a re-run of the full analyzer. This prevents silent failures
when the cache format evolves.
