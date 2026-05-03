# ADR-0002: Concurrency contract for trade ledger writes

**Status:** Accepted  
**Decided:** 2026-04-29  
**Sub-step:** 1.3  
**Implemented in:** `scripts/ingest_sales.py` — `with_exclusive_lock`, `with_shared_lock`,
`_open_and_lock`, `atomic_write_csv`

---

## Context

`trade_ledger.csv` lives in the GrailzeeData directory, which is a Google Drive
folder synced to the local filesystem via the Drive FUSE mount. Multiple processes
can read the ledger concurrently (the Grailzee cowork bundle reader, the
`read_ledger` script); the ingest generator is the only writer. Both correctness
(no torn reads) and data integrity (no partial writes) must be guaranteed without
relying on Drive's consistency model.

---

## Decision

### B1 — Lockfile on local filesystem

`LEDGER_LOCK_DEFAULT` resolves to `~/.grailzee/trade_ledger.lock`, which is on the
local (non-FUSE) filesystem. The CSV data file and all GrailzeeData content remain on
Drive; only the advisory lockfile is local.

**Why:** `flock(2)` on FUSE-mounted volumes does not guarantee cross-process exclusion.
The FUSE driver may implement `flock` as a no-op or as a process-local operation.
Separating the lockfile from the data avoids depending on a guarantee the filesystem
cannot make.

**Override:** `GRAILZEE_LOCK_PATH` env var. The resolver (`_resolve_lock_path`) never
raises on a missing env var — the local default is always valid and unambiguous.
This is a deliberate divergence from the data-path resolvers, which raise on a missing
`GRAILZEE_ROOT`.

### B2 — Inode re-check after flock acquire

After `flock()` succeeds, `_open_and_lock` compares `os.fstat(fd).st_ino` to
`os.stat(path).st_ino`. If they differ, the lock was acquired on a stale fd (another
process deleted and recreated the lockfile between this process's `open()` and
`flock()`). The stale lock is released and the open-plus-lock sequence retries from
the beginning against the remaining deadline budget.

**Why:** The split-brain race is low-probability but silent — without the re-check,
two processes would each believe they hold an exclusive lock. The fix costs one
`stat` call per acquisition. The decision at sub-step 1.3 was to tighten the contract
now rather than document the race and revisit it later.

### B3 — Read-modify-write under exclusive lock; atomic rewrite

The write path is: acquire `LOCK_EX` → read existing CSV → merge → write to
`path + ".tmp"` → `fsync` → `os.rename` → release lock. No append path exists.

`os.rename` on POSIX is atomic at the filesystem level: readers see either the
complete old file or the complete new file, never a partial write. `fsync` before
rename ensures that a crash or power loss after rename does not expose an empty or
truncated ledger.

The `.tmp` file is not cleaned up on rename failure; cleanup is a separate operational
concern. The target file is unchanged if rename fails, because the rename never
happened.

### B4 — Single writer, multiple readers

The ingest generator is the only process that calls `with_exclusive_lock`. All other
processes that read the ledger (cowork bundle assembly, reporting) must acquire
`with_shared_lock` using the same locally-resolved lock path before opening the CSV.

---

## Phase 2 dependency

The cowork bundle reader (`_read_full_ledger` or equivalent) must wrap its CSV open
in `with_shared_lock(LEDGER_LOCK_DEFAULT)` — or construct the lock path via
`_resolve_lock_path()` — so it contends correctly with the ingest writer. Using a
different lock path or skipping the lock produces a silent correctness failure: the
reader will not block the writer, and torn reads become possible under concurrent
ingest. This wiring must be present and tested before the Phase 2 sub-step that
introduces `_read_full_ledger` ships (design v1 §13.2); it is a Gate 1 prerequisite
for that sub-step, not a follow-on item.

---

## Alternatives considered

**Keep lockfile on Drive alongside the CSV.** Rejected; flock on FUSE is unreliable.
The cost of the separation is a single env var and a local directory. Acceptable.

**Accept the split-brain race without the inode re-check.** Rejected. The race window
is narrow but the consequence is data corruption that produces no immediate error.
The inode re-check is five lines and closes the window entirely.

**Append-only write path.** Rejected. Append-only complicates the update and prune
semantics defined in Rule Y (§8) and Phase 1 §10. Full rewrite under exclusive lock
is simpler to reason about and less error-prone than tracking append offsets and
in-place record rewrites.
