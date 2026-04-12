#!/usr/bin/env python3
"""
test_draft_schema.py — Validates draft_schema.json against known fixtures.

Run standalone: python3 test_draft_schema.py
No pytest needed. Exits 0 on all pass, 1 if any test fails.

Tests are structured as (name, draft_dict, expect_valid, reason_if_fail).
"""

import json
import os
import sys

try:
    import jsonschema
    from jsonschema import validate, ValidationError
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip3 install jsonschema")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load schema
# ---------------------------------------------------------------------------

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "draft_schema.json")
with open(SCHEMA_PATH) as f:
    SCHEMA = json.load(f)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimal step-0 draft: only the two required top-level fields + minimal inputs.
MINIMAL_STEP0 = {
    "step": 0,
    "timestamp": "2026-04-11T00:00:00Z",
    "inputs": {
        "internal_ref": "164WU",
        "model_ref": "IW371446-1"
    }
}

# Real Glashütte draft as it should look AFTER decomposed step 0 runs:
# condition is absent (WatchTrack says "Pre-owned", so we wait for Telegram confirmation).
# inputs_pending holds retail_net that arrived before step 1 gate.
# watchtrack.recent_comps uses the structured WatchTrack object format.
GLASHUTTE_STEP0_CLEAN = {
    "step": 0,
    "timestamp": "2026-04-10T11:16:00Z",
    "inputs": {
        "internal_ref": "542G4",
        "model_ref": "1-36-02-01-02-61",
        "brand": "Glashütte Original",
        "model": "Senator Excellence",
        "reference": "1-36-02-01-02-61",
        "included": "Watch with original box and papers",
        "year": "May 2023",
        "dial_color": "Silver",        # extra field — allowed by additionalProperties: true on inputs
        "case_material": "Steel",
        "movement": "Automatic"
        # condition intentionally absent — WatchTrack said "Pre-owned", user must confirm via Telegram
    },
    "inputs_pending": {
        "retail_net": 19000
    },
    "watchtrack": {
        "serial": "121030",
        "cost_basis": 14500,
        "retail_price_wt": 20499,      # extra WatchTrack fields — allowed by additionalProperties: true
        "wholesale_price_wt": 17500,
        "recent_comps": {              # structured object format (not the simple array)
            "source": "Chrono24 3/24/2026",
            "global_count": 88,
            "global_range": "$8,925-$20,299",
            "us_count": 17,
            "us_range": "$8,900-$20,299",
            "exact_ref_range": "$12,800-$20,299"
        },
        "sub_status": "Listing Prep",
        "sourced_from": "Purchase #TEYPA1042 (Michael Xylas)",
        "received": "November 4, 2025",
        "notes": "Serviced: With Victor (Nov 7, 2025). Checked in Nov 11, 2025."
    },
    "approved": {}
}

# Step-4 complete draft — all sections populated (IWC Portugieser example from spec).
COMPLETE_STEP4 = {
    "step": 4,
    "timestamp": "2026-03-29T14:32:00Z",
    "inputs": {
        "internal_ref": "164WU",
        "model_ref": "IW371446-1",
        "brand": "IWC",
        "model": "Portugieser Chronograph",
        "reference": "IW371446",
        "retail_net": 3200,
        "wholesale_net": None,
        "wta_price": 2900,
        "wta_comp": 3350,
        "reddit_price": 3100,
        "msrp": 7500,
        "tier": 1,
        "condition": "Excellent",
        "condition_detail": "Case: Light desk wear on polished surfaces. Brushed surfaces crisp.",
        "grailzee_format": "NR",
        "buffer": 5,
        "included": "Box and papers",
        "year": "2023",
        "case_size": "41mm",
        "case_material": "Stainless Steel",
        "movement": "IWC Calibre 89361"
    },
    "watchtrack": {
        "cost_basis": 2650,
        "recent_comps": [3100, 3250, 2975],   # simple array format
        "serial": "ABC12345",
        "notes": "Retail NET $3,200"
    },
    "pricing": {
        "ebay": {
            "list_price": 3849,
            "auto_accept": 3650,
            "auto_decline": 3250
        },
        "chrono24": {
            "list_price": 3675
        },
        "facebook_retail": {
            "list_price": 3400
        },
        "facebook_wholesale": None,
        "wta": {
            "price": 2900,
            "comp": 3350,
            "max_allowed": 3015,
            "sweet_spot": 2680,
            "status": "NOTE"
        },
        "reddit": {
            "list_price": 3100
        },
        "grailzee": {
            "format": "NR",
            "reserve_price": None
        }
    },
    "canonical": {
        "description": "The IWC Portugieser Chronograph remains one of the most coherent expressions of classical watchmaking in a contemporary case.",
        "condition_line": "Excellent condition with light desk wear. Full set with box and papers.",
        "grailzee_desc": "A watch built on a century of Portuguese nautical obsession."
    },
    "approved": {
        "photos": {
            "status": "approved",
            "notes": "Strong set. 14 images, all angles covered.",
            "timestamp": "2026-03-29T14:10:00Z"
        },
        "pricing": {
            "status": "approved",
            "table": {"ebay": 3849, "chrono24": 3675},
            "timestamp": "2026-03-29T14:32:00Z"
        },
        "descriptions": {
            "status": "approved",
            "timestamp": "2026-03-29T15:00:00Z"
        },
        "grailzee_gate": {
            "status": "proceed",
            "median": 3150,
            "recommendation": "YES — No Reserve",
            "timestamp": "2026-03-29T15:10:00Z"
        }
    }
}


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests():
    tests = [

        # ---- PASS cases ----

        (
            "T01: Minimal step-0 draft (only required fields)",
            MINIMAL_STEP0,
            True,
            None
        ),
        (
            "T02: Glashutte step-0 draft (no condition, structured recent_comps, extra WatchTrack fields)",
            GLASHUTTE_STEP0_CLEAN,
            True,
            None
        ),
        (
            "T03: Complete step-4 draft (all sections, NR grailzee, array-format recent_comps)",
            COMPLETE_STEP4,
            True,
            None
        ),
        (
            "T04: WTA status OK (at or below sweet spot)",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "wta": {
                "price": 2600, "comp": 3350, "max_allowed": 3015, "sweet_spot": 2680, "status": "OK"
            }}},
            True,
            None
        ),
        (
            "T05: WTA status OVER (schema allows it — business logic enforcement is run_pricing.py's job)",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "wta": {
                "price": 3200, "comp": 3350, "max_allowed": 3015, "sweet_spot": 2680, "status": "OVER"
            }}},
            True,
            None
        ),
        (
            "T06: Reserve grailzee with reserve_price set",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "grailzee": {
                "format": "Reserve", "reserve_price": 2750
            }}},
            True,
            None
        ),
        (
            "T07: grailzee_format skip -> pricing.grailzee is null",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "grailzee": None}},
            True,
            None
        ),
        (
            "T08: step 3.5 (Grailzee gate step)",
            {**MINIMAL_STEP0, "step": 3.5},
            True,
            None
        ),

        # ---- FAIL cases ----

        (
            "T09: Invalid step value (5)",
            {**MINIMAL_STEP0, "step": 5},
            False,
            "step must be in [0, 1, 2, 3, 3.5, 4]"
        ),
        (
            "T10: Missing required field 'step'",
            {"timestamp": "2026-04-11T00:00:00Z"},
            False,
            "'step' is required"
        ),
        (
            "T11: Missing required field 'timestamp'",
            {"step": 0},
            False,
            "'timestamp' is required"
        ),
        (
            "T12: Unknown top-level key",
            {**MINIMAL_STEP0, "surprise_key": "this should not be here"},
            False,
            "additionalProperties: false at top level"
        ),
        (
            "T13: condition 'Mint' (explicitly banned per Absolute Do Nots)",
            {**MINIMAL_STEP0, "inputs": {**MINIMAL_STEP0["inputs"], "condition": "Mint"}},
            False,
            "condition enum does not include Mint"
        ),
        (
            "T14: condition 'Pre-owned' (raw WatchTrack value — must be normalized before writing)",
            {**MINIMAL_STEP0, "inputs": {**MINIMAL_STEP0["inputs"], "condition": "Pre-owned"}},
            False,
            "condition enum does not include Pre-owned"
        ),
        (
            "T15: tier 4 (out of range)",
            {**MINIMAL_STEP0, "inputs": {**MINIMAL_STEP0["inputs"], "tier": 4}},
            False,
            "tier must be 1, 2, or 3"
        ),
        (
            "T16: grailzee_format 'auction' (invalid value)",
            {**MINIMAL_STEP0, "inputs": {**MINIMAL_STEP0["inputs"], "grailzee_format": "auction"}},
            False,
            "grailzee_format must be NR, Reserve, or skip"
        ),
        (
            "T17: pricing.ebay missing auto_accept (required field)",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "ebay": {
                "list_price": 3849,
                "auto_decline": 3250
                # auto_accept intentionally missing
            }}},
            False,
            "ebay requires list_price, auto_accept, auto_decline"
        ),
        (
            "T18: pricing.ebay extra field (additionalProperties: false on ebay)",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "ebay": {
                "list_price": 3849,
                "auto_accept": 3650,
                "auto_decline": 3250,
                "extra_field": "not allowed"
            }}},
            False,
            "pricing.ebay additionalProperties: false"
        ),
        (
            "T19: wta status 'COMPLIANT' (not in enum)",
            {**COMPLETE_STEP4, "pricing": {**COMPLETE_STEP4["pricing"], "wta": {
                "price": 2900, "comp": 3350, "max_allowed": 3015, "sweet_spot": 2680,
                "status": "COMPLIANT"
            }}},
            False,
            "wta.status must be OK, NOTE, or OVER"
        ),
        (
            "T20: approved.photos status 'pending' (not in enum)",
            {**COMPLETE_STEP4, "approved": {**COMPLETE_STEP4["approved"], "photos": {
                "status": "pending",
                "notes": "waiting",
                "timestamp": "2026-04-11T00:00:00Z"
            }}},
            False,
            "approved.photos.status must be approved or changes_requested"
        ),

    ]

    passed = 0
    failed = 0
    errors = []

    for name, draft, expect_valid, reason in tests:
        try:
            validate(instance=draft, schema=SCHEMA)
            actually_valid = True
        except ValidationError as e:
            actually_valid = False
            validation_message = e.message
        except Exception as e:
            actually_valid = False
            validation_message = f"Unexpected error: {e}"
        else:
            validation_message = None

        ok = (actually_valid == expect_valid)
        status = "PASS" if ok else "FAIL"

        if ok:
            passed += 1
            print(f"  {status}  {name}")
        else:
            failed += 1
            if expect_valid and not actually_valid:
                detail = f"       Expected VALID but got: {validation_message}"
            else:
                detail = f"       Expected INVALID (reason: {reason}) but schema accepted it"
            print(f"  {status}  {name}")
            print(detail)
            errors.append(name)

    print()
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")

    if errors:
        print("\nFailed tests:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("All tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
