# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## Grailzee Data Paths

These are hardcoded in `scripts/grailzee_common.py` via `GRAILZEE_ROOT`. Never search for them — go straight here.

```
GRAILZEE_ROOT = /Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData
```

| Purpose | Path |
|---|---|
| Incoming reports (xlsx) | `$GRAILZEE_ROOT/reports/` |
| Ingested CSVs (trend window) | `$GRAILZEE_ROOT/reports_csv/` |
| State files (cycle_focus, etc.) | `$GRAILZEE_ROOT/state/` |
| Output (xlsx, summaries) | `$GRAILZEE_ROOT/output/` |
| Briefs | `$GRAILZEE_ROOT/output/briefs/` |
| Backup | `$GRAILZEE_ROOT/backup/` |

### Staging / Incoming (secondary)

Reports sometimes land here first before being moved to `reports/`:
```
.../Vardalux Shared Drive/Market Intel/Grailzee Data Input and Processing/Incoming/
```

### Workspace root

```
/Users/ranbirchawla/.openclaw/workspace/skills/grailzee-eval/
```

---

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
