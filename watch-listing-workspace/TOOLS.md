# TOOLS.md

## Pipeline Tools

| Tool | Path | Purpose |
|------|------|---------|
| `draft_save.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/draft_save.py` | Safe read/merge/validate/write for `_draft.json`. Always use this — never write draft JSON directly. |
| `generate_listing_pdf.py` | `/Users/ranbirchawla/.openclaw/workspace/watch-listing-workspace/tools/generate_listing_pdf.py` | Generate PDF from `_Listing.md`. Pass full absolute path to the .md file. |
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
