# TOOLS.md

## Pipeline Tools

| Tool | Path | Purpose |
|------|------|---------|
| `draft_save.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py` | Safe read/merge/validate/write for `_draft.json`. Always use this — never write draft JSON directly. |
| `generate_listing_pdf.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/generate_listing_pdf.py` | Generate PDF from `_Listing.md`. Pass full absolute path to the .md file. |
| `run_pricing.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_pricing.py` | Calculate all platform prices from `inputs.retail_net`. Writes `pricing.*` to draft. |
| `run_phase_b.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_phase_b.py` | Assemble full `_Listing.md` from canonical + templates. Requires step 3.5. |
| `run_grailzee_gate.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_grailzee_gate.py` | Evaluate Grailzee deal viability. Posts recommendation, sets `grailzee_format`. |
| `run_char_subs.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_char_subs.py` | Apply Facebook character substitutions. Called internally by run_phase_b. |
| `run_checklist.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/run_checklist.py` | Generate platform posting checklist. Called internally by run_phase_b. |

## Known Feature Gaps (backlog)

- `run_pricing.py` — no per-platform override without re-entering retail_net.
  Fix: add `--override platform=price` flag (e.g. `--override ebay=15999`) that
  writes directly to `pricing.<platform>.list_price` without recalculating.
 - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## WatchTrack

- **URL:** https://watchtrack.com/store
- **Browser:** OpenClaw browser tool, `profile: openclaw`
- **Status:** Always kept logged in — never attempt to authenticate

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
