# Sub-step Z — GTD Storage Migration

## What this does

Migrates runtime data from `gtd-workspace/storage/` to `~/agent_data/gtd/ranbir/` and wires the
`GTD_STORAGE_ROOT` env var so future plugin tools read/write from the new location.

## Files changed

| File | Change |
|---|---|
| `gtd-workspace/scripts/migrate_storage.py` | One-shot migration script |
| `gtd-workspace/scripts/test_migrate_storage.py` | Pytest tests (8 cases) |
| `gtd-workspace/openclaw.json` | Added `"env": ["GTD_STORAGE_ROOT"]` |
| `gtd-workspace/docs/trina-build.md` | Copied from `~/Downloads/` (master design doc) |
| `Makefile` | Added `test-gtd` and `test-gtd-storage` targets |

## Design decisions

**Path injection via CLI flags** (`--source`, `--dest`). Tests call the script as a subprocess,
passing `tmp_path`-based paths. This avoids module-level constant patching, keeps the test contract
simple, and exercises real I/O paths including `shutil.copytree` and `Path.rename`. The same flags
are available at runtime if the operator ever needs to redirect paths without editing the script.

**Parked suffix is `.migrated` appended to the source directory name.** If source is
`storage`, parked becomes `storage.migrated`. Derived from source so the parked path is always
co-located and unambiguous.

**`rglob("*")` not `iterdir()` in `_hash_tree`.** TDD-proven; see Gate 1 report below.

**Sentinel + sha256 integrity (post-review, B-1 + B-2 compose).** After copy, the script
computes a sha256 hash over the full source tree (sorted by relative path), copies to dest,
verifies the dest hash matches, writes `dest/.migration_complete` containing the hash and
timestamp, then parks the source. On re-run with a non-empty dest, the script checks for the
sentinel: if present and hash matches, it completes the interrupted rename and exits ok with
`recovery_status: "recovered interrupted rename"`; if sentinel absent, it refuses with
"destination not empty".

**Empty pre-existing destination is intentionally accepted (M-1 review finding — documentation
only, no behavior change).** An empty `dest` that was pre-created by the operator (e.g., via
`launchd` or `mkdir -p`) passes the non-empty guard and the migration proceeds normally. This
is deliberate; only a non-empty destination triggers the refusal or sentinel-recovery path. The
intent is documented in the module docstring.

**`shutil.move` not `Path.rename` for parking.** `rename` raises `OSError: Invalid
cross-device link` when source and parked resolve to different filesystems. `shutil.move` falls
back to copy+delete on cross-device moves, making the script safe for `--source` overrides that
land on tmpfs in tests.

## TDD recursive-walk failure transcript

The test `test_recursive_walk_counts_all_depths` was written before the implementation. A broken
implementation using `iterdir()` was placed at the script path. Test run output:

```
FAILED test_recursive_walk_counts_all_depths
AssertionError: Expected 4 files but got 1;
likely _count_tree uses iterdir() instead of rglob()
```

The correct implementation uses `root.rglob("*")` and all 7 tests pass.

## Gate 1 report

### 1. Does each test reproduce the production failure it guards against?

| Test | Production failure guarded |
|---|---|
| `test_happy_path` | Silent data loss or incomplete copy on live migration |
| `test_dry_run` | Dry-run accidentally mutating disk (source renamed or dest created) |
| `test_refusal_dest_not_empty` | Overwriting live destination data on re-run |
| `test_refusal_source_missing_no_parked` | Confusing error when storage dir never existed |
| `test_refusal_already_migrated` | Re-running migrate after successful migration, clobbering parked source |
| `test_idempotent` | Second invocation corrupting a completed migration |
| `test_recursive_walk_counts_all_depths` | `iterdir()`-only walk silently undercounting files, causing verification to pass with data loss |
| `test_b1_recovery_interrupted_rename` | No recovery when copytree succeeded but park rename failed; operator left with two full copies and no diagnostic |

All tests use `tmp_path` real I/O fixtures and invoke the script as a subprocess. There is no
mocked filesystem. The failure modes listed above only surface against real I/O.

### 2. Did tests 7 and 8 fail against unfixed code before fixes were applied?

**Test 7 (recursive walk):** A broken implementation using `iterdir()` was placed at
`migrate_storage.py` before the correct implementation was written. Running `make test-gtd-storage`
produced:

```
FAILED test_happy_path — assert 1 == 4
FAILED test_dry_run — assert 1 == 4
FAILED test_recursive_walk_counts_all_depths — Expected 4 files but got 1
```

Three tests failed (happy path and dry-run fail too because they also assert correct counts).
After replacing `iterdir()` with `rglob("*")`, all 7 pass.

**Test 8 (B-1 recovery):** The test was added to the test file before the sentinel logic was
written into `migrate_storage.py`. Running it against the pre-fix script produced:

```
FAILED test_b1_recovery_interrupted_rename
AssertionError: recovery run failed:
  {'ok': False, 'error': "destination not empty: '...' already contains files; refusing to overwrite"}
assert 1 == 0
```

After adding the sentinel-check and recovery path, all 8 tests pass.

### 3. Model and temperature?

N/A — sub-step Z contains no LLM calls. The migration script is pure Python I/O. LLM test
requirements do not apply to this sub-step.

---

## Operator follow-up (after Gate 1 clears)

Run these steps in order after Gate 1 and Gate 2 clear:

### Dry run

```bash
python3 gtd-workspace/scripts/migrate_storage.py --dry-run
```

Verify reported `files_to_move` and `bytes_to_move` match the actual storage tree.
No disk changes occur.

### Live run

```bash
python3 gtd-workspace/scripts/migrate_storage.py
```

Expect exit 0 with JSON payload naming `source_parked_at`, `destination`, `files_moved`,
`bytes_moved`.

### Set env var on gateway process

Edit the gateway launchd plist (typically
`~/Library/LaunchAgents/com.openclaw.gateway.plist`) and add or update:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>GTD_STORAGE_ROOT</key>
  <string>/Users/ranbirchawla/agent_data/gtd/ranbir</string>
</dict>
```

### Restart gateway

```bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.gateway.plist
launchctl load  ~/Library/LaunchAgents/com.openclaw.gateway.plist
```

### Smoke test

Send a real GTD action through Telegram. Confirm the tool reads/writes hit
`~/agent_data/gtd/ranbir/` (check file timestamps after the action).

### Clean up parked source

After smoke test passes:

```bash
rm -rf gtd-workspace/storage.migrated
```

---

## Known issues / carry-forwards

None. This sub-step is self-contained. The `env` block in `openclaw.json` declares the var name
only; the gateway process is responsible for setting the value (out of scope per sub-step spec).
