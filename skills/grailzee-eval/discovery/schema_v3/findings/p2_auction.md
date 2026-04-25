# Phase 2: Auction type parsing

## W1

- Total rows: 9440
- NR rows (prefix `No Reserve - ` at start): 1912 (20.25%)
- RES (non-NR) rows: 7528
- Blank auction descriptor: 0
- Rows with `No Reserve` appearing mid-string (ambiguous): 0

Sample NR descriptors:
- `No Reserve - 2024 Rolex Submariner No-Date 41MM Black Dial Oyster Bracelet (124060)`
- `No Reserve - Seiko Prospex "Save the Ocean" S.E. 42MM Blue Dial Steel Bracelet (SRPG57)`
- `No Reserve - Breitling Navitimer 46MM Green Dial Leather Strap (AB0137)`
- `No Reserve - Rolex Datejust 36MM Champagne Dial Aftermarket Two-Tone Gold-Plated Jubilee Bracelet (16013)`
- `No Reserve - 2022 Tudor Black Bay Pro 39MM Black Dial Steel Bracelet (79470)`
- `No Reserve - 2026 Rolex Datejust 41MM White Dial Oyster Bracelet (126300)`

Sample RES descriptors:
- `2010 Jaeger-LeCoultre Master Compressor Extreme World Chronograph 46.3MM Black Dial Rubber Strap (Q1768470)`
- `2026 Omega Speedmaster Professional Moonwatch 42MM White Dial Rubber Strap (310.32.42.50.04.001)`
- `2025 Omega Speedmaster Anniversary Series "The First Omega In Space" 39.7MM Blue/Grey Dial Steel Bracelet (310.30.40.50.06.001)`
- `2025 Breitling Endurance Pro 44MM Quartz Black Dial Rubber Strap (X82310)`
- `2019 Omega Seamaster Aqua Terra 150M GMT 43MM Black Dial Leather Strap (231.13.43.22.01.001)`
- `2026 Rolex Explorer II "Polar" 42MM White Dial Oyster Bracelet (226570)`

## W2

- Total rows: 9895
- NR rows (prefix `No Reserve - ` at start): 2169 (21.92%)
- RES (non-NR) rows: 7726
- Blank auction descriptor: 0
- Rows with `No Reserve` appearing mid-string (ambiguous): 0

Sample NR descriptors:
- `No Reserve - Tag Heuer Monaco Calibre 12 39MM Black Dial Leather Strap (CAW2114)`
- `No Reserve - 2013 Rolex Datejust II 41MM White Dial Oyster Bracelet (116334)`
- `No Reserve - Cartier Santos 100 41.3MM White Dial Leather Strap (W20073X8)`
- `No Reserve - Hublot Big Bang King "All Black" L. E. 48MM Black Dial Rubber Strap (322.CM.1110.RX)`
- `No Reserve - Breitling Chronomat 39MM Blue Dial Leather Strap (D13047)`
- `No Reserve - Cartier Tank 25.5MM Quartz Silver Dial Leather Strap (3515)`

Sample RES descriptors:
- `Omega Seamaster Planet Ocean 600M 42MM Black Dial Steel Bracelet (232.30.42.21.01.003)`
- `Rolex Submariner Date "Bluesy" 41MM Blue Dial Two-Tone Oyster Bracelet (126613LB)`
- `2026 Rolex GMT-Master II "Batgirl" 40MM Black Dial Jubilee Bracelet (126710BLNR)`
- `Omega Seamaster Diver 300M 41MM Blue Dial Steel Bracelet (212.30.41.20.03.001)`
- `2023 Omega Seamaster Aqua Terra Worldtimer 43MM Grey Dial Rubber Strap (220.92.43.22.99.001)`
- `2025 Cartier Santos De Cartier 34.5MM Quartz Silver Dial Two-Tone Bracelet (W2SA0033)`

## Cross-check against `Sales Auction Type` aggregate sheet

### W1

-  |  |  | 
-  |  |  | 
- Month | Auction Type | % of sales per auction type | 
- 2026-03-01 00:00:00 | Classic / Reserve / Standard 4 to 7 Day Auction | 0.418 | 
- 2026-03-01 00:00:00 | Classic / No Reserve / Standard 4 to 7 Day Auction | 0.245 | 
- 2026-03-01 00:00:00 | Classic / Reserve / 24 Hour Flash Auction | 0.14 | 
- 2026-03-01 00:00:00 | Premium / Reserve / Standard 4 to 7 Day Auction | 0.099 | 
- 2026-03-01 00:00:00 | Premium / No Reserve / Standard 4 to 7 Day Auction | 0.0648 | 
- 2026-03-01 00:00:00 | Classic / No Reserve / 24 Hour Flash Auction | 0.0277 | 
- 2026-03-01 00:00:00 | Premium / Reserve / 24 Hour Flash Auction | 0.0024 | 
- 2026-03-01 00:00:00 | Premium / No Reserve / 24 Hour Flash Auction | 0.0018 | 
-  |  |  | 
-  |  |  | 
- Month | Auction Type | % of sales per auction type | 
- 2026-02-01 00:00:00 | Classic / Reserve / Standard 4 to 7 Day Auction | 0.47 | 
- 2026-02-01 00:00:00 | Classic / No Reserve / Standard 4 to 7 Day Auction | 0.215 | 
- 2026-02-01 00:00:00 | Classic / Reserve / 24 Hour Flash Auction | 0.135 | 
- 2026-02-01 00:00:00 | Premium / Reserve / Standard 4 to 7 Day Auction | 0.111 | 
- 2026-02-01 00:00:00 | Premium / No Reserve / Standard 4 to 7 Day Auction | 0.0397 | 
- 2026-02-01 00:00:00 | Classic / No Reserve / 24 Hour Flash Auction | 0.0241 | 

### W2

-  |  |  | 
- Month | Auction Type | % of sales per auction type | 
- 2026-04-01 00:00:00 | Classic / Reserve / Standard 4 to 7 Day Auction | 0.422 | 
- 2026-04-01 00:00:00 | Classic / No Reserve / Standard 4 to 7 Day Auction | 0.287 | 
- 2026-04-01 00:00:00 | Classic / Reserve / 24 Hour Flash Auction | 0.14 | 
- 2026-04-01 00:00:00 | Premium / Reserve / Standard 4 to 7 Day Auction | 0.0861 | 
- 2026-04-01 00:00:00 | Premium / No Reserve / Standard 4 to 7 Day Auction | 0.0426 | 
- 2026-04-01 00:00:00 | Classic / No Reserve / 24 Hour Flash Auction | 0.0218 | 
- 2026-04-01 00:00:00 | Premium / Reserve / 24 Hour Flash Auction | 0.0009 | 
-  |  |  | 
-  |  |  | 
- Month | Auction Type | % of sales per auction type | 
- 2026-03-01 00:00:00 | Classic / Reserve / Standard 4 to 7 Day Auction | 0.418 | 
- 2026-03-01 00:00:00 | Classic / No Reserve / Standard 4 to 7 Day Auction | 0.245 | 
- 2026-03-01 00:00:00 | Classic / Reserve / 24 Hour Flash Auction | 0.14 | 
- 2026-03-01 00:00:00 | Premium / Reserve / Standard 4 to 7 Day Auction | 0.099 | 
- 2026-03-01 00:00:00 | Premium / No Reserve / Standard 4 to 7 Day Auction | 0.0648 | 
- 2026-03-01 00:00:00 | Classic / No Reserve / 24 Hour Flash Auction | 0.0277 | 
- 2026-03-01 00:00:00 | Premium / Reserve / 24 Hour Flash Auction | 0.0024 | 
- 2026-03-01 00:00:00 | Premium / No Reserve / 24 Hour Flash Auction | 0.0018 | 

## Combined W1+W2

- Total rows: 19335
- NR rows: 3972 (20.54%)
- NR target per discovery doc: ~22%
