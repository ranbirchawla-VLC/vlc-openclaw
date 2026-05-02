# Sub-step 2 — Env Var Correction

_Naming alignment: master design doc and Sub-step 1 helper renamed to match the live OpenClaw launch environment._

_Date: 2026-05-02_

---

## What changed

| Field | Was (speculative in doc) | Now (live in OpenClaw env) |
|-------|--------------------------|----------------------------|
| Env var name | `GOOGLE_OAUTH_TOKEN_PATH` | `GOOGLE_OAUTH_CREDENTIALS` |
| File path | `/Users/ranbirchawla/.openclaw/secrets/google_token.json` | `/Users/ranbirchawla/.openclaw/credentials/trina-google-creds.json` |
| `GOOGLE_OAUTH_CLIENT_SECRETS_PATH` | Documented in §3 | Removed entirely |

The credentials file `trina-google-creds.json` carries client_id, client_secret, and refresh_token; no separate client_secrets.json is needed at runtime or in env.

## Why

The env var was already set in the OpenClaw launch environment when Sub-step 1 was being written. Doc §3 was speculative. Live operator config wins; doc was wrong.

## Files affected

- `trina-build.md` §3 — credential model section
- `gtd-workspace/scripts/common.py` — `get_google_credentials()` and structured error surfaces
- `gtd-workspace/scripts/test_common.py` — env var assertions in credential failure tests
- Sub-step 2 plan — all references updated

## Scope discipline

This is acknowledged scope expansion of Sub-step 1 files (`common.py`, `test_common.py`) and the master design doc (`trina-build.md` §3). Approved by supervisor; live operator config wins; no Sub-step 1 architectural decision is relitigated.

## Lesson captured

Doc §3 should mirror the live env var, not propose a new one. When a sub-step authors an env var name, confirm against the OpenClaw launch environment before writing the helper.
