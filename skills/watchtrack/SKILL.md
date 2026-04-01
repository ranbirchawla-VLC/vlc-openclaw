---
name: watchtrack
description: >
  Interact with the WatchTrack inventory management system via Claude in Chrome
  browser automation. Two capabilities: (1) Item Details: given a SKU and working
  folder, navigate to WatchTrack, search for the item, extract all item data
  (pricing, condition, specs, notes), and write a watchtrack.json file to the
  working folder. (2) Change Substatus: given a SKU and desired sub-status value,
  navigate to WatchTrack, find the item, open the sub-status edit modal, select
  the new value, and save. Use this skill whenever the user or an orchestrator
  (OpenClaw) says "look up item", "get item details", "pull from WatchTrack",
  "check WatchTrack", "update substatus", "change substatus", "set substatus",
  "mark as listed", "mark as sold", or references a SKU in the context of
  WatchTrack data retrieval or status updates. Also trigger when another skill
  (watch-listing, vardalux-pipeline) needs WatchTrack data as an input step.
---

# WatchTrack Browser Automation — Vardalux Collections

## Purpose

Provide reliable, repeatable browser automation for WatchTrack inventory lookups
and status updates. This skill is a standalone data access layer. It does not
know about listings, pricing, Grailzee, or platform templates. Other skills and
orchestrators call it when they need WatchTrack data or need to update an item's
workflow status.

Two capabilities in V1:

1. **Item Details** — Search by SKU, extract all item fields + expanded specs,
   write `watchtrack.json`
2. **Change Substatus** — Search by SKU, open the edit modal, set a new
   sub-status value

---

## Prerequisites

This skill requires **Claude in Chrome** browser automation tools. Before any
WatchTrack interaction:

1. Call `tabs_context_mcp` to verify Chrome connection exists
2. If no connection → return: `"Cannot access WatchTrack: No Chrome browser
   connected. Connect Claude in Chrome and ensure WatchTrack is logged in."`
3. Do NOT attempt to log in, create accounts, or enter credentials

The skill assumes the connected Chrome browser has an active, authenticated
WatchTrack session (cookies in place). If navigation lands on a login page
instead of the dashboard, halt and return the access error.

---

## Configuration

Read `references/watchtrack-config.json` before executing either capability.
This file contains:

- `inventory_url` — The URL to navigate to for inventory search
- `substatus_options` — Valid sub-status values for validation
- `auth_check` — Text indicators for authenticated vs. login states
- `item_detail_fields` — Base fields visible on the item detail page
- `expanded_spec_fields` — Additional spec fields revealed by "Show more details"
- `pricing_fields` — Pricing fields in the left panel
- `dom_notes` — Angular DOM patterns for reliable element location

---

## Data Extraction Method

**Primary method: Coordinate-based extraction.** WatchTrack is an Angular app
where labels and values share deeply nested containers. Standard DOM traversal
(parent/sibling walking) returns contaminated strings because the shared
ancestor contains all field texts.

The reliable extraction method is:

1. Find each label element (leaf node with exact text match)
2. Get its bounding rectangle via `getBoundingClientRect()`
3. Find the value element on the same Y position (within 8px), to the right
   of the label (left > label.left + 50), that is a leaf node with text
   content under 200 characters
4. Take the closest match (smallest left coordinate) to avoid picking up
   values from adjacent rows

This approach was validated in live testing (March 2026) and extracts all
fields cleanly on the first pass.

```javascript
// PROVEN EXTRACTION PATTERN — use this for all field extraction
function extractFields(labelNames) {
  const result = {};
  const allEls = [...document.querySelectorAll('*')];

  for (const label of labelNames) {
    const labelEl = allEls.find(el =>
      el.textContent.trim() === label &&
      el.children.length === 0
    );

    if (labelEl) {
      const labelRect = labelEl.getBoundingClientRect();
      let bestValue = null;
      let bestLeft = Infinity;

      for (const el of allEls) {
        if (el === labelEl) continue;
        if (el.children.length > 0) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        if (Math.abs(rect.top - labelRect.top) < 8) {
          if (rect.left > labelRect.left + 50) {
            const text = el.textContent.trim();
            if (text && !labelNames.includes(text) && text.length < 200) {
              if (rect.left < bestLeft) {
                bestLeft = rect.left;
                bestValue = text;
              }
            }
          }
        }
      }
      result[label] = bestValue || null;
    }
  }
  return result;
}
```

**Fallback method:** If coordinate extraction fails (e.g., WatchTrack UI
redesign changes layout), use `get_page_text` to extract all visible text
and parse label-value pairs from the flat text output.

---

## Capability 1: Item Details

### Inputs

| Input | Source | Required |
|-------|--------|----------|
| `sku` | Provided by caller (user or orchestrator) | Yes |
| `working_folder` | Provided by caller — absolute path where `watchtrack.json` will be written | Yes |

### Execution Steps

#### Step 1: Connect and Navigate

```
1. Call tabs_context_mcp (createIfEmpty: true)
2. Navigate to the inventory URL from config
3. Wait 2 seconds for page load
4. Take a screenshot
5. AUTH CHECK: Look for the page title "Inventory" or the search bar.
   If the page shows a login form or redirect, HALT:
   → Return: "Cannot access WatchTrack: Browser session is not authenticated.
     Please log into WatchTrack in Chrome and try again."
```

#### Step 2: Search for SKU

```
1. Find the inventory search bar
   → Use find tool: "search bar on inventory page"
   → Fallback: look for textbox with placeholder containing
     "Search by brand, reference number, serial number, stock ID"
   IMPORTANT: Use the INVENTORY PAGE search bar (ref with long placeholder),
   NOT the global search bar at the top of every page. The global search
   routes to Transactions, not Inventory.
2. Triple-click the search bar to select any existing text, then type the SKU
3. Press Enter (key: "Return")
4. Wait 2 seconds for results to filter
5. Take a screenshot to verify results
```

#### Step 3: Validate Results

```
1. Use get_page_text to extract page content
2. Look for "Viewing X-X of X result" text at the bottom
3. VALIDATE:
   - If "0 results" → HALT: Return "No item found for SKU: {sku}"
   - If more than 1 result → HALT: Return "Ambiguous: {count} items
     found for SKU: {sku}. Provide a more specific identifier."
   - If exactly 1 result → proceed
```

#### Step 4: Open Item Detail Page

```
1. Find the item card link on the results page
   → Use find tool: "item card link"
   → The link has href pattern /store/item/{uuid}
2. Click the item card
3. Wait 2 seconds for the detail page to load
4. Take a screenshot to confirm "Item details" header is visible
```

#### Step 5: Extract Title

The item title (e.g., "Hublot Classic Fusion") appears as a leaf text node
in the banner area of the detail page. It is NOT in a reliably classed
element, so use a text-matching approach:

```javascript
// Find the title by locating the prominent text in the banner area
// It appears between ~y180 and ~y260, centered on the page
const allEls = [...document.querySelectorAll('*')];
let title = null;
for (const el of allEls) {
  if (el.children.length > 0) continue;
  const rect = el.getBoundingClientRect();
  // Banner area: top 180-260px, centered, large text
  if (rect.top > 350 && rect.top < 500 && rect.left > 500 && rect.width > 200) {
    const text = el.textContent.trim();
    // Title is typically "Brand Model" format, 2+ words, no special chars
    if (text.length > 5 && text.length < 100 && !text.includes('$')
        && !text.includes('#') && text.split(' ').length >= 2) {
      title = text;
      break;
    }
  }
}
```

Parse `brand` as the first word and `model` as the remainder.
Example: "Hublot Classic Fusion" → brand: "Hublot", model: "Classic Fusion"

**Note:** The banner Y coordinates may shift depending on whether alerts or
banners (e.g., "Consignment in progress") are displayed above it. If the
title is not found in the expected range, widen the Y search to 150–500.

#### Step 6: Extract Base Fields

Run the coordinate-based extraction function (see Data Extraction Method
above) with the base field labels:

```
Stock ID, Serial Number, Reference Number, Sub-Status, List in Elite,
Sale Channel, Owner, Condition, Included Items, Month, Year, Dial Color,
Bracelet Type, Case Diameter
```

#### Step 7: Extract Pricing

Run the same coordinate-based extraction on the pricing panel (left side),
looking specifically for values that start with "$":

```javascript
const priceLabels = ['Retail Price', 'Wholesale Price', 'Consignment Payout'];
for (const label of priceLabels) {
  const labelEl = allEls.find(el =>
    el.textContent.trim() === label && el.children.length === 0
  );
  if (labelEl) {
    const labelRect = labelEl.getBoundingClientRect();
    for (const el of allEls) {
      if (el === labelEl || el.children.length > 0) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0) continue;
      if (Math.abs(rect.top - labelRect.top) < 8
          && rect.left > labelRect.left + 50) {
        const text = el.textContent.trim();
        if (text.startsWith('$')) {
          result[label] = text;
          break;
        }
      }
    }
  }
}
```

#### Step 8: Expand and Extract Specs

```
1. Find "Show more details" link on the page
   → Use find tool: "Show more details"
2. Click it
3. Wait 1 second for expanded fields to render
4. Run coordinate-based extraction on the expanded spec labels:

   Movement, Caliber, Base Caliber, Frequency, Power Reserve,
   Number of Jewels, Case Material, Bezel Material, Bezel Type,
   Thickness, Crystal, Water Resistance, Dial Numerals,
   Bracelet Material, Bracelet Color, Clasp Type, Clasp Material

5. If "Show more details" is not found, skip this step (not all items
   have expanded details). Set all spec fields to null.
```

#### Step 9: Extract Item Notes

```
1. Find the "Item notes" section heading
2. Check the content immediately below it
3. If the text is "No item notes" → store as null
4. Otherwise → store the notes text as-is
```

#### Step 10: Write watchtrack.json

Assemble all extracted data and write to `{working_folder}/watchtrack.json`:

```json
{
  "sku": "9971Z",
  "extracted_at": "2026-03-31T22:35:00Z",
  "source_url": "https://watchtrack.com/store/item/{uuid}",
  "item": {
    "stock_id": "9971Z",
    "brand": "Hublot",
    "model": "Classic Fusion",
    "serial": null,
    "reference": "525.NX.0170.LR.1104",
    "sub_status": "Ready for listing",
    "list_in_elite": null,
    "sale_channel": "Retail Listings, Social Push",
    "owner": "Todd Erdmann",
    "condition": "Pre-owned",
    "included": "Watch with original box",
    "month": null,
    "year": null,
    "dial_color": "Transparent",
    "bracelet_type": null,
    "case_diameter": "45mm"
  },
  "pricing": {
    "retail_price": 6750.00,
    "wholesale_price": 5500.00,
    "item_cost": 6480.00
  },
  "specs": {
    "movement": "Automatic",
    "caliber": null,
    "base_caliber": null,
    "frequency": null,
    "power_reserve": "42",
    "number_of_jewels": null,
    "case_material": "Titanium",
    "bezel_material": "Titanium",
    "bezel_type": null,
    "thickness": null,
    "crystal": null,
    "water_resistance": "Up to 50m",
    "dial_numerals": null,
    "bracelet_material": "Crocodile Skin",
    "bracelet_color": null,
    "clasp_type": null,
    "clasp_material": "Steel"
  },
  "item_notes": null
}
```

**Field normalization rules:**
- "N/A" string values → store as `null`
- "Serial N/A" → store serial as `null`
- "No item notes" → store item_notes as `null`
- Price strings like "$6,750.00" → strip "$" and commas, store as number: `6750.00`
- Brand and model parsed from page title: first word = brand, remainder = model
- Spec values that are purely numeric (e.g., "42" for power reserve) → store
  as string, not number (units vary and are sometimes included)

#### Step 11: Confirm

Return a summary to the caller:

```
WatchTrack data extracted for SKU {sku}:
  Brand: {brand}
  Model: {model}
  Reference: {reference}
  Condition: {condition}
  Retail: ${retail_price}
  Wholesale: ${wholesale_price}
  Item Cost: ${item_cost}
  Sub-Status: {sub_status}
  Case: {case_diameter} {case_material}
  Movement: {movement}
  File: {working_folder}/watchtrack.json
```

---

## Capability 2: Change Substatus

### Inputs

| Input | Source | Required |
|-------|--------|----------|
| `sku` | Provided by caller | Yes |
| `new_substatus` | Desired sub-status value | Yes |

### Input Validation

Before navigating, validate `new_substatus` against the allowed values
in `references/watchtrack-config.json`:

```
Valid values: Intake, Needs Service, Needs Photos, Needs Video,
Listing Prep, Ready for listing, On Chrono24, Grailzee First,
Fully Listed, Sold
```

If the provided value does not match any option (case-insensitive),
HALT and return:

```
Invalid sub-status: "{new_substatus}"
Valid options: Intake, Needs Service, Needs Photos, Needs Video,
Listing Prep, Ready for listing, On Chrono24, Grailzee First,
Fully Listed, Sold
```

### Execution Steps

#### Steps 1–4: Same as Item Details

Navigate to inventory, search for SKU, validate single result, open
item detail page. Follow Steps 1–4 from Capability 1 exactly.

#### Step 5: Read Current Substatus

```
1. Use the coordinate-based extraction to read the current Sub-Status value
2. If current value already matches new_substatus:
   → Return: "Sub-status for SKU {sku} is already set to
     '{new_substatus}'. No change needed."
   → Do NOT open the edit modal
```

#### Step 6: Open Sub-Status Edit Modal

The Sub-Status field has a pencil icon (`<img>` element) next to its
value. This icon is NOT accessible via standard accessibility tree tools
(find, read_page). It requires JavaScript to locate and click.

```javascript
// Find the Sub-Status label, then locate the pencil <img> on the same row
const allEls = [...document.querySelectorAll('*')];
const subStatusLabel = allEls.find(el =>
  el.textContent.trim() === 'Sub-Status' && el.children.length === 0
);

if (subStatusLabel) {
  const labelRect = subStatusLabel.getBoundingClientRect();
  const allImgs = document.querySelectorAll('img');

  for (const img of allImgs) {
    const imgRect = img.getBoundingClientRect();
    // Pencil is on the same row (within 15px vertically),
    // to the right, and small (< 20px wide)
    if (Math.abs(imgRect.top - labelRect.top) < 15
        && imgRect.left > labelRect.left + 100
        && imgRect.width > 0
        && imgRect.width < 20) {
      img.click();
      break;
    }
  }
}
```

After clicking, wait 1 second, then take a screenshot to confirm the
"Edit custom field" modal has appeared.

**If modal does not appear:** HALT and return:
```
"Could not open Sub-Status editor for SKU {sku}. The edit control
may have changed. Manual update required."
```

#### Step 7: Select New Value

```
1. Find the dropdown in the modal
   → Use find tool: "Sub-Status dropdown in modal"
   → Or find textbox with placeholder "Select an option"
2. Click the dropdown to open the options list
3. Wait 1 second for the list to render
4. Find and click the option matching new_substatus:
```

```javascript
// Find and click the matching dropdown option
// Options are leaf elements in the dropdown area (y > 800 in viewport)
const allEls = [...document.querySelectorAll('*')];
for (const el of allEls) {
  if (el.children.length > 0) continue;
  const rect = el.getBoundingClientRect();
  if (el.textContent.trim() === '{new_substatus}'
      && rect.width > 50
      && rect.top > 800) {
    el.click();
    break;
  }
}
```

**Note:** The dropdown scrolls. If the desired option is not visible in
the first pass (e.g., "Sold" is at the bottom), scroll within the
dropdown area before searching for the option element.

#### Step 8: Save Changes

```
1. Find the "Save changes" button in the modal
   → Use find tool: "Save changes button"
2. Click the button
3. Wait 2 seconds for the save to complete and modal to close
4. Take a screenshot to verify the modal has closed
```

#### Step 9: Verify and Confirm

```
1. Use the coordinate-based extraction to read the current Sub-Status
   value on the item detail page
2. If the value matches new_substatus:
   → Return: "Sub-status for SKU {sku} updated:
     '{old_value}' → '{new_substatus}'"
3. If the value does NOT match:
   → Return: "WARNING: Sub-status update may have failed for SKU {sku}.
     Expected '{new_substatus}', found '{current_value}'.
     Please verify manually in WatchTrack."
```

---

## Error Handling

All errors should be returned as clear messages to the caller. Never
fail silently. Never attempt workarounds that could modify the wrong data.

| Error | Response |
|-------|----------|
| No Chrome connection | "Cannot access WatchTrack: No Chrome browser connected." |
| Not authenticated | "Cannot access WatchTrack: Browser session is not authenticated." |
| SKU not found | "No item found for SKU: {sku}" |
| Multiple results | "Ambiguous: {count} items found for SKU: {sku}." |
| Pencil icon not found | "Could not open Sub-Status editor. Manual update required." |
| Invalid substatus value | List valid options and halt |
| Modal didn't open | "Could not open Sub-Status editor. Manual update required." |
| Save failed | "WARNING: Sub-status update may have failed. Verify manually." |
| Page load timeout | "WatchTrack page did not load. Check network connection." |
| Title not found | Set brand and model to null; log warning but continue extraction |
| Show more details not found | Set all spec fields to null; continue without halting |

---

## Navigation Pattern Summary

```
INVENTORY SEARCH → RESULT VALIDATION → ITEM DETAIL PAGE → ACTION
                                                          ├─ Extract data (Capability 1)
                                                          │   ├─ Base fields (Step 6)
                                                          │   ├─ Pricing (Step 7)
                                                          │   ├─ Expanded specs (Step 8)
                                                          │   └─ Item notes (Step 9)
                                                          └─ Edit substatus (Capability 2)
```

**Key URLs:**
- Inventory page: `https://watchtrack.com/store/inventory`
- Item detail: `https://watchtrack.com/store/item/{uuid}` (arrived at via card click)

**Search mechanics:**
- Use the INVENTORY PAGE search bar, NOT the global top search bar
- Inventory search bar placeholder: "Search by brand, reference number,
  serial number, stock ID, and more"
- Global search bar routes to Transactions (wrong destination)
- Type SKU → press Enter → results filter in card view
- Result count shown at bottom: "Viewing X-X of X result(s)"

**DOM notes (validated March 31, 2026):**
- WatchTrack is an Angular app (ng-tns class prefixes)
- Labels use class `item-detail-title-global`
- Labels and values share a common ancestor container, making DOM traversal
  unreliable. Coordinate-based extraction is the proven approach.
- Sub-Status pencil icon is an `<img>` element, not a `<button>` or `<svg>`.
  It is invisible to accessibility tools (find, read_page). Requires JS click.
- Edit modal class: `modal-outer` with trigger `scaleIn`
- Dropdown in modal is a textbox with placeholder "Select an option"
- Dropdown options appear as a scrollable list below the textbox
- "Save changes" button has gold/tan styling
- "Show more details" link expands 17 additional spec fields below
  Case Diameter. Clicking it again shows "Show less details" to collapse.
- Item title appears as a leaf text node in a banner element, not in a
  predictably classed container. Use text search with position filtering.

---

## What This Skill Does NOT Do

- Does NOT log in or manage authentication
- Does NOT create, delete, or modify inventory items (only reads data
  and updates the Sub-Status field)
- Does NOT know about listings, pricing, Grailzee, or any sales platform
- Does NOT interact with Transactions, Clients, Payments, or any other
  WatchTrack section beyond Inventory
- Does NOT modify any field other than Sub-Status (V1 scope)

Future versions may add: editing other custom fields (Sale Channel, List
in Elite), reading transaction history, extracting associated costs,
batch operations across multiple SKUs.
