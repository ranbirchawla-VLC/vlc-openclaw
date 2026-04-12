# OpenClaw Skill Lessons Learned

Last updated: April 8, 2026

These are hard-won lessons from building the Vardalux agent suite. Apply them
to every new skill and agent setup.

---

## Agent Setup

### 1. Every agent needs its own AGENTS.md
If you don't create one, the agent inherits the main workspace AGENTS.md and
behaves like a general assistant — loading memory, checking heartbeat, being
chatty. Every dedicated agent needs a focused AGENTS.md that:
- States exactly what the agent does
- Names the skill file to load
- Lists hard behavioral rules (no narration, no filler)
- Defines the only 3 reasons to send a message

### 2. Clear stale sessions when setting up a new agent
Old sessions carry `authProfileOverride: "anthropic:default"` which breaks
routing to the mnemo proxy. Always run:
```
rm -f ~/.openclaw/agents/{name}/sessions/*.jsonl
echo '{}' > ~/.openclaw/agents/{name}/sessions/sessions.json
```

### 3. Copy models.json to every new agent's agentDir
New agents don't get models.json automatically. Without it, the agent has no
model config and fails silently.
```
cp ~/.openclaw/agents/nutrios/agent/models.json ~/.openclaw/agents/{name}/agent/models.json
```

### 4. auth-profiles.json must exist
```
echo '{"version":1,"profiles":{}}' > ~/.openclaw/agents/{name}/agent/auth-profiles.json
```

---

## Telegram Configuration

### 5. requireMention: false is the correct field for groups
Not `mentionOnly`. Group IDs go under `groups`, not `groupAllowFrom`.
```json
"groups": {
  "-1001234567890": { "policy": "allow", "requireMention": false }
}
```

### 6. Group IDs change when a group becomes a supergroup
When you make a bot admin in a Telegram group, it upgrades to a supergroup
and gets a new chat ID (negative, starts with -100). Re-allowlist the new ID.

### 7. Bot needs admin rights to read group messages
A bot added to a group with default permissions has "no access to messages".
Make it admin or explicitly grant read access.

---

## Skill Design

### 8. Skill description drives intent routing — keep it broad
If the description is too narrow, the agent rejects valid triggers.
Example: "handles food logging" will reject "check my macros".
Include ALL trigger phrases and modes in the description frontmatter.

### 9. Be explicit about silence
Every unnecessary message costs an API call. AGENTS.md must state:
- Do NOT narrate steps
- Do NOT send status updates
- ONLY send: (1) missing field question, (2) confirmation summary, (3) hard error

### 10. Don't re-read SKILL.md every turn
If AGENTS.md says "read SKILL.md on every message", the agent will narrate
the read and burn tokens. Load the skill once at session start.

### 11. Make instructions prescriptive, not descriptive
"Extract seller info from the invoice header" → agent improvises and fails.
"Read the top section of the invoice. Extract: company name, full address,
phone, email. These are always in the header or 'From' section." → works.

---

## File I/O

### 12. exec requires absolute paths, one command at a time
No `cd`, no `&&`, no pipes, no relative paths. The exec preflight rejects them.
```
# Wrong
exec: cd /some/dir && cp file.pdf /dest/

# Right
exec: cp /full/source/path/file.pdf /full/dest/path/file.pdf
```

### 13. pdf tool can't read from Google Drive or /tmp
Copy to workspace directory first, use pdf tool, then clean up.
```
exec: cp /tmp/file.pdf /Users/ranbirchawla/.openclaw/workspace/skills/{skill}/file.pdf
pdf tool: /Users/ranbirchawla/.openclaw/workspace/skills/{skill}/file.pdf
exec: rm /Users/ranbirchawla/.openclaw/workspace/skills/{skill}/file.pdf
```

### 14. pdftotext (poppler) is the reliable PDF extractor
Native pdf tool hits size/path limits. Use the pdf_read.js tool (pdftotext
via exec) for reliable text extraction from any PDF.
```
node /Users/ranbirchawla/.openclaw/workspace/skills/purchase-intake/gmail/pdf_read.js
input: { "path": "/full/path/to/file.pdf" }
```

### 15. Session state doesn't survive resets — write to Drive
Any dedup tracking, partial state, or progress must be written to a JSON file
on Google Drive. Never rely on in-session memory for cross-turn state.

### 16. Google Drive files are local filesystem paths
No special API needed. Files are mounted at:
```
/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/{Drive Name}/
```
Use read/write tools directly with the full path.

---

## Agent Routing

### 17. Bindings use accountId to route Telegram bots
Each Telegram bot is a separate account. Route them via:
```json
"bindings": [
  { "type": "route", "agentId": "nutrios", "match": { "channel": "telegram", "accountId": "default" }},
  { "type": "route", "agentId": "grailzee", "match": { "channel": "telegram", "accountId": "grailzee" }}
]
```

### 18. New agent checklist
For each new agent:
- [ ] Create `~/.openclaw/agents/{name}/agent/` directory
- [ ] Copy `models.json` from existing agent
- [ ] Create `auth-profiles.json`
- [ ] Create `~/.openclaw/agents/{name}/sessions/` directory
- [ ] Create empty `sessions.json`
- [ ] Create dedicated workspace with focused `AGENTS.md`
- [ ] Add agent to `agents.list` in openclaw.json
- [ ] Add Telegram account to `channels.telegram.accounts`
- [ ] Add binding to `bindings`
- [ ] Add group IDs to `groups` if group chat

---

## Architecture

### 19. One agent per bot, one workspace per agent
Shared workspaces cause agents to inherit each other's AGENTS.md behavior.
Each agent needs its own workspace directory.

### 20. Never spawn Claude Code for browser work
OpenClaw native browser tool is the only reliable way to interact with web
apps (WatchTrack, etc.). Claude Code spawns don't have browser access.

### 21. No cron for on-demand work
If the user triggers the action manually via Telegram, don't add a cron job.
Cron is only for scheduled recurring tasks that run without user prompting.
