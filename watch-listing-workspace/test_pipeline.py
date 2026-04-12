#!/usr/bin/env python3
"""
test_pipeline.py — Tests for pipeline.py.

Run standalone: python3 test_pipeline.py
Exits 0 on all pass, 1 if any test fails.

Test structure:
  Section 1 — parse_folder_name (unit)
  Section 2 — watch_label (unit)
  Section 3 — write_seed_draft / archive_draft (filesystem)
  Section 4 — dispatch routing (mock subprocess + Telegram)
  Section 5 — main() behaviour (exit codes, resume prompt, start-over)
  Section 6 — Integration: empty folder through seed + skill signal
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make sure pipeline.py is importable from this directory.
WORKSPACE = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE))

import pipeline


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def ok(condition: bool, name: str) -> None:
    global _passed, _failed
    if condition:
        print(f"  PASS  {name}")
        _passed += 1
    else:
        print(f"  FAIL  {name}")
        _failed += 1


def raises(exc_type, fn, name: str) -> None:
    global _passed, _failed
    try:
        fn()
        print(f"  FAIL  {name}  (no exception raised)")
        _failed += 1
    except exc_type:
        print(f"  PASS  {name}")
        _passed += 1
    except Exception as e:
        print(f"  FAIL  {name}  (wrong exception: {e!r})")
        _failed += 1


# ---------------------------------------------------------------------------
# Section 1 — parse_folder_name
# ---------------------------------------------------------------------------

def test_parse_folder_name():
    print("\n--- Section 1: parse_folder_name ---")

    ref, model = pipeline.parse_folder_name(Path("164WU-IW371446-1"))
    ok(ref == "164WU",       "internal_ref from 164WU-IW371446-1")
    ok(model == "IW371446-1", "model_ref from 164WU-IW371446-1")

    ref, model = pipeline.parse_folder_name(Path("14618-M28500-0003"))
    ok(ref == "14618",         "internal_ref from 14618-M28500-0003")
    ok(model == "M28500-0003", "model_ref from 14618-M28500-0003")

    ref, model = pipeline.parse_folder_name(Path("99ABC-Explorer-II"))
    ok(ref == "99ABC",          "internal_ref from 99ABC-Explorer-II")
    ok(model == "Explorer-II",  "model_ref preserves sub-hyphens")

    ref, model = pipeline.parse_folder_name(Path("STANDALONE"))
    ok(ref == "STANDALONE", "single segment: internal_ref = basename")
    ok(model == "",          "single segment: model_ref empty")


# ---------------------------------------------------------------------------
# Section 2 — watch_label
# ---------------------------------------------------------------------------

def test_watch_label():
    print("\n--- Section 2: watch_label ---")

    draft_with_brand = {"inputs": {"brand": "Tudor", "model": "Black Bay GMT"}}
    ok(pipeline.watch_label(draft_with_brand) == "Tudor Black Bay GMT",
       "brand + model → 'Brand Model'")

    draft_refs_only = {
        "inputs": {"internal_ref": "164WU", "model_ref": "IW371446-1"}
    }
    ok(pipeline.watch_label(draft_refs_only) == "164WU-IW371446-1",
       "no brand/model → internal_ref-model_ref")

    draft_iref_only = {"inputs": {"internal_ref": "164WU"}}
    ok(pipeline.watch_label(draft_iref_only) == "164WU",
       "model_ref absent → internal_ref only")

    draft_empty = {"inputs": {}}
    ok(pipeline.watch_label(draft_empty) == "",
       "empty inputs → empty string")

    draft_no_inputs = {}
    ok(pipeline.watch_label(draft_no_inputs) == "",
       "no inputs key → empty string")


# ---------------------------------------------------------------------------
# Section 3 — write_seed_draft / archive_draft
# ---------------------------------------------------------------------------

def test_seed_and_archive():
    print("\n--- Section 3: write_seed_draft / archive_draft ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)

        # write_seed_draft
        pipeline.write_seed_draft(folder, "164WU", "IW371446-1")
        draft_path = folder / "_draft.json"
        ok(draft_path.exists(), "seed draft file created")

        with open(draft_path, encoding="utf-8") as f:
            seed = json.load(f)

        ok(seed.get("inputs", {}).get("internal_ref") == "164WU",
           "seed: internal_ref correct")
        ok(seed.get("inputs", {}).get("model_ref") == "IW371446-1",
           "seed: model_ref correct")
        ok("step" not in seed,     "seed: step field absent (not yet set)")
        ok("timestamp" in seed,    "seed: timestamp present")

        # archive_draft
        pipeline.archive_draft(folder)
        bak_path = folder / "_draft.json.bak"
        ok(bak_path.exists(),       "archive: .bak file created")
        ok(not draft_path.exists(), "archive: original _draft.json removed")

        # archive_draft with no file — no error
        pipeline.archive_draft(folder)  # should be silent
        ok(True, "archive with no draft: no exception")


# ---------------------------------------------------------------------------
# Section 4 — dispatch routing
# ---------------------------------------------------------------------------

def _make_draft(step, brand="Tudor", model="Black Bay GMT") -> dict:
    d: dict = {
        "timestamp": "2026-04-11T10:00:00Z",
        "inputs": {
            "internal_ref": "164WU",
            "model_ref": "79830RB",
            "brand": brand,
            "model": model,
            "retail_net": 3200,
            "condition": "Excellent",
            "grailzee_format": "NR",
            "tier": 1,
        },
    }
    if step is not None:
        d["step"] = step
    return d


def test_dispatch_routing():
    print("\n--- Section 4: dispatch routing ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)

        # ── No draft → seed + step0-watchtrack signal ──────────────────────
        with patch.object(pipeline, "write_seed_draft") as mock_seed, \
             patch.object(pipeline, "tg_post") as mock_tg, \
             patch.object(pipeline, "invoke_skill") as mock_skill:
            pipeline.dispatch(folder)
            ok(mock_seed.called,  "no draft: write_seed_draft called")
            ok(mock_skill.call_args[0][0] == "step0-watchtrack",
               "no draft: invokes step0-watchtrack")

        # ── step=None → re-invoke WatchTrack ───────────────────────────────
        # _make_draft(None) already omits the step key, simulating a seed draft.
        draft_path = folder / "_draft.json"
        with open(draft_path, "w") as f:
            json.dump(_make_draft(None), f)

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "invoke_skill") as mock_skill:
            pipeline.dispatch(folder)
            ok(mock_skill.call_args[0][0] == "step0-watchtrack",
               "step=None: re-invokes step0-watchtrack")

        # ── step=0 → step1-photos ──────────────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(0), f)

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "invoke_skill") as mock_skill:
            pipeline.dispatch(folder)
            ok(mock_skill.call_args[0][0] == "step1-photos",
               "step=0: invokes step1-photos")

        # ── step=1 → run_pricing.py ────────────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(1), f)

        pricing_output = "PRICING SUMMARY\neBay  $3,649\nChrono24  $3,625\n"
        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "tg_post_buttons") as mock_btn, \
             patch.object(pipeline, "run_tool", return_value=(0, pricing_output)) as mock_rt:
            pipeline.dispatch(folder)
            ok(str(pipeline.RUN_PRICING) in str(mock_rt.call_args),
               "step=1: calls run_pricing.py")
            ok(mock_btn.called, "step=1: posts approval buttons")
            ok("Approve" in str(mock_btn.call_args),
               "step=1: Approve button present")
            ok("Request Changes" in str(mock_btn.call_args),
               "step=1: Request Changes button present")

        # ── step=2 → step3a-canonical ──────────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(2), f)

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "invoke_skill") as mock_skill:
            pipeline.dispatch(folder)
            ok(mock_skill.call_args[0][0] == "step3a-canonical",
               "step=2: invokes step3a-canonical")

        # ── step=3 → run_grailzee_gate.py ─────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(3), f)

        gate_output = "Gate: PROCEED\nMedian: $3,150\n"
        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "tg_post_buttons") as mock_btn, \
             patch.object(pipeline, "run_tool", return_value=(0, gate_output)) as mock_rt:
            pipeline.dispatch(folder)
            ok(str(pipeline.RUN_GRAILZEE) in str(mock_rt.call_args),
               "step=3: calls run_grailzee_gate.py")
            ok("Proceed with Current Pricing" in str(mock_btn.call_args),
               "step=3: Proceed button present")
            ok("Adjust Pricing" in str(mock_btn.call_args),
               "step=3: Adjust Pricing button present")

        # ── step=3.5 → phase_b + pdf ───────────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(3.5), f)

        def fake_run_tool(script, folder_arg, dry_run=False):
            return (0, "assembled" if "phase_b" in str(script) else "pdf_ok")

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "tg_post_buttons"), \
             patch.object(pipeline, "slack_post_completion"), \
             patch.object(pipeline, "run_tool", side_effect=fake_run_tool) as mock_rt:
            pipeline.dispatch(folder)
            calls = [str(c.args[0]) for c in mock_rt.call_args_list]
            ok(any("phase_b" in c for c in calls), "step=3.5: calls run_phase_b.py")
            ok(any("generate_listing_pdf" in c for c in calls),
               "step=3.5: chains to generate_listing_pdf.py")

        # ── step=4 → generate pdf only ─────────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(4), f)

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "slack_post_completion") as mock_slack, \
             patch.object(pipeline, "run_tool", return_value=(0, "{}")) as mock_rt:
            pipeline.dispatch(folder)
            ok(str(pipeline.RUN_PDF) in str(mock_rt.call_args),
               "step=4: calls generate_listing_pdf.py")
            ok(mock_slack.called, "step=4: posts to Slack")

        # ── unknown step → exit 1 ──────────────────────────────────────────
        with open(draft_path, "w") as f:
            json.dump({**_make_draft(2), "step": 99}, f)

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"):
            with_exit = None
            try:
                pipeline.dispatch(folder)
            except SystemExit as e:
                with_exit = e.code
            ok(with_exit == 1, "unknown step: exits 1")


# ---------------------------------------------------------------------------
# Section 5 — main() behaviour
# ---------------------------------------------------------------------------

def test_main_behaviour():
    print("\n--- Section 5: main() behaviour ---")

    # ── Missing folder → exit 2 ────────────────────────────────────────────
    with patch.object(sys, "argv", ["pipeline.py", "/nonexistent/path/xyz"]):
        try:
            pipeline.main()
            ok(False, "missing folder: should have exited")
        except SystemExit as e:
            ok(e.code == 2, "missing folder: exits 2")

    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        draft_path = folder / "_draft.json"

        # ── No draft → dispatch (fresh start) ─────────────────────────────
        with patch.object(sys, "argv", ["pipeline.py", str(folder)]), \
             patch.object(pipeline, "dispatch") as mock_dispatch:
            pipeline.main()
            ok(mock_dispatch.called, "no draft: dispatch called")

        # ── Draft exists, no flags → resume prompt ─────────────────────────
        with open(draft_path, "w") as f:
            json.dump(_make_draft(1), f)

        with patch.object(sys, "argv", ["pipeline.py", str(folder)]), \
             patch.object(pipeline, "tg_post_buttons") as mock_btn, \
             patch.object(pipeline, "dispatch") as mock_dispatch:
            pipeline.main()
            ok(mock_btn.called,        "existing draft, no flags: resume prompt shown")
            ok(not mock_dispatch.called, "existing draft, no flags: dispatch NOT called")
            ok("Resume" in str(mock_btn.call_args), "resume prompt has Resume button")
            ok("Start Over" in str(mock_btn.call_args), "resume prompt has Start Over button")

        # ── Draft exists, --resume → dispatch immediately ──────────────────
        with patch.object(sys, "argv", ["pipeline.py", str(folder), "--resume"]), \
             patch.object(pipeline, "tg_post_buttons") as mock_btn, \
             patch.object(pipeline, "dispatch") as mock_dispatch:
            pipeline.main()
            ok(mock_dispatch.called,   "--resume: dispatch called")
            ok(not mock_btn.called,    "--resume: no prompt shown")

        # ── Draft exists, --start-over → archive + fresh dispatch ──────────
        with patch.object(sys, "argv", ["pipeline.py", str(folder), "--start-over"]), \
             patch.object(pipeline, "tg_post") as mock_tg, \
             patch.object(pipeline, "dispatch") as mock_dispatch:
            pipeline.main()
            bak = folder / "_draft.json.bak"
            ok(bak.exists(),            "--start-over: .bak created")
            ok(not draft_path.exists(), "--start-over: original draft removed")
            ok(mock_dispatch.called,    "--start-over: dispatch called after archive")

        # ── --dry-run prevents seed write ──────────────────────────────────
        with patch.object(sys, "argv", ["pipeline.py", str(folder), "--dry-run"]), \
             patch.object(pipeline, "write_seed_draft") as mock_seed, \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "invoke_skill"):
            pipeline.main()
            ok(not mock_seed.called, "--dry-run: write_seed_draft not called")


# ---------------------------------------------------------------------------
# Section 6 — Integration: empty folder → seed created + skill signalled
# ---------------------------------------------------------------------------

def test_integration_empty_folder():
    print("\n--- Section 6: Integration (empty folder) ---")

    with tempfile.TemporaryDirectory(suffix="-164WU-79830RB") as tmpdir:
        # Use a sub-folder with the naming convention
        parent   = Path(tmpdir)
        folder   = parent / "164WU-79830RB"
        folder.mkdir()

        # Capture stdout to inspect the skill signal
        import io
        stdout_capture = io.StringIO()

        with patch("sys.stdout", stdout_capture), \
             patch.object(pipeline, "tg_post"):
            pipeline.dispatch(folder)

        output = stdout_capture.getvalue()
        lines = [l for l in output.strip().splitlines() if l.startswith("{")]
        ok(len(lines) >= 1, "dispatch emits at least one JSON line")

        signal = json.loads(lines[0])
        ok(signal.get("openclaw_action") == "invoke_skill",
           "signal: openclaw_action = invoke_skill")
        ok(signal.get("skill") == "step0-watchtrack",
           "signal: skill = step0-watchtrack")
        ok("164WU-79830RB" in signal.get("folder", ""),
           "signal: folder contains listing name")

        draft_path = folder / "_draft.json"
        ok(draft_path.exists(), "seed _draft.json created")

        with open(draft_path, encoding="utf-8") as f:
            seed = json.load(f)
        ok(seed["inputs"]["internal_ref"] == "164WU",
           "seed: internal_ref = 164WU")
        ok(seed["inputs"]["model_ref"] == "79830RB",
           "seed: model_ref = 79830RB")
        ok("step" not in seed, "seed: step absent (WatchTrack not yet run)")

    # Step-through: simulate progression to each Python-tool step
    with tempfile.TemporaryDirectory() as tmpdir:
        folder    = Path(tmpdir)
        draft_path = folder / "_draft.json"

        with open(draft_path, "w") as f:
            json.dump(_make_draft(1), f)

        stdout_cap = __import__("io").StringIO()
        pricing_table = "PRICING SUMMARY\neBay  $3,649\n"

        with patch("sys.stdout", stdout_cap), \
             patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post"), \
             patch.object(pipeline, "tg_post_buttons"), \
             patch.object(pipeline, "run_tool", return_value=(0, pricing_table)):
            pipeline.dispatch(folder)

        ok(True, "step=1 dispatch with mocked run_tool: no exception")


# ---------------------------------------------------------------------------
# Section 7 — Scan mode
# ---------------------------------------------------------------------------

def _make_pipeline_root(tmpdir: Path) -> Path:
    """
    Build a mini pipeline root with two brand folders and assorted listing folders.

    Structure:
      root/
        .hidden/              ← must be skipped
        Omega/
          123XX-SM300/        ← new (no draft)
          456YY-SM300/        ← complete (step 4)  ← must be skipped
          .hidden-listing/    ← must be skipped
          nolisting/          ← no hyphen — must be skipped
        Tudor/
          164WU-79830RB/      ← incomplete (step 1)
          789ZZ-BB41/         ← new (no draft)
        EmptyBrand/           ← brand with no listings — fine to include
    """
    root = tmpdir / "pipeline"
    root.mkdir()

    (root / ".hidden").mkdir()

    omega = root / "Omega"
    omega.mkdir()
    (omega / ".hidden-listing").mkdir()
    (omega / "nolisting").mkdir()   # no hyphen — must not appear in scan

    # New listing
    (omega / "123XX-SM300").mkdir()

    # Complete listing (step 4) — should NOT appear in scan
    complete = omega / "456YY-SM300"
    complete.mkdir()
    with open(complete / "_draft.json", "w") as f:
        json.dump({"step": 4, "timestamp": "2026-04-11T10:00:00Z",
                   "inputs": {"internal_ref": "456YY", "model_ref": "SM300"}}, f)

    tudor = root / "Tudor"
    tudor.mkdir()

    # Incomplete listing (step 1)
    inc = tudor / "164WU-79830RB"
    inc.mkdir()
    with open(inc / "_draft.json", "w") as f:
        json.dump({"step": 1, "timestamp": "2026-04-11T10:00:00Z",
                   "inputs": {"internal_ref": "164WU", "model_ref": "79830RB",
                               "brand": "Tudor", "model": "Black Bay GMT"}}, f)

    # New listing
    (tudor / "789ZZ-BB41").mkdir()

    (root / "EmptyBrand").mkdir()

    return root


def test_listing_status():
    print("\n--- Section 7a: listing_status ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # No hyphen — not a listing
        no_hyph = root / "nohyphen"
        no_hyph.mkdir()
        ok(pipeline.listing_status(no_hyph) is None,
           "no hyphen: not a listing")

        # New (no draft)
        new_folder = root / "123XX-SM300"
        new_folder.mkdir()
        ok(pipeline.listing_status(new_folder) == "new",
           "no draft: status = 'new'")

        # Seed draft (no step field)
        seed_folder = root / "123XX-seed"
        seed_folder.mkdir()
        with open(seed_folder / "_draft.json", "w") as f:
            json.dump({"timestamp": "T", "inputs": {}}, f)
        status = pipeline.listing_status(seed_folder)
        ok(status is not None and "WatchTrack pending" in status,
           "seed draft: status mentions WatchTrack pending")

        # Incomplete step 1
        inc = root / "456YY-BB36"
        inc.mkdir()
        with open(inc / "_draft.json", "w") as f:
            json.dump({"step": 1, "timestamp": "T", "inputs": {}}, f)
        status = pipeline.listing_status(inc)
        ok(status is not None and "incomplete" in status,
           "step=1: status = incomplete")
        ok("Photo Review" in (status or ""),
           "step=1: status mentions Photo Review")

        # Complete (step 4)
        done = root / "789ZZ-M126600"
        done.mkdir()
        with open(done / "_draft.json", "w") as f:
            json.dump({"step": 4, "timestamp": "T", "inputs": {}}, f)
        ok(pipeline.listing_status(done) is None,
           "step=4: not actionable (complete)")

        # Corrupt draft
        corrupt = root / "000AA-corrupt"
        corrupt.mkdir()
        with open(corrupt / "_draft.json", "w") as f:
            f.write("{not json")
        status = pipeline.listing_status(corrupt)
        ok(status is not None and "unreadable" in status,
           "corrupt draft: status = unreadable")


def test_build_scan_queue():
    print("\n--- Section 7b: build_scan_queue ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_pipeline_root(Path(tmpdir))
        queue = pipeline.build_scan_queue(root)

        names = [Path(r["folder"]).name for r in queue]
        brands = [r["brand"] for r in queue]
        statuses = [r["status"] for r in queue]

        ok("456YY-SM300" not in names,
           "complete listing excluded")
        ok("nolisting" not in names,
           "no-hyphen folder excluded")
        ok("123XX-SM300" in names,
           "new Omega listing included")
        ok("164WU-79830RB" in names,
           "incomplete Tudor listing included")
        ok("789ZZ-BB41" in names,
           "new Tudor listing included")
        ok("Omega" in brands and "Tudor" in brands,
           "both brands discovered")
        ok(all(not b.startswith(".") for b in brands),
           "hidden brand folders excluded")

        # Incomplete before new
        idx_incomplete = next(
            (i for i, r in enumerate(queue) if "incomplete" in r["status"]), None
        )
        idx_new_omega = next(
            (i for i, r in enumerate(queue)
             if Path(r["folder"]).name == "123XX-SM300"), None
        )
        ok(
            idx_incomplete is not None
            and idx_new_omega is not None
            and idx_incomplete < idx_new_omega,
            "incomplete listings appear before new listings",
        )


def test_scan_queue_persistence():
    print("\n--- Section 7c: scan queue persistence ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Override SCAN_QUEUE_PATH to use tmpdir
        orig_path = pipeline.SCAN_QUEUE_PATH
        pipeline.SCAN_QUEUE_PATH = Path(tmpdir) / "_scan_queue.json"
        try:
            records = [
                {"brand": "Tudor", "folder": "/fake/Tudor/164WU-79830RB", "status": "new"},
                {"brand": "Omega", "folder": "/fake/Omega/123XX-SM300",   "status": "new"},
            ]
            pipeline.write_scan_queue(records)
            ok(pipeline.SCAN_QUEUE_PATH.exists(), "write_scan_queue: file created")

            loaded = pipeline.read_scan_queue()
            ok(len(loaded) == 2, "read_scan_queue: correct item count")
            ok(loaded[0]["brand"] == "Tudor", "read_scan_queue: order preserved")

            # Absent file returns []
            pipeline.SCAN_QUEUE_PATH.unlink()
            ok(pipeline.read_scan_queue() == [], "absent queue file returns []")
        finally:
            pipeline.SCAN_QUEUE_PATH = orig_path


def test_scan_fresh():
    print("\n--- Section 7d: _scan_fresh ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_pipeline_root(Path(tmpdir))

        orig_path = pipeline.SCAN_QUEUE_PATH
        pipeline.SCAN_QUEUE_PATH = Path(tmpdir) / "_scan_queue.json"
        try:
            tg_calls: list[str] = []
            btn_calls: list = []

            with patch.object(pipeline, "get_pipeline_root", return_value=root), \
                 patch.object(pipeline, "tg_post",
                               side_effect=lambda t: tg_calls.append(t)), \
                 patch.object(pipeline, "tg_post_buttons",
                               side_effect=lambda t, b: btn_calls.append((t, b))):
                pipeline._scan_fresh(dry_run=False)

            ok(pipeline.SCAN_QUEUE_PATH.exists(),
               "_scan_fresh: queue file written")
            ok(any("Found" in m for m in tg_calls),
               "_scan_fresh: found count message posted")
            ok(len(btn_calls) == 1,
               "_scan_fresh: exactly one item presented with buttons")
            ok("Start This" in str(btn_calls[0][1]),
               "_scan_fresh: Start This button present")
            ok("Skip" in str(btn_calls[0][1]),
               "_scan_fresh: Skip button present")
            ok("scan:start" in str(btn_calls[0][1]),
               "_scan_fresh: callback data is scan:start")
            ok("scan:skip" in str(btn_calls[0][1]),
               "_scan_fresh: callback data is scan:skip")
        finally:
            pipeline.SCAN_QUEUE_PATH = orig_path


def test_scan_empty_pipeline():
    print("\n--- Section 7e: scan with no actionable listings ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "empty_pipeline"
        root.mkdir()
        brand = root / "Rolex"
        brand.mkdir()
        # Only complete listings
        done = brand / "001AA-M116900"
        done.mkdir()
        with open(done / "_draft.json", "w") as f:
            json.dump({"step": 4, "timestamp": "T", "inputs": {}}, f)

        tg_calls: list[str] = []
        with patch.object(pipeline, "get_pipeline_root", return_value=root), \
             patch.object(pipeline, "tg_post",
                           side_effect=lambda t: tg_calls.append(t)):
            pipeline._scan_fresh(dry_run=False)

        ok(any("No new" in m for m in tg_calls),
           "empty scan: 'No new or incomplete listings' posted")


def test_scan_next():
    print("\n--- Section 7f: _scan_next ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = pipeline.SCAN_QUEUE_PATH
        pipeline.SCAN_QUEUE_PATH = Path(tmpdir) / "_scan_queue.json"
        try:
            queue = [
                {"brand": "Tudor", "folder": "/f/Tudor/A",  "status": "new"},
                {"brand": "Omega", "folder": "/f/Omega/B",  "status": "new"},
                {"brand": "Rolex", "folder": "/f/Rolex/C",  "status": "new"},
            ]
            pipeline.write_scan_queue(queue)

            btn_calls: list = []
            with patch.object(pipeline, "tg_post"), \
                 patch.object(pipeline, "tg_post_buttons",
                               side_effect=lambda t, b: btn_calls.append(t)):
                pipeline._scan_next()

            remaining = pipeline.read_scan_queue()
            ok(len(remaining) == 2, "_scan_next: first item removed")
            ok(remaining[0]["brand"] == "Omega",
               "_scan_next: Omega is now first")
            ok(len(btn_calls) == 1,
               "_scan_next: next item presented")

            # Exhaust queue
            pipeline._scan_next()
            pipeline._scan_next()

            tg_calls: list[str] = []
            with patch.object(pipeline, "tg_post",
                               side_effect=lambda t: tg_calls.append(t)):
                pipeline._scan_next()

            ok(any("empty" in m.lower() or "complete" in m.lower()
                   for m in tg_calls),
               "_scan_next on empty queue: appropriate message posted")
        finally:
            pipeline.SCAN_QUEUE_PATH = orig_path


def test_scan_start():
    print("\n--- Section 7g: _scan_start ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two real listing folders so dispatch / folder checks work
        listing1 = Path(tmpdir) / "164WU-79830RB"
        listing2 = Path(tmpdir) / "789ZZ-BB41"
        listing1.mkdir()
        listing2.mkdir()

        queue = [
            {"brand": "Tudor", "folder": str(listing1), "status": "new"},
            {"brand": "Tudor", "folder": str(listing2), "status": "new"},
        ]

        orig_path = pipeline.SCAN_QUEUE_PATH
        pipeline.SCAN_QUEUE_PATH = Path(tmpdir) / "_scan_queue.json"
        try:
            pipeline.write_scan_queue(queue)

            dispatched: list[Path] = []
            btn_calls: list[str] = []

            with patch.object(pipeline, "tg_post"), \
                 patch.object(pipeline, "tg_post_buttons",
                               side_effect=lambda t, b: btn_calls.append(t)), \
                 patch.object(pipeline, "dispatch",
                               side_effect=lambda f, dr=False: dispatched.append(f)):
                pipeline._scan_start(dry_run=False)

            ok(len(dispatched) == 1, "_scan_start: dispatch called once")
            ok(dispatched[0] == listing1,
               "_scan_start: dispatched the correct folder")
            ok(len(pipeline.read_scan_queue()) == 1,
               "_scan_start: first item removed from queue")
            ok(len(btn_calls) == 1,
               "_scan_start: next item presented after dispatch")

            # Last item in queue — dispatch it and verify queue empties
            with patch.object(pipeline, "tg_post"), \
                 patch.object(pipeline, "tg_post_buttons"), \
                 patch.object(pipeline, "dispatch"):
                pipeline._scan_start(dry_run=False)

            ok(pipeline.read_scan_queue() == [],
               "_scan_start on last item: queue emptied")
        finally:
            pipeline.SCAN_QUEUE_PATH = orig_path


def test_scan_main_entry():
    print("\n--- Section 7h: --scan flag in main() ---")

    with patch.object(sys, "argv", ["pipeline.py", "--scan"]), \
         patch.object(pipeline, "run_scan") as mock_run_scan:
        pipeline.main()
        ok(mock_run_scan.called, "--scan: run_scan called")
        ok("--scan" in mock_run_scan.call_args[0][0],
           "--scan: args forwarded to run_scan")

    with patch.object(sys, "argv", ["pipeline.py", "--scan", "--next"]), \
         patch.object(pipeline, "run_scan") as mock_run_scan:
        pipeline.main()
        ok("--next" in mock_run_scan.call_args[0][0],
           "--scan --next: --next forwarded")

    with patch.object(sys, "argv", ["pipeline.py", "--scan", "--start"]), \
         patch.object(pipeline, "run_scan") as mock_run_scan:
        pipeline.main()
        ok("--start" in mock_run_scan.call_args[0][0],
           "--scan --start: --start forwarded")


# ---------------------------------------------------------------------------
# Section 8 — Additional coverage (review gaps)
# ---------------------------------------------------------------------------

def test_tool_failure_path():
    print("\n--- Section 8a: tool failure path ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        with open(folder / "_draft.json", "w") as f:
            json.dump(_make_draft(1), f)

        tg_calls: list[str] = []

        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post",
                           side_effect=lambda t: tg_calls.append(t)), \
             patch.object(pipeline, "tg_post_buttons"), \
             patch.object(pipeline, "run_tool", return_value=(1, "pricing math error")):
            try:
                pipeline.dispatch(folder)
            except SystemExit as e:
                ok(e.code == 1, "run_pricing failure: exits 1")

        ok(any("failed" in m.lower() for m in tg_calls),
           "run_pricing failure: error message posted to Telegram")
        ok(any("pricing math error" in m for m in tg_calls),
           "run_pricing failure: tool output included in message")

    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        with open(folder / "_draft.json", "w") as f:
            json.dump(_make_draft(3), f)

        tg_calls = []
        with patch.object(pipeline, "validate_draft"), \
             patch.object(pipeline, "tg_post",
                           side_effect=lambda t: tg_calls.append(t)), \
             patch.object(pipeline, "tg_post_buttons"), \
             patch.object(pipeline, "run_tool", return_value=(1, "evaluator unavailable")):
            try:
                pipeline.dispatch(folder)
            except SystemExit as e:
                ok(e.code == 1, "run_grailzee failure: exits 1")

        ok(any("failed" in m.lower() for m in tg_calls),
           "run_grailzee failure: error message posted to Telegram")


def test_scan_fresh_dry_run():
    print("\n--- Section 8b: _scan_fresh dry_run=True ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_pipeline_root(Path(tmpdir))

        orig_path = pipeline.SCAN_QUEUE_PATH
        pipeline.SCAN_QUEUE_PATH = Path(tmpdir) / "_scan_queue.json"
        try:
            with patch.object(pipeline, "get_pipeline_root", return_value=root), \
                 patch.object(pipeline, "tg_post"), \
                 patch.object(pipeline, "tg_post_buttons"):
                pipeline._scan_fresh(dry_run=True)

            ok(not pipeline.SCAN_QUEUE_PATH.exists(),
               "_scan_fresh dry_run=True: queue file not written")
        finally:
            pipeline.SCAN_QUEUE_PATH = orig_path


def test_listing_status_all_steps():
    print("\n--- Section 8c: listing_status for all step values ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        step_cases = [
            (0,   "S0AA-REF",  "WatchTrack Lookup"),
            (1,   "S1AA-REF",  "Photo Review"),
            (2,   "S2AA-REF",  "Pricing"),
            (3,   "S3AA-REF",  "Descriptions"),
            (3.5, "S35AA-REF", "Grailzee Gate"),
        ]
        for step, folder_name, expected_fragment in step_cases:
            d = root / folder_name
            d.mkdir(exist_ok=True)
            with open(d / "_draft.json", "w") as f:
                json.dump({"step": step, "timestamp": "T", "inputs": {}}, f)
            status = pipeline.listing_status(d)
            ok(status is not None and "incomplete" in status,
               f"step={step}: status is 'incomplete'")
            ok(expected_fragment in (status or ""),
               f"step={step}: status mentions '{expected_fragment}'")


def test_get_pipeline_root_env_var():
    print("\n--- Section 8d: get_pipeline_root with VARDALUX_PIPELINE_ROOT ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        real_root = Path(tmpdir)
        with patch.dict(os.environ, {"VARDALUX_PIPELINE_ROOT": str(real_root)}):
            result = pipeline.get_pipeline_root()
            ok(result == real_root, "env var: returns the env-var path")

    # Non-existent path → fail
    with patch.dict(os.environ, {"VARDALUX_PIPELINE_ROOT": "/nonexistent_pipeline_root"}):
        try:
            pipeline.get_pipeline_root()
            ok(False, "bad env var: should have exited")
        except SystemExit as e:
            ok(e.code == 1, "bad env var: exits 1")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    test_parse_folder_name()
    test_watch_label()
    test_seed_and_archive()
    test_dispatch_routing()
    test_main_behaviour()
    test_integration_empty_folder()
    test_listing_status()
    test_build_scan_queue()
    test_scan_queue_persistence()
    test_scan_fresh()
    test_scan_empty_pipeline()
    test_scan_next()
    test_scan_start()
    test_scan_main_entry()
    test_tool_failure_path()
    test_scan_fresh_dry_run()
    test_listing_status_all_steps()
    test_get_pipeline_root_env_var()

    print(f"\nResults: {_passed} passed, {_failed} failed out of {_passed + _failed} tests")
    if _failed:
        print("Some tests FAILED.")
        sys.exit(1)
    print("All tests passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
