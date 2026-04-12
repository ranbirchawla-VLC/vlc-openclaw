#!/usr/bin/env python3
"""
pipeline.py — Vardalux listing pipeline orchestrator.

Pure Python. No LLM. Reads _draft.json to determine state, then dispatches
to the correct next step.

Usage:
  python3 pipeline.py /path/to/listing-folder           # fresh start or resume prompt
  python3 pipeline.py /path/to/listing-folder --resume  # skip prompt, dispatch now
  python3 pipeline.py /path/to/listing-folder --start-over
  python3 pipeline.py /path/to/listing-folder --dry-run

  python3 pipeline.py --scan           # walk pipeline root, present first actionable listing
  python3 pipeline.py --scan --next    # skip current, present next
  python3 pipeline.py --scan --start   # dispatch current listing, present next

Exit codes:
  0  step dispatched or pipeline complete
  1  validation or configuration error
  2  folder not found or not a directory

== Dispatch Table ==
  No draft    → create seed _draft.json, invoke step0-watchtrack skill
  step = None → WatchTrack in progress; re-invoke step0-watchtrack skill
  step = 0    → invoke step1-photos skill
  step = 1    → run run_pricing.py, post table + approval buttons to Telegram
  step = 2    → invoke step3a-canonical skill
  step = 3    → run run_grailzee_gate.py, post gate decision + buttons to Telegram
  step = 3.5  → run run_phase_b.py, immediately run generate_listing_pdf.py
  step = 4    → run generate_listing_pdf.py, post completion to Telegram + Slack

== LLM Skill Dispatch Protocol ==
For micro-skills (step0-watchtrack, step1-photos, step3a-canonical), pipeline.py
emits a JSON signal line to stdout:

  {"openclaw_action": "invoke_skill", "skill": "<name>", "folder": "<abs-path>"}

OpenClaw reads this and invokes the named skill. The skill handles its own
Telegram interaction, writes results to _draft.json (advancing the step), then
re-invokes pipeline.py:

  python3 pipeline.py <folder> --resume

== Approval Flow ==
Python-tool steps (1, 3) run synchronously. pipeline.py posts results to
Telegram with approval buttons, then exits. OpenClaw handles the button tap
and re-invokes with --resume. Steps 3.5 → 4 chain automatically (no user gate).

== Resume vs. Prompt ==
No flag, draft exists: post Resume / Start Over buttons and exit.
--resume:      skip the prompt, dispatch from the current step immediately.
--start-over:  archive old draft, begin fresh.

== Environment Variables ==
  TELEGRAM_BOT_TOKEN  — required for Telegram posting (falls back to stdout)
  SLACK_BOT_TOKEN     — required for Step 4 Slack notification

== Telegram / Slack ==
  TELEGRAM_CHAT_ID = "8712103657"   (all approvals and mid-pipeline interaction)
  SLACK_CHANNEL_ID = "C0APPJX0FGC"  (Step 4 completion only)
== Scan Mode ==
When the user says "check for new listings", "scan pipeline", or similar,
OpenClaw calls:

  python3 pipeline.py --scan          # walk pipeline root, present first item
  python3 pipeline.py --scan --next   # skip current, present next
  python3 pipeline.py --scan --start  # dispatch current, advance to next

Scan state is persisted in watch-listing-workspace/_scan_queue.json between
Telegram button taps. Each item is presented one at a time. Brand folders are
discovered dynamically — no hardcoded list. New brands appear automatically.

Pipeline root resolution order:
  1. VARDALUX_PIPELINE_ROOT environment variable
  2. ~/.openclaw/workspace/pipeline symlink (→ Google Drive folder)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEGRAM_CHAT_ID = "8712103657"
SLACK_CHANNEL_ID = "C0APPJX0FGC"

WORKSPACE    = Path(__file__).parent
TOOLS_DIR    = WORKSPACE / "tools"
SCHEMA_PATH  = WORKSPACE / "schema" / "draft_schema.json"
DRAFT_SAVE   = TOOLS_DIR / "draft_save.py"
RUN_PRICING  = TOOLS_DIR / "run_pricing.py"
RUN_GRAILZEE = TOOLS_DIR / "run_grailzee_gate.py"
RUN_PHASE_B  = TOOLS_DIR / "run_phase_b.py"
RUN_PDF      = TOOLS_DIR / "generate_listing_pdf.py"

# Scan state persists between Telegram button taps.
SCAN_QUEUE_PATH  = WORKSPACE / "_scan_queue.json"
PIPELINE_SYMLINK = Path.home() / ".openclaw" / "workspace" / "pipeline"

# Listing folder naming pattern: at least one char, a hyphen, at least one char.
# Excludes hidden folders (handled separately) and bare brand-folder names.
_LISTING_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9]*-.+$")

# Human-readable names for what just completed at each step
STEP_NAMES: dict[int | float | None, str] = {
    None: "WatchTrack (in progress)",
    0:    "WatchTrack Lookup",
    1:    "Photo Review",
    2:    "Pricing",
    3:    "Descriptions",
    3.5:  "Grailzee Gate",
    4:    "Listing Assembly",
}

# Human-readable names for what runs next
NEXT_STEP_NAMES: dict[int | float | None, str] = {
    None: "WatchTrack Lookup",
    0:    "Photo Review",
    1:    "Pricing",
    2:    "Descriptions",
    3:    "Grailzee Gate",
    3.5:  "Listing Assembly + PDF",
    4:    "PDF Generation",
}


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def fail(msg: str) -> NoReturn:
    """Print error to stderr and exit 1."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_draft(draft: dict) -> None:
    """
    Validate draft against schema/draft_schema.json.

    Emits a warning (does not fail) if jsonschema is not installed.
    """
    if not SCHEMA_PATH.exists():
        print("WARNING: Schema not found, skipping validation.", file=sys.stderr)
        return
    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=draft, schema=schema)
    except ImportError:
        print("WARNING: jsonschema not installed, skipping schema validation.", file=sys.stderr)
    except jsonschema.ValidationError as e:
        fail(f"_draft.json schema validation failed: {e.message}")


# ---------------------------------------------------------------------------
# Draft I/O
# ---------------------------------------------------------------------------

def load_draft(folder: Path) -> dict | None:
    """Return parsed _draft.json, or None if the file does not exist."""
    draft_path = folder / "_draft.json"
    if not draft_path.exists():
        return None
    with open(draft_path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            fail(f"_draft.json is not valid JSON: {e}")


def write_seed_draft(folder: Path, internal_ref: str, model_ref: str) -> None:
    """
    Write a minimal seed _draft.json for a fresh listing.

    Does not set the step field — that is written by step0-watchtrack when it
    completes. Uses an atomic write (tmp + rename) to avoid partial writes.
    """
    seed = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {
            "internal_ref": internal_ref,
            "model_ref": model_ref,
        },
    }
    draft_path = folder / "_draft.json"
    tmp_path   = draft_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2)
    tmp_path.rename(draft_path)


# ---------------------------------------------------------------------------
# Folder name parsing
# ---------------------------------------------------------------------------

def parse_folder_name(folder: Path) -> tuple[str, str]:
    """
    Parse listing folder basename into (internal_ref, model_ref).

    Naming convention: {internalRef}-{modelRef}/
    Examples:
      164WU-IW371446-1  → ("164WU", "IW371446-1")
      14618-M28500-0003 → ("14618", "M28500-0003")
      STANDALONE        → ("STANDALONE", "")
    """
    basename = folder.name
    parts = basename.split("-", 1)
    if len(parts) < 2:
        return basename, ""
    return parts[0], parts[1]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def watch_label(draft: dict) -> str:
    """
    Return 'Brand Model' when available, else 'internal_ref-model_ref'.

    Used in all Telegram status messages for a human-readable listing ID.
    """
    inputs = draft.get("inputs", {})
    brand  = inputs.get("brand", "")
    model  = inputs.get("model", "")
    if brand and model:
        return f"{brand} {model}"
    iref = inputs.get("internal_ref", "")
    mref = inputs.get("model_ref", "")
    return f"{iref}-{mref}" if mref else iref


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def _telegram_token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def tg_post(text: str) -> None:
    """
    Post a plain text message to Telegram chat 8712103657.

    Falls back to stdout prefixed with [TELEGRAM] when TELEGRAM_BOT_TOKEN is
    not set — enables standalone testing without a live bot.
    """
    token = _telegram_token()
    if not token:
        print(f"[TELEGRAM] {text}")
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
    except Exception as e:
        print(f"WARNING: Telegram post failed: {e}", file=sys.stderr)


def tg_post_buttons(text: str, buttons: list[tuple[str, str]]) -> None:
    """
    Post a Telegram message with a single row of inline keyboard buttons.

    Each button is (label, callback_data). callback_data encodes the action
    and folder path so OpenClaw can re-invoke pipeline.py correctly when
    the user taps.

    Falls back to stdout listing of buttons if TELEGRAM_BOT_TOKEN is absent.
    """
    token = _telegram_token()
    if not token:
        print(f"[TELEGRAM] {text}")
        print("[TELEGRAM BUTTONS] " + " | ".join(label for label, _ in buttons))
        return
    try:
        import requests
        keyboard = {
            "inline_keyboard": [
                [{"text": label, "callback_data": data} for label, data in buttons]
            ]
        }
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"WARNING: Telegram button post failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Slack helpers
# ---------------------------------------------------------------------------

def slack_post_completion(text: str) -> None:
    """
    Post a completion notification to Slack channel C0APPJX0FGC.

    Called only after PDF is generated (Step 4 complete). All mid-pipeline
    interaction goes to Telegram, never to Slack.
    """
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print(f"[SLACK] {text}")
        return
    try:
        import requests
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": SLACK_CHANNEL_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"WARNING: Slack post failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# LLM skill dispatch (OpenClaw signal)
# ---------------------------------------------------------------------------

def invoke_skill(skill_name: str, folder: Path) -> None:
    """
    Signal OpenClaw to invoke a micro-skill by emitting a JSON line to stdout.

    Applicable skills: step0-watchtrack, step1-photos, step3a-canonical.

    OpenClaw reads this line and invokes the named skill from the
    watch-listing-workspace/skills/ directory. The skill handles its own
    Telegram interaction, writes results + step number to _draft.json, then
    re-invokes pipeline.py with --resume when the user approves.

    Signal format:
      {"openclaw_action": "invoke_skill", "skill": "<name>", "folder": "<abs-path>"}
    """
    print(json.dumps({
        "openclaw_action": "invoke_skill",
        "skill": skill_name,
        "folder": str(folder.resolve()),
    }))


# ---------------------------------------------------------------------------
# Python tool runner
# ---------------------------------------------------------------------------

def run_tool(
    script: Path,
    folder: Path,
    dry_run: bool = False,
) -> tuple[int, str]:
    """
    Run a Python tool as a subprocess. Returns (returncode, stdout).

    stderr from the tool is forwarded immediately so it lands in the
    pipeline's stderr stream. stdout is captured and returned so the caller
    can decide what to post to Telegram.
    """
    cmd = [sys.executable, str(script), str(folder)]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode, result.stdout


# ---------------------------------------------------------------------------
# Start Over
# ---------------------------------------------------------------------------

def archive_draft(folder: Path) -> None:
    """Archive _draft.json → _draft.json.bak, overwriting any previous backup."""
    draft_path = folder / "_draft.json"
    if draft_path.exists():
        draft_path.rename(folder / "_draft.json.bak")


# ---------------------------------------------------------------------------
# Scan mode
# ---------------------------------------------------------------------------

def get_pipeline_root() -> Path:
    """
    Resolve the Vardalux Photo Pipeline root directory.

    Resolution order:
      1. VARDALUX_PIPELINE_ROOT environment variable
      2. ~/.openclaw/workspace/pipeline symlink
    """
    env_root = os.environ.get("VARDALUX_PIPELINE_ROOT")
    if env_root:
        root = Path(env_root)
        if root.exists():
            return root
        fail(f"VARDALUX_PIPELINE_ROOT does not exist: {root}")

    if PIPELINE_SYMLINK.exists():
        resolved = PIPELINE_SYMLINK.resolve()
        if resolved.is_dir():
            return resolved
        fail(
            f"Pipeline symlink resolves to {resolved}, which is not an accessible "
            "directory. Check that Google Drive is mounted and the symlink target exists."
        )

    fail(
        "Pipeline root not found. Set VARDALUX_PIPELINE_ROOT or create "
        "~/.openclaw/workspace/pipeline symlink pointing to the Google Drive folder."
    )


def listing_status(folder: Path) -> str | None:
    """
    Return a human-readable status string if the folder is actionable, else None.

    Actionable means the listing needs work:
      - No _draft.json → "new"
      - _draft.json with step < 4 → "incomplete — <step name>"
      - step absent (seed draft) → "new (WatchTrack pending)"

    Returns None for complete listings (step 4) and non-listing folders
    (no hyphen in name).
    """
    if not _LISTING_RE.match(folder.name):
        return None

    draft_path = folder / "_draft.json"
    if not draft_path.exists():
        return "new"

    try:
        with open(draft_path, encoding="utf-8") as f:
            draft = json.load(f)
    except (json.JSONDecodeError, OSError):
        return "unreadable draft"

    step = draft.get("step")
    if step is None:
        return "new (WatchTrack pending)"
    if step < 4:
        return f"incomplete \u2014 {STEP_NAMES.get(step, f'step {step}')}"
    return None  # step 4 = complete


def build_scan_queue(pipeline_root: Path) -> list[dict]:
    """
    Walk the pipeline root and return an ordered list of actionable listing records.

    Brand folders are every non-hidden subdirectory at the root level. No
    hardcoded list — new brands appear automatically. Within each brand folder,
    listing folders are identified by the {internalRef}-{modelRef} naming pattern.

    Sort order: incomplete listings first (step > 0, in-progress work), then
    new listings, both sorted by brand → folder name.

    Each record:
      {"brand": str, "folder": str (absolute), "status": str}
    """
    incomplete: list[dict] = []
    new:        list[dict] = []

    try:
        brand_dirs = sorted(pipeline_root.iterdir())
    except PermissionError as e:
        fail(f"Cannot read pipeline root: {e}")

    for brand_dir in brand_dirs:
        if not brand_dir.is_dir() or brand_dir.name.startswith("."):
            continue
        brand = brand_dir.name

        try:
            listing_dirs = sorted(brand_dir.iterdir())
        except PermissionError as e:
            print(f"WARNING: Cannot read brand folder {brand}: {e}", file=sys.stderr)
            continue

        for listing_dir in listing_dirs:
            if not listing_dir.is_dir() or listing_dir.name.startswith("."):
                continue
            status = listing_status(listing_dir)
            if status is None:
                continue
            record = {
                "brand":  brand,
                "folder": str(listing_dir.resolve()),
                "status": status,
            }
            if status.startswith("incomplete"):
                incomplete.append(record)
            else:
                new.append(record)

    return incomplete + new


def read_scan_queue() -> list[dict]:
    """Read the persisted scan queue. Returns [] if the file is absent or unreadable."""
    if not SCAN_QUEUE_PATH.exists():
        return []
    try:
        with open(SCAN_QUEUE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("queue", [])
    except (json.JSONDecodeError, OSError):
        return []


def write_scan_queue(queue: list[dict]) -> None:
    """Persist the scan queue to _scan_queue.json (atomic write)."""
    tmp = SCAN_QUEUE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "queue": queue,
            },
            f,
            indent=2,
        )
    tmp.rename(SCAN_QUEUE_PATH)


def present_scan_item(item: dict, position: int, total: int) -> None:
    """
    Post a single scan item to Telegram with Start This / Skip buttons.

    Callback data values:
      "scan:start" — OpenClaw calls: python3 pipeline.py --scan --start
      "scan:skip"  — OpenClaw calls: python3 pipeline.py --scan --next
    """
    brand  = item["brand"]
    folder = Path(item["folder"])
    name   = folder.name
    status = item["status"]
    counter = f"[{position}/{total}] " if total > 1 else ""

    tg_post_buttons(
        f"{counter}Found {status} listing: *{brand}* / {name}",
        [
            ("Start This", "scan:start"),
            ("Skip",       "scan:skip"),
        ],
    )


def run_scan(args: list[str], dry_run: bool = False) -> None:
    """
    Entry point for all scan sub-commands. Dispatches based on args.

    --scan          → fresh walk, build queue, present first item
    --scan --next   → skip current, present next
    --scan --start  → dispatch current listing, advance queue, present next
    """
    if "--start" in args:
        _scan_start(dry_run)
    elif "--next" in args:
        _scan_next()
    else:
        _scan_fresh(dry_run)


def _scan_fresh(dry_run: bool) -> None:
    """Walk the pipeline root, build a new queue, and present the first item."""
    root  = get_pipeline_root()
    tg_post(f"Scanning pipeline\u2026")
    queue = build_scan_queue(root)

    if not queue:
        tg_post("No new or incomplete listings found.")
        if SCAN_QUEUE_PATH.exists():
            SCAN_QUEUE_PATH.unlink()
        return

    if not dry_run:
        write_scan_queue(queue)

    n = len(queue)
    tg_post(f"Found {n} listing{'s' if n != 1 else ''} to review.")
    present_scan_item(queue[0], position=1, total=n)


def _scan_next() -> None:
    """Skip the current item and present the next one."""
    queue = read_scan_queue()
    if not queue:
        tg_post("Scan queue is empty. Run --scan to start a new scan.")
        return

    queue.pop(0)
    if not queue:
        write_scan_queue([])
        tg_post("Scan complete. All listings reviewed.")
        return

    write_scan_queue(queue)
    present_scan_item(queue[0], position=1, total=len(queue))


def _scan_start(dry_run: bool) -> None:
    """Dispatch the current scan item, advance the queue, present the next."""
    queue = read_scan_queue()
    if not queue:
        tg_post("Scan queue is empty. Run --scan to start a new scan.")
        return

    current       = queue.pop(0)
    folder        = Path(current["folder"])
    folder_exists = folder.exists()

    if not folder_exists:
        tg_post(f"Folder no longer exists: {folder.name}. Skipping.")
    else:
        dispatch(folder, dry_run)

    if not queue:
        write_scan_queue([])
        if folder_exists:
            # dispatch() already posted its own status; just note scan is done
            tg_post("No more listings in queue.")
    else:
        write_scan_queue(queue)
        present_scan_item(queue[0], position=1, total=len(queue))


# ---------------------------------------------------------------------------
# Step dispatchers (private)
# ---------------------------------------------------------------------------

def _dispatch_no_draft(folder: Path, dry_run: bool) -> None:
    """No _draft.json exists — parse folder, write seed draft, invoke WatchTrack."""
    internal_ref, model_ref = parse_folder_name(folder)
    if not dry_run:
        write_seed_draft(folder, internal_ref, model_ref)
    label = f"{internal_ref}-{model_ref}" if model_ref else internal_ref
    tg_post(f"Starting new listing for *{label}*. Launching WatchTrack lookup\u2026")
    invoke_skill("step0-watchtrack", folder)


def _dispatch_step_none(folder: Path, draft: dict) -> None:
    """Seed draft exists but WatchTrack never completed — re-invoke WatchTrack."""
    label = watch_label(draft)
    tg_post(f"Resuming WatchTrack lookup for *{label}*\u2026")
    invoke_skill("step0-watchtrack", folder)


def _dispatch_step0(folder: Path, draft: dict) -> None:
    """Step 0 complete (WatchTrack confirmed) — invoke photo review skill."""
    label = watch_label(draft)
    tg_post(f"WatchTrack complete for *{label}*. Launching photo review\u2026")
    invoke_skill("step1-photos", folder)


def _dispatch_step1(folder: Path, draft: dict, dry_run: bool) -> None:
    """Step 1 complete (photos approved) — run pricing calculator."""
    label = watch_label(draft)
    tg_post(f"Photos approved for *{label}*. Calculating pricing\u2026")
    rc, output = run_tool(RUN_PRICING, folder, dry_run)
    if rc != 0:
        tg_post(f"Pricing calculation failed for *{label}*.\n```\n{output.strip()}\n```")
        fail(f"run_pricing.py exited {rc}")
    tg_post_buttons(
        f"*PRICING \u2014 {label}*\n\n```\n{output.strip()}\n```\n\nReview and confirm:",
        [
            ("Approve", f"approve_pricing:{folder.resolve()}"),
            ("Request Changes", f"changes_pricing:{folder.resolve()}"),
        ],
    )


def _dispatch_step2(folder: Path, draft: dict) -> None:
    """Step 2 complete (pricing approved) — invoke canonical descriptions skill."""
    label = watch_label(draft)
    tg_post(f"Pricing approved for *{label}*. Writing descriptions\u2026")
    invoke_skill("step3a-canonical", folder)


def _dispatch_step3(folder: Path, draft: dict, dry_run: bool) -> None:
    """Step 3 complete (descriptions approved) — run Grailzee eligibility gate."""
    label = watch_label(draft)
    tg_post(f"Descriptions approved for *{label}*. Running Grailzee gate\u2026")
    rc, output = run_tool(RUN_GRAILZEE, folder, dry_run)
    if rc != 0:
        tg_post(f"Grailzee gate failed for *{label}*.\n```\n{output.strip()}\n```")
        fail(f"run_grailzee_gate.py exited {rc}")
    tg_post_buttons(
        f"*GRAILZEE GATE \u2014 {label}*\n\n```\n{output.strip()}\n```",
        [
            ("Proceed with Current Pricing", f"proceed_grailzee:{folder.resolve()}"),
            ("Adjust Pricing", f"adjust_grailzee:{folder.resolve()}"),
        ],
    )


def _dispatch_step35(folder: Path, draft: dict, dry_run: bool) -> None:
    """Step 3.5 complete (Grailzee resolved) — run Phase B then immediately PDF."""
    label = watch_label(draft)
    tg_post(f"Grailzee gate resolved for *{label}*. Assembling listing\u2026")
    rc, output = run_tool(RUN_PHASE_B, folder, dry_run)
    if rc != 0:
        tg_post(f"Listing assembly failed for *{label}*.\n```\n{output.strip()}\n```")
        fail(f"run_phase_b.py exited {rc}")
    # Phase B writes step=4. No user gate before PDF — chain immediately.
    tg_post(f"Listing assembled. Generating PDF for *{label}*\u2026")
    _run_pdf(folder, label, dry_run)


def _dispatch_step4(folder: Path, draft: dict, dry_run: bool) -> None:
    """Step 4 complete (listing assembled) — generate PDF. (Reached via --resume.)"""
    label = watch_label(draft)
    tg_post(f"Generating PDF for *{label}*\u2026")
    _run_pdf(folder, label, dry_run)


def _run_pdf(folder: Path, label: str, dry_run: bool) -> None:
    """Run generate_listing_pdf.py and post completion to Telegram and Slack."""
    if dry_run:
        tg_post(f"[dry-run] PDF generation skipped for *{label}*.")
        print("[dry-run] generate_listing_pdf.py not called")
        return
    rc, output = run_tool(RUN_PDF, folder, dry_run=False)
    if rc != 0:
        tg_post(f"PDF generation failed for *{label}*.\n```\n{output.strip()}\n```")
        fail(f"generate_listing_pdf.py exited {rc}")
    tg_post(f"\u2705 Listing complete: *{label}*. PDF generated.")
    slack_post_completion(
        f":white_check_mark: Listing complete: {label}. PDF generated in listing folder."
    )


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def dispatch(folder: Path, dry_run: bool = False) -> None:
    """
    Read _draft.json step and dispatch to the correct next action.

    The core routing function. Called after the draft exists and any
    resume / start-over prompt has been handled in main().
    """
    draft = load_draft(folder)

    if draft is None:
        _dispatch_no_draft(folder, dry_run)
        return

    validate_draft(draft)
    step = draft.get("step")

    match step:
        case None:
            _dispatch_step_none(folder, draft)
        case 0:
            _dispatch_step0(folder, draft)
        case 1:
            _dispatch_step1(folder, draft, dry_run)
        case 2:
            _dispatch_step2(folder, draft)
        case 3:
            _dispatch_step3(folder, draft, dry_run)
        case 3.5:
            _dispatch_step35(folder, draft, dry_run)
        case 4:
            _dispatch_step4(folder, draft, dry_run)
        case _:
            fail(f"Unknown step value in _draft.json: {step!r}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(
            "Usage:\n"
            "  pipeline.py <listing_folder> [--resume] [--start-over] [--dry-run]\n"
            "  pipeline.py --scan [--next] [--start] [--dry-run]",
            file=sys.stderr,
        )
        sys.exit(1)

    dry_run    = "--dry-run"    in args
    resume     = "--resume"     in args
    start_over = "--start-over" in args

    # ── Scan mode ────────────────────────────────────────────────────────────
    if "--scan" in args:
        run_scan(args, dry_run)
        return

    folder = Path(args[0])

    if not folder.exists() or not folder.is_dir():
        print(f"ERROR: Folder not found: {folder}", file=sys.stderr)
        sys.exit(2)

    draft = load_draft(folder)

    if start_over:
        if not dry_run and draft is not None:
            archive_draft(folder)
        tg_post(f"Starting over for *{folder.name}*. Previous draft archived.")
        dispatch(folder, dry_run)
        return

    # Existing draft, no --resume: show resume/start-over prompt and exit.
    # OpenClaw re-invokes with --resume or --start-over when the button is tapped.
    if draft is not None and not resume:
        step     = draft.get("step")
        label    = watch_label(draft)
        done     = STEP_NAMES.get(step, f"step {step}")
        upcoming = NEXT_STEP_NAMES.get(step, "next step")
        tg_post_buttons(
            f"Found in-progress listing for *{label}*.\n"
            f"Last completed: {done}.",
            [
                (f"Resume \u2014 {upcoming}", f"resume:{folder.resolve()}"),
                ("Start Over",               f"start_over:{folder.resolve()}"),
            ],
        )
        return

    dispatch(folder, dry_run)


if __name__ == "__main__":
    main()
