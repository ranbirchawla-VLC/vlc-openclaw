# Grailzee Eval v2 — Implementation Plan & Design Detail
**For Claude Code Build | April 15, 2026**

---

## 1. WHAT THIS DOCUMENT IS

A complete specification for rebuilding the Grailzee evaluation system from a monolithic skill into a focused, multi-skill architecture. Claude Code should be able to execute this spec without coming back for design clarification. If a decision is ambiguous, this document resolves it. If something isn't covered, flag it before building.

---

## 2. PROBLEM STATEMENT

The current system (grailzee-eval) is a single OpenClaw skill with three modes crammed into one SKILL.md, backed by a 49K monolithic Python analyzer. Two structural problems:

**The system is a rearview mirror, not a radar.** It orbits a fixed reference list, treats discovery as a secondary footnote, and has no concept of momentum or trajectory. It tells you what was true. It doesn't tell you what's becoming true.

**The system never learns from outcomes.** It recommends buys but never checks what happened. No feedback loop from closed trades to model accuracy. The presentation premium (+14% across measured trades) exists as a manual number rather than an automated input to buy calculations.

---

## 3. ARCHITECTURE OVERVIEW

### Before (current)

```
One SKILL.md → 3 modes → 4 Python scripts (49K + 20K + 9K + 8.5K)
                         → 2 reference files
                         → 1 analysis cache on Google Drive
```

### After (target)

```
grailzee-router     →  Intent detection, dispatch only (~50 lines)
   ├─ grailzee-report    →  Report processing, reference scoring, name resolution, outcome validation
   ├─ grailzee-deal      →  Single deal evaluation with confidence scoring
   ├─ grailzee-targets   →  Active hunting list with momentum signals
   └─ grailzee-ledger    →  Trade logging, performance queries, premium tracking
```

**Shared data layer (Google Drive):**

```
GrailzeeData/
├── reports/              ← Raw Excel files (drop new ones here)
├── reports_csv/          ← Converted CSVs (analyzer writes on ingest)
├── output/               ← Human-readable outputs (spreadsheet, summary, brief)
├── state/
│   ├── analysis_cache.json    ← Deal evaluator reads this
│   ├── sourcing_brief.json    ← Target query reads this
│   ├── trade_ledger.csv       ← Outcome tracking (append-only)
│   ├── name_cache.json        ← Reference → display name lookup (append-only)
│   └── run_history.json       ← Analyzer run log
└── backup/               ← Auto-rotated previous caches (last 10)
```

**Base path (all skills share this constant):**
```
/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/
```

---

## 4. TRADE LEDGER — SCHEMA & RULES

### 4.1 CSV Format

Filename: `trade_ledger.csv`
Location: `GrailzeeData/state/trade_ledger.csv`
Encoding: UTF-8, standard CSV (RFC 4180)

**Manual entry columns (what the user provides):**

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| date_closed | YYYY-MM-DD | 2026-02-14 | Date the trade settled |
| brand | string | Tudor | Case-insensitive on read |
| reference | string | 79830RB | As listed in Grailzee/platform |
| platform | string | GNR | Short code (see platform codes below) |
| buy_price | number | 2750 | No dollar sign, no commas |
| sell_price | number | 3200 | No dollar sign, no commas |

**Platform codes:**

| Code | Platform |
|------|----------|
| GNR | Grailzee No Reserve (branded account) |
| GRES | Grailzee Reserve (separate account) |
| EBAY | eBay |
| C24 | Chrono24 |
| FB | Facebook groups |
| WTA | WTA Dealer Chat |
| VYW | Value Your Watch |
| REDDIT | Reddit r/watchexchange |
| OTHER | Any platform not listed |

**Example rows:**
```csv
date_closed,brand,reference,platform,buy_price,sell_price
2025-10-10,Tudor,79830RB,GNR,2750,3200
2025-11-15,Tudor,91650,GNR,1500,1675
2025-12-01,Tudor,79230R,GNR,2800,3150
2026-01-05,Panerai,PAM01360,EBAY,3400,3664
2026-02-14,Tudor,28600,GNR,1900,2100
2026-03-01,Breitling,A17320,GNR,2100,2350
```

### 4.2 Calculated Fields (computed at analysis time, never stored in CSV)

The analyzer and ledger query scripts compute these by joining ledger rows against the cache/report data closest to the trade date:

| Field | Formula | Purpose |
|-------|---------|---------|
| platform_fees | Looked up from fee table by platform code | Grailzee NR=$149, Reserve=$199, eBay=tiered, C24=7.5%, FB=$0 |
| net_profit | sell_price - buy_price - platform_fees | Actual dollar return |
| roi_pct | (net_profit / buy_price) * 100 | Per-trade return |
| median_at_trade | Median from cache closest to date_closed | What the model thought the reference was worth |
| max_buy_at_trade | MAX BUY from cache closest to date_closed | What the model recommended |
| model_correct | buy_price <= max_buy_at_trade AND net_profit > 0 | Did the model's YES result in a profitable trade? |
| premium_vs_median | ((sell_price - median_at_trade) / median_at_trade) * 100 | Presentation premium per trade (Marissa's edge) |

### 4.3 Fee Table (for calculated fields)

```python
PLATFORM_FEES = {
    "GNR":   lambda buy, sell: 149,                    # $49 fee + $100 ship
    "GRES":  lambda buy, sell: 199,                    # $99 fee + $100 ship
    "EBAY":  lambda buy, sell: ebay_fee(sell),          # Tiered: 12.5%/4%/3%
    "C24":   lambda buy, sell: round(sell * 0.075, 2),  # 7.5% flat
    "FB":    lambda buy, sell: round(sell * 0.045, 2),  # CC fee only (4.5%)
    "WTA":   lambda buy, sell: 0,                       # No platform fee
    "VYW":   lambda buy, sell: 0,                       # Verify and update
    "REDDIT": lambda buy, sell: 0,                      # No platform fee
    "OTHER": lambda buy, sell: 0,                       # Manual adjustment
}

def ebay_fee(sell_price):
    """eBay tiered fee: 12.5% on first $1K, 4% on $1K-$5K, 3% above $5K"""
    if sell_price <= 1000:
        return round(sell_price * 0.125, 2)
    elif sell_price <= 5000:
        return round(125 + (sell_price - 1000) * 0.04, 2)
    else:
        return round(125 + 160 + (sell_price - 5000) * 0.03, 2)
```

### 4.4 Presentation Premium Auto-Calculation

Every time the analyzer runs, it reads the trade ledger and computes:

```python
def calculate_presentation_premium(ledger_rows):
    """
    Returns:
        avg_premium: float (average % above median across all measured trades)
        trade_count: int (number of trades with measurable premium)
        threshold_met: bool (10+ trades at +8% or above triggers MAX BUY adjustment)
        adjustment: float (half the average premium, applied to MAX BUY if threshold met)
    """
    premiums = [row.premium_vs_median for row in ledger_rows if row.median_at_trade is not None]
    if not premiums:
        return {"avg_premium": 0, "trade_count": 0, "threshold_met": False, "adjustment": 0}

    avg = statistics.mean(premiums)
    count = len(premiums)
    threshold_met = count >= 10 and avg >= 8.0
    adjustment = round(avg / 2, 1) if threshold_met else 0

    return {
        "avg_premium": round(avg, 1),
        "trade_count": count,
        "threshold_met": threshold_met,
        "adjustment": adjustment,
    }
```

When `threshold_met` is True, every MAX BUY calculation gets adjusted:

```python
def adjusted_max_buy(median, fixed_cost, premium_adjustment_pct):
    """
    If presentation premium threshold is met, raise MAX BUY by half the avg premium.
    Example: 14% avg premium → 7% adjustment → MAX BUY uses 1.05 - 0.07 effective margin.
    Implementation: apply adjustment to the median (our expected sell is higher than median).
    """
    adjusted_median = median * (1 + premium_adjustment_pct / 100)
    return round((adjusted_median - fixed_cost) / 1.05, -1)
```

### 4.5 Confidence Scoring (per reference)

When the deal evaluator runs, it joins against the trade ledger to add confidence context:

```python
def reference_confidence(ledger_rows, brand, reference):
    """
    How confident is the model on this specific reference?
    Returns None if no trades exist for this reference.
    """
    trades = [r for r in ledger_rows if r.brand == brand and r.reference == reference]
    if not trades:
        return None

    profitable = sum(1 for t in trades if t.net_profit > 0)
    avg_roi = statistics.mean([t.roi_pct for t in trades])
    avg_premium = statistics.mean([t.premium_vs_median for t in trades if t.premium_vs_median is not None])

    return {
        "trades": len(trades),
        "profitable": profitable,
        "win_rate": round(profitable / len(trades) * 100, 1),
        "avg_roi": round(avg_roi, 1),
        "avg_premium": round(avg_premium, 1) if avg_premium else None,
        "last_trade": max(t.date_closed for t in trades),
    }
```

This gets added to the deal evaluator response. "We've traded this reference 4 times, 100% win rate, 9.2% average ROI" is actionable intelligence that "YES at $2,750" alone is not.

---

## 5. ROLLING MARKET WINDOW

### 5.1 Report Ingestion

When a new Grailzee Pro Excel report arrives:

1. Convert to CSV immediately. Write to `reports_csv/` with naming: `grailzee_YYYY-MM-DD.csv`
2. Archive the original Excel in `reports/` (never delete)
3. The CSV is the canonical data format from this point forward

**CSV conversion rules:**
- Read the "Auctions Sold" sheet (or first sheet if not found)
- Auto-detect header row (scan first 5 rows for column keywords)
- Preserve all columns: reference, make, title, condition, papers, sold price, date, sell-through %
- Strip currency symbols and commas from price columns
- Normalize condition values to lowercase
- Write with standard headers (see Section 5.3)

### 5.2 Window Boundaries

| Window | Purpose | Reports | Duration |
|--------|---------|---------|----------|
| Pricing window | Current median, MAX BUY, risk | Latest 2 reports | ~4 weeks |
| Trend window | Direction, momentum, trajectory | Latest 6 reports | ~3 months |
| Archive | Historical record | Everything older | Unlimited |

**Rules:**
- Pricing calculations (median, MAX BUY, risk) use only the pricing window (most recent 2 reports)
- Trend calculations (median movement, volume trajectory, sell-through direction) use the full trend window (most recent 6 reports)
- Reports older than the trend window are ignored in active analysis but never deleted
- If fewer than 6 reports exist, use all available reports for trends
- If only 1 report exists, no trend data (flag as "First report, no trend history")

### 5.3 Standardized CSV Headers

```
date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct
```

The analyzer script must normalize whatever headers the Grailzee Pro report uses into these standard columns. The column mapping logic already exists in the current `analyze_report.py` (lines 130-152) and should be preserved.

---

## 6. REFERENCE ANALYSIS ENGINE

This is the most important architectural change. The system scores every reference in the dataset on its own merits. No fixed list, no tiers, no special treatment. The data determines what's worth trading.

### 6.1 Full-Dataset Scoring

On every report processing run, the analyzer scans ALL references in the data set. Every reference with 3+ sales in the current report gets scored:

```python
def analyze_all_references(all_sales, name_cache):
    """
    Score every reference in the dataset. No core list, no tiers.
    The data determines priority, not a hardcoded list.
    """
    results = {}

    for ref, sales in group_by_reference(all_sales):
        if len(sales) < 3:
            continue  # Not enough data to evaluate

        metrics = analyze_reference(sales)
        display_name = name_cache.get(ref, {"brand": sales[0].brand, "model": ref})

        results[ref] = {
            "brand": display_name["brand"],
            "model": display_name.get("model", ref),
            "reference": ref,
            "named": ref in name_cache,  # False = needs LLM name resolution
            "volume": len(sales),
            "median": metrics.median,
            "max_buy_nr": max_buy_nr(metrics.median),
            "risk_nr": metrics.risk,
            "signal": metrics.signal,
            "st_pct": metrics.sell_through,
        }

    return results
```

### 6.2 Change Detection

| Category | Criteria | What it means |
|----------|----------|---------------|
| **Emerged** | 3+ sales in current report, fewer than 3 in previous report (or absent entirely) | New on the radar. Wasn't scoreable before, now has enough volume |
| **Shifted** | Present in both periods, median moved >5% in either direction | Price signal changing. Worth attention whether up or down |
| **Faded** | Was scoreable last period (3+ sales), now dropped below 3 | Losing steam. May recover next period or may be seasonal |
| **Unnamed** | Scored but not in the name cache | Needs LLM name resolution via web search. Queued for the LLM after Python finishes |

### 6.3 Momentum Scoring

For every reference with data in 3+ reports within the trend window:

```python
def momentum_score(trend_data):
    """
    Score -3 to +3 based on directional signals across reports.
    +1 for each report where median rose
    -1 for each report where median fell
    Additional +/-1 for volume trend (increasing/decreasing)
    Capped at +/-3.

    Returns:
        score: int (-3 to +3)
        label: str (Cooling, Stable, Warming, Hot)
    """
    median_changes = [t.median_pct_change for t in trend_data]
    volume_changes = [t.volume_change for t in trend_data]

    score = 0
    for mc in median_changes:
        if mc > 2:
            score += 1
        elif mc < -2:
            score -= 1

    vol_trend = sum(1 if v > 0 else -1 if v < 0 else 0 for v in volume_changes)
    if vol_trend > 0:
        score += 1
    elif vol_trend < 0:
        score -= 1

    score = max(-3, min(3, score))

    labels = {
        -3: "Cooling Fast", -2: "Cooling", -1: "Softening",
        0: "Stable", 1: "Warming", 2: "Heating Up", 3: "Hot"
    }

    return {"score": score, "label": labels[score]}
```

This score gets written into the cache and the sourcing brief. The deal evaluator uses it as context. The target query sorts by it. "Tudor 79830RB is Hot (+3), median up 8% across 3 reports, volume increasing" is a fundamentally different signal than "Tudor 79830RB is Stable."

### 6.4 Name Cache

**File:** `GrailzeeData/state/name_cache.json`

A flat JSON dictionary mapping reference numbers to display names. Python reads this for spreadsheet labels, summary formatting, and brief generation. The LLM writes to it when resolving unknown references via web search.

```python
def load_name_cache(cache_path=None):
    """Load the reference → display name lookup."""
    cache_path = cache_path or os.path.join(GRAILZEE_ROOT, "state", "name_cache.json")
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path, 'r') as f:
        return json.load(f)

def save_name_cache(cache, cache_path=None):
    """Write updated name cache. Append-only in practice."""
    cache_path = cache_path or os.path.join(GRAILZEE_ROOT, "state", "name_cache.json")
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2, sort_keys=True)

def resolve_display_name(ref, name_cache, fallback_brand=""):
    """Get display name from cache, or return raw reference."""
    entry = name_cache.get(ref)
    if entry:
        return f"{entry['brand']} {entry['model']}"
    return f"{fallback_brand} {ref}".strip()
```

**Name resolution flow (LLM, not Python):**

After the orchestrator runs, it returns a list of unnamed references. The LLM in the grailzee-report skill handles resolution:

1. For each unnamed reference, web search: `"{brand} {reference} watch"`
2. Parse the result for official model name
3. Call a small Python helper to append the new entry to `name_cache.json`
4. MNEMO captures the search + resolution as episodic memory automatically

The name cache never shrinks. References only get added. On a mature system (after 3-4 report cycles), the unnamed list is typically empty.

**Alternate reference matching:** The name cache supports an `alt_refs` field (e.g., `"79830RB"` also matches `"M79830RB-0001"`). The `normalize_ref()` function in `grailzee_common.py` handles stripping prefixes and suffixes for fuzzy matching. If a new variant appears in the data, the LLM can add it to the `alt_refs` array.

---

## 7. MNEMO Integration

MNEMO (`watzon/mnemo`) is a transparent HTTP proxy running at `127.0.0.1:9999` between OpenClaw and the Anthropic API. It injects semantically relevant memories into every LLM call and captures every response as a searchable memory. All OpenClaw Grailzee skills route through it automatically.

**What MNEMO does for this system without any skill-level code:**

- Captures every deal evaluation, report summary, and trade log as episodic memory
- On future calls, injects relevant past context (e.g., "last time we evaluated Tudor 79830RB, the recommendation was YES at $2,750 with 8.2% margin")
- Name resolutions from web searches get captured and may surface in future sessions before the LLM even needs to search

**What skills should NOT do because MNEMO handles it:**

- Re-state business context (fee structures, account rules, margin targets) in SKILL.md files. Seed these as semantic memories at setup and MNEMO injects them when relevant
- Carry conversation history manually. MNEMO's episodic memory handles cross-session context
- Duplicate the name cache in the SKILL.md. MNEMO may already have the reference → name mapping from a previous session

**What skills SHOULD do:**

- Verify MNEMO is running: `curl http://localhost:9999/health` in the startup check
- Keep SKILL.md files focused on workflow steps and dispatch logic only
- Let Python handle all deterministic work (the name cache JSON is the authoritative source for scripts, not MNEMO)

**Initial MNEMO seeding (Phase 13 of the build):**

```bash
# Business model context
mnemo-cli memory add "Grailzee NR fixed cost is $149 ($49 fee + $100 shipping). Reserve is $199 ($99 + $100). Target margin per trade is 5%." --type semantic
mnemo-cli memory add "MAX BUY NR formula: (Median - 149) / 1.05. MAX BUY Reserve: (Median - 199) / 1.05." --type semantic
mnemo-cli memory add "Branded Grailzee account is NR only. Separate reserve account being built to Pro status." --type semantic
mnemo-cli memory add "Presentation premium currently +14% across measured trades. Threshold for auto-adjustment: 10 trades at +8% or above." --type semantic

# Operational context
mnemo-cli memory add "Grailzee data lives on Google Drive at Vardalux Shared Drive/GrailzeeData/. Reports in reports/, CSVs in reports_csv/, state in state/." --type procedural
mnemo-cli memory add "Trade ledger is state/trade_ledger.csv. Six columns: date_closed, brand, reference, platform, buy_price, sell_price. Platform codes: GNR, GRES, EBAY, C24, FB." --type procedural
mnemo-cli memory add "Name cache is state/name_cache.json. Maps reference numbers to brand + model display names. LLM web-searches unknown references and appends." --type procedural

# Globalize all seeded memories so they're available across sessions
mnemo-cli memory list --type semantic | # globalize each
mnemo-cli memory list --type procedural | # globalize each
```

**Ongoing maintenance:** None. MNEMO compounds knowledge automatically from every interaction. The only manual intervention is if a seeded fact changes (e.g., Grailzee changes their fee structure), in which case delete the old memory and seed the updated fact.

---

## 8. SKILL SPECIFICATIONS

### 8.1 grailzee-router

**Purpose:** Intent detection and dispatch. Lives in the Telegram group chat. Does not know how to analyze, evaluate, or query. Only knows how to route.

**Size target:** Under 50 lines of SKILL.md.

**Routing logic (priority order):**

1. Message not @mentioning the bot → ignore completely
2. Message contains brand + reference + dollar amount → dispatch to **grailzee-deal**
3. Message contains "new report" / "report is in" / "process" / "new file" → dispatch to **grailzee-report**
4. Message contains "closed" / "sold" / "traded" / "booked" + brand or reference + dollar amounts → dispatch to **grailzee-ledger** (trade logging)
5. Message asks about performance / "how are we doing" / "show me trades" / "P&L" / "premium" → dispatch to **grailzee-ledger** (query mode)
6. Message asks about targets / priorities / what to buy / "what's hot" / buy list → dispatch to **grailzee-targets**
7. None of the above → reply: "Send me a deal (brand, ref, price), report a closed trade, ask what to buy, or let me know when a new report is ready."

**SKILL.md should include:** routing table only, Telegram group chat rules (only respond when @mentioned, professional tone, no raw errors), and the dispatch mechanism. No business logic, no formulas, no formatting templates.

---

### 8.2 grailzee-report

**Purpose:** Process new Grailzee Pro reports into the full analysis output. Scores every reference in the dataset, tracks momentum, detects changes (emerged/shifted/faded), validates against the trade ledger, and resolves unknown reference names via web search.

**Triggers:** Dispatched by router when a new report is mentioned.

**Workflow:**

1. Acknowledge immediately: "Running the analyzer now..."
2. Locate new Excel file in `reports/` folder
3. Convert to CSV, save to `reports_csv/`
4. Load all CSVs within the 3-month trend window (max 6 reports)
5. Run full analysis:
   a. Score all references with 3+ sales (pricing window: latest 2 reports)
   b. Trend comparison (trend window: all 6 reports)
   c. Categorize changes: emerged, shifted, faded (current vs. previous report)
   d. Momentum scoring (all references with 3+ reports of data)
   e. Read trade ledger → calculate presentation premium, per-reference confidence
   f. If premium threshold met (10+ trades at +8%), apply adjustment to all MAX BUY calculations
6. Name resolution (LLM step):
   a. Python flags all references where `named == False` (not in name_cache.json)
   b. LLM web-searches each unnamed reference (e.g., "Breitling A17326 watch") to resolve brand + model
   c. LLM writes resolved names back to `name_cache.json`
   d. MNEMO automatically captures the resolutions as episodic memory
   e. On mature systems, this step processes 0-3 references. On first run, it may process 10-20.
7. Write outputs:
   a. Branded 4-tab spreadsheet (all scored references, sorted by momentum + signal)
   b. Markdown analysis summary (market snapshot, movers, emerged/shifted/faded, premium status)
   c. Sourcing brief (markdown + JSON with momentum scores)
   d. Updated analysis cache (with momentum, confidence, premium data)
8. Post summary to Telegram (chunked, max 4000 chars per message)
9. Final message includes: "[N] references scored, [N] emerged, [N] momentum signals. Premium: [X]% across [N] trades ([threshold met/not met])."

**Python scripts this skill calls:**

| Script | Responsibility |
|--------|---------------|
| `ingest_report.py` | Excel → CSV conversion, header normalization, file management |
| `analyze_references.py` | Score all references with 3+ sales, pricing calculations, risk signals |
| `analyze_trends.py` | Period-over-period comparison, momentum scoring |
| `analyze_changes.py` | Compare current vs previous: emerged, shifted, faded |
| `read_ledger.py` | Parse trade_ledger.csv, calculate per-reference stats and premium |
| `build_spreadsheet.py` | Branded spreadsheet output |
| `build_summary.py` | Markdown analysis summary |
| `build_brief.py` | Sourcing brief (MD + JSON) |
| `write_cache.py` | Analysis cache with all enrichments |

**LLM's job in this skill:**
- Resolve unnamed references via web search (the main LLM value-add beyond formatting)
- Read the markdown summary and present it conversationally in Telegram
- Flag anything unusual the Python scripts surfaced (a reference that emerged with strong metrics, premium threshold being reached, a high-volume reference that shifted significantly)
- Route errors cleanly without exposing stack traces

**LLM does NOT:**
- Calculate any metrics (all Python)
- Parse Excel files (all Python)
- Write CSV or JSON directly (all Python, except name cache append via helper)
- Decide which references matter (the data decides, not a list)

---

### 8.3 grailzee-deal

**Purpose:** Answer one question: "I can buy this watch at this price. Should I list it on Grailzee?"

**Triggers:** Dispatched by router when a brand + reference + price is detected.

**Workflow:**

1. Parse brand, reference, purchase price from message
2. Run the evaluator:
```bash
python3 evaluate_deal.py <brand> <reference> <purchase_price>
```
3. Evaluator internally:
   a. Check analysis cache for the reference
   b. If found: apply standard decision logic (YES/NO/MAYBE, NR/Reserve, margin %, ad budget)
   c. If not found: fall back to raw report scan
   d. If not in raw report: return `not_found` status
   e. In all cases: read trade ledger for confidence scoring on this reference
   f. In all cases: check if premium adjustment is active and factor into MAX BUY
4. Format response:

**When reference is found (cache or raw report):**
```
Tudor BB GMT Pepsi (79830RB) @ $2,750

Grailzee: YES
Format: NR
Margin: 8.2% ($262 at median)
Ad Budget: $37–50
Momentum: Warming (+2)

Buy works. $2,750 is within MAX BUY ($2,910). Signal is Strong.
Sell-through 78%. 12 sales in period. Trending up.

Trade History: 4 trades, 100% profitable, avg ROI 9.2%, avg premium +15.3%
```

**When reference is NOT found (not_found status):**
The LLM does the web research. This is the correct use of the LLM. Search Chrono24 and eBay for recent sold comps. Collect prices, compute median, apply the standard formula, deliver a YES/NO/MAYBE. Always deliver a recommendation. Never tell the user to research it themselves.

Format same as above but add: "⚠ No Grailzee data. Based on [N] Chrono24/eBay comps."

**Python script responsibilities:**
- All pricing math
- Cache lookup with fuzzy reference matching
- Raw report fallback
- Trade ledger read for confidence data
- Premium adjustment check

**LLM responsibilities:**
- Natural language input parsing
- Web research for not_found references (Chrono24, eBay, WatchRecon)
- Applying standard formula to web research results
- Formatting the response for Telegram
- Never punting to the user

---

### 8.4 grailzee-targets

**Purpose:** Return the active hunting list with momentum signals and confidence data.

**Triggers:** Dispatched by router when user asks about targets, priorities, what to buy.

**Workflow:**

1. Parse optional filters (signal, brand, budget, format, minimum volume, emerged-only)
2. Run the target query:
```bash
python3 query_targets.py [--signal LEVEL] [--brand NAME] [--budget AMOUNT] [--format FMT] [--min-volume N] [--emerged-only]
```
3. Format response:

```
6 Strong+ targets (cache: April 12, 2026)

🔥 Tudor BB GMT Pepsi (79830RB) — Hot (+3)
   MAX BUY: $2,910 | Signal: Strong | NR
   3 trades, 100% profitable, avg ROI 9.2%

🔥 Cartier Santos 40mm (WSSA0030) — Warming (+2)
   MAX BUY: $4,280 | Signal: Strong | NR
   No trade history

🔥 Tudor BB 58 Black (79030N) — Heating Up (+2)
   MAX BUY: $2,540 | Signal: Strong | NR
   1 trade, profitable, 6.1% ROI

🆕 Longines HydroConquest (L3.781.4.96.9) — Emerged
   MAX BUY: $1,380 | Signal: Normal | NR | 5 sales
   No trade history

[...]
```

**Filtering logic:**
- Default: all references with Signal = Strong or Normal, sorted by momentum (highest first)
- `--signal Strong` → only Strong signal references
- `--brand Tudor` → filter by brand
- `--budget 3000` → only references with MAX BUY at or below $3,000
- `--format NR` → only NR-recommended references
- `--min-volume 5` → minimum sales volume in current report
- `--emerged-only` → only references categorized as Emerged (new this period)

**Key changes from current:**
- No core/discovery split. All references scored equally, sorted by momentum + signal
- Momentum label replaces static trend signal
- Emerged references flagged with 🆕 so new opportunities are visible
- Trade history inline (from ledger)
- Default sort by momentum score (highest first), then by signal strength
- If premium adjustment is active, MAX BUY values reflect it (flag with note)

**Python handles:** Sourcing brief read, filtering, sorting, trade ledger join
**LLM handles:** Response formatting for Telegram, routing "what about Tudor?" follow-ups

---

### 8.5 grailzee-ledger

**Purpose:** Log closed trades and serve performance queries. This is Mode 4, the new capability.

**Triggers:** Dispatched by router for trade logging ("closed Tudor 79830RB, bought 2750, sold 3200 on Grailzee NR") or performance queries ("how are we doing this month", "show me all Tudor trades", "what's the premium at").

**Sub-mode A: Trade Logging**

1. Parse the message for: brand, reference, buy price, sell price, platform, date
   - Platform defaults to GNR if not specified (most common)
   - Date defaults to today if not specified
2. Present the parsed row back for confirmation:
```
Got it. Logging this trade:

Tudor 79830RB | GNR | Bought $2,750 | Sold $3,200 | April 15, 2026

Confirm? (yes/no)
```
3. On confirmation: append row to `trade_ledger.csv`
4. After appending: calculate and show the trade summary:
```
✅ Trade logged.

Net profit: $301 (after $149 Grailzee NR fees)
ROI: 10.9%
Premium vs median: +15.3% ($3,200 vs $2,775 median)

Running total: 8 trades, 100% profitable, avg ROI 8.4%
Presentation premium: +14.2% across 8 measured trades
Threshold: 2 more trades to trigger MAX BUY adjustment
```

**Sub-mode B: Performance Queries**

Supported queries:
- "how are we doing" / "P&L" / "performance" → full summary
- "show me Tudor trades" / "all Breitling" → filtered by brand
- "trades this month" / "last 30 days" → filtered by date
- "what's the premium" / "premium status" → presentation premium detail
- "model accuracy" → how often the model's YES resulted in a profitable trade

**Python script:**

`ledger_manager.py` handles both sub-modes:
- `ledger_manager.py log <brand> <reference> <platform> <buy_price> <sell_price> [--date YYYY-MM-DD]` → appends row, returns computed fields as JSON
- `ledger_manager.py summary [--brand NAME] [--since YYYY-MM-DD] [--reference REF]` → returns aggregate stats as JSON
- `ledger_manager.py premium` → returns presentation premium detail as JSON

**LLM handles:** Natural language parsing, confirmation flow, formatting for Telegram
**LLM does NOT:** Write to CSV directly, calculate fees or ROI (all Python)

---

## 9. PYTHON DECOMPOSITION

### 9.1 Current State → Target State

| Current Script | Size | Target | Notes |
|----------------|------|--------|-------|
| analyze_report.py | 49K / 1071 lines | Split into 5 focused scripts | The monolith |
| evaluate_deal.py | 20K / 556 lines | Keep as single script, add ledger read | Mostly well-structured |
| query_targets.py | 9K / ~220 lines | Keep as single script, add momentum + ledger | Reasonable size |
| write_cache.py | 8.5K / 231 lines | Keep, update schema for momentum + premium | Reasonable size |

### 9.2 analyze_report.py Decomposition

The 49K monolith breaks into these focused scripts:

| New Script | Source Functions | Responsibility |
|------------|-----------------|----------------|
| `ingest_report.py` | `get_report_date`, `find_reports`, `find_column_mapping`, `parse_report` | Excel → CSV conversion, header normalization, report discovery |
| `analyze_references.py` | `is_quality_sale`, `calc_risk`, `analyze_reference`, `normalize_ref`, `match_reference`, `classify_dj_config` | Score ALL references with 3+ sales. No core list filter. Per-reference metrics, risk signals, format recommendations, DJ 126300 config breakout. Flags unnamed references for LLM resolution |
| `analyze_trends.py` | `compare_periods` | Period-over-period comparison, momentum scoring (new) |
| `analyze_changes.py` | New (replaces old discovery logic) | Compare current vs previous report. Categorize: emerged, shifted, faded. No core/non-core distinction |
| `build_spreadsheet.py` | `build_spreadsheet`, `s`, `write_section`, `write_hdrs`, `write_row` | Branded spreadsheet output, all references sorted by momentum + signal. All openpyxl styling |
| `build_summary.py` | `build_summary` | Markdown analysis summary |
| `build_brief.py` | `build_sourcing_brief` | Sourcing brief (MD + JSON) with momentum scores |
| `read_ledger.py` | New | Parse trade_ledger.csv, compute per-reference stats, premium, confidence |

**Shared module:**

`grailzee_common.py` — constants, formulas, reference matching, fee tables. Imported by all scripts. Contains:
- `NR_FIXED`, `RES_FIXED`, `TARGET_MARGIN`, `RISK_RESERVE_THRESHOLD`
- `max_buy_nr()`, `max_buy_reserve()`, `breakeven_nr()`, `breakeven_reserve()`
- `risk_vg_plus()`, `signal_from_risk()`
- `normalize_ref()`, `match_reference()`, `strip_ref()`
- `QUALITY_CONDITIONS`, `PLATFORM_FEES`
- `DJ_CONFIGS` dict (Rolex 126300 config breakout logic — stays as special-case parser)
- `GRAILZEE_ROOT` and all path constants
- `NAME_CACHE_PATH` constant pointing to `GrailzeeData/state/name_cache.json`
- `load_name_cache()`, `save_name_cache()` — read/write the reference name lookup
- Brand colors for spreadsheet styling

**No hardcoded reference list.** There is no `CORE_REFERENCES` list. The entire report dataset is the input universe. Every reference with 3+ sales gets analyzed on its own merits. The name cache (see Section 6.4) provides human-readable display names. MNEMO (see Section 7) compounds name knowledge across sessions.

**Name cache seed file:** On first run, seed the cache with known mappings so the initial output is clean. This is the starting data for `name_cache.json`, not a fixed trading list:

```json
{
  "28600": {"brand": "Tudor", "model": "Royal 41mm"},
  "91650": {"brand": "Tudor", "model": "1926 41mm"},
  "91550": {"brand": "Tudor", "model": "1926 39mm"},
  "79830RB": {"brand": "Tudor", "model": "BB GMT Pepsi", "alt_refs": ["M79830RB", "M79830RB-0001"]},
  "79230R": {"brand": "Tudor", "model": "BB Heritage Red", "alt_refs": ["M79230R-0012"]},
  "79230B": {"brand": "Tudor", "model": "BB Heritage Blue", "alt_refs": ["M79230B-0007"]},
  "79030N": {"brand": "Tudor", "model": "BB 58 Black"},
  "7941A1A0RU": {"brand": "Tudor", "model": "BB 58 41mm Black"},
  "7939G1A0NRU": {"brand": "Tudor", "model": "BB 58 GMT Coke"},
  "79950": {"brand": "Tudor", "model": "Ranger"},
  "210.30.42.20.03.001": {"brand": "Omega", "model": "SMD 300M Blue"},
  "210.30.42.20.04.001": {"brand": "Omega", "model": "SMD 300M Black"},
  "A17320": {"brand": "Breitling", "model": "Superocean Heritage 42"},
  "A17326": {"brand": "Breitling", "model": "Navitimer 41 Auto"},
  "AB0138241C1A1": {"brand": "Breitling", "model": "Navitimer 41 Chrono"},
  "WSSA0030": {"brand": "Cartier", "model": "Santos 40mm"},
  "126300": {"brand": "Rolex", "model": "Datejust 41", "config_breakout": true},
  "116900": {"brand": "Rolex", "model": "Air-King (prev gen)"},
  "126900": {"brand": "Rolex", "model": "Air-King"},
  "126610LN": {"brand": "Rolex", "model": "Submariner Date"},
  "210.90.42.20.01.001": {"brand": "Omega", "model": "NTTD Titanium"},
  "210.92.42.20.01.001": {"brand": "Omega", "model": "NTTD NATO"}
}
```

This seed is a convenience for day one. After that, the LLM resolves unknown references via web search and appends them. The cache grows organically. No manual maintenance required.

### 9.3 Orchestrator

`run_analysis.py` — the entry point that the grailzee-report skill calls. Replaces `generate_output()` from the monolith.

```python
def run_analysis(reports_folder, output_folder):
    """
    Orchestrator. Calls focused scripts in sequence.
    Returns the path to the markdown summary and a list of unnamed references
    for the LLM to resolve via web search.
    """
    # 1. Ingest
    csv_path = ingest_report.convert_latest(reports_folder)

    # 2. Load rolling window
    csvs = ingest_report.load_window(reports_csv_folder, months=3)

    # 3. Load name cache
    name_cache = grailzee_common.load_name_cache()

    # 4. Score all references (pricing window = latest 2)
    all_results = analyze_references.run(csvs[-2:], name_cache)

    # 5. Trends + momentum (full window)
    trends = analyze_trends.run(csvs)

    # 6. Changes vs previous report (emerged, shifted, faded)
    changes = analyze_changes.run(csvs[-2:] if len(csvs) >= 2 else csvs)

    # 7. Read ledger for outcome data
    ledger_stats = read_ledger.run()

    # 8. Apply premium adjustment if threshold met
    if ledger_stats.premium.threshold_met:
        analyze_references.apply_premium_adjustment(all_results, ledger_stats.premium.adjustment)

    # 9. Collect unnamed references for LLM resolution
    unnamed = [ref for ref, data in all_results.items() if not data["named"]]

    # 10. Write outputs
    build_spreadsheet.run(all_results, trends, changes, ledger_stats, output_folder)
    summary_path = build_summary.run(all_results, trends, changes, ledger_stats, output_folder)
    build_brief.run(all_results, trends, changes, output_folder)
    write_cache.run(all_results, trends, changes, ledger_stats)

    return summary_path, unnamed
```

**After the orchestrator returns**, the LLM handles name resolution:

```
For each reference in `unnamed`:
    1. Web search: "{brand from report data} {reference} watch"
    2. Parse result for official model name
    3. Write to name_cache.json: {"reference": {"brand": "...", "model": "..."}}
    4. MNEMO captures this automatically as episodic memory
```

This is the correct LLM/Python split. Python scores everything. The LLM enriches the output with knowledge it can find on the web. On a mature system, the unnamed list is empty or near-empty.

### 9.4 evaluate_deal.py Updates

The existing script is mostly well-structured. Changes needed:

1. **Add ledger read:** After computing the recommendation, call `read_ledger.reference_confidence()` to get trade history for this reference
2. **Add premium adjustment:** Check if `ledger_stats.premium.threshold_met` and adjust MAX BUY accordingly
3. **Add momentum to response:** Pull momentum score from cache entry
4. **Use name cache for display names.** Load `name_cache.json` to resolve reference → brand/model for response formatting. If not in cache, use brand from report data + raw reference number
5. **Remove duplicated formula functions.** Import from `grailzee_common.py`

### 9.5 query_targets.py Updates

1. **Add momentum score** to each target in the output
2. **Add trade history** per reference from ledger
3. **Sort by momentum** (highest first) as default, then priority
4. **Add premium status** to the summary line if threshold is approaching or met
5. **Import shared constants** from `grailzee_common.py`

---

## 10. CACHE SCHEMA v2

The analysis cache needs new fields to carry momentum, confidence, and premium data.

```json
{
  "schema_version": 2,
  "generated_at": "2026-04-15T10:30:00",
  "source_report": "grailzee_2026-04-12.csv",
  "market_window": {
    "pricing_reports": ["grailzee_2026-04-12.csv", "grailzee_2026-03-29.csv"],
    "trend_reports": ["grailzee_2026-04-12.csv", "...", "grailzee_2026-01-18.csv"]
  },
  "premium_status": {
    "avg_premium": 14.2,
    "trade_count": 8,
    "threshold_met": false,
    "adjustment": 0,
    "trades_to_threshold": 2
  },
  "references": {
    "79830RB": {
      "brand": "Tudor",
      "model": "BB GMT Pepsi",
      "reference": "79830RB",
      "named": true,
      "median": 3200,
      "max_buy_nr": 2910,
      "max_buy_res": 2860,
      "risk_nr": 8.5,
      "signal": "Strong",
      "volume": 12,
      "st_pct": 0.78,
      "momentum": {"score": 2, "label": "Heating Up"},
      "confidence": {
        "trades": 4,
        "profitable": 4,
        "win_rate": 100.0,
        "avg_roi": 9.2,
        "avg_premium": 15.3,
        "last_trade": "2026-03-15"
      },
      "trend_signal": "Rising",
      "trend_median_change": 125,
      "trend_median_pct": 4.1
    }
  },
  "dj_configs": { },
  "changes": {
    "emerged": ["L3.781.4.96.9", "A13313161C1A1"],
    "shifted": {"210.30.42.20.03.001": {"direction": "up", "pct": 6.2}},
    "faded": ["AB0138241C1A1"]
  },
  "unnamed": ["L3.781.4.96.9", "A13313161C1A1"],
  "summary": {
    "total_references": 35,
    "strong_count": 8,
    "normal_count": 14,
    "reserve_count": 6,
    "caution_count": 7,
    "emerged_count": 2,
    "unnamed_count": 2,
    "hot_references": 3,
    "premium_status": "8 trades, +14.2%, 2 to threshold"
  }
}
```

---

## 11. MIGRATION PLAN

### 11.1 What Gets Replaced

| Current | Replaced By |
|---------|-------------|
| `grailzee-eval/` (single skill) | `grailzee-router/`, `grailzee-report/`, `grailzee-deal/`, `grailzee-targets/`, `grailzee-ledger/` |
| `grailzee-analyzer/` (Claude Chat skill) | Updated to use same Python scripts as the OpenClaw skills. Shared code, different interaction model |
| `analyze_report.py` (49K monolith) | 8 focused scripts + 1 shared module + 1 orchestrator |
| Hardcoded `CORE_REFERENCES` in multiple files | Eliminated. Replaced by `name_cache.json` (display names only) + data-driven scoring of all references |
| `core-references.md` (fixed trading list) | Removed as a concept. Seed data lives in `name_cache.json`. No reference gets special treatment |
| `business-model.md` (reference doc) | Still exists as documentation, but formulas live in `grailzee_common.py` |

### 11.2 Folder Structure (on disk, in the OpenClaw workspace)

```
~/.openclaw/workspace/skills/
├── grailzee-router/
│   └── SKILL.md
├── grailzee-report/
│   ├── SKILL.md
│   └── scripts/          ← symlink to shared scripts folder
├── grailzee-deal/
│   ├── SKILL.md
│   └── scripts/          ← symlink to shared scripts folder
├── grailzee-targets/
│   ├── SKILL.md
│   └── scripts/          ← symlink to shared scripts folder
├── grailzee-ledger/
│   ├── SKILL.md
│   └── scripts/          ← symlink to shared scripts folder
└── grailzee-shared/
    ├── grailzee_common.py
    ├── ingest_report.py
    ├── analyze_references.py
    ├── analyze_trends.py
    ├── analyze_changes.py
    ├── build_spreadsheet.py
    ├── build_summary.py
    ├── build_brief.py
    ├── write_cache.py
    ├── read_ledger.py
    ├── ledger_manager.py
    ├── evaluate_deal.py
    ├── query_targets.py
    ├── run_analysis.py       ← orchestrator
    └── references/
        └── business-model.md  ← human documentation
```

All four worker skills symlink their `scripts/` to `grailzee-shared/`. One codebase, four interfaces.

### 11.3 Build Order

Build in this order. Each step should be tested before proceeding.

| Phase | What | Depends On | Test |
|-------|------|-----------|------|
| 1 | `grailzee_common.py` (shared constants, formulas, matching, name cache I/O) | Nothing | Unit tests: formula outputs match current, reference matching works, name cache read/write |
| 2 | `read_ledger.py` + `ledger_manager.py` + trade_ledger.csv template | Phase 1 | Create CSV with sample data, verify calculations |
| 3 | `ingest_report.py` (Excel → CSV) | Phase 1 | Feed it an existing Grailzee Pro report, verify CSV output |
| 4 | `analyze_references.py` (score all references, no core list) | Phase 1, 3 | Feed it CSVs, verify metrics. Compare to current analyzer output for known references |
| 5 | `analyze_trends.py` (period comparison + momentum) | Phase 1, 3 | Feed it multiple CSVs, verify trend detection |
| 6 | `analyze_changes.py` (emerged, shifted, faded) | Phase 1, 3 | Feed it two CSVs, verify categorization |
| 7 | `build_spreadsheet.py`, `build_summary.py`, `build_brief.py` | Phase 4, 5, 6 | Generate outputs, verify formatting and completeness |
| 8 | `write_cache.py` v2 (updated schema) | Phase 4, 5, 6, 2 | Verify JSON schema matches Section 10 spec |
| 9 | `run_analysis.py` (orchestrator) | All above | End-to-end: Excel in → all outputs generated, unnamed list returned |
| 10 | `evaluate_deal.py` v2 (add ledger, momentum, premium, name cache) | Phase 1, 2, 8 | Test with cache + ledger, verify confidence in response |
| 11 | `query_targets.py` v2 (add momentum, ledger data) | Phase 1, 2, 8 | Test filtered queries, verify sorting by momentum |
| 12 | Seed `name_cache.json` with known reference mappings | Phase 1 | Verify all seed entries load correctly |
| 13 | Seed MNEMO with business context and known reference names | Phase 12 | Verify `mnemo-cli memory list --type semantic` shows seeded memories |
| 14 | Four SKILL.md files + router SKILL.md | All Python done | Manual test in Telegram group chat |

### 11.4 Backfill

Before the system goes live, populate the trade ledger with historical data from the existing closed positions tracker. Source file: `Vardalux_Grailzee_Closed_Positions.md` in project knowledge.

This can be done in a Claude Chat session or by hand in the CSV. Once backfilled, all historical trades feed into confidence scoring and premium calculations from day one.

### 11.5 GitHub Repository

Target repo: `vardalux-skills` (existing). All Python scripts and SKILL.md files commit there. Three deploy targets as established: chat-project, cowork, openclaw.

---

## 12. EXISTING GRAILZEE PRO REPORTS

Two historical reports exist in project knowledge for testing:
- `Grailzee_Pro_BiWeekly_Report__February_W1.xlsx`
- `Grailzee_Pro_BiWeekly_Report__August1.xlsx`

The current `Vardalux_Grailzee_Buy_Targets.xlsx` in project knowledge is an output from a previous analyzer run. Use it as a comparison baseline when validating Phase 4 output.

---

## 13. DECISION LOG

Decisions made during design that Claude Code should not re-litigate:

| Decision | Rationale |
|----------|-----------|
| CSV as canonical format after ingest | Stable, parseable, no openpyxl dependency on reads |
| Rolling 3-month / 6-report trend window | Enough for directional signal without stale data pressure |
| Trade ledger is all-time, never rolls off | Structurally tiny (hundreds of rows), every trade teaches the model |
| Manual CSV entry + chat logging interface | ERP export too complex; 6-column CSV is maintainable by hand |
| Calculated fields computed at analysis time, not stored | Fee structures may change; audit trail stays clean |
| One shared Python codebase, four SKILL.md interfaces | DRY principle; avoids drift between worker skills |
| Momentum scoring -3 to +3 | Simple, sortable, human-readable labels |
| All references scored equally, 3+ sales threshold | No core list. The data determines priority, not a hardcoded list |
| Router skill is intent-only, no business logic | Under 50 lines; no wasted context on dispatch |
| Premium auto-adjustment at 10 trades, +8% average | Previously manual; now automatic through ledger integration |
| Core references concept eliminated entirely | Was a rearview mirror that trapped the system into a fixed universe. Discovery engine + data-driven scoring replaces it |
| Name cache JSON + LLM web search for resolution | Python needs deterministic name lookup (spreadsheets, briefs). LLM resolves unknowns. Cache grows organically |
| MNEMO captures name resolutions automatically | Compounds knowledge across sessions. LLM web searches decrease over time as cache matures |
| MNEMO seeded with business context at setup | Fee structures, account rules, known references seeded as semantic memories. Skills stay lean |
| DJ 126300 config breakout preserved as special case | Same reference, wildly different prices by dial/bracelet. This is a data parsing problem, not a naming problem |

---

*Implementation Plan v1 | April 15, 2026*
*Ready for Claude Code execution*