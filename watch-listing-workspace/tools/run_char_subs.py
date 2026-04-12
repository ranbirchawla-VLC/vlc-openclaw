#!/usr/bin/env python3
"""
run_char_subs.py — Facebook character substitution engine.

Parses references/character-substitutions.md at runtime (single source of truth).
Applies substitutions longest-key-first via case-sensitive str.replace().

Usage as library (imported by run_phase_b.py):
  from run_char_subs import apply_substitutions, needs_substitution

Usage standalone (pipe text through):
  echo "Omega Speedmaster automatic" | python3 run_char_subs.py --platform facebook_retail
  echo "Omega Speedmaster automatic" | python3 run_char_subs.py --platform wta  # no-op

Substitutions apply to: facebook_retail, facebook_wholesale.
Substitutions do NOT apply to: ebay, chrono24, grailzee, wta, reddit,
  value_your_watch, instagram.

Note on case sensitivity: substitutions are case-sensitive per spec.
  "automatic" matches, "Automatic" does not.
  "Papers" matches, "papers" does not.
  "Wire" matches, "wire" does not.
  run_phase_b.py is responsible for using canonical forms in Facebook text.
"""

import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SUBS_PATH = os.path.join(TOOLS_DIR, "..", "references", "character-substitutions.md")

# Platforms that require character substitutions (Facebook algorithm avoidance).
FACEBOOK_PLATFORMS = {"facebook_retail", "facebook_wholesale"}

# Module-level cache — loaded once on first use.
_SUBSTITUTIONS = None


def needs_substitution(platform: str) -> bool:
    """Return True only for Facebook platforms (retail and wholesale)."""
    return platform in FACEBOOK_PLATFORMS


def load_substitutions(ref_path: str = None) -> list:
    """
    Parse character-substitutions.md markdown tables into a list of
    (clean_text, substitution) tuples, sorted longest-key-first.

    Longest-first ordering prevents partial matches: e.g. if "Speedmaster"
    and "master" were both entries, "Speedmaster" must be processed first.
    With the current table the critical cases are multi-word brand entries
    (Jaeger-LeCoultre, Audemars Piguet, Patek Philippe, Royal Oak, TAG Heuer).

    Skips:
      - Header rows (col[0] == "Clean Text" or starts with "-")
      - Separator rows (|---|)
      - Entries where substitution is "No substitution needed" (e.g. USDT)
    """
    if ref_path is None:
        ref_path = SUBS_PATH

    subs = {}
    with open(ref_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]  # drop empty strings from split edges
            if len(parts) < 2:
                continue
            clean, sub = parts[0], parts[1]
            if clean == "Clean Text" or clean.startswith("-"):
                continue
            if "No substitution needed" in sub or sub.startswith("-"):
                continue
            if not clean or not sub:
                continue
            subs[clean] = sub

    # Sort descending by key length — longer strings processed first.
    return sorted(subs.items(), key=lambda x: len(x[0]), reverse=True)


def _get_substitutions() -> list:
    """Return cached substitutions, loading from disk on first call."""
    global _SUBSTITUTIONS
    if _SUBSTITUTIONS is None:
        _SUBSTITUTIONS = load_substitutions()
    return _SUBSTITUTIONS


def apply_substitutions(text: str, subs: list = None) -> str:
    """
    Apply all character substitutions to text via case-sensitive str.replace().
    Substitutions are applied longest-first to prevent partial matches.

    Args:
        text: Clean text string to substitute.
        subs: Optional explicit list of (clean, sub) tuples — used by tests
              to bypass file I/O. Defaults to the loaded markdown table.

    Returns:
        Text with all substitutions applied. Unmodified if no matches.
    """
    if subs is None:
        subs = _get_substitutions()
    for clean, sub in subs:
        text = text.replace(clean, sub)
    return text


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Apply Facebook character substitutions to stdin text."
    )
    parser.add_argument(
        "--platform",
        required=True,
        help="Platform name: facebook_retail, facebook_wholesale, wta, reddit, etc.",
    )
    args = parser.parse_args()

    text = sys.stdin.read()

    if needs_substitution(args.platform):
        sys.stdout.write(apply_substitutions(text))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
