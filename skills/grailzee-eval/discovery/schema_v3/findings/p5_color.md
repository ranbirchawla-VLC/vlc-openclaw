# Phase 5: Dial color audit (the gated investigation)

## Parse rule

1. Require literal `dial` in the Auction descriptor (case-insensitive)
   as an anchor. No anchor → `unparseable`.
2. Scan for base-color vocabulary within a 4-word window
   preceding `dial`.
3. Scan for compound dial names anywhere in the descriptor
   (31 known names).
4. Classification:
   - `clean`: exactly one base color, no compound qualifier
   - `ambiguous`: compound hit, multiple base colors, or base color
     plus compound qualifier
   - `unparseable`: no anchor, or anchor with no color vocabulary

Base color vocabulary: ['black', 'white', 'silver', 'blue', 'green', 'red', 'yellow', 'pink', 'purple', 'orange', 'brown', 'grey', 'gray', 'gold', 'champagne', 'cream', 'ivory', 'tan', 'slate', 'teal', 'turquoise', 'rhodium', 'anthracite', 'salmon', 'copper', 'bronze']
Compound names: ['mother of pearl', 'mother-of-pearl', 'mop', 'skeleton', 'skeletonized', 'wimbledon', 'tiffany', 'stella', 'tapestry', 'meteorite', 'aventurine', 'malachite', 'lapis', 'onyx', 'jade', 'opal', 'panda', 'reverse panda', 'tropical', 'linen', 'waffle', 'pave', 'pavé', 'gem-set', 'diamond pave', 'diamond dial', 'sunburst', 'sunray', 'celebration', 'palm', 'chromalight']

## Headline parse-rate

| Bucket | Count | Pct |
|---|---|---|
| Clean unambiguous color | 17657 | 91.32% |
| Ambiguous | 1286 | 6.65% |
| Unparseable | 392 | 2.03% |
| **Total** | **19335** | |

### Route decision against pre-locked thresholds

**Headline clean parse-rate: 91.32%**
**Route: ≥90% → color joins as fourth keying axis (4-axis schema)**

## Parse rate stratified by reference family

| Family | Total | Clean | Ambiguous | Unparseable | Clean pct |
|---|---|---|---|---|---|
| other | 12243 | 11332 | 693 | 218 | 92.56% |
| sport_rolex | 3506 | 3406 | 87 | 13 | 97.15% |
| datejust | 1540 | 1203 | 304 | 33 | 78.12% |
| tudor_sport | 1401 | 1233 | 158 | 10 | 88.01% |
| oyster_perpetual | 645 | 483 | 44 | 118 | 74.88% |

## Compound cases enumerated

| Compound name | Row count |
|---|---|
| `skeleton` | 396 |
| `wimbledon` | 201 |
| `panda` | 173 |
| `mother of pearl` | 160 |
| `meteorite` | 27 |
| `tiffany` | 26 |
| `aventurine` | 23 |
| `reverse panda` | 20 |
| `tapestry` | 17 |
| `pavé` | 15 |
| `linen` | 15 |
| `celebration` | 13 |
| `tropical` | 13 |
| `palm` | 10 |
| `mother-of-pearl` | 6 |
| `diamond dial` | 5 |
| `waffle` | 2 |
| `lapis` | 1 |
| `onyx` | 1 |
| `sunray` | 1 |

## Base-color distribution among clean rows

| Color | Count |
|---|---|
| black | 7106 |
| blue | 3891 |
| silver | 1911 |
| white | 1767 |
| green | 815 |
| grey | 618 |
| champagne | 406 |
| brown | 233 |
| red | 158 |
| pink | 129 |
| turquoise | 128 |
| slate | 86 |
| rhodium | 78 |
| ivory | 70 |
| salmon | 56 |
| yellow | 50 |
| orange | 36 |
| purple | 30 |
| cream | 27 |
| bronze | 21 |
| anthracite | 16 |
| gold | 14 |
| copper | 11 |

## Samples of unparseable rows (first 15)

- `Omega` `310.30.40.50.06.001`: `2025 Omega Speedmaster Anniversary Series "The First Omega In Space" 39.7MM Blue/Grey Dial Steel Bracelet (310.30.40.50.06.001)`
- `Tudor` `7939A1A0RU`: `No Reserve - 2026 Tudor Black Bay 58' 39MM Burgundy Dial Steel Bracelet (7939A1A0RU)`
- `Panerai` `PAM01075`: `2020 Panerai Luminor 1950 Left-Handed 3 Days 47MM Beige Dial Leather Strap (PAM01075)`
- `Tudor` `7939A1A0RU`: `No Reserve - 2025 Tudor Black Bay 58' 39MM Burgundy Dial Rubber Strap (7939A1A0RU)`
- `IWC Schaffhausen` `IW377903`: `2024 IWC Schaffhausen Pilot "AMG Edition" 43MM Carbon Fiber Dial Leather Strap (IW377903)`
- `Tudor` `7939A1A0RU`: `No Reserve - 2026 Tudor Black Bay 58' 39MM Burgundy Dial Steel Bracelet (7939A1A0RU)`
- `Hublot` `301.CI.1770.RX`: `2010 Hublot Big Bang "Black Magic" 44MM Carbon Fiber Dial Rubber Strap (301.CI.1770.RX)`
- `Rolex` `134300.0`: `No Reserve - 2026 Rolex Oyster Perpetual 41MM Beige Dial Oyster Bracelet (134300)`
- `IWC Schaffhausen` `IW377903`: `2023 IWC Schaffhausen Pilot "AMG Edition" 43MM Carbon Fiber Dial Leather Strap (IW377903)`
- `Omega` `220.10.38.20.09.001`: `2024 Omega Seamaster Aqua Terra 150M 38MM Sandstone Dial Steel Bracelet (220.10.38.20.09.001)`
- `Bvlgari` `102713.0`: `2022 Bvlgari Octo Finissimo 40MM Titanium Dial Titanium Bracelet (102713)`
- `Rolex` `126000.0`: `2025 Rolex Oyster Perpetual 36MM Beige Dial Oyster Bracelet (126000)`
- `Gevril` `48962B`: `Gevril West Village "Stone Dial" L.E. 40MM Carbon Dial Steel Bracelet (48979B)`
- `Rolex` `134300.0`: `2025 Rolex Oyster Perpetual 41MM Lavender Dial Oyster Bracelet (134300)`
- `Breitling` `E10379`: `No Reserve - 2026 Breitling Superocean Super Diver 46MM Camo Dial Rubber Strap (E10379351B1S1)`

## Samples of ambiguous rows (first 15)

- `Rolex` `126334.0`: note=`base color plus compound qualifier`, compounds=`wimbledon`, color=`slate`
    desc: `2026 Rolex Datejust "Wimbledon" 41MM Slate Dial Jubilee Bracelet (126334)`
- `Hublot` `311.SX.2010.GR.GAP10`: note=`compound name only; no base color`, compounds=`skeleton`, color=`None`
    desc: `2011 Hublot Big Bang "Aero Bang Garmisch" L.E. 44MM Skeleton Dial Leather Strap (311.SX.2010.GR.GAP10)`
- `Rolex` `126300.0`: note=`base color plus compound qualifier`, compounds=`wimbledon`, color=`slate`
    desc: `2022 Rolex Datejust "Wimbledon" 41MM Slate Dial Oyster Bracelet (126300)`
- `Rolex` `126234.0`: note=`base color plus compound qualifier`, compounds=`wimbledon`, color=`slate`
    desc: `2022 Rolex Datejust "Wimbledon" 36MM Slate Dial Jubilee Bracelet (126234)`
- `Rolex` `126300.0`: note=`compound name only; no base color`, compounds=`pavé`, color=`None`
    desc: `No Reserve - 2023 Rolex Datejust 41MM Aftermarket Diamond Pavé Dial Aftermarket Diamonds Jubilee Bracelet (126300)`
- `Rolex` `126500LN`: note=`base color plus compound qualifier`, compounds=`panda`, color=`white`
    desc: `2025 Rolex Cosmograph Daytona "Panda" 40MM White Dial Oyster Bracelet (126500LN)`
- `Tag Heuer` `WAR1315.BA0778`: note=`compound name only; no base color`, compounds=`mother of pearl`, color=`None`
    desc: `2015 Tag Heuer Carrera 32MM Quartz Mother Of Pearl Dial Steel Bracelet (WAR1315.BA0778)`
- `Girard Perregaux` `84000-21-3236-5CX`: note=`compound name only; no base color`, compounds=`skeleton`, color=`None`
    desc: `2024 Girard Perregaux Bridges "Neo Bridges Aston Martin" L.E. 45MM Skeleton Dial Textile Strap (84000-21-3236-5CX)`
- `Omega` `3511.5`: note=`base color plus compound qualifier`, compounds=`reverse panda`, color=`black`
    desc: `No Reserve - 1990 Omega Speedmaster "Reverse Panda" 39MM Black Dial Steel Bracelet (3511.50)`
- `Tag Heuer` `CR5090.FN6001`: note=`compound name only; no base color`, compounds=`skeleton`, color=`None`
    desc: `Tag Heuer Monza Flyback Chronometer S. E. 42MM Skeleton Dial Textile Strap (CR5090.FN6001)`
- `Rolex` `126300.0`: note=`base color plus compound qualifier`, compounds=`wimbledon`, color=`slate`
    desc: `No Reserve - 2020 Rolex Datejust "Wimbledon" 41MM Slate Dial Oyster Bracelet (126300)`
- `Hublot` `647.NX.1137.RX`: note=`compound name only; no base color`, compounds=`skeleton`, color=`None`
    desc: `No Reserve - 2018 Hublot Spirit of Big Bang Moonphase 42MM Skeleton Dial Rubber Strap (647.NX.1137.RX)`
- `Frederique Constant` `FC-200MPDC14B`: note=`compound name only; no base color`, compounds=`mother of pearl`, color=`None`
    desc: `2025 Frederique Constant Classics Carrée 23MM Quartz Mother Of Pearl Dial Steel Bracelet (FC-200MPDC14B)`
- `Tudor` `79660.0`: note=`multiple base colors`, compounds=``, color=`black`
    desc: `No Reserve - 2026 Tudor Black Bay 39MM Blue Dial Steel Bracelet (79660)`
- `Hublot` `614.CI.1170.RX`: note=`base color plus compound qualifier`, compounds=`skeleton`, color=`black`
    desc: `2025 Hublot Spirit Of Big Bang Meca-10 Black Magic 45MM Skeleton Dial Rubber Strap (614.CI.1170.RX)`
