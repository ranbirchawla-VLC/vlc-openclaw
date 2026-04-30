# Architecture Decision: v2 Meal-Log Path

**Status:** Locked, pending build spec
**Date:** 2026-04-30
**Branch:** `feature/nutriosv2-v2`
**Relationship to existing docs:** Addendum to `architecture-decision-v2.md`. Specifies the meal-log tool surface at a granularity the parent doc did not. Where this addendum and the parent doc disagree on the meal-log path, this addendum is authoritative.
**Canonical location after operator approval:** `skills/nutriosv2/docs/architecture-decision-v2-meal-log-path.md`

---

## 1. Why this exists

`architecture-decision-v2.md` established the v2 architectural commitment: LLM for synthesis and judgment; Python for everything deterministic; never compute; never infer the date; recipes and other context-resident facts are read from disk, not reconstructed from training. That document was written before the meal-log path was specified at tool granularity.

The meal-log path is the highest-traffic surface in the bot. The Wispr breakfast spike is the customer-outcome test that decides whether v2's premise actually holds. To run that spike correctly, the tool surface underneath the outer LLM has to be unambiguous; today it is not. This addendum specifies the meal-log path in the shape required for the spike, with the architectural commitments preserved.

## 2. The user outcome being delivered

The user opens Wispr Flow, dictates a paragraph describing a meal in their natural voice, and gets back a conversational confirmation that the meal was logged correctly. Numbers are right. Date is right. Recipes the user has defined are read from disk every time, ensuring consistent macros across logs of the same recipe. Ad-hoc items the user has not defined are estimated fresh each time; the user accepts that estimation is best-effort. Everything resolves in one outer LLM turn for the happy path.

The example that defines pass:

> *"Okay so for breakfast I had my morning shake, two eggs, half an avocado, and a coffee with oat milk."*

Returns: a meal log entry with shake macros pulled from the user's defined recipe, eggs estimated at two units, avocado at half a unit, coffee with oat milk as one serving. Totals computed in Python. Conversational reply from the bot reading the totals back without procedural narration.

## 3. Why the existing tool surface fails the user outcome

Discovery on the v2 surface at HEAD `b8132e8` surfaced an unresolved contract between the two macro tools the LLM has access to:

- `estimate_macros_from_description("two eggs")` returns macros for two eggs.
- `estimate_macros_from_description("egg")` returns macros for one egg.
- `calculate_macros(base, portion=2)` doubles whatever's in `base`.

So *"two eggs"* can be handled two ways: (a) `estimate("two eggs")` once, or (b) `estimate("egg")` then `calculate(base, portion=2)`. Both produce numbers; the numbers differ because the downstream LLM rounds at different scales. Neither path is documented as canonical.

For a multi-item Wispr breakfast, the outer LLM has to resolve this routing per item, sequence multiple tool calls, hold partial state across calls, and assemble the final log. That is the v1 sequencer-mode failure pattern surfacing in the tool layer instead of the orchestration layer. Code review cannot catch it. Only customer-outcome failure exposes it; by then the architectural premise looks broken.

## 4. The locked architecture

One new tool, `log_meal_items`, becomes the entry point for the meal-log path. The outer LLM (Sonnet at high thinking) parses the dictation into a structured list and calls `log_meal_items` once. Inside the tool, Python orchestrates a deterministic sequence: disk-first lookup against recipes, semantic-match attempt for any unmatched items, batch estimation for any still-unmatched items, portion application, totals. The outer LLM sees one tool, calls it once, gets one structured result back.

### 4.1 Tool contract (shape locked, exact schema deferred to spec phase)

```
log_meal_items(items: list[{description: string, portion: float}])
→ {
    items: list[{
      description: string,         # echoed back verbatim
      source: "recipe" | "estimate",
      recipe_match: string | null, # name of matched recipe if source=recipe
      base_macros: {calories, protein_g, fat_g, carbs_g},
      portion: float,
      scaled_macros: {calories, protein_g, fat_g, carbs_g}
    }],
    totals: {calories, protein_g, fat_g, carbs_g},
    warnings: list[string]         # ambiguous matches, low-confidence estimates, etc.
  }
```

Cardinality: list-in, structured-result-out. Always a list, even for a single item. No single-item convenience form.

The tool computes and returns; it does not write. The outer LLM decides whether to call `write_meal_log` based on the result. For the happy path (no warnings, no ambiguity), the outer LLM calls `write_meal_log` immediately in the same turn. For ambiguous cases, the outer LLM has the option to surface to the user first. Two tool calls in one outer turn is the normal happy-path pattern; the operator's "one outer LLM call" goal refers to one Sonnet turn, which can compose multiple tool calls without conversation between them.

### 4.2 Internal flow

For each item in the input list:

**Step 1: Exact match against recipes folder.**
Read the recipe filenames or recipe IDs from the recipes folder on disk. Normalize the input description and the recipe names with the same normalization function (lowercase; strip leading articles; collapse whitespace). If exactly one recipe matches, mark the item resolved with `source="recipe"`. No LLM call.

**Step 2: Semantic match for unmatched items.**
Collect all items not resolved in Step 1. If the unmatched list is empty, skip this step. Otherwise, make one inner LLM call to a dedicated semantic-match skill. The skill receives the unmatched item descriptions and the full recipe name list; for each unmatched item, it returns either a single recipe name or `null`. Items that match are marked resolved with `source="recipe"`. Items returned `null` proceed to Step 3.

**Step 3: Batch estimation for still-unmatched items.**
Collect all items not resolved in Steps 1 or 2. If the list is empty, skip this step. Otherwise, make one inner LLM call to a dedicated batch-estimation skill. The skill receives the list of food descriptions and returns per-unit base macros for each. Items are marked resolved with `source="estimate"`.

**Step 4: Portion application and totals.**
For every resolved item, multiply the base macros by the user-supplied portion (deterministic Python; same math as `calculate_macros`). Sum scaled macros across items to produce totals. Return the structured result.

Maximum two inner LLM calls per `log_meal_items` invocation, regardless of input size. Often one. Sometimes zero (all known with exact matches).

## 5. Inner LLM behaviors

The inner LLMs are skills, not free-reasoning agents. Each has a tightly scoped prompt with explicit constraints. Both follow the existing `estimate_macros_from_description` pattern: direct Anthropic API call, temperature 0, structured JSON return, hard-fail with one retry.

### 5.1 Semantic-match skill

**Purpose:** resolve colloquial recipe references against an explicit recipe list. The user says *"my tikka lunch"* and the bot finds the right recipe even though the recipe is filed under a longer formal name.

**Critical rule, stated explicitly in the prompt:** the skill matches only when the user's description clearly names or paraphrases a specific recipe in the list. The skill does not match by category, cuisine, or general similarity. If no recipe in the list is a clear match, the skill returns `null` for that item.

**Examples of correct match behavior:**

- User has one recipe named "Chicken Tikka Lunch Bowl." User says *"log my tikka lunch."* Match. The user is naming the recipe in shorter form.
- User has one recipe named "Chicken Tikka Lunch Bowl." User says *"log my tikka masala lunch."* Match. The user is naming the recipe with a slight variation; there is only one tikka recipe in the list, and the user clearly intends it.
- User has two recipes: "Chicken Tikka Lunch Bowl" and "Recovery Shake." User says *"log my tikka lunch."* Match to Chicken Tikka Lunch Bowl. The other recipe is unrelated.

**Examples of correct non-match behavior; the skill must return `null`, not invent a match:**

- User has one recipe named "Recovery Shake." User says *"log my tikka lunch."* No match. The skill must not match "tikka lunch" to "Recovery Shake" just because both are foods on the list. Return `null`; the item proceeds to estimation.
- User has one recipe named "Qdoba Chicken Bowl." User says *"log my Chipotle chicken bowl."* No match. Qdoba and Chipotle are different restaurants with different macros. The user did not name the Qdoba recipe; they named a Chipotle bowl. The skill must return `null`. The item proceeds to estimation. Matching here is the failure mode the rule exists to prevent: silent substitution of a similarly-named recipe whose macros differ from what the user actually ate.
- User has one recipe named "Pad Thai." User says *"log my Thai noodles."* No match. "Thai noodles" is a category, not a recipe reference. The skill must return `null`. If the user meant Pad Thai, they should say Pad Thai or define the recipe under a name that matches their natural speech.
- User has recipes for "Morning Protein Shake" and "Recovery Shake." User says *"log my shake."* Two recipes plausibly match. The skill returns `null` and the item proceeds to estimation; user owns the disambiguation by naming their recipes more distinctly or dictating more specifically.

**The general rule the prompt states:** prefer false negatives (return `null` when uncertain) over false positives (match the wrong recipe). A wrong match silently logs the wrong macros under an authoritative-looking source; the user notices days later when their totals drift. A false negative routes the item to fresh estimation; the user gets approximately-right macros and can correct by logging again or defining the recipe explicitly. The cost asymmetry justifies the bias.

### 5.2 Batch-estimation skill

**Purpose:** estimate per-unit macros for a list of ad-hoc food descriptions in a single LLM call.

**Critical rule, stated explicitly in the prompt:** the skill estimates macros for one unit of each described food, ignoring quantifiers in the description. Quantity scaling happens in Python after the skill returns. If the description is *"two eggs"*, the skill returns macros for one egg. If the description is *"half an avocado"*, the skill returns macros for one whole avocado. The portion field on the parent tool input handles the scaling.

This is a deliberate shift from the current `estimate_macros_from_description` behavior, which interprets quantifiers itself. The shift makes the inner skill deterministic in shape ("one unit of X") and moves all portion math to a single point (Step 4). The outer LLM's job is to separate quantifier from food when parsing the dictation; the skill assumes quantifier-free descriptions.

**The prompt also states:** if a description is genuinely ambiguous about what "one unit" means (for example, *"rice"* could be a cup, a bowl, or a side), the skill defaults to a typical single serving and notes the assumption in a `confidence` or `notes` field returned alongside the macros. The user can clarify by being more specific in the dictation, or by defining a recipe.

### 5.3 Error handling

Hard-fail with one retry, matching the existing `estimate_macros_from_description` pattern. If an inner LLM returns malformed JSON or fails schema validation, the same prompt is retried once at temperature 0. If the second attempt fails, the entire `log_meal_items` call fails with a structured error returned to the outer LLM. The outer LLM surfaces the failure to the user conversationally; no items are partially logged.

Partial-success returns (some items resolved, others failed) are deliberately out of scope for v1. See §7.

## 6. Disk-first matching rule, in detail

**Step 1's exact-match logic** uses a normalization function applied identically to the user's description and to recipe names on disk:

1. Lowercase.
2. Strip leading articles (`a`, `an`, `the`, `my`).
3. Collapse internal whitespace to single spaces.
4. Strip leading and trailing whitespace.

If exactly one recipe matches after normalization, the item is resolved as `source="recipe"`. If multiple recipes match (rare; suggests the user has poorly named recipes), Step 1 returns no match for that item and it proceeds to semantic match. If zero recipes match, the item proceeds to semantic match.

The user owns ambiguity. If the user has two recipes named confusingly close ("Morning Shake" and "Evening Shake") and dictates *"log my shake,"* the system makes its best inference via semantic match; if the inference is wrong, the user fixes it manually by re-logging or by renaming the recipes. This is the documented user contract; it is the consequence of choosing forgiving matching over strict matching, and the operator has explicitly accepted it.

## 7. What is deliberately out of scope

The following were considered and excluded from v1 of this design. They may be reconsidered later, but only with explicit architectural discussion. They are not omissions; they are decisions.

**Memo cache for ad-hoc estimates.** Caching the result of *"half an avocado"* across logs would save tokens but would silently freeze a number that the user may want re-estimated. The user already has a clear path for "remember this": define a recipe. No memo cache.

**Partial-success returns.** If the batch-estimation inner LLM returns six items good and one malformed, the temptation is to return six successes and surface the one error to the outer LLM. This adds shape complexity (the outer LLM has to reason about partial results) and creates a class of bugs where some items log and others do not. v1 hard-fails the entire call on any inner failure; the outer LLM surfaces the failure conversationally and the user retries. If observed retry rates make this painful in production, revisit.

**Semantic match returns ambiguity markers.** If the user has two equally plausible recipes for *"shake,"* one design has the semantic-match skill return an ambiguity marker that the outer LLM surfaces to the user as a clarifying question. The other design has the skill return `null` and let the item fall through to estimation. The first is more user-friendly; the second is structurally simpler and avoids dragging the outer LLM into mid-tool conversational logic. Decision deferred to spec phase; see §9.

**`log_meal_items` writing directly.** The tool computes and returns; it does not write. The outer LLM calls `write_meal_log` separately. This adds one tool call per turn but preserves clean separation between compute and persist, and lets the outer LLM mediate ambiguous cases before writing.

**Cross-meal totals.** This tool handles a single meal entry. Daily totals, weekly totals, and reconciliation against the active mesocycle are the job of `get_daily_reconciled_view` and other tools that already exist.

**Concurrent inner LLM calls.** The two inner LLM calls (semantic match and batch estimation) are sequential, not parallel. Step 3's input depends on what Step 2 left unmatched. Performance is not the constraint; sequential is fine.

**Recipe ingredient decomposition.** When a recipe is matched in Step 1 or 2, the tool returns the recipe's stored macros directly. It does not look up individual ingredients of the recipe. Recipes are atomic units of nutritional truth; the user defines them at the granularity they want.

## 8. Connections to existing architecture

**`estimate_macros_from_description`.** Becomes internal-only. The new batch-estimation skill replaces it for the meal-log path. The existing tool's removal from `tools.allow` is a follow-up architectural decision; it should not be unregistered until `log_meal_items` lands, is verified in the Wispr spike, and is confirmed to cover all meal-log paths the existing tool currently serves. Stage-gate the unregistration.

**`calculate_macros`.** Becomes internal-only by the same logic. Step 4's portion math is deterministic Python that mirrors `calculate_macros`'s math. Whether `log_meal_items` shells out to `calculate_macros.py`, imports its function directly, or duplicates the (trivial) math is a build-time decision; the architectural rule is that no portion math happens in the LLM. Same staged unregistration; do not remove from `tools.allow` until `log_meal_items` is verified.

**`write_meal_log`.** Unchanged. The outer LLM calls it after `log_meal_items` returns successfully.

**`write_recipe`.** Unchanged. The user (via the bot) defines recipes; `log_meal_items` reads them.

**`context_builder.py`.** May need a small extension to surface the recipe filename list (or normalized form) into the context block so the outer LLM knows which recipes exist and can phrase the user-facing reply with the right names. `log_meal_items` reads the recipes folder directly at invocation time regardless; the two reads share a source. Build-time decision on whether `context_builder` needs touching.

**SOUL.md and USER.md.** Unchanged. They handle voice. They were load-bearing before this addendum; they remain so.

**SKILL.md.** Will need to describe `log_meal_items` and the architectural commitment that the outer LLM's job is to parse the dictation into structured items, not to compute or sequence. The principles already locked for SKILL.md (never compute; never infer the date; never fabricate context-resident facts) extend cleanly to this design without modification.

## 9. Open sub-questions, deferred to spec phase

These are real decisions, but they do not require architectural debate. They will be resolved at the spec-phase build prompt.

1. Exact-match normalization: should trailing words like `recipe`, `meal`, `bowl` be stripped, or only when not present in the recipe name?
2. Semantic match ambiguity: return `null` (let item fall through to estimation) or return an ambiguity marker (let the outer LLM ask)?
3. Batch-estimation skill: which model pin? `claude-sonnet-4-6` matching the existing `estimate_macros_from_description` pattern, or something faster like Haiku for the cost profile?
4. Recipe surfacing: does `log_meal_items` read the recipes folder directly at invocation, and does `context_builder` also need to inject the recipe list into the outer LLM's context so it can phrase replies correctly?
5. Portion math implementation: does `log_meal_items` shell out to `calculate_macros.py`, import its function, or duplicate the math inline?

## 10. Spike implications

The Wispr breakfast spike was originally scoped against the old tool surface. With `log_meal_items` in place, the spike is structurally simpler: the outer LLM parses, calls `log_meal_items` once, calls `write_meal_log` once, replies conversationally. The spike's success criteria are unchanged:

- All items get logged (writes land).
- Numbers correct (Python returned them; LLM didn't compute).
- Response feels conversational, not procedural.
- Date context correct ("what day is it?" mid-session).

What changes: failure-mode interpretations from the prior spike scope no longer apply directly. With `log_meal_items` in the loop, scenario 3 failure decomposes into specific layers:

- Outer LLM parsed the dictation wrong (missed an item, mis-extracted a portion). Failure surfaces in the items list before the inner LLMs are called. SKILL.md issue.
- Disk-first match missed a recipe the user has defined. Tool issue (normalization).
- Semantic match invented a wrong recipe match. Inner-skill prompt issue.
- Batch estimation returned wrong macros. Inner-skill prompt or model-pin issue.
- Portion math wrong. Python bug; rare, since the math is the same as `calculate_macros` which is well-tested.
- Conversational reply procedural. SOUL or USER not pulling weight as expected.

Each failure mode now has a specific layer to investigate. That is the point.

Gate 3 for `log_meal_items` is rolled into the Wispr spike per supervisor decision earlier this session: scenarios 1 through 4 collectively serve as the release check.

## 11. Build sequence (high level)

Each step lands as its own sub-step under CLAUDE.md's gate definition: TDD-first; code-reviewer subagent in fresh context; two-commit pattern when fixes are warranted.

1. Specify the Python contract for `log_meal_items` (input/output schema, error envelope) in a build-spec doc; resolve open sub-questions 1, 4, and 5 there.
2. TDD-build `log_meal_items.py` against the spec.
3. Specify and prompt-engineer the semantic-match inner skill; resolve open sub-question 2 there.
4. Specify and prompt-engineer the batch-estimation skill; resolve open sub-question 3 there.
5. Register `log_meal_items` in the plugin and `tools.allow`. Do not yet unregister `estimate_macros_from_description` or `calculate_macros`.
6. Update `context_builder.py` if the §8 decision goes that way.
7. Draft compact SKILL.md against the locked v2 surface plus `log_meal_items`.
8. Run the Wispr breakfast spike. All four scenarios.
9. If spike clean, stage-gate the unregistration of `estimate_macros_from_description` and `calculate_macros`. Decide based on observed paths during the spike whether either has remaining LLM-facing utility.

---

*End architecture decision addendum. Next action after operator approval: spec the `log_meal_items` Python contract.*
