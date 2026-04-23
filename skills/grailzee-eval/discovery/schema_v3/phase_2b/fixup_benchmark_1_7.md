# §1.7 analytical-quality benchmark (v2 vs v3 post-fixup)

**Date**: 2026-04-24
**Branch**: `feature/grailzee-eval-v2`
**Script**: `discovery/schema_v3/phase_2b/fixup_benchmark_1_7.py`

**Window note**: v2 is Drive's live cache (source W1.5 = 2026-03-23,
generated 2026-04-22). v3 is a fresh W1+W2 regeneration under post-fixup
code. Window mismatch is tolerated because the operator reads this to
judge "less useful for strategy session," which is about field set and
presentation, not market-value drift.

**Ledger note**: v2 was regenerated against the real trade_ledger; v3
is a tmp-tree rerun with an empty ledger. `confidence`, `realized_premium_pct`,
and `premium_vs_market_pct` on the v2 side may therefore appear populated
where v3 shows null. The sole correct reading of the diff is: "v2 flat
fields are gone from v3; v3 has buckets and drops the synthesized
ledger-vs-market fields entirely." Not a regression.

**What to read for**: dial-color / auction-type splits. Many references
(79830RB is the canonical example) carry very different medians for
black vs white dials, or NR vs Reserve auctions. v2 blended all of these
into one median and one signal; v3 exposes the split.

v2 cache: schema_version=2, refs=1,229, source=grailzee_2026-03-23.csv
v3 cache (fresh): schema_version=3, refs=3,878, source=grailzee_2026-04-21.csv

## 79830RB

  v2 (Tudor BB GMT Pepsi):
    brand: Tudor
    capital_required_nr: 3289.0
    capital_required_res: 3289.0
    condition_mix: {"excellent": 0, "very_good": 47, "like_new": 13, "new": 28, "below_quality": 27}
    confidence: {"trades": 2, "profitable": 1, "win_rate": 50.0, "avg_roi": 9.2, "avg_premium": -8.4, "last_trade": "2026-03-24"}
    expected_net_at_median_nr: 261.0
    expected_net_at_median_res: 261.0
    max_buy_nr: 3240.0
    max_buy_res: 3190.0
    median: 3550.0
    model: BB GMT Pepsi
    momentum: {"score": -2, "label": "Cooling"}
    named: True
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 2
    realized_premium_pct: -2.8
    realized_premium_trade_count: 1
    reference: 79830RB
    risk_nr: 23.863636363636363
    signal: Reserve
    st_pct: 0.5204347826086957
    trend_median_change: -100.0
    trend_median_pct: -2.78
    trend_signal: Stable
    volume: 115

  v3 (Tudor BB GMT Pepsi):
    brand: Tudor
    buckets: (4 buckets)
      no numerals|res|black: signal=Reserve median=3050.0 volume=25 st_pct=0.5492 named_special=None
      no numerals|res|white: signal=Reserve median=3900.0 volume=23 st_pct=0.5491304347826087 named_special=None
      no numerals|nr|black: signal=Strong median=3050.0 volume=11 st_pct=0.55 named_special=None
      no numerals|nr|white: signal=Normal median=3750.0 volume=9 st_pct=0.55 named_special=None
    confidence: None
    model: BB GMT Pepsi
    momentum: {"score": 0, "label": "Stable"}
    named: True
    reference: 79830RB
    trend_median_change: -75.0
    trend_median_pct: -2.08
    trend_signal: Stable

---

## 126300

  v2 (Rolex Datejust 41):
    brand: Rolex
    capital_required_nr: 9619.0
    capital_required_res: 9619.0
    condition_mix: {"excellent": 0, "very_good": 108, "like_new": 26, "new": 134, "below_quality": 34}
    confidence: None
    expected_net_at_median_nr: 581.0
    expected_net_at_median_res: 581.0
    max_buy_nr: 9570.0
    max_buy_res: 9520.0
    median: 10200.0
    model: Datejust 41
    momentum: {"score": -1, "label": "Softening"}
    named: True
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 0
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: 126300
    risk_nr: 26.515151515151516
    signal: Reserve
    st_pct: 0.31
    trend_median_change: -25.0
    trend_median_pct: -0.25
    trend_signal: Stable
    volume: 302

  v3 (Rolex Datejust 41):
    brand: Rolex
    buckets: (26 buckets)
      no numerals|res|blue: signal=Normal median=10200.0 volume=29 st_pct=0.31 named_special=None
      roman|res|slate: signal=Normal median=10700.0 volume=31 st_pct=0.31 named_special=wimbledon
      roman|res|white: signal=Careful median=9200.0 volume=13 st_pct=0.31 named_special=None
      no numerals|res|green: signal=Careful median=11250.0 volume=15 st_pct=0.31 named_special=None
      roman|res|black: signal=Low data median=None volume=1 st_pct=0.31 named_special=None
      no numerals|res|silver: signal=Normal median=8825.0 volume=10 st_pct=0.31 named_special=None
      ... (+20 more)
    confidence: None
    model: Datejust 41
    momentum: {"score": 1, "label": "Warming"}
    named: True
    reference: 126300
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Stable

---

## 126334

  v2 (Rolex 126334):
    brand: Rolex
    capital_required_nr: 13429.0
    capital_required_res: 13429.0
    condition_mix: {"excellent": 0, "very_good": 62, "like_new": 40, "new": 177, "below_quality": 10}
    confidence: None
    expected_net_at_median_nr: 771.0
    expected_net_at_median_res: 771.0
    max_buy_nr: 13380.0
    max_buy_res: 13330.0
    median: 14200.0
    model: 126334
    momentum: {"score": 1, "label": "Warming"}
    named: False
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 0
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: 126334
    risk_nr: 19.35483870967742
    signal: Normal
    st_pct: 0.21505190311418684
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Stable
    volume: 289

  v3 (Rolex 126334):
    brand: Rolex
    buckets: (21 buckets)
      no numerals|res|green: signal=Careful median=16200.0 volume=19 st_pct=0.21 named_special=None
      roman|res|blue: signal=Reserve median=13950.0 volume=14 st_pct=0.21 named_special=None
      no numerals|res|rhodium: signal=Normal median=14450.0 volume=7 st_pct=0.21 named_special=None
      roman|res|slate: signal=Strong median=14100.0 volume=23 st_pct=0.21 named_special=wimbledon
      no numerals|res|white: signal=Normal median=13740.0 volume=6 st_pct=0.21 named_special=None
      diamond|res|rhodium: signal=Low data median=None volume=2 st_pct=0.21 named_special=None
      ... (+15 more)
    confidence: None
    model: 126334
    momentum: {"score": 1, "label": "Warming"}
    named: False
    reference: 126334
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Now Reserve

---

## 79360N

  v2 (Tudor 79360N):
    brand: Tudor
    capital_required_nr: 4189.0
    capital_required_res: 4189.0
    condition_mix: {"excellent": 0, "very_good": 128, "like_new": 32, "new": 45, "below_quality": 19}
    confidence: {"trades": 1, "profitable": 1, "win_rate": 100.0, "avg_roi": 8.4, "avg_premium": 119.2, "last_trade": "2026-02-16"}
    expected_net_at_median_nr: 305.0
    expected_net_at_median_res: 305.0
    max_buy_nr: 4140.0
    max_buy_res: 4090.0
    median: 4494.0
    model: 79360N
    momentum: {"score": -2, "label": "Cooling"}
    named: False
    premium_vs_market_pct: 119.2
    premium_vs_market_sale_count: 1
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: 79360N
    risk_nr: 41.5
    signal: Careful
    st_pct: 0.4250892857142857
    trend_median_change: -168.5
    trend_median_pct: -3.67
    trend_signal: Stable
    volume: 224

  v3 (Tudor 79360N):
    brand: Tudor
    buckets: (11 buckets)
      no numerals|res|white: signal=Careful median=4100.0 volume=38 st_pct=0.43 named_special=panda
      no numerals|res|black: signal=Careful median=4050.0 volume=24 st_pct=0.43 named_special=None
      no numerals|res|blue: signal=Strong median=9375.0 volume=4 st_pct=0.43 named_special=None
      no numerals|nr|black: signal=Strong median=3350.0 volume=4 st_pct=0.43 named_special=None
      no numerals|nr|turquoise: signal=Reserve median=9200.0 volume=4 st_pct=0.43 named_special=None
      no numerals|res|turquoise: signal=Normal median=9300.0 volume=18 st_pct=0.43 named_special=None
      ... (+5 more)
    confidence: None
    model: 79360N
    momentum: {"score": 2, "label": "Heating Up"}
    named: False
    reference: 79360N
    trend_median_change: 100.0
    trend_median_pct: 2.18
    trend_signal: Stable

---

## 126710BLNR

  v2 (Rolex 126710BLNR):
    brand: Rolex
    capital_required_nr: 16649.0
    capital_required_res: 16649.0
    condition_mix: {"excellent": 0, "very_good": 60, "like_new": 25, "new": 77, "below_quality": 20}
    confidence: None
    expected_net_at_median_nr: 926.0
    expected_net_at_median_res: 926.0
    max_buy_nr: 16600.0
    max_buy_res: 16550.0
    median: 17575.0
    model: 126710BLNR
    momentum: {"score": -1, "label": "Softening"}
    named: False
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 0
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: 126710BLNR
    risk_nr: 14.814814814814813
    signal: Normal
    st_pct: 0.4348901098901099
    trend_median_change: -50.0
    trend_median_pct: -0.28
    trend_signal: Stable
    volume: 182

  v3 (Rolex 126710BLNR):
    brand: Rolex
    buckets: (2 buckets)
      no numerals|res|black: signal=Normal median=17450.0 volume=85 st_pct=0.41117647058823525 named_special=None
      no numerals|nr|black: signal=Normal median=17600.0 volume=19 st_pct=0.41 named_special=None
    confidence: None
    model: 126710BLNR
    momentum: {"score": 1, "label": "Warming"}
    named: False
    reference: 126710BLNR
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Stable

---

## 124060

  v2 (Rolex 124060):
    brand: Rolex
    capital_required_nr: 11909.0
    capital_required_res: 11909.0
    condition_mix: {"excellent": 0, "very_good": 42, "like_new": 15, "new": 132, "below_quality": 6}
    confidence: None
    expected_net_at_median_nr: 691.0
    expected_net_at_median_res: 691.0
    max_buy_nr: 11860.0
    max_buy_res: 11810.0
    median: 12600.0
    model: 124060
    momentum: {"score": -1, "label": "Softening"}
    named: False
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 0
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: 124060
    risk_nr: 14.814814814814813
    signal: Normal
    st_pct: 0.5551282051282052
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Stable
    volume: 195

  v3 (Rolex 124060):
    brand: Rolex
    buckets: (2 buckets)
      no numerals|res|black: signal=Normal median=12600.0 volume=77 st_pct=0.5507792207792208 named_special=None
      no numerals|nr|black: signal=Reserve median=13100.0 volume=29 st_pct=0.550344827586207 named_special=None
    confidence: None
    model: 124060
    momentum: {"score": 0, "label": "Stable"}
    named: False
    reference: 124060
    trend_median_change: 100.0
    trend_median_pct: 0.79
    trend_signal: Stable

---

## 28500

  v2 (Tudor 28500):
    brand: Tudor
    capital_required_nr: 1839.0
    capital_required_res: 1839.0
    condition_mix: {"excellent": 0, "very_good": 2, "like_new": 1, "new": 6, "below_quality": 3}
    confidence: {"trades": 3, "profitable": 3, "win_rate": 100.0, "avg_roi": 12.6, "avg_premium": 13.3, "last_trade": "2026-04-19"}
    expected_net_at_median_nr: 186.0
    expected_net_at_median_res: 186.0
    max_buy_nr: 1790.0
    max_buy_res: 1740.0
    median: 2025.0
    model: 28500
    momentum: {"score": -2, "label": "Cooling"}
    named: False
    premium_vs_market_pct: 18.5
    premium_vs_market_sale_count: 3
    realized_premium_pct: 18.5
    realized_premium_trade_count: 2
    reference: 28500
    risk_nr: 22.22222222222222
    signal: Reserve
    st_pct: 0.4066666666666667
    trend_median_change: -150.0
    trend_median_pct: -7.14
    trend_signal: Cooling | Now NR
    volume: 12

  v3 (Tudor 28500):
    brand: Tudor
    buckets: (7 buckets)
      roman|nr|silver: signal=Low data median=None volume=1 st_pct=0.47 named_special=None
      roman|nr|black: signal=Low data median=None volume=1 st_pct=0.47 named_special=None
      roman|res|salmon: signal=Low data median=None volume=1 st_pct=0.47 named_special=None
      roman|nr|blue: signal=Low data median=None volume=2 st_pct=0.47 named_special=None
      roman|res|silver: signal=Low data median=None volume=1 st_pct=0.47 named_special=None
      diamond|nr|salmon: signal=Low data median=None volume=1 st_pct=0.47 named_special=None
      ... (+1 more)
    confidence: None
    model: 28500
    momentum: {"score": 0, "label": "Stable"}
    named: False
    reference: 28500
    trend_median_change: -75.0
    trend_median_pct: -3.57
    trend_signal: Stable

---

## A17320

  v2 (Breitling Superocean Heritage 42):
    brand: Breitling
    capital_required_nr: 2379.0
    capital_required_res: 2389.0
    condition_mix: {"excellent": 0, "very_good": 16, "like_new": 0, "new": 0, "below_quality": 17}
    confidence: None
    expected_net_at_median_nr: 221.0
    expected_net_at_median_res: 211.0
    max_buy_nr: 2330.0
    max_buy_res: 2290.0
    median: 2600.0
    model: Superocean Heritage 42
    momentum: {"score": -2, "label": "Cooling"}
    named: True
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 0
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: A17320
    risk_nr: 66.66666666666666
    signal: Pass
    st_pct: 0.46575757575757576
    trend_median_change: -80.0
    trend_median_pct: -3.08
    trend_signal: Stable
    volume: 33

  v3 (Breitling Superocean Heritage 42):
    brand: Breitling
    buckets: (7 buckets)
      no numerals|res|brown: signal=Low data median=None volume=1 st_pct=0.49 named_special=None
      no numerals|nr|black: signal=Low data median=2575.0 volume=6 st_pct=0.49 named_special=None
      no numerals|res|black: signal=Low data median=2600.0 volume=3 st_pct=0.49 named_special=None
      no numerals|nr|ivory: signal=Low data median=None volume=1 st_pct=0.49 named_special=None
      no numerals|res|blue: signal=Low data median=2300.0 volume=3 st_pct=0.49 named_special=None
      no numerals|nr|blue: signal=Low data median=None volume=2 st_pct=0.49 named_special=None
      ... (+1 more)
    confidence: None
    model: Superocean Heritage 42
    momentum: {"score": 0, "label": "Stable"}
    named: True
    reference: A17320
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Stable

---

## 116500LN

  v2 (Rolex 116500LN):
    brand: Rolex
    capital_required_nr: 26239.0
    capital_required_res: 26239.0
    condition_mix: {"excellent": 0, "very_good": 26, "like_new": 2, "new": 0, "below_quality": 4}
    confidence: None
    expected_net_at_median_nr: 1411.0
    expected_net_at_median_res: 1411.0
    max_buy_nr: 26190.0
    max_buy_res: 26140.0
    median: 27650.0
    model: 116500LN
    momentum: {"score": 0, "label": "Stable"}
    named: False
    premium_vs_market_pct: 0.0
    premium_vs_market_sale_count: 0
    realized_premium_pct: None
    realized_premium_trade_count: 0
    reference: 116500LN
    risk_nr: 39.285714285714285
    signal: Careful
    st_pct: 0.19
    trend_median_change: 0.0
    trend_median_pct: 0.0
    trend_signal: Stable
    volume: 32

  v3 (Rolex 116500LN):
    brand: Rolex
    buckets: (3 buckets)
      no numerals|res|white: signal=Normal median=29150.0 volume=8 st_pct=0.19 named_special=panda
      no numerals|res|black: signal=Strong median=25500.0 volume=8 st_pct=0.19 named_special=None
      no numerals|nr|black: signal=Low data median=None volume=1 st_pct=0.19 named_special=None
    confidence: None
    model: 116500LN
    momentum: {"score": 1, "label": "Warming"}
    named: False
    reference: 116500LN
    trend_median_change: 350.0
    trend_median_pct: 1.27
    trend_signal: Stable

---

## 215.30.44.22.01.002

  v2: (not in v2 cache)

  v3: (not in v3 cache)

---

