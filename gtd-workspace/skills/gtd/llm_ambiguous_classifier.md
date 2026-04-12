# llm_ambiguous_classifier

Classify ambiguous input that the Python normalizer could not resolve with sufficient confidence (`needs_llm: true`).

## Input

```json
{
  "raw_input": "the original user text",
  "candidate": {
    "title": "normalizer's best guess at a title",
    "context_hint": "@phone or null",
    "priority_hint": "normal or null",
    "area_hint": "business or null",
    "missing_fields": ["intent", "context"]
  },
  "contexts": ["@phone", "@computer", "@errands", "@home", "@watch-desk", "@ai-review", "@team"]
}
```

## Output

Return JSON only. No text outside the JSON block.

```json
{
  "record_type": "task|idea|delegation|parking_lot",
  "rationale": "one sentence"
}
```

Classification rules:
- `task` — a clear next physical action the user must do
- `idea` — conceptual, exploratory, or worth revisiting later; not immediately actionable
- `delegation` — directed at a specific person; implies a waiting-for or follow-up relationship
- `parking_lot` — too ambiguous to classify reliably; capture raw

If `context_hint` is already populated (non-null), assume the context is known — focus only on distinguishing the record type.

## Examples

**Input:**
```json
{
  "raw_input": "build a watch scanning agent that finds underpriced listings",
  "candidate": { "title": "build a watch scanning agent", "context_hint": null }
}
```
**Output:**
```json
{ "record_type": "idea", "rationale": "Exploratory technical concept with no specific next action defined." }
```

---

**Input:**
```json
{
  "raw_input": "tell Alex I need the invoice numbers before Thursday",
  "candidate": { "title": "tell Alex invoice numbers before Thursday", "context_hint": null }
}
```
**Output:**
```json
{ "record_type": "delegation", "rationale": "Directed at a specific person; implies waiting on or following up with them." }
```

---

**Input:**
```json
{
  "raw_input": "that thing with the shipment",
  "candidate": { "title": "that thing with the shipment", "context_hint": null }
}
```
**Output:**
```json
{ "record_type": "parking_lot", "rationale": "Too vague to classify reliably." }
```

---

**Input:**
```json
{
  "raw_input": "send the warranty claim form for the watch I returned last month",
  "candidate": { "title": "send warranty claim form", "context_hint": null }
}
```
**Output:**
```json
{ "record_type": "task", "rationale": "Clear next physical action with a specific deliverable." }
```
