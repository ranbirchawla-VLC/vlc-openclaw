# ADR Addendum: Mesocycle Tool Surface — Sun→Sat Weekday Ordering

**Status:** Locked
**Date:** 2026-05-02
**Branch:** `feature/nutriosv2-v2`
**Supersedes:** Three weekday-ordering clauses in `architecture-decision-mesocycle-tool-surface.md`:
- §2.1 output spec ("7 rows, ordered monday → sunday")
- §2.3 row shape ("array of 7 rows, ordered Monday through Sunday")
- §5.2 Step 2 validator ("enforce ordering Monday → Sunday")

All other clauses of the base ADR stand unchanged.

---

## 1. The decision

`macro_table` rows are ordered **Sunday → Saturday**. `rows[0].weekday == "sunday"`, `rows[6].weekday == "saturday"`. Validators in the row model and in Step 2 enforce this order. Weekday uniqueness rule from base ADR §5.2 is unchanged.

## 2. Reasoning

Operator decision, supervisor session 2026-05-02. The base ADR pinned Mon→Sun without flagging the ordering as a decision needing operator confirmation. Surfaced as a separate decision per the operating rule that ADR-locked clauses are amended deliberately, not silently.

Sun→Sat aligns with the operator's calendar mental model. The ordering is downstream-trivial: every consumer reads `macro_table` rows by weekday name (base ADR §3.2), so positional iteration order does not change lookup logic in `meal_log`, `today_view`, or future reminders.

## 3. Scope of this amendment

- Pydantic `MacroRow` validator enforces the seven rows in order Sunday, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday.
- `build_macro_grid` output rows are produced in Sun→Sat order.
- `lock_mesocycle.macro_table` validator accepts Sun→Sat order.
- Test fixtures across `test_mesocycle.py`, `test_models.py`, `test_recompute_macros.py`, and the new `test_build_macro_grid.py` construct rows starting Sunday.
- Constraint-violation error messages that name ordering reference Sun→Sat.

## 4. What this does not change

- Mathematical behavior of `build_macro_grid`, `recompute_macros_with_overrides`, or `lock_mesocycle`.
- Read paths in `meal_log`, `today_view`, or any other downstream consumer — all read by weekday name (base ADR §3.2).
- The Phase 1 build sequence in base ADR §5. Step 1 (`rationale` → optional) is unaffected. Steps 2–4 apply Sun→Sat.
- The Phase 2 capability rewrite scope.

## 5. Migration cost

Zero. No live cycles in production. Test fixtures update with the schema change in Step 2.

---

*End of addendum.*
