# Grailzee Eval v2 — Implementation Plan
**For Claude Code Build | April 16, 2026**

---

## 1. WHAT THIS DOCUMENT IS

A complete specification for rebuilding the Grailzee evaluation system. The current `grailzee-eval` OpenClaw agent — a single agent with a 9.7K monolithic SKILL.md backed by a 49K Python analyzer — gets transformed into a single agent with focused capability modules and a decomposed Python codebase. A new Chat-level strategy skill handles planning conversations that shouldn't happen in Telegram.

Claude Code should be able to execute this spec without coming back for design clarification. If a decision is ambiguous, this document resolves it. If something isn't covered, flag it before building.

**Branch:** `feature/grailzee-eval-v2` (already exists)
**Repo:** `/Users/ranbirchawla/.openclaw/workspace`
**Build location during development:** `skills/grailzee-eval-v2/` (parallel to existing `skills/grailzee-eval/`)
**Final location after migration:** `skills/grailzee-eval/` (existing directory replaced by v2 contents)
**Strategy skill location:** installed outside the main OpenClaw skill directory, as a Chat-level skill

---

## 2. CORE DESIGN PRINCIPLES

These principles shape every implementation decision. When in doubt, refer back.

1. **Python does analysis. LLM does language, judgment, and web research.** Every metric, every filter, every score, every aggregation is Python. The LLM parses input, resolves unknowns, formats output, frames data against intent. Never the reverse.

2. **The data determines priority, not a hardcoded list.** Every reference with 3+ sales in a report gets scored on its own merits. No core references, no tiers, no special treatment.

3. **Detection is deterministic. Strategy is conversational.** The analyzer surfaces everything that's moving. Strategy framing happens separately, with human intent in the loop.

4. **Strict cycle discipline on targets.** The targets capability does not return a filtered list until a strategy session has set the cycle focus. Override exists but requires explicit intent.

5. **Ad hoc deal evaluation is always available.** Deal evaluation answers "should I buy this?" regardless of cycle focus, annotated with cycle alignment.

6. **The ledger is Grailzee-only.** Only trades closed through Grailzee (NR or Reserve accounts) enter the ledger. Cross-platform P&L is a different product and belongs elsewhere.

7. **One agent, multiple capability modules.** The Grailzee agent is a single OpenClaw agent following the standard agent convention. Its capabilities (report processing, deal evaluation, target queries, trade logging) are internal workflow modules, not separate agents.

8. **MNEMO handles cross-session context.** Business context, fee structures, known references are seeded as semantic memories. SKILL.md and capability files stay lean.

---

## 3. ARCHITECTURE OVERVIEW

### System layout

```
OPENCLAW (Telegram — tactical, fast)
skills/grailzee-eval/ (one agent, four capabilities)
  ├── Agent scaffolding (AGENTS.md, SOUL.md, USER.md, IDENTITY.md, TOOLS.md, HEARTBEAT.md)
  ├── SKILL.md (intent dispatch at the top level)
  ├── capabilities/ (four workflow modules)
  │   ├── report.md    → Report ingestion, detection, orchestration
  │   ├── deal.md      → Single deal evaluation (always available, cycle-aware)
  │   ├── targets.md   → Active hunting list (cycle-filtered, discipline enforced)
  │   └── ledger.md    → Trade logging and performance queries
  ├── scripts/ (decomposed Python codebase)
  └── references/ (business-model.md preserved if present)

CHAT (strategic, slow)
grailzee-strategy (separate Chat-level skill)
  → Cycle planning, monthly reviews, quarterly allocation
```

The router from earlier plans is now internal: the top-level SKILL.md parses incoming intent and dispatches to the correct capability file. No separate router skill.

### Data layer (Google Drive)

**Base path (all scripts use this constant):**
```
/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData/
```

**Folder structure:**
```
GrailzeeData/
├── reports/                      ← Raw Excel workbooks (archived, never deleted)
├── reports_csv/                  ← Converted CSVs (ingest writes here)
├── output/                       ← Human-readable outputs
│   └── briefs/                   ← Archived cycle briefs from strategy skill
├── state/
│   ├── analysis_cache.json       ← Deal evaluator reads this
│   ├── sourcing_brief.json       ← Target query reads this
│   ├── trade_ledger.csv          ← Outcome tracking (append-only, Grailzee-only)
│   ├── name_cache.json           ← Reference → display name (append-only)
│   ├── cycle_focus.json          ← Active cycle's hunting list (strategy-written)
│   ├── cycle_outcome.json        ← Previous cycle's actual trade results
│   ├── monthly_goals.json        ← Platform goals, updated monthly
│   ├── quarterly_allocation.json ← Capital allocation decisions, updated quarterly
│   └── run_history.json          ← Analyzer run log
└── backup/                       ← Auto-rotated previous caches (last 10)
```

---

## 4. CYCLE MODEL

### Definitions

- **Cycle** — One biweekly period anchored to a Grailzee Pro report. Default duration ~2 weeks. Identifier: `cycle_YYYY-NN` where NN is the cycle number within the year (01-26).
- **Month** — Calendar month. Triggers monthly platform goals review during the strategy session that crosses the month boundary.
- **Quarter** — Calendar quarter. Triggers capital allocation review during the strategy session that crosses the quarter boundary.

### Cycle lifecycle

1. New Grailzee Pro report lands in `reports/`
2. Agent processes it via the `report` capability (Python analysis, LLM name resolution, outputs written)
3. Telegram summary ends with: **"Ready to strategize in Chat."**
4. User opens Chat, invokes `grailzee-strategy`
5. Strategy skill reads: latest analyzer output, ledger, previous cycle_focus, previous cycle_outcome, monthly/quarterly state if applicable
6. Structured conversation: past performance → new signal → capital and volume goals → narrowed focus
7. Strategy writes: `cycle_focus.json`, `cycle_brief.md`, any monthly/quarterly updates
8. `targets` capability now filters by new cycle focus
9. At next report, prior cycle's trades roll up into `cycle_outcome.json` for strategic review

### Cycle discipline enforcement

- `targets` capability returns no filtered list until `cycle_focus.json` is current (cycle_id matches latest report's cycle_id)
- If called without current focus: "No active cycle focus for Cycle [cycle_id]. Strategy session required. Run `grailzee-strategy` in Chat to set targets for this cycle."
- Override flag `--ignore-cycle` returns raw momentum-sorted universe with explicit warning: "⚠ Operating outside cycle focus. Targets not filtered by strategic intent."
- `deal` capability is never blocked by cycle discipline. Annotates cycle alignment in response.

---

## 5. TRADE LEDGER — SCHEMA & RULES

### 5.1 Scope

**Grailzee-only.** The ledger captures trades closed on either Grailzee account (branded NR or separate Reserve). Cross-platform sales do not enter this ledger.

### 5.2 CSV Format

**Filename:** `trade_ledger.csv`
**Location:** `GrailzeeData/state/trade_ledger.csv`
**Encoding:** UTF-8, standard CSV (RFC 4180)

**Columns:**

| Column | Type | Example | Notes |
|--------|------|---------|-------|
| date_closed | YYYY-MM-DD | 2026-02-14 | Date the trade settled |
| cycle_id | string | cycle_2026-06 | Auto-assigned by ledger_manager based on date_closed |
| brand | string | Tudor | Case-insensitive on read |
| reference | string | 79830RB | As listed in Grailzee |
| account | string | NR | Two values only: NR or RES |
| buy_price | number | 2750 | No dollar sign, no commas |
| sell_price | number | 3200 | No dollar sign, no commas |

**Account codes:**

| Code | Account |
|------|---------|
| NR | Grailzee No Reserve (branded account) |
| RES | Grailzee Reserve (separate account) |

**Example rows:**
```csv
date_closed,cycle_id,brand,reference,account,buy_price,sell_price
2025-10-10,cycle_2025-41,Tudor,79830RB,NR,2750,3200
2025-11-15,cycle_2025-46,Tudor,91650,NR,1500,1675
2025-12-01,cycle_2025-48,Tudor,79230R,NR,2800,3150
2026-01-05,cycle_2026-01,Tudor,28600,RES,4200,4750
2026-02-14,cycle_2026-06,Tudor,28600,NR,1900,2100
2026-03-01,cycle_2026-09,Breitling,A17320,NR,2100,2350
```

### 5.3 Calculated Fields

Never stored in CSV. Computed at analysis time by joining ledger rows against cache/report data closest to `date_closed`.

| Field | Formula | Purpose |
|-------|---------|---------|
| platform_fees | NR = $149, RES = $199 | Account-based fixed cost |
| net_profit | sell_price - buy_price - platform_fees | Actual dollar return |
| roi_pct | (net_profit / buy_price) * 100 | Per-trade return |
| median_at_trade | Median from cache closest to date_closed | What the model thought the reference was worth |
| max_buy_at_trade | MAX BUY from cache closest to date_closed | What the model recommended |
| model_correct | buy_price <= max_buy_at_trade AND net_profit > 0 | Did the model's YES result in a profitable trade? |
| premium_vs_median | ((sell_price - median_at_trade) / median_at_trade) * 100 | Presentation premium per trade |

### 5.4 Fee Structure

```python
ACCOUNT_FEES = {
    "NR":  149,    # $49 Grailzee fee + $100 shipping
    "RES": 199,    # $99 Grailzee fee + $100 shipping
}
```

That's the entire fee table. No tiered logic, no platform variations. If Grailzee changes fees in the future, one constant changes.

### 5.5 Presentation Premium Auto-Calculation

Runs every time the analyzer runs:

```python
def calculate_presentation_premium(ledger_rows):
    premiums = [row.premium_vs_median for row in ledger_rows
                if row.median_at_trade is not None]
    if not premiums:
        return {"avg_premium": 0, "trade_count": 0,
                "threshold_met": False, "adjustment": 0}

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

When `threshold_met` is True, MAX BUY calculations are adjusted:

```python
def adjusted_max_buy(median, fixed_cost, premium_adjustment_pct):
    adjusted_median = median * (1 + premium_adjustment_pct / 100)
    return round((adjusted_median - fixed_cost) / 1.05, -1)
```

### 5.6 Per-Reference Confidence Scoring

Used by `deal` capability to enrich recommendations:

```python
def reference_confidence(ledger_rows, brand, reference):
    trades = [r for r in ledger_rows
              if r.brand.lower() == brand.lower()
              and r.reference == reference]
    if not trades:
        return None

    profitable = sum(1 for t in trades if t.net_profit > 0)
    avg_roi = statistics.mean([t.roi_pct for t in trades])
    premiums = [t.premium_vs_median for t in trades
                if t.premium_vs_median is not None]
    avg_premium = statistics.mean(premiums) if premiums else None

    return {
        "trades": len(trades),
        "profitable": profitable,
        "win_rate": round(profitable / len(trades) * 100, 1),
        "avg_roi": round(avg_roi, 1),
        "avg_premium": round(avg_premium, 1) if avg_premium is not None else None,
        "last_trade": max(t.date_closed for t in trades),
    }
```

### 5.7 Cycle Rollup

At each new report ingestion, the ledger manager produces `cycle_outcome.json` for the *previous* cycle:

```json
{
  "cycle_id": "cycle_2026-14",
  "date_range": {"start": "2026-03-31", "end": "2026-04-13"},
  "trades": [
    {"date": "2026-04-02", "brand": "Tudor", "reference": "79830RB",
     "account": "NR", "buy": 2750, "sell": 3200,
     "net": 301, "roi": 10.9, "in_focus": true}
  ],
  "summary": {
    "total_trades": 3,
    "profitable": 3,
    "in_focus_count": 2,
    "off_cycle_count": 1,
    "avg_roi": 8.4,
    "total_net": 642,
    "capital_deployed": 8100,
    "capital_returned": 8742
  },
  "cycle_focus": {
    "targeted_references": ["79830RB", "210.30.42.20.03.001", "A17320"],
    "hits": ["79830RB", "A17320"],
    "misses": ["210.30.42.20.03.001"],
    "off_cycle_trades": ["91650"]
  }
}
```

The strategy skill reads this to frame the next cycle's conversation.

---

## 6. ROLLING MARKET WINDOW

### 6.1 Report Ingestion

When a new Grailzee Pro Excel report arrives:

1. Convert sales sheet to CSV immediately. Write to `reports_csv/` with naming: `grailzee_YYYY-MM-DD.csv`
2. Archive original Excel in `reports/` (never delete)
3. The CSV is canonical from this point forward

**CSV conversion rules:**
- Read only the sales sheet ("Auctions Sold" or first sheet if not found)
- Auto-detect header row (scan first 5 rows for column keywords)
- Preserve required columns: reference, make, title, condition, papers, sold price, date, sell-through %
- Strip currency symbols and commas from price columns
- Normalize condition values to lowercase
- Write with standard headers (see 6.3)

**Why CSV-only ingest:** The Excel workbook may contain additional sheets (unsold auctions, bid activity, rollups), but the scoring engine only uses sales data. Ingesting everything wastes tokens and adds maintenance surface. If future analysis needs additional sheets, add a second extract at ingest time.

### 6.2 Window Boundaries

| Window | Purpose | Reports | Duration |
|--------|---------|---------|----------|
| Pricing window | Current median, MAX BUY, risk | Latest 2 reports | ~4 weeks |
| Trend window | Direction, momentum, trajectory | Latest 6 reports | ~3 months |
| Archive | Historical record | Everything older | Unlimited |

**Rules:**
- Pricing calculations use only the pricing window
- Trend calculations use the full trend window
- Older reports ignored in active analysis, never deleted
- If fewer than 6 reports exist, use all available
- If only 1 report exists, no trend data (flag as "First report, no trend history")

### 6.3 Standardized CSV Headers

```
date_sold,make,reference,title,condition,papers,sold_price,sell_through_pct
```

The analyzer normalizes whatever headers the Grailzee Pro report uses into these. Column mapping logic exists in the current `analyze_report.py` and should be preserved during Python extraction.

---

## 7. REFERENCE ANALYSIS ENGINE

### 7.1 Full-Dataset Scoring

Every reference with 3+ sales in the current report gets scored. No core list, no tiers, no special treatment.

```python
def analyze_all_references(all_sales, name_cache):
    results = {}
    for ref, sales in group_by_reference(all_sales):
        if len(sales) < 3:
            continue
        metrics = analyze_reference(sales)
        display_name = name_cache.get(ref, {"brand": sales[0].brand, "model": ref})
        results[ref] = {
            "brand": display_name["brand"],
            "model": display_name.get("model", ref),
            "reference": ref,
            "named": ref in name_cache,
            "volume": len(sales),
            "median": metrics.median,
            "max_buy_nr": max_buy_nr(metrics.median),
            "max_buy_res": max_buy_reserve(metrics.median),
            "risk_nr": metrics.risk,
            "signal": metrics.signal,
            "st_pct": metrics.sell_through,
        }
    return results
```

### 7.2 Change Detection

| Category | Criteria | Meaning |
|----------|----------|---------|
| **Emerged** | 3+ sales this report, fewer than 3 previous | New on the radar |
| **Shifted** | Present both periods, median moved >5% | Price signal changing |
| **Faded** | Was scoreable last period, dropped below 3 | Losing steam |
| **Unnamed** | Scored but not in name cache | LLM web search required |

### 7.3 Breakout Detection

```python
def detect_breakouts(current_refs, previous_refs):
    breakouts = []
    for ref, current in current_refs.items():
        prev = previous_refs.get(ref)
        if not prev:
            continue
        signals = []
        median_delta = ((current.median - prev.median) / prev.median) * 100
        if abs(median_delta) > 8:
            signals.append(f"Median {'+' if median_delta > 0 else ''}{median_delta:.1f}%")
        if current.volume > prev.volume * 2 and prev.volume >= 3:
            signals.append(f"Volume surge ({prev.volume} → {current.volume})")
        st_delta = (current.st_pct - prev.st_pct) * 100
        if st_delta > 15:
            signals.append(f"Sell-through +{st_delta:.0f}pp")
        if signals:
            breakouts.append({"reference": ref, "signals": signals})
    return breakouts
```

### 7.4 Watch List Detection

```python
def detect_watch_list(current_sales, previous_refs):
    watch = []
    for ref, sales in group_by_reference(current_sales):
        if len(sales) < 1 or len(sales) >= 3:
            continue
        prev = previous_refs.get(ref)
        if not prev or prev.volume == 0:
            watch.append({
                "reference": ref,
                "current_sales": len(sales),
                "avg_price": statistics.mean([s.sold_price for s in sales]),
            })
    return watch
```

### 7.5 Brand-Level Rollups

```python
def brand_momentum(all_refs):
    by_brand = defaultdict(list)
    for ref_data in all_refs.values():
        by_brand[ref_data["brand"]].append(ref_data.get("momentum", {}).get("score", 0))
    rollups = {}
    for brand, scores in by_brand.items():
        if len(scores) < 2:
            continue
        warming = sum(1 for s in scores if s > 0)
        cooling = sum(1 for s in scores if s < 0)
        rollups[brand] = {
            "reference_count": len(scores),
            "avg_momentum": round(statistics.mean(scores), 1),
            "warming": warming,
            "cooling": cooling,
            "signal": "Brand heating" if warming > cooling * 2 else
                      "Brand cooling" if cooling > warming * 2 else
                      "Mixed",
        }
    return rollups
```

### 7.6 Momentum Scoring

```python
def momentum_score(trend_data):
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
         0: "Stable",        1: "Warming",  2: "Heating Up", 3: "Hot"
    }
    return {"score": score, "label": labels[score]}
```

### 7.7 Name Cache

**File:** `GrailzeeData/state/name_cache.json`

```python
def load_name_cache(cache_path=None):
    cache_path = cache_path or NAME_CACHE_PATH
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path, 'r') as f:
        return json.load(f)

def save_name_cache(cache, cache_path=None):
    cache_path = cache_path or NAME_CACHE_PATH
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2, sort_keys=True)
```

**Seed data (day one):**

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
  "210.90.42.20.01.001": {"brand": "Omega", "model": "NTTD Titanium"},
  "210.92.42.20.01.001": {"brand": "Omega", "model": "NTTD NATO"},
  "A17320": {"brand": "Breitling", "model": "Superocean Heritage 42"},
  "A17326": {"brand": "Breitling", "model": "Navitimer 41 Auto"},
  "AB0138241C1A1": {"brand": "Breitling", "model": "Navitimer 41 Chrono"},
  "WSSA0030": {"brand": "Cartier", "model": "Santos 40mm"},
  "126300": {"brand": "Rolex", "model": "Datejust 41", "config_breakout": true},
  "116900": {"brand": "Rolex", "model": "Air-King (prev gen)"},
  "126900": {"brand": "Rolex", "model": "Air-King"},
  "126610LN": {"brand": "Rolex", "model": "Submariner Date"}
}
```

**Name resolution flow (LLM):**

After the orchestrator returns, the agent handles unnamed references:

1. For each unnamed reference, web search: `"{brand} {reference} watch"`
2. Parse result for official model name
3. Call helper to append entry to `name_cache.json`
4. MNEMO captures the resolution as episodic memory automatically

Alternate reference matching supported via `alt_refs` array. `normalize_ref()` handles prefix/suffix stripping.

---

## 8. MNEMO INTEGRATION

MNEMO runs at `127.0.0.1:9999` as a transparent HTTP proxy between OpenClaw and Anthropic's API. The agent's LLM calls route through it automatically.

### What MNEMO does automatically

- Captures every deal evaluation, report summary, trade log as episodic memory
- Injects semantically relevant memories into every LLM call
- Name resolutions from web searches are captured for future retrieval

### What the agent should NOT do

- Re-state business context in SKILL.md or capability files (fees, account rules, margin targets). Seed as semantic memories once.
- Carry conversation history manually.
- Duplicate name cache in any .md file.

### What the agent SHOULD do

- Verify MNEMO running on startup: `curl http://localhost:9999/health`
- Keep SKILL.md and capability files focused on workflow steps and dispatch logic
- Let Python handle all deterministic work (`name_cache.json` is authoritative for scripts, not MNEMO)

### Initial MNEMO seeding (Phase 18)

```bash
# Business model
mnemo-cli memory add "Grailzee NR fixed cost is $149 ($49 fee + $100 shipping). Reserve is $199 ($99 + $100). Target margin per trade is 5%." --type semantic
mnemo-cli memory add "MAX BUY NR formula: (Median - 149) / 1.05. MAX BUY Reserve: (Median - 199) / 1.05." --type semantic
mnemo-cli memory add "Branded Grailzee account is NR only. Separate Reserve account being built to Pro status." --type semantic
mnemo-cli memory add "Presentation premium threshold: 10 trades at +8% or above triggers automatic MAX BUY adjustment." --type semantic
mnemo-cli memory add "Trade ledger is Grailzee-only. NR and RES accounts both count. Cross-platform sales are not tracked here." --type semantic

# Operational
mnemo-cli memory add "Grailzee data lives on Google Drive at Vardalux Shared Drive/GrailzeeData/. Reports in reports/, CSVs in reports_csv/, state in state/." --type procedural
mnemo-cli memory add "Trade ledger is state/trade_ledger.csv. Seven columns: date_closed, cycle_id, brand, reference, account, buy_price, sell_price. Account codes: NR or RES only." --type procedural
mnemo-cli memory add "Name cache is state/name_cache.json. Maps reference numbers to brand + model display names." --type procedural
mnemo-cli memory add "Strict cycle discipline: targets capability will not filter by cycle focus until grailzee-strategy in Chat has set it. Override flag --ignore-cycle available." --type procedural
mnemo-cli memory add "Cycle identifier format: cycle_YYYY-NN where NN is the cycle number within the year (01-26)." --type procedural
```

---

## 9. AGENT STRUCTURE

### 9.1 Directory layout

Final agent directory after Phase 22 migration:

```
skills/grailzee-eval/
├── AGENTS.md              ← OpenClaw agent convention (preserved from v1)
├── SOUL.md                ← Agent identity/voice (preserved from v1)
├── USER.md                ← User context (preserved from v1 unless customization found in Phase 0)
├── IDENTITY.md            ← Agent identity (preserved from v1 unless customization found in Phase 0)
├── TOOLS.md               ← Tools reference (preserved from v1 unless customization found in Phase 0)
├── HEARTBEAT.md           ← Heartbeat checklist (preserved from v1 unless customization found in Phase 0)
├── SKILL.md               ← NEW: top-level intent dispatch
├── memory/                ← Fresh directory, daily files accumulate
├── capabilities/
│   ├── report.md
│   ├── deal.md
│   ├── targets.md
│   └── ledger.md
├── scripts/
│   ├── grailzee_common.py
│   ├── ingest_report.py
│   ├── analyze_references.py
│   ├── analyze_trends.py
│   ├── analyze_changes.py
│   ├── analyze_breakouts.py
│   ├── analyze_watchlist.py
│   ├── analyze_brands.py
│   ├── read_ledger.py
│   ├── ledger_manager.py
│   ├── roll_cycle.py
│   ├── build_spreadsheet.py
│   ├── build_summary.py
│   ├── build_brief.py
│   ├── write_cache.py
│   ├── evaluate_deal.py
│   ├── query_targets.py
│   └── run_analysis.py
└── references/
    └── business-model.md (if present in current directory)
```

### 9.2 Top-level SKILL.md

**Purpose:** Intent detection and dispatch to capability modules. Replaces the current 9.7K monolith.

**Size target:** Under 100 lines.

**Content template:**

```markdown
# Grailzee Eval Agent

You are the Grailzee Eval agent. Your job is to help Vardalux evaluate
Grailzee auction data, track trades, and answer tactical questions in
Telegram. For strategic planning, direct the user to the grailzee-strategy
skill in Chat.

## When to Respond

This agent operates in a Telegram group chat. Respond only when @mentioned.

## Intent Dispatch

Parse the incoming message and route to the correct capability file:

1. Not @mentioned → ignore
2. Contains brand + reference + dollar amount → load `capabilities/deal.md`
3. Contains "new report" / "report is in" / "process" / "new file" → load `capabilities/report.md`
4. Contains "closed" / "sold" / "traded" / "booked" + brand or reference + dollar amounts → load `capabilities/ledger.md` (logging mode)
5. Asks about performance / "how are we doing" / "show me trades" / "P&L" / "premium" → load `capabilities/ledger.md` (query mode)
6. Asks about targets / priorities / what to buy / "what's hot" / buy list → load `capabilities/targets.md`
7. None of the above → reply: "Send me a deal (brand, ref, price), report a closed trade, ask what to buy, or let me know when a new report is ready."

## Global Behavior

- Grailzee-only scope. Cross-platform questions get redirected.
- Errors are reported cleanly. No raw stack traces in Telegram.
- MNEMO is available; business context is injected automatically.
- Strategic planning lives in Chat, not here. Hand off when asked.

## Capability Files

Each capability file in `capabilities/` is loaded on demand based on intent.
The capability file contains the full workflow for that task. The agent does
not need to hold all four in context simultaneously.
```

No business logic, no formulas, no formatting templates in SKILL.md. Those live in capability files and Python.

### 9.3 Capability module pattern

Each capability file is self-contained: the workflow for one task. When the agent dispatches to a capability, that's the only one loaded.

**Capability file structure:**

```markdown
# [Capability name]

## Purpose
[One paragraph describing what this capability does]

## Trigger
[How the dispatcher identifies this capability]

## Workflow
[Step-by-step procedure, including Python script calls]

## Response Format
[Exact output structure for Telegram]

## LLM Responsibilities
[What the LLM does in this capability]

## What the LLM Does NOT Do
[Explicit restrictions]
```

---

## 10. CAPABILITY SPECIFICATIONS

### 10.1 capabilities/report.md

**Purpose:** Process new Grailzee Pro reports. Scores every reference, tracks momentum, detects changes, validates against ledger, resolves unknown names, hands off to strategy.

**Trigger:** Message mentions new report, file ready, time to process.

**Workflow:**

1. Acknowledge: "Running the analyzer now..."
2. Call `python3 scripts/run_analysis.py`
3. Orchestrator internally:
   - Converts Excel to CSV (`ingest_report.py`)
   - Loads trend window (up to 6 reports)
   - Scores all references (`analyze_references.py`)
   - Trends, momentum (`analyze_trends.py`)
   - Changes: emerged, shifted, faded (`analyze_changes.py`)
   - Breakouts (`analyze_breakouts.py`)
   - Watch list (`analyze_watchlist.py`)
   - Brand rollups (`analyze_brands.py`)
   - Ledger stats, presentation premium (`read_ledger.py`)
   - Applies premium adjustment if threshold met
   - Rolls previous cycle into `cycle_outcome.json` (`roll_cycle.py`)
   - Writes spreadsheet, summary, brief, cache
   - Returns: summary path, unnamed references list, current cycle_id
4. Name resolution (LLM step):
   - For each unnamed reference, web search: `"{brand} {reference} watch"`
   - Parse result for official model name
   - Append to `name_cache.json`
5. Post summary to Telegram (chunked, max 4000 chars)
6. Final message:

```
Cycle [cycle_id] analyzed.
[N] references scored, [N] emerged, [N] breakouts, [N] momentum signals.
Premium: [X]% across [N] trades ([threshold status]).
Previous cycle outcome: [N] trades, [X]% avg ROI, [hits]/[total] in focus.

⚠ Ready to strategize in Chat.
Open grailzee-strategy to set this cycle's focus. Targets will not filter
until strategy runs.
```

**LLM responsibilities:**
- Web-search unnamed references
- Present summary conversationally
- Flag notable items (strong emerger, premium threshold reached, high-volume momentum flip)
- Route errors cleanly

**LLM does NOT:**
- Calculate metrics
- Parse Excel
- Write CSV or JSON (except name cache append via helper)
- Decide which references matter

---

### 10.2 capabilities/deal.md

**Purpose:** Answer one question: "I can buy this watch at this price. Should I list it on Grailzee?"

**Always available.** Cycle discipline does not block deal evaluation.

**Trigger:** Message contains brand + reference + dollar amount.

**Workflow:**

1. Parse brand, reference, purchase price from message
2. Call `python3 scripts/evaluate_deal.py <brand> <reference> <purchase_price>`
3. Script internally:
   - Check analysis cache for reference
   - If found: standard decision logic (YES/NO/MAYBE, NR/Reserve, margin %, ad budget)
   - If not found in cache: fall back to raw report scan
   - If not in raw report: return `not_found` status
   - Always: read ledger for confidence scoring
   - Always: check premium adjustment
   - Always: check `cycle_focus.json` for alignment
4. Format response based on result:

**Reference found, in cycle focus:**
```
Tudor BB GMT Pepsi (79830RB) @ $2,750

Grailzee: YES
Format: NR
Margin: 8.2% ($262 at median)
Ad Budget: $37–50
Momentum: Warming (+2)

Buy works. $2,750 is within MAX BUY ($2,910). Signal Strong.
Sell-through 78%. 12 sales in period.

Trade History: 4 trades, 100% profitable, avg ROI 9.2%, avg premium +15.3%
Cycle Focus: ✓ In current hunting list (Cycle 2026-15)
```

**Reference found, off-cycle:**
```
Breitling Navitimer 41 (A17326) @ $2,400

Grailzee: YES
Format: NR
Margin: 7.1% ($170 at median)
Ad Budget: $30–40
Momentum: Heating Up (+2)

Buy works. $2,400 is within MAX BUY ($2,480). Signal Normal.
Sell-through 65%. 8 sales in period.

Trade History: No trades logged
Cycle Focus: ✗ Not in current hunting list (Cycle 2026-15)
Note: Strategy identified Breitling Superocean this cycle, not Navitimer.
Off-cycle buy — proceed on your judgment.
```

**Reference NOT found (not_found status):**

LLM does web research. Chrono24, eBay, WatchRecon for recent sold comps. Computes median, applies formula, delivers recommendation with added note:

```
⚠ No Grailzee data. Based on [N] Chrono24/eBay comps.
```

Always delivers a recommendation. Never punts to the user.

**LLM responsibilities:** Input parsing, web research for not_found, formula application to web results, Telegram formatting.

---

### 10.3 capabilities/targets.md

**Purpose:** Return the active hunting list. **Strict cycle discipline enforced.**

**Trigger:** Message asks about targets, priorities, what to buy.

**Workflow:**

1. Call `python3 scripts/query_targets.py [filters]` — the script checks cycle focus freshness first
2. **If no current cycle focus:** script returns gate signal, agent posts:

```
No active cycle focus for Cycle 2026-15.
Strategy session required before targets are set.

Run `grailzee-strategy` in Chat to plan this cycle.
```

3. **If cycle focus is current:** parse optional filters, return cycle-filtered list:

```
Cycle 2026-15 Focus (set April 14, 2026)
6 active targets

🔥 Tudor BB GMT Pepsi (79830RB) — Hot (+3)
   MAX BUY: $2,910 | Signal: Strong | NR
   4 trades, 100% profitable, avg ROI 9.2%
   Cycle reason: Core Grailzee performer, data shows momentum

🔥 Cartier Santos 40mm (WSSA0030) — Warming (+2)
   MAX BUY: $4,280 | Signal: Strong | NR
   No trade history
   Cycle reason: New lane, volume surge this period

[...]
```

4. **Override flag `--ignore-cycle`** returns raw momentum-sorted universe with warning:

```
⚠ Operating outside cycle focus. Targets not filtered by strategic intent.
Full market view, sorted by momentum:

[full list]
```

**Cycle reason field:** Written by the strategy skill, carried in `cycle_focus.json`. One-line explanation.

**LLM responsibilities:** Response formatting, conversational follow-ups, discipline enforcement messaging.

---

### 10.4 capabilities/ledger.md

**Purpose:** Log closed trades and serve performance queries. Grailzee-only.

**Triggers:** Trade logging or performance queries.

**Sub-mode A: Trade Logging**

1. Parse message for: brand, reference, buy price, sell price, account, date
   - Account defaults to NR if not specified
   - Date defaults to today if not specified
   - cycle_id auto-assigned from date
2. Present parsed row for confirmation:

```
Got it. Logging this trade:

Tudor 79830RB | NR | Bought $2,750 | Sold $3,200 | April 15, 2026
Cycle: cycle_2026-15

Confirm? (yes/no)
```

3. On confirmation: `python3 scripts/ledger_manager.py log <brand> <reference> <account> <buy_price> <sell_price>`
4. Show trade summary:

```
✅ Trade logged.

Net profit: $301 (after $149 Grailzee NR fees)
ROI: 10.9%
Premium vs median: +15.3% ($3,200 vs $2,775 median)

Cycle 2026-15 running: 2 trades, 2 profitable, avg ROI 9.5%
All-time: 8 trades, 100% profitable, avg ROI 8.4%
Presentation premium: +14.2% across 8 measured trades
Threshold: 2 more trades to trigger MAX BUY adjustment
```

**Sub-mode B: Performance Queries**

Supported queries:
- "how are we doing" / "P&L" / "performance" → full summary
- "this cycle" / "cycle performance" → current cycle rollup
- "show me Tudor trades" / "all Breitling" → filtered by brand
- "trades this month" / "last 30 days" → filtered by date
- "what's the premium" / "premium status" → presentation premium detail
- "model accuracy" → how often model's YES resulted in profitable trade
- "in focus" / "off cycle" → breakdown of cycle adherence

**Python script:** `ledger_manager.py`

```
ledger_manager.py log <brand> <reference> <account> <buy_price> <sell_price> [--date YYYY-MM-DD]
ledger_manager.py summary [--brand NAME] [--since YYYY-MM-DD] [--reference REF] [--cycle ID]
ledger_manager.py premium
ledger_manager.py cycle_rollup <cycle_id>
```

Returns JSON in all cases.

**LLM handles:** Natural language parsing, confirmation flow, Telegram formatting.
**LLM does NOT:** Write CSV directly, calculate fees or ROI.

---

## 11. STRATEGY SKILL (CHAT)

**Location:** Installed outside the OpenClaw skill directory, as a Chat-level skill. Exact install path depends on how Chat skills are configured on the system; Claude Code will confirm during Phase 24.

**Purpose:** Cycle planning, monthly platform review, quarterly capital allocation. The strategist.

**Triggers:**
- User invokes after Telegram handoff
- Explicit: "run strategy", "cycle strategy", "strategize grailzee", "plan this cycle"

**Structure:**

```
grailzee-strategy/
├── SKILL.md
└── references/
    └── strategy-framework.md
```

The strategy skill does not need its own Python. It reads state files and drives conversation. When it needs to call helpers (ledger queries, cycle rollups), it uses absolute paths into the agent's scripts directory:

```
/Users/ranbirchawla/.openclaw/workspace/skills/grailzee-eval/scripts/ledger_manager.py
```

**Workflow:**

1. Read all state:
   - Latest analysis cache (`analysis_cache.json`)
   - Latest markdown summary
   - Latest sourcing brief (`sourcing_brief.json`)
   - Previous `cycle_focus.json`
   - Previous `cycle_outcome.json`
   - Trade ledger (`trade_ledger.csv`)
   - `monthly_goals.json` (if month boundary crossed)
   - `quarterly_allocation.json` (if quarter boundary crossed)

2. Present structured briefing:

```
Cycle [new_cycle_id] Strategy Session
Previous cycle: [previous_cycle_id] ([date range])

WHAT WE SAID WE'D HUNT:
[List from previous cycle_focus with cycle_reason]
Capital plan: [previous capital allocation]
Volume target: [previous volume target]

WHAT WE ACTUALLY BOUGHT:
[List from previous cycle_outcome with roi]
Capital deployed: [actual]
Volume achieved: [actual]

PERFORMANCE:
[N] of [N] closed profitable
[N] hit the cycle focus
[N] off-cycle trades

WHAT THE NEW DATA SAYS:
- Emergers: [list with momentum and LLM-enriched context]
- Breakouts: [list with signals]
- Warming: [top references with momentum]
- Cooling: [references losing steam]
- Brand rollups: [any brand-level shifts]

PREMIUM STATUS: [premium summary, threshold distance]

MONTHLY CHECK-IN: (if cycle crosses month boundary)
QUARTERLY REVIEW: (if cycle crosses quarter boundary)

QUESTIONS FOR THIS SESSION:
1. [specific questions based on what changed]
2. [gaps or surprises worth discussing]
3. [capital and volume targets for the cycle]
4. [any specific brand/category lean-in or pullback]
```

3. Conduct structured conversation:
   - User responds
   - Strategy skill pushes back where data doesn't support reasoning
   - Clarifies tradeoffs, surfaces implications
   - Narrows toward focus list

4. Confirm cycle focus before writing:

```
Proposed cycle focus:
- [Reference 1] — [cycle_reason]
- [Reference 2] — [cycle_reason]
[...]

Capital target: [amount]
Volume target: [count]
Specific leans: [brand/category emphasis]

Confirm? (yes/no/refine)
```

5. On confirmation, write:
   - `cycle_focus.json` — narrowed targets with reasoning
   - `cycle_brief.md` — human-readable brief archived to `GrailzeeData/output/briefs/cycle_YYYY-NN_brief.md`
   - `monthly_goals.json` — if month boundary crossed
   - `quarterly_allocation.json` — if quarter boundary crossed

6. Final message:

```
Cycle [cycle_id] focus locked.
[N] targets set. Capital target: [amount]. Volume target: [count].

Targets now active in Telegram. Run `grailzee-targets` there to see the cycle list.
Ad hoc deals can be evaluated any time via the deal capability.

Next strategy session: when Cycle [next_cycle_id] report lands (~[date]).
```

**`cycle_focus.json` schema:**

```json
{
  "cycle_id": "cycle_2026-15",
  "set_at": "2026-04-14T10:30:00",
  "report_source": "grailzee_2026-04-12.csv",
  "targets": [
    {
      "reference": "79830RB",
      "brand": "Tudor",
      "model": "BB GMT Pepsi",
      "cycle_reason": "Core Grailzee performer, data shows momentum",
      "max_buy_override": null
    }
  ],
  "capital_target": 15000,
  "volume_target": 5,
  "brand_emphasis": ["Tudor"],
  "brand_pullback": [],
  "notes": "Leaning into Tudor sourcing through FB groups. Testing Cartier Santos as new lane."
}
```

**Strategy skill discipline:**

- Must read ALL state files before opening the session
- Must push back when user reasoning conflicts with data
- Must surface tradeoffs explicitly when capital and volume goals conflict
- Must not soften hard data points
- Must produce a written brief, not just a chat transcript

---

## 12. PYTHON DECOMPOSITION

### 12.1 Script Inventory

Location: `skills/grailzee-eval/scripts/` (final path after migration)

| Script | Size Target | Responsibility |
|--------|-------------|----------------|
| `grailzee_common.py` | ~200 lines | Constants, formulas, matching, paths, cache I/O, cycle helpers |
| `ingest_report.py` | ~150 lines | Excel → CSV, header normalization, report discovery |
| `analyze_references.py` | ~250 lines | Score all references, risk, format recs, DJ config |
| `analyze_trends.py` | ~100 lines | Period comparison, momentum scoring |
| `analyze_changes.py` | ~80 lines | Emerged, shifted, faded |
| `analyze_breakouts.py` | ~80 lines | Breakout detection |
| `analyze_watchlist.py` | ~60 lines | Watch list detection |
| `analyze_brands.py` | ~80 lines | Brand-level rollups |
| `read_ledger.py` | ~150 lines | Ledger parse, stats, premium, confidence |
| `ledger_manager.py` | ~200 lines | Log trades, serve queries, cycle rollup |
| `roll_cycle.py` | ~100 lines | Produce cycle_outcome.json at report ingestion |
| `build_spreadsheet.py` | ~250 lines | Branded openpyxl output |
| `build_summary.py` | ~120 lines | Markdown analysis summary |
| `build_brief.py` | ~120 lines | Sourcing brief (MD + JSON) |
| `write_cache.py` | ~100 lines | Cache v2 schema writer |
| `evaluate_deal.py` | ~250 lines | Single deal evaluation |
| `query_targets.py` | ~120 lines | Cycle-gated or full target list |
| `run_analysis.py` | ~80 lines | Orchestrator |

**Total target:** ~2,590 lines across 18 files vs. the current ~87K across 4 files.

### 12.2 Logic extraction from current scripts

The existing scripts in `skills/grailzee-eval/scripts/` contain working logic that must be preserved, not rewritten. During Phase 1 extraction, Claude Code reads:

- `analyze_report.py` (49,961 bytes) — source for: header detection, quality filters, risk calculation, DJ 126300 config breakout, reference matching (`normalize_ref`, `match_reference`), compare_periods logic, spreadsheet formatting
- `evaluate_deal.py` (19,753 bytes) — source for: decision logic (YES/NO/MAYBE), format recommendation, margin calculation, ad budget computation
- `query_targets.py` (9,028 bytes) — source for: filter parsing, sort logic
- `write_cache.py` (8,242 bytes) — source for: cache schema v1 (upgrade to v2), backup rotation

**Extract. Refactor into the decomposed structure. Do not rewrite from scratch.**

### 12.3 Shared Module

`grailzee_common.py` contains all constants, formulas, paths, and shared utilities. Every other script imports from it.

**Key constants:**

```python
GRAILZEE_ROOT = "/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Shared Drive/GrailzeeData"
REPORTS_PATH = f"{GRAILZEE_ROOT}/reports"
CSV_PATH = f"{GRAILZEE_ROOT}/reports_csv"
OUTPUT_PATH = f"{GRAILZEE_ROOT}/output"
STATE_PATH = f"{GRAILZEE_ROOT}/state"
BACKUP_PATH = f"{GRAILZEE_ROOT}/backup"

CACHE_PATH = f"{STATE_PATH}/analysis_cache.json"
BRIEF_PATH = f"{STATE_PATH}/sourcing_brief.json"
LEDGER_PATH = f"{STATE_PATH}/trade_ledger.csv"
NAME_CACHE_PATH = f"{STATE_PATH}/name_cache.json"
CYCLE_FOCUS_PATH = f"{STATE_PATH}/cycle_focus.json"
CYCLE_OUTCOME_PATH = f"{STATE_PATH}/cycle_outcome.json"
MONTHLY_GOALS_PATH = f"{STATE_PATH}/monthly_goals.json"
QUARTERLY_PATH = f"{STATE_PATH}/quarterly_allocation.json"
RUN_HISTORY_PATH = f"{STATE_PATH}/run_history.json"

NR_FIXED = 149
RES_FIXED = 199
TARGET_MARGIN = 0.05
RISK_RESERVE_THRESHOLD = 0.40

ACCOUNT_FEES = {"NR": NR_FIXED, "RES": RES_FIXED}

VARDALUX_COLORS = {
    "rich_black": "231F20",
    "warm_gold": "C9A84C",
    "deep_teal": "315159",
}

QUALITY_CONDITIONS = {"excellent", "very good plus", "very good"}
```

Plus functions: `max_buy_nr`, `max_buy_reserve`, `breakeven_nr`, `breakeven_reserve`, `normalize_ref`, `match_reference`, `classify_dj_config`, `is_quality_sale`, `load_name_cache`, `save_name_cache`, `load_cycle_focus`, `is_cycle_focus_current`, `cycle_id_from_date`, `cycle_date_range`.

### 12.4 Orchestrator

`run_analysis.py` — entry point called by the report capability.

```python
def run_analysis(reports_folder=None, output_folder=None):
    reports_folder = reports_folder or REPORTS_PATH
    output_folder = output_folder or OUTPUT_PATH

    csv_path = ingest_report.convert_latest(reports_folder)
    current_cycle_id = cycle_id_from_csv(csv_path)
    csvs = ingest_report.load_window(CSV_PATH, months=3)
    name_cache = grailzee_common.load_name_cache()

    all_results = analyze_references.run(csvs[-2:], name_cache)
    trends = analyze_trends.run(csvs)
    changes = analyze_changes.run(csvs[-2:] if len(csvs) >= 2 else csvs)
    breakouts = analyze_breakouts.run(csvs[-2:] if len(csvs) >= 2 else csvs)
    watchlist = analyze_watchlist.run(csvs[-2:] if len(csvs) >= 2 else csvs)
    brands = analyze_brands.run(all_results)
    ledger_stats = read_ledger.run()

    if ledger_stats.premium.threshold_met:
        analyze_references.apply_premium_adjustment(
            all_results, ledger_stats.premium.adjustment
        )

    roll_cycle.run(previous_cycle_id=prev_cycle(current_cycle_id))

    unnamed = [ref for ref, data in all_results.items() if not data["named"]]

    build_spreadsheet.run(all_results, trends, changes, breakouts,
                          watchlist, brands, ledger_stats, output_folder)
    summary_path = build_summary.run(all_results, trends, changes, breakouts,
                                      watchlist, brands, ledger_stats,
                                      current_cycle_id, output_folder)
    build_brief.run(all_results, trends, changes, breakouts, brands, output_folder)
    write_cache.run(all_results, trends, changes, breakouts, watchlist,
                    brands, ledger_stats, current_cycle_id)

    return {
        "summary_path": summary_path,
        "unnamed": unnamed,
        "cycle_id": current_cycle_id,
    }
```

---

## 13. CACHE SCHEMA v2

```json
{
  "schema_version": 2,
  "generated_at": "2026-04-15T10:30:00",
  "source_report": "grailzee_2026-04-12.csv",
  "cycle_id": "cycle_2026-15",
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
  "dj_configs": {},
  "changes": {
    "emerged": ["L3.781.4.96.9", "A13313161C1A1"],
    "shifted": {"210.30.42.20.03.001": {"direction": "up", "pct": 6.2}},
    "faded": ["AB0138241C1A1"]
  },
  "breakouts": [
    {"reference": "WSSA0030", "signals": ["Volume surge (4 → 11)", "Sell-through +22pp"]}
  ],
  "watchlist": [
    {"reference": "L2.752.4.76.0", "current_sales": 2, "avg_price": 2100}
  ],
  "brands": {
    "Tudor": {"reference_count": 8, "avg_momentum": 1.2, "warming": 5, "cooling": 1, "signal": "Brand heating"}
  },
  "unnamed": ["L3.781.4.96.9", "A13313161C1A1"],
  "summary": {
    "total_references": 35,
    "strong_count": 8,
    "normal_count": 14,
    "reserve_count": 6,
    "caution_count": 7,
    "emerged_count": 2,
    "breakout_count": 1,
    "watchlist_count": 3,
    "unnamed_count": 2,
    "hot_references": 3,
    "premium_status": "8 trades, +14.2%, 2 to threshold"
  }
}
```

---

## 14. BUILD ORDER

Each phase is tested before proceeding. Integration tests run at phase boundaries.

### Phase 0 — Preflight (MANDATORY before any build)

**Before any code changes**, Claude Code does a full read of the existing agent and reports back:

1. Read all .md files in `skills/grailzee-eval/`: AGENTS.md, SOUL.md, USER.md, IDENTITY.md, TOOLS.md, HEARTBEAT.md, SKILL.md, BOOTSTRAP.md (if present), folder-structure.md
2. **Report** which files are generic OpenClaw scaffolding (like SOUL.md already confirmed to be) vs. which contain grailzee-specific customization
3. Read current Python scripts: `analyze_report.py`, `evaluate_deal.py`, `query_targets.py`, `write_cache.py`
4. Catalog the functions, constants, and logic patterns that need to be preserved
5. Confirm MNEMO is running: `curl http://localhost:9999/health`
6. Confirm branch is `feature/grailzee-eval-v2`: `git branch --show-current`
7. **Stop and report.** If any agent .md file contains grailzee-specific customization, the user decides what carries forward before Phase 1 begins. If all are generic, proceed to Phase 1.

### Build phases (all work under `skills/grailzee-eval-v2/`)

| Phase | What | Depends On | Test |
|-------|------|-----------|------|
| 1 | Create `skills/grailzee-eval-v2/` directory. Copy agent .md files from `grailzee-eval/` (per Phase 0 findings). Build `scripts/grailzee_common.py` | Phase 0 | Unit tests: formulas, matching, cycle_id generation, file I/O |
| 2 | Seed `name_cache.json` with known mappings (in GrailzeeData/state/) | Phase 1 | Verify all seed entries load, alt_refs match correctly |
| 3 | `scripts/read_ledger.py` + `scripts/ledger_manager.py` + trade_ledger.csv template | Phase 1 | Create CSV with sample data, verify calculations, cycle rollup |
| 4 | Backfill historical trades from `Vardalux_Grailzee_Closed_Positions.md` (Grailzee-only) | Phase 3 | Verify backfilled data produces expected premium stats |
| 5 | `scripts/ingest_report.py` (Excel → CSV) | Phase 1 | Feed existing Grailzee Pro reports, verify CSVs |
| 6 | `scripts/analyze_references.py` (score all, no core list) | Phase 1, 5 | Verify metrics match current analyzer for known references |
| 7 | `scripts/analyze_trends.py` (momentum scoring) | Phase 1, 5 | Feed multiple CSVs, verify trend detection |
| 8 | `scripts/analyze_changes.py` (emerged/shifted/faded) | Phase 1, 5 | Feed two CSVs, verify categorization |
| 9 | `scripts/analyze_breakouts.py` (breakout detection) | Phase 1, 5 | Verify breakout signals |
| 10 | `scripts/analyze_watchlist.py` (watch list) | Phase 1, 5 | Verify early-signal detection |
| 11 | `scripts/analyze_brands.py` (brand rollups) | Phase 6 | Verify aggregate signals |
| 12 | `scripts/roll_cycle.py` (cycle_outcome.json) | Phase 3 | Verify cycle rollup produces correct JSON |
| 13 | `scripts/build_spreadsheet.py`, `build_summary.py`, `build_brief.py` | Phases 6-11 | Generate outputs, verify formatting |
| 14 | `scripts/write_cache.py` v2 (updated schema) | Phases 6-11 | Verify JSON matches Section 13 spec |
| 15 | `scripts/run_analysis.py` (orchestrator) | All above | End-to-end: Excel in → all outputs generated, unnamed returned |
| 16 | `scripts/evaluate_deal.py` v2 (ledger, momentum, premium, cycle focus, name cache) | Phases 1, 3, 14 | Test with cache + ledger, verify cycle annotation |
| 17 | `scripts/query_targets.py` v2 (cycle discipline, momentum, ledger) | Phases 1, 3, 14 | Test cycle-gated queries, override flag |
| 18 | MNEMO seeding | Phase 1 | Verify `mnemo-cli memory list` shows all seeded memories |
| 19 | Build capability files: `capabilities/report.md`, `deal.md`, `targets.md`, `ledger.md` | All Python done | Manual review for completeness |
| 20 | Write new top-level `SKILL.md` (intent dispatch only) | Phase 19 | Dry run: paste sample messages, verify routing logic |
| 21 | Pre-deletion audit (see Section 15) | All above | All four audit commands return empty |
| 22 | Migration: rename directories, delete old contents | Phase 21 | See Section 15 protocol |
| 23 | Integration test on clean final tree | Phase 22 | Full cycle: new report → strategy → targets → deal → trade log → next cycle |
| 24 | Strategy skill install (outside main repo) | Phase 23 | Test full Telegram handoff to Chat session |
| 25 | Commit and push | Phase 24 | Clean commits with clear messages, branch pushed |

---

## 15. MIGRATION PROTOCOL

### 15.1 File manifest

Claude Code operates strictly within these categories. If a file is not listed, Claude Code asks before touching it.

**PRESERVE AND READ FOR LOGIC EXTRACTION (do not modify during build):**
- `skills/grailzee-eval/scripts/analyze_report.py`
- `skills/grailzee-eval/scripts/evaluate_deal.py`
- `skills/grailzee-eval/scripts/query_targets.py`
- `skills/grailzee-eval/scripts/write_cache.py`

**PRESERVE AND REVIEW (read during Phase 0, copy forward during Phase 1 unless customization found):**
- `skills/grailzee-eval/AGENTS.md`
- `skills/grailzee-eval/SOUL.md`
- `skills/grailzee-eval/USER.md`
- `skills/grailzee-eval/IDENTITY.md`
- `skills/grailzee-eval/TOOLS.md`
- `skills/grailzee-eval/HEARTBEAT.md`

**PRESERVE IF PRESENT:**
- `skills/grailzee-eval/references/` directory (if it exists with business-model.md or similar)

**DELETE DURING PHASE 22 MIGRATION:**
- `skills/grailzee-eval/scripts/analyze_report.py` (replaced by decomposed scripts)
- `skills/grailzee-eval/scripts/evaluate_deal.py` (replaced by v2)
- `skills/grailzee-eval/scripts/query_targets.py` (replaced by v2)
- `skills/grailzee-eval/scripts/write_cache.py` (replaced by v2)
- `skills/grailzee-eval/scripts/__pycache__/` (Python build artifact)
- `skills/grailzee-eval/SKILL.md` (old monolith, replaced by intent dispatcher)
- `skills/grailzee-eval/BOOTSTRAP.md` (if present — AGENTS.md says delete after first run)
- `skills/grailzee-eval/folder-structure.md` (superseded by this implementation plan)

**BUILD NEW IN `skills/grailzee-eval-v2/` (Phases 1-20):**
- Everything listed in Section 9.1 except agent .md files (those are copied in Phase 1)

### 15.2 Pre-deletion audit (Phase 21)

Before any deletion in Phase 22, Claude Code runs these commands and reports output:

```bash
cd /Users/ranbirchawla/.openclaw/workspace

# Verify no new code imports from old location
grep -rn "from grailzee-eval" skills/grailzee-eval-v2/
grep -rn "import.*analyze_report" skills/grailzee-eval-v2/
grep -rn "CORE_REFERENCES" skills/grailzee-eval-v2/

# Verify new directory is self-contained
grep -rn "skills/grailzee-eval/" skills/grailzee-eval-v2/
```

**All four commands must return empty.** If any match, Phase 22 is blocked. Claude Code reports the matches, fixes the references, re-runs the audit. Only after all four return empty does Phase 22 proceed.

### 15.3 Migration sequence (Phase 22)

Execute in exact order. Each step is a separate shell operation for clean rollback.

```bash
cd /Users/ranbirchawla/.openclaw/workspace

# Step 1: Rename old directory to preserve it temporarily
mv skills/grailzee-eval skills/grailzee-eval-old

# Step 2: Rename new directory to the production name
mv skills/grailzee-eval-v2 skills/grailzee-eval

# Step 3: Verify new structure is in place
ls -la skills/grailzee-eval/

# Step 4: Run integration test (Phase 23)
# If integration test fails, ROLLBACK:
#   rm -rf skills/grailzee-eval
#   mv skills/grailzee-eval-old skills/grailzee-eval

# If integration test passes:

# Step 5: Delete the old directory
rm -rf skills/grailzee-eval-old

# Step 6: Verify final tree
ls -la skills/grailzee-eval/
```

**Rollback if integration test fails:**

```bash
rm -rf skills/grailzee-eval
mv skills/grailzee-eval-old skills/grailzee-eval
# Branch is still on feature/grailzee-eval-v2; investigate, fix, retry
```

Git also provides rollback via `git checkout main`, but the in-place rename gives the faster path if the issue is caught immediately.

### 15.4 .gitignore verification

Before Phase 25 commit, verify `.gitignore` at repo root excludes:

```
__pycache__/
*.pyc
*.pyo
.DS_Store
```

If not present, add them. Python build artifacts should never enter git.

---

## 16. BACKFILL PLAN

Before the system goes live, populate the trade ledger with historical data from `Vardalux_Grailzee_Closed_Positions.md` in project knowledge.

Only Grailzee trades (NR or RES) get backfilled. Other platforms are excluded.

**Process:**
1. Read existing tracker
2. Filter to Grailzee-only closed positions
3. For each: determine cycle_id from date_closed
4. Append to trade_ledger.csv
5. Run `ledger_manager.py summary` to verify stats match expected historical performance

After backfill, confidence scoring and premium calculations work from day one.

---

## 17. TESTING STRATEGY

### 17.1 Unit tests

Every Python module gets a `tests/` directory with pytest tests. Coverage targets:

- `grailzee_common.py`: 90%+
- `analyze_*.py`: 80%+
- `read_ledger.py`, `ledger_manager.py`: 85%+
- `evaluate_deal.py`: 80%+
- Build scripts: 60%+

### 17.2 Integration tests

- `tests/integration/test_full_cycle.py` — end-to-end run with fixture data
- `tests/integration/test_ledger_roundtrip.py` — log trades, query, verify stats
- `tests/integration/test_cycle_discipline.py` — verify targets gate on cycle focus
- `tests/integration/test_migration.py` — validates Phase 22 migration succeeded

### 17.3 Fixture data

- `tests/fixtures/grailzee_2026-01-18.csv`
- `tests/fixtures/grailzee_2026-02-01.csv`
- `tests/fixtures/grailzee_2026-02-15.csv`
- `tests/fixtures/trade_ledger_sample.csv` — 10 sample trades
- `tests/fixtures/cycle_focus_sample.json`
- `tests/fixtures/cycle_outcome_sample.json`

Reports `Grailzee_Pro_BiWeekly_Report__February_W1.xlsx` and `Grailzee_Pro_BiWeekly_Report__August1.xlsx` in project knowledge are the starting fixtures (convert to CSV first).

---

## 18. DECISION LOG

Decisions that are locked. Claude Code should not re-litigate these.

| Decision | Rationale |
|----------|-----------|
| One agent with capability modules, not multiple agents | AGENTS.md convention is written for a single agent. OpenClaw runtime expects one agent per directory |
| Top-level SKILL.md becomes intent dispatcher | Router stops being a skill; it becomes internal dispatch in the existing agent structure |
| Build in parallel v2 directory, rename at migration (Option 3) | Clean rollback, runtime not confused during build, final name matches existing OpenClaw reference |
| Grailzee-only ledger (NR + RES accounts) | Cross-platform P&L is a different product. Keeps scope clean, makes premium math defensible |
| CSV as canonical format after ingest | Stable, parseable, no openpyxl dependency on reads. Excel preserved in archive |
| Ingest sales sheet only | Other sheets unused by analyzer. Token and maintenance cost not justified |
| Rolling 3-month / 6-report trend window | Enough for directional signal without stale data |
| Trade ledger all-time, never rolls off | Structurally small, every trade teaches the model |
| Manual CSV entry + chat logging interface | 7-column CSV maintainable by hand |
| Calculated fields computed at analysis time | Fee structures may change; audit trail stays clean |
| Momentum scoring -3 to +3 | Simple, sortable, human-readable labels |
| All references scored equally, 3+ sales threshold | Data determines priority, not a hardcoded list |
| Premium auto-adjustment at 10 trades, +8% average | Previously manual; now automatic |
| Name cache JSON + LLM web search for resolution | Python needs deterministic lookup. LLM resolves unknowns. Cache grows organically |
| MNEMO captures name resolutions automatically | Compounds knowledge across sessions |
| MNEMO seeded with business context | Keeps SKILL.md and capability files lean |
| DJ 126300 config breakout preserved as special case | Same reference, wildly different prices by config. Data parsing problem, not naming |
| Python does detection, LLM does language and web research | Deterministic math, reproducible answers, auditable model |
| Strategy is a Chat skill, not OpenClaw | Strategy needs multi-turn depth, not single-message speed |
| Strict cycle discipline on targets capability | User explicitly chose discipline. Override flag available |
| Ad hoc deal evaluation always available | Cycle governs strategic hunting, not tactical opportunity |
| Biweekly cycle = report cadence | Realistic hunt-buy-list-sell loop is 2 weeks |
| Monthly goals layered at month boundaries | Platform performance review |
| Quarterly allocation reviews at quarter boundaries | Capital allocation decisions |
| Breakout + watch list + brand rollups in v1 | Pattern detection beyond momentum |
| Strategy skill reads all state before session | No half-informed strategy |
| Strategy writes cycle_brief.md as markdown archive | Historical record of strategic reasoning |
| Phase 0 preflight reads agent .md files first | Don't assume scaffolding is generic; verify before carrying forward |
| Pre-deletion audit gates Phase 22 | Deletion only happens after new system proves it doesn't depend on old files |
| Logic extraction preferred over rewrite | Working code in current scripts has value. Refactor, don't restart |

---

## 19. OUT OF SCOPE FOR v2

Explicitly not being built. Named here so they don't get confused with v2 features.

- Cross-platform P&L tracking (use WatchTrack or QuickBooks)
- Automated listing generation from cycle focus (separate skill, existing)
- Condition-tier momentum scoring
- Seasonal pattern detection (requires year-over-year comparison)
- Comp-set disruption detection (dealer flooding)
- Automatic cycle focus based on data alone (strategy requires human intent)
- Mobile-specific UI for strategy skill (Chat is the only interface)
- Webhook or polling for new Grailzee Pro reports (manual drop into reports/)

These are v3+ candidates. Not v2 scope.

---

*Implementation Plan v2 | April 16, 2026*
*Ready for Claude Code execution on branch `feature/grailzee-eval-v2`*

