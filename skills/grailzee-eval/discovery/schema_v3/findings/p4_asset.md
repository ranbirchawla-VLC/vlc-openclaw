# Phase 4: Asset class detection

Pattern: `\d+(\.\d+)?\s*x\s*\d+(\.\d+)?(\s*x\s*\d+(\.\d+)?)?\s*IN\b` (case-insensitive)

Applied to `Auction` descriptor field.

## W1

Total rows: 9440
Inch-pattern matches: 0


Brand distribution of matches:

## W2

Total rows: 9895
Inch-pattern matches: 3

| Reference | Make | Auction descriptor (trunc 140) |
|---|---|---|
| `On My Side MM M53826` | `Louis Vuitton` | `2011 Louis Vuitton On My Side 9.6 x 12 x 5.5IN Leather Gold-Color Hardware Leather Strap (On My Side MM M53826)` |
| `Pochette Liv` | `Louis Vuitton` | `Louis Vuitton Liv Pochette 5.3 x 9.6IN Damier Azur Coated Canvas Steel Hardware Leather Strap (Pochette Liv)` |
| `M28351` | `Louis Vuitton` | `2025 Louis Vuitton Neverfull Reversible 11 x 18IN Leather/Textile Steel Hardware Leather Strap (M28351)` |

Brand distribution of matches:
- Louis Vuitton: 3

## False-positive check

Any matched row whose `Make` is a watch brand (not Louis Vuitton,
Hermes, Chanel, Gucci, etc.) flags as a false positive.

### W1
False positives: 0

### W2
False positives: 0

## False-negative check

Any row whose `Make` is in the handbag-brand set but whose `Auction`
descriptor does not match the inch pattern.

### W1
False negatives: 20
- `Dior` `3025.0`: `No Reserve - Dior Vintage 21MM Quartz Blue Dial Steel Bracelet (3025)`
- `Hermès` `SP1.747C`: `No Reserve - 2025 Hermès H08 39MM Green Dial Rubber Strap (SP1.747C)`
- `Dior` `D78-109`: `No Reserve - Dior Malice 19MM Quartz Mother of Pearl Dial Aftermarket Leather Strap (D78-109)`
- `Chanel` `H2009`: `Chanel J12 41MM White Dial Ceramic Bracelet (H2009)`
- `Dior` `3025.0`: `No Reserve - Dior Christal Vintage 22MM Quartz Champagne Dial Two-Tone Gold-Plated Bracelet (3025)`
- `Dior` `D44-120`: `No Reserve - Dior Bagheera 24MM Quartz White Dial Steel Bracelet (D44-120)`
- `Hermès` `AR7Q.810`: `2024 Hermès Arceau 40MM Quartz White Dial Leather Strap (AR7Q.810)`
- `Hermès` `W049430WW00`: `2024 Hermès H08 39MM Grey Dial Rubber Strap (W049430WW00)`
- `Dior` `D48-203`: `No Reserve - 1996 Dior Vintage Swing Octagon 25MM Quartz Champagne Dial Gold-Plated Bracelet (D48-203)`
- `Hermès` `W056950WW00`: `No Reserve - 2025 Hermès H08 39MM Blue Dial Rubber Strap (W056950WW00)`
- `Hermès` `W049433WW`: `2022 Hermès H08 Graphene 39MM Black Dial Rubber Strap (W049433WW)`
- `Hermès` `SP1.746C`: `Hermès H08 39MM Grey Dial Rubber Strap (SP1.746C)`
- `Hermès` `AR3.220`: `No Reserve - Hermès Arceau 25MM Quartz Champagne Dial Two-Tone Bracelet (AR3.220)`
- `Hermès` `CL5.210`: `No Reserve - Hermès Clipper Diver 28MM Quartz Blue Dial Steel Bracelet (CL5.210)`
- `Hermès` `SP1.747C`: `2024 Hermès H08 38.5MM Green Dial Rubber Strap (SP1.747C)`

### W2
False negatives: 22
- `Hermès` `SP1.746A`: `2025 Hermès H08 42MM Grey Dial Rubber Strap (SP1.746A)`
- `Hermès` `W049433WW00`: `2025 Hermès H08 39MM Black Dial Rubber Strap (W049433WW00)`
- `Dior` `3025.0`: `No Reserve - Dior Vintage 21MM Quartz Blue Dial Steel Bracelet (3025)`
- `Hermès` `SP1.747C`: `No Reserve - 2025 Hermès H08 39MM Green Dial Rubber Strap (SP1.747C)`
- `Dior` `D78-109`: `No Reserve - Dior Malice 19MM Quartz Mother of Pearl Dial Aftermarket Leather Strap (D78-109)`
- `Chanel` `H2009`: `Chanel J12 41MM White Dial Ceramic Bracelet (H2009)`
- `Dior` `3025.0`: `No Reserve - Dior Christal Vintage 22MM Quartz Champagne Dial Two-Tone Gold-Plated Bracelet (3025)`
- `Dior` `D44-120`: `No Reserve - Dior Bagheera 24MM Quartz White Dial Steel Bracelet (D44-120)`
- `Hermès` `AR7Q.810`: `2024 Hermès Arceau 40MM Quartz White Dial Leather Strap (AR7Q.810)`
- `Hermès` `W049430WW00`: `2024 Hermès H08 39MM Grey Dial Rubber Strap (W049430WW00)`
- `Dior` `D48-203`: `No Reserve - 1996 Dior Vintage Swing Octagon 25MM Quartz Champagne Dial Gold-Plated Bracelet (D48-203)`
- `Hermès` `W056950WW00`: `No Reserve - 2025 Hermès H08 39MM Blue Dial Rubber Strap (W056950WW00)`
- `Hermès` `W049433WW`: `2022 Hermès H08 Graphene 39MM Black Dial Rubber Strap (W049433WW)`
- `Hermès` `SP1.746C`: `Hermès H08 39MM Grey Dial Rubber Strap (SP1.746C)`
- `Hermès` `AR3.220`: `No Reserve - Hermès Arceau 25MM Quartz Champagne Dial Two-Tone Bracelet (AR3.220)`

## Filter behavior

Phase 2 implementation: at ingest, set `asset_class = "handbag"`
for rows matching the inch pattern, else `asset_class = "watch"`.
Scoring pipeline filters on `asset_class == "watch"`. Handbag rows
remain in the report store but are excluded from analyzer scoring,
bucket construction, confidence calculations, and premium math.