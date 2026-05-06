# Known Issues

Issues tracked here are non-blocking carry-forwards from sub-step gates.
Each entry lists priority and the target sub-step for resolution.

---

## Documentation

**[docs] agent_api_integration_pattern.md missing OAuth user-flow pointer**
Priority: low
Target: Sub-step 6 (persona surface) or standalone docs cleanup

The integration pattern doc shows service-account credential pattern only.
Agents using OAuth 2.0 user flow (e.g., GTD/Trina) should be directed to
`gtd-workspace/docs/trina-build.md §3` for the OAuth token model.
Add a pointer in the integration pattern doc.

Added: Sub-step 1 review, 2026-05-02.

---

## Grailzee

**[test] `_apply_unnamed_filter` in test_run_analysis.py mirrors production filter expression**
Priority: low
Target: if unnamed filter logic in `run_analysis.py` grows more complex

`_apply_unnamed_filter` in `tests/test_run_analysis.py` duplicates the list
comprehension from `run_analysis.run_analysis` step 13. If the production
expression changes, the test helper must be updated in the same commit or the
unit tests silently diverge from what the pipeline actually does.

Fix: extract the filter into a named function in `run_analysis.py` (e.g.
`_filter_unnamed(references: dict) -> list[str]`) and import it directly in
the test. Only worth doing if the filter gains conditional logic or additional
parameters.

Added: 2026-05-06.

---

## Co-Work Plugin

**[ops] grailzee-local plugin has no single authoritative source; patches diverge**
Priority: medium
Target: next grailzee-cowork plugin version bump or consolidation task

`build_bundle.py` exists in at least five locations, none clearly canonical:
- `~/ai-code/vlc-openclaw/grailzee-cowork/grailzee_bundle/` (repo)
- `~/grailzee-cowork-plugin/skills/grailzee-bundle/grailzee_bundle/`
- `~/Desktop/vardalux-plugins/grailzee-cowork/grailzee_bundle/`
- `~/.claude/plugins/cache/grailzee-local/grailzee-cowork/0.1.0/skills/grailzee-bundle/grailzee_bundle/`
- `~/Library/Application Support/Claude/local-agent-mode-sessions/<session>/rpm/<plugin>/skills/grailzee-bundle/grailzee_bundle/`

The session copy is installed from the plugin cache; the plugin cache is
installed from one of the source locations (unclear which). Patches applied
to the wrong source don't propagate. The sourcing_brief fix (2026-05-06)
had to be applied to five separate files before taking effect.

Fix: designate one directory as the authoritative source (likely
`~/grailzee-cowork-plugin`), delete or symlink the others, and document
the install/update flow so future patches go to the right place first.

Added: 2026-05-06.
