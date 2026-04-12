# llm_clarification_generator

Generate a single short clarification question for a missing required field. Ask one question only. Skip fields already populated in the candidate.

Clarification order — task: `context` → `title` (if too vague) → task vs idea distinction  
Clarification order — idea: `domain` → `context` → `review_cadence`

If the field value is strongly implied by the content, infer it rather than asking.

## Input

```json
{
  "record_type": "task|idea",
  "missing_field": "context|domain|title|intent|review_cadence",
  "candidate": {
    "title": "current best-guess title",
    "context_hint": "@phone or null",
    "priority_hint": "normal or null",
    "area_hint": "business or null",
    "missing_fields": ["context", "domain"]
  },
  "taxonomy": {
    "contexts": ["@phone", "@computer", "@errands", "@home", "@watch-desk", "@ai-review", "@team"],
    "domains": ["ai-automation", "watch-business", "business-improvement", "meetings-to-schedule", "home-life", "learning", "content"]
  }
}
```

Pass only the taxonomy fields relevant to the missing field type — if `missing_field` is `context`, omit `domains`; if `missing_field` is `domain`, omit `contexts`.

## Output

Return JSON only. No text outside the JSON block.

```json
{
  "status": "clarify",
  "question": "one short sentence",
  "missing_field": "field_name",
  "options": ["value1", "value2", "value3"]
}
```

List at most 4–5 options from the user's taxonomy. Order by most likely first.

## Examples

**Input:**
```json
{
  "record_type": "task",
  "missing_field": "context",
  "candidate": { "title": "Call the customs broker", "context_hint": null },
  "taxonomy": { "contexts": ["@phone", "@computer", "@errands", "@home", "@watch-desk"] }
}
```
**Output:**
```json
{
  "status": "clarify",
  "question": "Where will you do this?",
  "missing_field": "context",
  "options": ["@phone", "@computer", "@errands"]
}
```

---

**Input:**
```json
{
  "record_type": "idea",
  "missing_field": "domain",
  "candidate": { "title": "Experiment with lighting setups for watch photography" },
  "taxonomy": { "domains": ["ai-automation", "watch-business", "business-improvement", "home-life", "learning", "content"] }
}
```
**Output:**
```json
{
  "status": "clarify",
  "question": "Which area does this idea belong to?",
  "missing_field": "domain",
  "options": ["watch-business", "content", "learning"]
}
```

---

**Input** *(last-resort: context and title have both been resolved, type is still ambiguous)*:
```json
{
  "record_type": "task",
  "missing_field": "intent",
  "candidate": { "title": "something about an auction system idea" },
  "taxonomy": {}
}
```
**Output:**
```json
{
  "status": "clarify",
  "question": "Is this a task to action, or an idea to develop?",
  "missing_field": "intent",
  "options": ["task", "idea"]
}
```
