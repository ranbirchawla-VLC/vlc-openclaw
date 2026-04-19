# REVIEW_phase24a.md — Cowork plugin (OUTBOUND + INBOUND bundle handoff)

**Verdict:** Self-contained Claude Code plugin built at repo root under
`grailzee-cowork/`. One skill (`grailzee-bundle`), two modes (OUTBOUND,
INBOUND), 70 tests, full suite 612/612 passing. Staff-engineer review
returned 5 blocking + 6 advisory items; all 5 blocking resolved
in-scope, advisory items with real user impact also landed.

Branch ahead of `origin/feature/grailzee-eval-v2`: 20 commits (was 15;
+5 this phase — one per checkpoint plus the hardening-pass remediation
folded into Checkpoint 4).

## Checkpoint log

| # | Commit | Scope |
|---|--------|-------|
| 1 | `71a8571` | Scaffolding: `plugin.json`, repo-root `pytest.ini`, `README.md`, `LICENSE`, `grailzee_bundle/` + `tests/` package stubs, `_fixtures.py` helpers. Root `.python-version = 3.12.10` added (both subdirs that pin Python already pin to 3.12.10; unpinned subdirs now inherit). |
| 2 | `5544411` | `grailzee_bundle/build_bundle.py` (OUTBOUND) + 28 tests. |
| 3 | `33af648` | `grailzee_bundle/unpack_bundle.py` (INBOUND) + 32 tests. |
| 4 | (this commit) | `test_round_trip.py` (3 tests) + SKILL.md + README fill-out + security hardening from code review (+7 tests). |

## Architecture

```
grailzee-cowork/
├── .claude-plugin/plugin.json       # name: vardalux-grailzee-cowork
├── skills/grailzee-bundle/SKILL.md  # capability description
├── grailzee_bundle/
│   ├── build_bundle.py              # OUTBOUND
│   └── unpack_bundle.py             # INBOUND
├── tests/
│   ├── _fixtures.py                 # build_fake_grailzee_tree, build_inbound_bundle_zip
│   ├── test_build_bundle.py         # 28 tests
│   ├── test_unpack_bundle.py        # 39 tests (32 initial + 7 hardening regressions)
│   └── test_round_trip.py           # 3 tests
├── REVIEW_phase24a.md               # this file
├── README.md
└── LICENSE
```

### Package-name collision avoided

Both `skills/grailzee-eval/scripts/` and a naive `grailzee-cowork/scripts/`
would collide on shared `pythonpath`. Cowork's Python module is named
`grailzee_bundle`, not `scripts`, so imports are unambiguous.

Correspondingly, `skills/grailzee-eval/tests/` is a package (its tests do
`from tests._fixture_builders import ...`); `grailzee-cowork/tests/` is NOT
a package (no `__init__.py`) and `grailzee-cowork/tests` is on
pythonpath, so cowork tests import helpers as `from _fixtures import ...`.
`--import-mode=importlib` in the root `pytest.ini` keeps same-named
`tests` dirs on disjoint module identities.

## Bundle format

Manifest schema `v1`:

```json
{
  "manifest_version": 1,
  "bundle_kind": "outbound" | "inbound",
  "generated_at": "<iso-8601 UTC with Z suffix>",
  "cycle_id": "cycle_YYYY-MM",
  "source": "<origin tag>",
  "scope": {"month_boundary": <bool>, "quarter_boundary": <bool>},
  "files": [
    {"path": "<arcname>", "role": "<role-name>",
     "sha256": "<hex>", "size_bytes": <int>}
  ]
}
```

OUTBOUND roles: `analysis_cache`, `cycle_focus_current`, `monthly_goals`,
`quarterly_allocation`, `trade_ledger_snippet`, `sourcing_brief`,
`latest_report_csv`.

INBOUND role whitelist: `cycle_focus`, `monthly_goals`,
`quarterly_allocation` (3).

The role rename `cycle_focus_current` → `cycle_focus` across the
directional boundary is deliberate: OUTBOUND reports "what's current on
the agent now"; INBOUND delivers "the plan the Chat session decided on".

### Filename + collision

Bundle filename: `grailzee_outbound_<cycle_id>_<YYYYMMDD_HHMMSS_ffffff>.zip`.
Microsecond precision in the timestamp follows the Batch B1 `write_cache.py`
precedent and means two bundles built in the same second get distinct
names.

### Output location

`<GRAILZEE_ROOT>/bundles/` — sibling of `state/` and `output/`, not
inside `output/`. Directory is created by the builder if absent.

### Boundary detection

`scope.month_boundary` and `scope.quarter_boundary` are stamped into
outbound manifests by comparing the current cache's `cycle_id` against
the **most recent `run_history.json` entry whose cycle_id DIFFERS** —
not simply the last entry, which the agent may have appended for the
current cycle before bundling. Using the last entry as anchor would
mask the boundary. Exercised by
`test_boundary_anchor_skips_current_cycle_entries`.

## INBOUND validation (8 conceptual rules, 15 actual checks)

| Rule | Checks |
|------|--------|
| 1 | `manifest.json` present; under `MAX_MANIFEST_BYTES` (1 MB) before read |
| 2 | JSON decodes; manifest_version == 1 |
| 3 | bundle_kind == "inbound" |
| 4 | cycle_id matches current cache (toggleable via `--allow-cycle-mismatch`) |
| 5 | All roles in whitelist; file count ≤ `MAX_MANIFEST_FILES` (16) |
| 6 | No symlink entries (S_IFLNK mode bits rejected) |
| 7 | No unsafe arcnames (abs paths, `..`, backslashes, drive prefixes, NUL bytes), checked on both ZipInfo.filename AND manifest.files[].path |
| 8 | Per-member size ≤ `MAX_MEMBER_BYTES` (4 MB) pre-read; aggregate ≤ `MAX_TOTAL_DECOMPRESSED_BYTES` (16 MB); no duplicate arcnames; sha256 + size match per-member; no archive member outside the manifest |

All rules run BEFORE any write. No partial state is ever produced.

## Atomic commit

Two-phase with hardlink-based snapshot:

1. Pre-check: refuse to start if any `.tmp.<pid>` or `.prior.<pid>`
   sibling already exists in `state_dir` (defends against pid reuse from
   a crashed prior invocation).
2. Phase 1: write each new payload to `<target>.tmp.<pid>`.
3. Phase 2: `os.link(target, prior)` to snapshot each existing target
   (atomic; fails loudly if prior exists).
4. Phase 3: `tmp.replace(target)` per target in order; on any exception,
   restore all successfully replaced targets from their hardlink
   snapshots and re-raise.
5. Success cleanup: unlink all `.prior.<pid>` siblings.

**Contract:** exception-atomic. Not crash-atomic (a `kill -9` between
Phase 2 and Phase 3 can leave siblings on disk). The pre-check in step 1
enforces manual cleanup on retry rather than silently clobbering
operator artifacts. Documented in the `_atomic_write_targets` docstring.

## Code review remediation

Staff-engineer review (`/agent code-reviewer`) returned 5 blocking
issues; all 5 resolved in-scope before the Checkpoint 4 commit:

| # | Issue | Resolution |
|---|-------|------------|
| B1 | Zip-bomb: `zf.read()` decompressed payload before any size check | Per-member cap (`MAX_MEMBER_BYTES`) + aggregate cap (`MAX_TOTAL_DECOMPRESSED_BYTES`) + manifest cap (`MAX_MANIFEST_BYTES`), all checked against `ZipInfo.file_size` pre-read |
| B2 | Duplicate arcnames silently accepted (hostile same-named twin could substitute after sha256 check) | Explicit duplicate-name detection in `infolist` before any read; `zf.read(info)` by ZipInfo, not by name |
| B3 | Non-atomic snapshot (`read_bytes` + `write_bytes`) would clobber a stale `.prior.<pid>` on pid reuse | Pre-check refuses leftover siblings; `os.link()` for snapshots (atomic, fails-on-exist); docstring now distinguishes exception-atomic from crash-atomic |
| B4 | NUL byte in arcname could bypass `_is_unsafe_arcname` on some FSs | NUL explicitly rejected |
| B5 | Manifest-declared `path` never re-validated (attacker could declare `../escape.json`) | `_is_unsafe_arcname` now runs on `entry["path"]` too |

Advisory items with real impact that also landed:

- Silent `JSONDecodeError` on corrupt `run_history.json` now emits a
  stderr warning (boundary flags still default to False, so a corrupt
  history never blocks an outbound bundle).
- `manifest.files` length cap (`MAX_MANIFEST_FILES = 16`).
- `build_bundle` tmp path no longer uses the `with_suffix` trick.

Advisory items deferred (low-impact for v0.1):

- Reproducible-bundle mtime (advisory: set `ZipInfo.date_time` to a
  fixed value). Bundles are intended as single-shot handoffs, not a
  build artifact with byte-for-byte reproducibility requirements.
- Optional deterministic commit ordering by role. Dict insertion order
  is stable on 3.7+ and that's sufficient.

Hardening added 7 regression tests (duplicate arcname, per-member cap,
manifest size cap, manifest-path traversal, file-count cap, NUL in
arcname helper, leftover-sibling pre-check).

## Test totals

| Suite | Before | After |
|-------|--------|-------|
| `skills/grailzee-eval/tests/` | 542 | 542 (unchanged) |
| `grailzee-cowork/tests/test_build_bundle.py` | — | 28 |
| `grailzee-cowork/tests/test_unpack_bundle.py` | — | 39 |
| `grailzee-cowork/tests/test_round_trip.py` | — | 3 |
| **Total at repo root** | 542 | **612** |

All 612 pass under `python3 -m pytest` from repo root.

## Interpreter pinning

`/Users/ranbirchawla/ai-code/vlc-openclaw/.python-version` was added
pinning the entire repo to 3.12.10. Both subdirs that previously pinned
(`skills/grailzee-eval/`, `gtd-workspace/`) already pinned to 3.12.10, so
they're unaffected. Previously-unpinned subdirs (watch-listing-workspace,
nutrios-workspace, etc.) now inherit 3.12.10 instead of the global
3.9.2; none of them depend on 3.9-specific behavior per a pre-commit
audit.

## Anomalies

- None. Scope was tight, reviewer's blockers were crisp, remediation
  landed without architectural rework.

## State at phase close

- **Branch:** `feature/grailzee-eval-v2`
- **Commits ahead of `origin/feature/grailzee-eval-v2`:** 20
- **Working tree:** clean post-commit
- **Plugin live:** `grailzee-cowork/` (self-contained; does not import
  from `skills/grailzee-eval/` at runtime)
- **Not touched by this phase:** `skills/grailzee-eval/` (other than
  test infrastructure that runs alongside via the shared `pytest.ini`)
- **Next:** Phase 24b builds the Chat strategy skill against this
  bundle format. Phase 25 pushes the accumulated work to origin.
