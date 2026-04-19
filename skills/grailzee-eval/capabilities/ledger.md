# Trade Ledger

## Purpose

Log closed Grailzee trades and serve performance queries. Two sub-modes: trade logging (write, requires confirmation) and performance queries (read).

Grailzee-only scope. Only trades closed on Grailzee NR or Reserve accounts are logged here. Cross-platform sales belong elsewhere.

## Trigger

### Trade Logging

Message mentions closing, selling, trading, or booking a trade with brand/reference and dollar amounts. Examples: "closed Tudor 79830RB, bought 2750 sold 3200", "sold the Breitling A17320 for 2400, paid 2100", "booked a trade on the Cartier Santos".

### Performance Queries

Message asks about performance, P&L, trades, premium, or cycle results. Examples: "how are we doing?", "show me Tudor trades", "what's the premium?", "this cycle's performance", "P&L", "model accuracy".

## Trade Logging Workflow

### Step 1: Parse the message

Extract from the message:
- **brand** (required)
- **reference** (required)
- **buy_price** (required)
- **sell_price** (required)
- **account** (NR or RES; default NR if not specified)
- **date** (YYYY-MM-DD; default today if not specified)

### Step 2: Present for confirmation

You MUST present the parsed trade data and wait for explicit confirmation before writing. Do not log the trade without a "yes."

Recommended confirmation message:

```
Got it. Logging this trade:

{brand} {reference} | {account} | Bought ${buy_price} | Sold ${sell_price} | {date}
Cycle: {cycle_id (auto from date)}

Confirm? (yes/no)
```

### Step 3: Handle the response

**On "yes" (or "y", "confirm", "proceed"):** Call the log command:

```
python3 scripts/ledger_manager.py log {brand} {reference} {account} {buy_price} {sell_price} --date {YYYY-MM-DD}
```

The script returns: `{"status": "ok", "trade": {date_closed, cycle_id, brand, reference, account, buy_price, sell_price}}`

Then query the current state for the response:

```
python3 scripts/ledger_manager.py summary --reference {reference}
python3 scripts/ledger_manager.py premium
python3 scripts/ledger_manager.py summary --cycle {cycle_id}
```

Format the post-log summary (see Response Format below).

**On anything other than yes:** Abort the trade. Reply:

```
Trade not logged. Re-send the trade details with corrections when ready.
```

Do not re-parse, do not ask follow-up clarification questions, do not attempt to correct the parse. The operator re-sends cleanly.

### Step 4: Post the trade summary

```
Trade logged.

Net profit: ${net_profit} (after ${fees} Grailzee {account} fees)
ROI: {roi_pct}%
Premium vs median: {premium_vs_median}% (${sell_price} vs ${median} median)

Cycle {cycle_id} running: {cycle_trades} trades, {cycle_profitable} profitable, avg ROI {cycle_avg_roi}%
All-time: {total_trades} trades, {win_rate}% profitable, avg ROI {avg_roi}%
Presentation premium: {avg_premium}% across {premium_trade_count} measured trades
Threshold: {trades_to_threshold} more trades to trigger MAX BUY adjustment
```

If the premium threshold is already met, replace the threshold line:

```
Presentation premium: {avg_premium}% across {premium_trade_count} trades. Threshold met; MAX BUY adjustment active (+{adjustment}%).
```

### Error handling

If any script returns an error, surface it:

```
Trade logging failed: {message}
```

## Performance Query Workflow

Map the operator's query to the appropriate ledger_manager.py subcommand:

| Operator says | Subcommand | Flags |
|---------------|-----------|-------|
| "how are we doing" / "P&L" / "performance" / "summary" | summary | (none) |
| "this cycle" / "cycle performance" | summary | --cycle {current_cycle_id} |
| "show me Tudor trades" / "all Breitling" | summary | --brand {brand} |
| "trades this month" / "last 30 days" | summary | --since {date} |
| "what's the premium" / "premium status" | premium | (none) |
| "{reference} trades" / "how did {ref} do" | summary | --reference {ref} |
| "cycle {id} results" / "last cycle" | cycle_rollup | {cycle_id} |

### CLI invocations

```
python3 scripts/ledger_manager.py summary [--brand NAME] [--since YYYY-MM-DD] [--reference REF] [--cycle ID]
python3 scripts/ledger_manager.py premium
python3 scripts/ledger_manager.py cycle_rollup <cycle_id>
```

### Response format for summary

```
{total_trades} trades, {profitable} profitable ({win_rate}%)
Total net: ${total_net_profit}
Capital deployed: ${total_deployed}
Avg ROI: {avg_roi_pct}%
```

If filtered (brand, reference, cycle, date range), lead with the filter context:

```
Tudor trades since 2026-01-01:
{summary as above}
```

### Response format for premium

```
Presentation premium: {avg_premium}% across {trade_count} trades
Threshold: {threshold status}
{trades_to_threshold} trades to trigger | Adjustment: {adjustment}%
```

### Response format for cycle_rollup

```
Cycle {cycle_id} ({start} to {end})
{total_trades} trades, {profitable} profitable
Avg ROI: {avg_roi}%
Capital: ${capital_deployed} deployed, ${capital_returned} returned

Focus adherence: {in_focus_count} in focus, {off_cycle_count} off-cycle
{hits/misses/off_cycle details if cycle_focus data present}
```

### Error

```
Ledger query failed: {message}
```

## LLM Responsibilities

- Parse trade details from natural language messages
- Present parsed trade for confirmation before any write
- Abort cleanly on rejection (no re-parsing, no follow-up questions)
- Map performance queries to the correct subcommand and flags
- Compute date ranges for "last 30 days" / "this month" queries
- Redirect cross-platform questions: "The trade ledger is Grailzee-only. For cross-platform P&L, check WatchTrack."

## What the LLM Does NOT Do

- Write to the CSV directly (ledger_manager.py handles all writes)
- Calculate fees, ROI, or premium (scripts return computed values)
- Log trades without explicit confirmation
- Accept trades from non-Grailzee platforms
- Restate fee structures or account rules (MNEMO provides business context)

Voice and tone follow Vardalux conventions per SOUL.md.
