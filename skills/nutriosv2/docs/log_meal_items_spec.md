# log_meal_items — Python Contract Spec

**Status:** Draft for review, supervisor proposal
**Date:** 2026-04-30
**Branch:** `feature/nutriosv2-v2`
**Predecessor (authoritative):** `skills/nutriosv2/docs/architecture-decision-v2-meal-log-path.md`
**Canonical location after operator approval:** `skills/nutriosv2/docs/log_meal_items_spec.md`

---

## 1. Scope

This spec locks the `log_meal_items` Python tool contract and the two inner-LLM skills it invokes (semantic match, batch estimation). It resolves all five open sub-questions from the arch doc §9 plus the subprocess-vs-in-process question from the 2026-04-30 handoff. The output is the input to three TDD build prompts: one for `log_meal_items.py`, one for the semantic-match inner skill, one for the batch-estimation inner skill.

Out of scope:
- `write_meal_log` shape (unchanged; outer LLM calls it separately after `log_meal_items` returns)
- SKILL.md drafting (post-spec, blocked behind `log_meal_items` landing)
- Wispr breakfast spike scenarios (defined in Unregistration handoff; this spec is a precondition)

---

## 2. Input contract

### 2.1 Schema

```
log_meal_items(user_id: int, items: list[Item])

Item:
  description: str
  portion: float
```

Note: `user_id` is required per codebase convention (every disk-reading tool requires it); §2.1 of the original draft omitted it. The implementation adds it.

Cardinality: list-in. Always a list, even for a single item. No single-item convenience form.

### 2.2 Field constraints

**`description`:** non-empty after `.strip()`. Whitespace-only descriptions reject with `validation_error`. No length cap; the inner skills handle long descriptions naturally.

**`portion`:** strictly positive float. `portion <= 0` rejects with `validation_error`. A zero-portion entry is meaningless — if the user said "I had no rice," the outer LLM should not include the item in its parse at all. No upper bound.

### 2.3 No optional fields in v1

`meal_id` does not appear on the input. `log_meal_items` computes and returns; it does not write. The outer LLM constructs the `write_meal_log` call separately. Keeping `log_meal_items` ignorant of `meal_id` keeps compute-vs-persist clean.

### 2.4 Empty input list

`log_meal_items(items=[])` returns a valid success envelope with `items=[]`, zero totals, empty warnings. No-op rather than failure. Outer LLM should not call this with an empty list; if it does, the call is harmless.

---

## 3. Output contract

### 3.1 Success envelope

```
{
  ok: true,
  data: {
    items: list[ResolvedItem],
    totals: {calories: int, protein_g: int, fat_g: int, carbs_g: int},
    warnings: list[str]
  }
}

ResolvedItem:
  description: str            # echoed back verbatim
  source: "recipe" | "estimate"
  recipe_match: str | null    # name of matched recipe if source=recipe
  recipe_id: int | null       # ID of matched recipe if source=recipe, null otherwise
  base_macros: {calories: int, protein_g: int, fat_g: int, carbs_g: int}
  portion: float              # echoed back from input
  scaled_macros: {calories: int, protein_g: int, fat_g: int, carbs_g: int}
  notes: str | null           # per-item annotation from inner skills
```

### 3.2 Macro values are integers

All macro fields are integers. Step 4 computes `base × portion` as float and rounds to integer per item. Same rounding behavior as `calculate_macros.py`. Totals sum the rounded scaled values; small per-item rounding can accumulate but the operator has accepted this trade in prior decisions.

### 3.3 Confidence handling — per-item, not warnings list

Confidence or assumption notes from the batch-estimation inner skill bubble into the per-item `notes` field, not into the cross-item `warnings` list.

Reasoning: `notes` is per-item ("which item is uncertain"). `warnings` is for cross-item or system-level concerns. Putting per-item confidence in warnings forces the outer LLM to cross-reference indices, which is the kind of complexity the structured return is meant to eliminate.

### 3.4 Warnings list

Free-form string list. Populated when:
- Semantic match returned `null` on multi-recipe ambiguity ("multiple recipes plausibly matched 'shake'; routed to estimation").
- An inner skill succeeded only on retry (system-level note that the first attempt failed).

Empty list on the happy path.

### 3.5 Error envelope

```
{
  ok: false,
  err: {
    code: str,
    message: str,
    details: dict | null
  }
}
```

Matches the existing `common.ok` / `common.err` pattern. Build prompt verifies exact field names against `scripts/common.py`. Hard-fail with one retry on inner LLM failures; if both attempts fail, return error envelope. No partial success.

Error codes:
- `validation_error` — input failed schema or constraint validation
- `semantic_match_failed` — semantic-match inner LLM failed twice in a row
- `batch_estimation_failed` — batch-estimation inner LLM failed twice in a row
- `recipes_folder_unreadable` — Step 1 could not read the recipes folder

The outer LLM surfaces failures conversationally via SOUL/USER. No items partially logged on inner failure.

---

## 4. Internal flow

### 4.1 Step 1: exact match against recipes folder

**Read:** scan the user's recipes folder at invocation time. Disk-first means disk-at-call. No cache.

**Normalization function** applied identically to user descriptions and recipe names:

1. Lowercase
2. Strip leading articles: `a`, `an`, `the`, `my`
3. Collapse internal whitespace to single spaces
4. Strip leading and trailing whitespace

**Decision on Q1 (trailing-word stripping):** **do not strip** trailing words like `recipe`, `meal`, `bowl`. Step 1 is strict; Step 2 handles forgiving matches.

Reasoning: stripping trailing words creates false-positive risk and pushes work into Step 1 that Step 2 is purpose-built to handle. Leading-article stripping covers the common natural-speech variants ("my shake" → "shake"). Anything beyond is the semantic skill's job by design.

**Match logic:** if exactly one recipe matches the normalized description, the item resolves as `source="recipe"` with `recipe_match` set to the recipe name and `recipe_id` set to the recipe's integer ID. If zero or multiple match, the item proceeds to Step 2.

**No LLM call.** Pure Python and disk read.

### 4.2 Step 2: semantic match (inner LLM)

**Trigger:** unmatched items remaining after Step 1. If empty, skip.

**Implementation:** in-process function call. See §4.5.

**Decision on Q2 (null vs ambiguity marker):** **return `null` on ambiguity.** Items returned `null` proceed to Step 3.

Reasoning: arch doc §5.1 already commits the skill to false-negative bias, and the §5.1 prompt examples explicitly lock `null` on multi-recipe ambiguity. The ambiguity-marker alternative would force the outer LLM to reason about a new return shape mid-tool, violating "one tool call out, one structured result back." Falling through to estimation gives the user approximately-right macros; the user owns disambiguation by naming recipes more distinctly. This is the documented user contract.

When the skill returns a recipe name, the item resolves as `source="recipe"` with `recipe_match` set to the matched name and `recipe_id` set to the recipe's integer ID (looked up from the recipe record by name).

When the skill returns `null` on multi-recipe ambiguity, Step 2 appends a warning: `"Multiple recipes plausibly matched '<description>'; routed to estimation. Consider renaming for distinct match."`

### 4.3 Step 3: batch estimation (inner LLM)

**Trigger:** items still unmatched after Step 2. If empty, skip.

**Implementation:** in-process function call. See §4.5.

**Decision on Q3 (model pin):** **`claude-sonnet-4-6`**, matching the existing `estimate_macros_from_description` pattern.

Reasoning: estimation quality is the variable that affects user trust. The bot is already on Sonnet 4 with high thinking; the inner LLM is not the latency bottleneck. Per the operator's framing — *"Wired the smartest way; Python should be fast, the LLM is the slow part"* — don't trade quality for speed at the inner-skill layer. Build at Sonnet first; revisit only with cost or latency data.

**Behavior:** receives quantifier-free food descriptions, returns per-unit base macros for each. See §6.2 for the prompt spec. Estimation-resolved items have `recipe_match: null` and `recipe_id: null`.

### 4.4 Step 4: portion math and totals

For each resolved item:
1. `scaled_macros = scale_macros(base_macros, portion)` where `scale_macros` is imported from `calculate_macros.py`.
2. Append the `ResolvedItem` to the items list.

**Totals:** sum of all `scaled_macros` across items.

**Decision on Q5 (portion math implementation):** **import the function from `calculate_macros.py`.** Do not shell out (subprocess overhead per item). Do not duplicate the math (drift risk).

If `calculate_macros.py` is currently script-only (sys.argv-driven, no callable function exposed), the build step refactors: extract the math into a callable function; the existing script wraps it. Trivial change. Spec defers verification to TDD time.

This keeps `calculate_macros.py` as the single source of truth for portion math, both for the now-internal-only tool surface and for `log_meal_items` Step 4.

### 4.5 Inner skill execution: in-process function calls

**Decision on subprocess-vs-in-process:** **in-process function calls.** Each inner skill is a Python module under `scripts/inner_skills/` with a callable function that makes its own Anthropic API call (temperature 0, structured JSON, hard-fail with one retry).

```
scripts/inner_skills/
  semantic_match.py       # match_recipes(unmatched_items, recipe_names) -> list[str | None]
  batch_estimate.py       # estimate_macros(descriptions) -> list[BaseMacrosOrError]
```

Reasoning against subprocess (which would mirror `estimate_macros_from_description`):
- Python interpreter cold-start cost on every inner call.
- OTel wiring across subprocess boundaries is more complex than in-process spans.
- Test surface: subprocess requires mocking the subprocess; in-process mocks the API client directly, which is closer to what production runs.
- The existing subprocess pattern was correct for separate tools the agent calls independently. `log_meal_items` orchestrates these inner skills as part of its own implementation; they are not LLM-facing tools.

**Pushback flag:** the alternative is subprocess for pattern parity with the existing `estimate_macros_from_description.py`. Supervisor lean is in-process. If you prefer parity, this flips cleanly — affects build-prompt structure but not the spec's external shape.

**API client:** mirror the existing convention in `estimate_macros_from_description.py`. Build prompt verifies the exact import and instantiation pattern.

---

## 5. Recipe surfacing path

**Decision on Q4:** **both reads happen, separately.**

### 5.1 `log_meal_items` reads recipes folder at invocation

Step 1 reads recipe filenames (or normalized form) from the user's recipes folder when `log_meal_items` is called. No cache. Non-negotiable per the disk-first rule.

### 5.2 `context_builder.py` injects recipe names into outer LLM context

The outer LLM also needs to know recipe names so it can phrase replies correctly ("logged your tikka lunch") and recognize when the user is referencing a known recipe. Small extension to `context_builder.py`:

- Add a recipe-list section to the injected context block.
- Format: names only, alphabetical (matches the v1 list-flow read-back format that survives in v2 locks).
- Source: same recipes folder read by Step 1, but called at outer LLM turn start, not at tool invocation.

### 5.3 Read consistency across the two paths

The two reads can disagree if the user adds a recipe between context build (turn start) and tool invocation (mid-turn). For v1, accept the corner case: the outer LLM may not see a just-added recipe in the same turn, but `log_meal_items` will. Next turn rebuilds the context block.

---

## 6. Inner skill prompt specs

Spec-level only. Actual prompt strings get drafted at build time, with operator review of each prompt before TDD lands.

### 6.1 Semantic-match prompt

**Purpose:** match colloquial recipe references against an explicit recipe list, biased toward false negatives.

**Inputs:**
- `unmatched_items`: list of normalized item descriptions
- `recipe_names`: list of recipe names from the user's recipes folder

**Output:** JSON list, same length as `unmatched_items`, each element a recipe name (verbatim from `recipe_names`) or `null`.

**Critical rules stated in the prompt:**

1. Match only when the user's description clearly names or paraphrases a specific recipe in the list. Match by name reference, not by category, cuisine, or general similarity.
2. If multiple recipes plausibly match, return `null` for that item. Let it fall through to estimation.
3. If no recipe in the list is a clear match, return `null`. Do not invent a match.
4. Different restaurants are different recipes. "Qdoba bowl" and "Chipotle bowl" do not match each other regardless of similarity.
5. Categories are not recipes. "Thai noodles" does not match "Pad Thai."
6. Variations and shortenings of a single recipe name match. "Tikka lunch" matches "Chicken Tikka Lunch Bowl" if it is the only tikka recipe.

**Examples in prompt:** the four examples from arch doc §5.1, verbatim. They came out of an operator-led conversation and capture the rule shape better than any rewording.

**API call shape:**
- Model `claude-sonnet-4-6`, temperature 0
- Structured JSON return, schema-validated
- Retry once on malformed return; hard-fail on second failure

**Prompt size discipline:** rules + four examples + recipe list + unmatched items. No worked breakfast scenarios. Examples illustrate the rule; they do not teach the LLM how to handle a Wispr breakfast (that becomes a flowchart, same lesson as SKILL.md).

### 6.2 Batch-estimation prompt

**Purpose:** estimate per-unit macros for a list of food descriptions in a single LLM call.

**Inputs:**
- `descriptions`: list of food description strings, quantifier-free (the outer LLM separates quantifier from food at parse time).

**Output:** JSON list, same length as `descriptions`. Each element is a `BaseMacros` object with `calories`, `protein_g`, `fat_g`, `carbs_g` (integers) plus optional `notes` for ambiguous-unit assumptions.

**Critical rules stated in the prompt:**

1. Estimate macros for **one unit** of the described food. Ignore quantifiers in the description; quantity scaling happens in Python after this returns. "Two eggs" returns macros for one egg. "Half an avocado" returns macros for one whole avocado.
2. If "one unit" is genuinely ambiguous (e.g., "rice" — cup, bowl, side?), default to a typical single serving and note the assumption in `notes`. The user clarifies by being more specific or defining a recipe.
3. Return integers for all macro fields. Round to nearest integer.

**API call shape:**
- Model `claude-sonnet-4-6`, temperature 0
- Structured JSON return, schema-validated
- Retry once on malformed return; hard-fail on second failure

**Prompt size discipline:** rules + a few examples illustrating the quantifier-free rule and the ambiguous-unit default. No multi-item breakfast worked scenarios.

---

## 7. Test scenarios

The TDD build for `log_meal_items.py` satisfies these scenarios. Inner-skill test coverage lives in their own build prompts.

### 7.1 Resolution path coverage

1. **All exact match.** All items resolve via Step 1. No inner LLM calls. Verifies disk-first path and normalization.
2. **All semantic match.** All items resolve via Step 2. One inner LLM call. Verifies Step 1 → Step 2 handoff and result merging.
3. **All estimation.** All items resolve via Step 3. One inner LLM call. Verifies Step 2 → Step 3 handoff.
4. **Mixed.** Input contains items that resolve at Step 1, items that resolve at Step 2, and items that resolve at Step 3. Two inner LLM calls. Verifies the full waterfall and result assembly across sources.

### 7.2 Input edge cases

5. **Empty input list.** Returns success with empty items, zero totals, no warnings. No inner LLM calls.
6. **Single item.** Verifies cardinality discipline (list-in, no shortcut).
7. **Description with extra whitespace.** `"  two   eggs  "` validates after strip; proceeds normally.
8. **Empty / whitespace-only description.** Rejects with `validation_error`.
9. **`portion <= 0`.** Rejects with `validation_error`.
10. **`portion = 0.001`.** Validates. Trivially small portion produces near-zero scaled macros.
11. **Very large portion.** Validates. No upper bound.

### 7.3 Inner LLM failure modes

12. **Semantic-match retry success.** First call returns malformed JSON; second call succeeds. Result envelope succeeds; warnings list includes a system-level note about the retry.
13. **Semantic-match hard-fail.** Both calls fail. Returns error envelope with code `semantic_match_failed`.
14. **Batch-estimation retry success.** Mirror of #12.
15. **Batch-estimation hard-fail.** Mirror of #13.

### 7.4 Step 1 specifics

16. **Article variation matches.** Recipe "Recovery Shake"; description "my recovery shake" → matches.
17. **Multi-recipe ambiguity at Step 1.** Recipes "Morning Shake" and "Evening Shake"; description "shake" → Step 1 returns no match; item proceeds to Step 2; Step 2 returns `null`; item proceeds to Step 3.
18. **Internal whitespace collapses.** Recipe "Chicken  Tikka  Bowl" (double-spaced); description "chicken tikka bowl" → matches after normalization.

### 7.5 Recipes folder edge cases

19. **Empty recipes folder.** All items proceed to Step 2 (which can only return `null`), then to Step 3. No errors.
20. **Recipes folder unreadable.** Returns error envelope with code `recipes_folder_unreadable`. Defensive case.

### 7.6 Output assembly

21. **Items returned in input order.** Output list aligns positionally with input.
22. **Totals correctness.** For a known set of base macros and portions, totals match the expected sum within rounding.
23. **`notes` and `warnings` populate correctly.** Scenario constructed to produce both.

Inner-skill specs (semantic-match, batch-estimation) carry their own focused test scenarios in their respective build prompts.

---

## 8. Build sequence

Single spec, three TDD build prompts:

1. **`log_meal_items.py`** — orchestration, Step 1 normalization, Step 4 portion math, output assembly, error envelope. Inner skills mocked at this layer; integration against real implementations after both inner-skill builds land.
2. **`scripts/inner_skills/semantic_match.py`** — semantic-match prompt and Anthropic API call. Tested against synthetic recipe lists and item descriptions; the four arch-doc examples are explicit fixtures.
3. **`scripts/inner_skills/batch_estimate.py`** — batch-estimation prompt and Anthropic API call. Tested against quantifier-free descriptions and ambiguous-unit cases.

After all three land:

4. Register `log_meal_items` in plugin and `tools.allow`. Do not yet unregister `estimate_macros_from_description` or `calculate_macros`.
5. Update `context_builder.py` for the recipe-list injection per §5.2.
6. SKILL.md draft against the new tool surface (separate session per Unregistration handoff).
7. Wispr breakfast spike — four scenarios from Unregistration handoff. Gate 3 for the entire `log_meal_items` build sequence rolls into the spike.

Each build prompt follows the two-commit gate pattern from `CLAUDE.md`: TDD-first, code-reviewer subagent in fresh context, two-commit pattern when fixes are warranted.

---

## 9. Open items deferred to build prompts

Codebase verification at TDD time, not architectural decisions:

1. Exact `common.ok` / `common.err` field names: build prompt reads `scripts/common.py` and confirms.
2. Whether `calculate_macros.py` exposes a callable function or is script-only. If script-only, build refactors to expose the math.
3. Pydantic model conventions for input validation: build matches the convention in nearby tools.
4. Anthropic client instantiation pattern: build mirrors `estimate_macros_from_description.py`.
5. Recipe filename vs recipe-id-from-folder-contents: build prompt reads the existing recipe folder structure (likely filename-based per Session 2 data model) and confirms.

---

*End spec. Next action after operator approval: build prompt for `log_meal_items.py`. Inner-skill specs convert to build prompts after `log_meal_items.py` lands and tests cleanly.*
