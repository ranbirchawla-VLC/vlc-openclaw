# Platform Posting Checklist — Auto-Generation Logic
## Vardalux Watch Listings

**Purpose:** Generate the correct posting checklist for every watch based on
final list price and brand. Every watch gets a minimum of 6 platforms. The
checklist appears at the end of every listing document.

---

## TIER 1: UNIVERSAL PLATFORMS (Every Watch)

Post ALL watches to these four platforms regardless of brand or price:

- [ ] eBay
- [ ] Chrono24
- [ ] Value Your Watch
- [ ] Watch Trader Community (Facebook) — https://www.facebook.com/groups/watchtradercommunity

---

## TIER 2: PRICE-BASED FACEBOOK GROUPS

Every watch gets exactly two price-based groups. Which two depends on the
final Facebook retail list price:

### $5,000 or less:
- [ ] TWAT (5K or less) — https://www.facebook.com/groups/388782265512153/
- [ ] Bay Watch Under 10K — https://www.facebook.com/groups/911491502379901

### $5,001 to $9,999:
- [ ] TWAT (Over $5K) — https://www.facebook.com/groups/645732992585010/
- [ ] Bay Watch Under 10K — https://www.facebook.com/groups/911491502379901

### $10,000+:
- [ ] TWAT (Over $5K) — https://www.facebook.com/groups/645732992585010/
- [ ] Bay Watch Club (Over $10K) — https://www.facebook.com/groups/omarbay

### Quick Reference

| Final Price | TWAT Group | Bay Watch Group |
|-------------|-----------|-----------------|
| ≤ $5,000 | 5K or less | Under 10K |
| $5,001–$9,999 | Over $5K | Under 10K |
| ≥ $10,000 | Over $5K | Club (Over 10K) |

---

## TIER 3: BRAND-SPECIFIC FACEBOOK GROUPS

Add these based on the watch brand. Not all brands have dedicated groups.

### Omega (all models):
- [ ] Omega Watches Buy and Sell — https://www.facebook.com/groups/967376425025667

### Omega Speedmaster (in addition to general Omega group):
- [ ] Omega Speedmaster Buy and Sell — https://www.facebook.com/groups/317784437216258

*Note: Speedmasters go to BOTH Omega groups.*

### Breitling:
- [ ] Breitling Owners and Enthusiasts

### Panerai:
- [ ] Panerai Watches: Buy, Sell, Trade — https://www.facebook.com/groups/1000482317936935
- [ ] Panerai Watches For Sale
- [ ] Paneristi.com Sellers

### Hublot:
- [ ] HUBLOT Watches Buy and Sell — https://www.facebook.com/groups/6536262816386227
- [ ] Hublot Watches: Buy, Sell, Trade and Discuss All Things Hublot

### Tudor:
*No dedicated Tudor Facebook group in current list. Post to universal and
price-based groups only. Update this file when Tudor groups are identified.*

### Rolex:
*No Rolex-specific Facebook group in current list. Post to universal and
price-based groups only. Update this file when Rolex groups are identified.*

### Other brands:
*Add brand-specific groups as they are discovered and vetted.*

### Brand Coverage Summary

| Brand | Groups | Total |
|-------|--------|-------|
| Omega (non-Speedmaster) | Omega Buy/Sell | 1 |
| Omega Speedmaster | Omega Buy/Sell + Speedmaster Buy/Sell | 2 |
| Breitling | Owners and Enthusiasts | 1 |
| Panerai | Buy/Sell/Trade + For Sale + Paneristi | 3 |
| Hublot | Buy/Sell + Discussion | 2 |
| Tudor | None currently | 0 |
| Rolex | None currently | 0 |
| Other | Add as discovered | 0 |

---

## TIER 4: OPTIONAL PLATFORMS (Ask Before Including)

### Wholesale Facebook Groups (requires separate wholesale pricing)

Ask: "Do you want to list in wholesale groups with different pricing?"

If yes, get the target wholesale NET and add:

**All price points:**
- [ ] Watch Trading Academy Buy/Sell/Trade Group

**Under $10K:**
- [ ] Moda Watch Club — 10k & Under

**Over $10K:**
- [ ] Moda Watch Club

### WTA Dealer Chat (requires separate WTA pricing and comp)

Ask: "Do you want to list on WTA Dealer Chat?"

If yes, get the WTA asking price and lowest US dealer comp. Validate
against WTA pricing rules (see SKILL.md Step 2) before including.

- [ ] WTA Dealer Chat

### Reddit r/watchexchange (requires separate Reddit pricing)

Ask: "Do you want to list on Reddit r/watchexchange?"

If yes, get the Reddit asking price. Search for MSRP if not provided.

- [ ] Reddit r/watchexchange

### Grailzee (requires format decision)

If `grailzee_format` is not "skip":

- [ ] Grailzee ([NR / Reserve] format)

### Instagram

Instagram is included by default for all listings:

- [ ] Instagram (no pricing, "Tell Me More" CTA)

---

## CHECKLIST GENERATION LOGIC

To generate the checklist, collect:
1. Final Facebook retail list price (for price-based group routing)
2. Watch brand (for brand-specific group routing)
3. Which optional platforms are requested

Then assemble:

```
PLATFORM POSTING CHECKLIST — [Brand] [Model] [Reference]

UNIVERSAL:
- [ ] eBay — $[price]
- [ ] Chrono24 — $[price]
- [ ] Value Your Watch — $[price]
- [ ] Watch Trader Community (FB) — $[FB retail price]

PRICE-BASED (FB):
- [ ] [Group 1] — $[FB retail price]
- [ ] [Group 2] — $[FB retail price]

BRAND-SPECIFIC (FB):
- [ ] [Group(s) based on brand]

OPTIONAL (if requested):
- [ ] Grailzee — [NR/Reserve]
- [ ] WTA Dealer Chat — $[WTA price]
- [ ] Reddit r/watchexchange — $[Reddit price]
- [ ] Facebook Wholesale — $[wholesale price]
  - [ ] Watch Trading Academy
  - [ ] Moda Watch Club [appropriate tier]

ALWAYS:
- [ ] Instagram (no price)

Total platforms: [count]
```

---

## TYPICAL PLATFORM COUNTS

| Scenario | Platforms |
|----------|----------|
| Standard listing (no optional) | 7-9 |
| With Grailzee + Instagram | 9-11 |
| Full deployment (all optional) | 12-15 |

---

*Aligned to The Vardalux Way v1.3 | March 2026*
*Update this document when new Facebook groups are discovered and vetted.*
