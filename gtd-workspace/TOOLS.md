# Tools — GTD Workspace

Environment-specific configuration. Keep this separate from shared skills.

---

## Python Tools

| Tool | Purpose | Invocation |
|------|---------|-----------|
| `common.py` | Shared schema loading, path resolution, task store I/O helpers | Imported by other tools |
| `gtd_normalize.py` | Parse raw captures (text, voice transcript, structured) into task/idea/parking_lot schema | `python3 tools/gtd_normalize.py '<raw_input>'` |
| `gtd_validate.py` | Validate a JSON object against the appropriate schema | `python3 tools/gtd_validate.py <type> <file.json>` |
| `gtd_write.py` | Persist validated items to the task store — never write directly | `python3 tools/gtd_write.py <item.json>` |
| `gtd_query.py` | Query stored items by context, area, tag, status, or type | `python3 tools/gtd_query.py --context "@computer" --status active` |
| `gtd_review.py` | Surface items for daily/weekly review; flag stale next actions | `python3 tools/gtd_review.py --mode weekly` |
| `gtd_delegation.py` | Track delegated tasks, follow-up cadence, and resolution | `python3 tools/gtd_delegation.py --action list --status pending` |

---

## Paths

```
task_store:    (set after bootstrap)
pipeline_root: ~/.openclaw/workspace/gtd-workspace/
schemas:       references/schemas/
taxonomy:      references/taxonomy.json
```

---

## Notes

Add environment-specific paths, device nicknames, or tool quirks here.
Do not put shared skill logic here — that belongs in skills/gtd/SKILL.md.
