# Closed Transform Vocabulary

Every field mapping MUST use exactly one `transform` from this closed list. The future gateway
runtime implements each one deterministically, so the LLM may **not** invent new transform names
or free-form expressions. If no listed transform fits, set `status: "unmapped"` and explain in
`rationale` (do not force a transform).

Paths are **JSONPath**. `[*]` denotes element-wise application across an array (the runtime maps
each source element to the corresponding target element).

| transform | meaning | `args` | example |
|---|---|---|---|
| `copy` | value taken as-is, same type | — | `$.email` → `$.buyer.email` |
| `rename` | copy with a different field name (semantic rename) | — | `$.items[*].sku` → `$.line_items[*].item.id` |
| `const` | inject a fixed value; no source | `{ "value": <any> }` | → `$.links` = `[]` |
| `default` | use source if present else fixed value | `{ "value": <any> }` | `$.currency` (default `"USD"`) |
| `cents_from_major` | major units → integer minor units (×100, rounded) | `{ "scale": 100 }` | `$.price_usd` → `$.item.price` |
| `major_from_cents` | integer minor units → major units (response side) | `{ "scale": 100 }` | `$.item.price` → `$.price_usd` |
| `date_rfc3339` | parse source date → RFC 3339 string | `{ "from": "epoch_ms\|epoch_s\|iso\|auto" }` | `$.created_at` → `$.expires_at` |
| `enum_map` | translate enum values via a dictionary | `{ "map": { "src": "dst", ... }, "default": "..." }` | client status → UCP `status` |
| `concat` | join multiple source paths into one string | `{ "sources": ["$.first","$.last"], "sep": " " }` | → `$.buyer.full_name` |
| `split` | split one source string into target parts | `{ "sep": " ", "index": 0 }` | `$.name` → `$.buyer.first_name` |
| `reshape` | structural move/nesting only (no value change) | — | flat fields → nested object |
| `jsonpath_pick` | select a sub-value from a source via JSONPath | `{ "expr": "$.address.region" }` | nested client field → flat UCP field |
| `computed` | value is computed by the provider (no client source) | `{ "note": "..." }` | `$.totals`, server-generated `$.id` |

## `status` discipline (per field)

- `mapped` — a real `source_path` + transform produces the target.
- `computed` — UCP requires it but it is **server-authoritative / derived** (totals, generated ids, `ucp` metadata). No `source_path`. Use transform `computed`.
- `default` — no client source; a fixed/sensible value is injected. Use `const` or `default`.
- `unmapped` — no source and no safe default; this is a **gap** for human review.

Rules:
1. Never invent a `source_path` to satisfy a required field — prefer `computed`/`default`/`unmapped`.
2. `confidence` (0–1) reflects certainty of the source↔target semantic match; `< 0.6` ⇒ also add to `review_queue`.
3. Unit/format conventions (cents, RFC 3339) are enforced by the **rules engine** even if the LLM omitted them.
</content>
