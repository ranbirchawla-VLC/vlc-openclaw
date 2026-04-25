# NutriOS Migration Report

**Source:** <SOURCE>
**Destination:** <DEST>
**User ID:** alice
**Run at:** 2026-04-24T18:30:00+00:00
**TDEE/Deficit Rule Fired:** 1

## Counts

- Migrated cleanly: 15
- Repaired (with rules): 0
- Quarantined: 1

## By kind

| Kind | Migrated | Repaired | Quarantined |
|---|---|---|---|
| weigh_ins | 3 | 0 | 0 |
| med_notes | 2 | 0 | 0 |
| events | 4 | 0 | 0 |
| log_entries | 4 | 0 | 0 |
| recipes | 2 | 0 | 1 |

## Discarded

- water_count: total 19 (per-day: 2026-04-15=6, 2026-04-16=8, 2026-04-17=5)
- day_notes (non-empty values surfaced verbatim):
  - 2026-04-15: Felt good, gym in afternoon.
  - 2026-04-17: Rough day.
- .bak files: 1 (protocol.json.bak)

## Markers set

| Marker | Reason |
|---|---|
| gallbladder | v1 had no field; default "unknown" set, marker raised for user confirmation. |
| carbs_shape | v1 carbs migrated as min-only; user confirms shape (min/max/both) in Phase 2. |
| deficits | Per-day-type deficits require user confirmation in Phase 2. |
| nominal_deficit | Cycle-level nominal deficit requires user confirmation in Phase 2. |

## Warnings

- Historical dose lines synthesized from current protocol snapshot: 1
  - 2026-04-16: brand=Mounjaro, dose_mg=10.0
- Historical mesocycles with null TDEE (v1 did not carry historical TDEE; null preserved):
  - cut_jan
  - recomp_q4

## TDEE/Deficit Resolution

Rule fired: 1
Resulting state:
- Active mesocycle TDEE: 2600
- Per-day-type deficits:
  - rest: 600
  - training: 200
- Nominal cycle deficit: 600
