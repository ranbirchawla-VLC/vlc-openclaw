# llm_title_rewriter

Rewrite garbled or verbose voice transcription into a concise, clean title.

For `task`: start with a verb (action-oriented). For `idea`: use a concise noun phrase or question. Return the cleaned title string only — no JSON, no explanation, no surrounding quotes.

## Input

```json
{ "raw_text": "...", "record_type": "task|idea" }
```

## Examples

`task` | "um so I basically need to call the customs broker about the shipment thing from last week at some point today probably"
→ `Call customs broker about last week's shipment`

`idea` | "what if we like made something that could automatically scan for watches going for below market value you know like an agent or something"
→ `Automated watch scanner for below-market listings`

`task` | "don't forget to send Alex the invoice numbers he was asking for you know before end of week"
→ `Send Alex invoice numbers before end of week`

Return only the cleaned title. No other output.
