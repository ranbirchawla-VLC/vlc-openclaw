# vlc-openclaw — Summary: `make test` scope

Branch: feature/nutrios-v2  

`make test` already runs bare `$(PYTEST)` — no change needed. Auto-discovery is correctly scoped by `pytest.ini` (`testpaths = skills`).

| Target | Count |
|---|---|
| `make test` | **138 passed** |
| `make test-nutrios-time` | 22 |
| `make test-nutrios-store` | 28 |
| `make test-nutrios-engine` | 67 |
| `make test-nutrios-models` | 21 |
| **Sum of scoped** | **138** ✓ |

Gate ready. Allowlist. Step 4.
