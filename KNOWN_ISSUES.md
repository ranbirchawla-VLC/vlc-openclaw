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
