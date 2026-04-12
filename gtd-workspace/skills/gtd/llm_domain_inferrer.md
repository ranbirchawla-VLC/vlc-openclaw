# llm_domain_inferrer

Assign a domain to an idea that the Python normalizer could not match against the existing taxonomy.

## Input

```json
{
  "title": "idea title",
  "spark_note": "optional note or null",
  "domains": ["ai-automation", "watch-business", "business-improvement", "meetings-to-schedule", "home-life", "learning", "content"]
}
```

## Output

Return JSON only. No text outside the JSON block.

```json
{
  "suggested_domain": "existing-domain-or-new-slug",
  "is_new_domain": false,
  "rationale": "one sentence"
}
```

Use an existing domain when the fit is clear. Propose a new slug only when no existing domain applies. New domain slugs: lowercase, hyphen-separated, three words maximum.

## Examples

**Input:**
```json
{
  "title": "Build a tool to auto-generate watchlist valuation reports",
  "spark_note": null,
  "domains": ["ai-automation", "watch-business", "business-improvement", "meetings-to-schedule", "home-life", "learning", "content"]
}
```
**Output:**
```json
{ "suggested_domain": "ai-automation", "is_new_domain": false, "rationale": "Automation tooling for the watch business." }
```

---

**Input:**
```json
{
  "title": "Research standing desk ergonomics for the studio",
  "spark_note": "neck strain getting worse with current setup",
  "domains": ["... same list as above ..."]
}
```
**Output:**
```json
{ "suggested_domain": "home-life", "is_new_domain": false, "rationale": "Physical workspace improvement at home." }
```

---

**Input:**
```json
{
  "title": "Draft a sourcing strategy targeting estate sale channels",
  "spark_note": "met a dealer who focuses exclusively on estate pieces",
  "domains": ["... same list as above ..."]
}
```
**Output:**
```json
{ "suggested_domain": "watch-business", "is_new_domain": false, "rationale": "Watch acquisition strategy and sourcing channels." }
```
