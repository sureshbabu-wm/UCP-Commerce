# UCP Mapper — UI Integration Reference

> For the **UI developer**. This documents the HTTP API the UCP Gateway Portal calls: every
> endpoint, its request/response shape, which UI panel consumes it, and the recommended flow.
> Companion artifacts: the **Postman collection** (`postman/UCP-Mapper.postman_collection.json`) and
> the **live OpenAPI/Swagger UI** at `http://localhost:8000/docs` (always matches the running code).

Base URL (local/Docker): `http://localhost:8000`

---

## 1. Endpoints at a glance

| Method | Path | Needs API key? | UI use |
|---|---|---|---|
| GET | `/versions` | no | populate the UCP version selector |
| GET | `/ucp/{version}/structure` | no | **left panel** (capabilities → fields) + field dropdowns |
| POST | `/swagger/parse` | no | **right panel** (parsed endpoints → fields) |
| POST | `/map/endpoints` | **yes** | **phase 1** — endpoint routing (review/edit) |
| POST | `/map/fields` | **yes** | **phase 2** — field mappings for the (edited) endpoints |
| POST | `/map` | **yes** | one-shot full mapping (phase 1 + 2) |

The API key is sent **per request** in the body (`api_key`). It is used transiently and never stored.

---

## 2. Recommended flow (matches the workspace UI)

```
Upload Swagger ─┐
                ├─▶ POST /swagger/parse ───────────────▶ right panel (endpoints + fields)
Select version ─┴─▶ GET /ucp/{version}/structure ─────▶ left panel (capabilities + fields, dropdowns)

Click "Generate Mapping":
   POST /map/endpoints ──▶ show endpoint matches; user may EDIT them
                           │
                           ▼ (send the edited endpoint_mappings back)
   POST /map/fields  ─────▶ Request/Response tabs, buckets, coverage, review queue
                           │
                           ▼
   (Save to DB — persistence endpoint: not built yet)
```

`POST /map` does endpoints+fields in one call if you don't need the review-between-phases step.

---

## 3. Path/notation conventions (IMPORTANT)

Two notations appear and the UI must reconcile them:

- **Structure endpoints** (`/ucp/.../structure`, `/swagger/parse`) emit **dot notation**:
  `line_items[].item.id`, `products[].sku`.
- **Mapping endpoints** (`/map*`) emit **JSONPath** in `target_path`/`source_path`:
  `$.line_items[*].item.id`, `$.products[*].sku`.

To match a `field_mapping` row back to a structure field, normalize: strip leading `$.` and replace
`[*]` → `[]`. (i.e. `$.line_items[*].item.id` ⇄ `line_items[].item.id`.)

`target_path` is always the **UCP** side; `source_path` is always the **service/swagger** side, in
both `request` and `response` blocks.

---

## 4. Endpoint reference

### 4.1 `GET /versions`
Response:
```json
{ "ucp_versions": ["2026-01-23", "2026-04-08"] }
```

### 4.2 `GET /ucp/{version}/structure`  → left panel + dropdowns
`version` e.g. `2026-04-08`.
```json
{
  "ucp_version": "2026-04-08",
  "title": "UCP Shopping Service",
  "capabilities": [
    {
      "capability": "CHECKOUT",
      "operations": ["cancel_checkout", "complete_checkout", "create_checkout", "get_checkout", "update_checkout"],
      "fields": [
        { "path": "id", "type": "string", "required": true, "description": "..." },
        { "path": "line_items[].item.price", "type": "integer", "required": true, "unit": "cents" },
        { "path": "status", "type": "string", "required": true, "enum": ["incomplete", "ready_for_complete", "..."] }
      ]
    }
  ]
}
```
- `capabilities[]` → the left-panel groups (`CHECKOUT`, `CART`, `CATALOG.SEARCH`, `CATALOG.LOOKUP`, `ORDER`).
- `fields[]` → the UCP fields under each capability, and the **options for the "map to UCP field" dropdowns**.
- Optional per-field hints: `enum`, `unit` (`cents`/`major_units`), `format` (`date-time`/`uri`), `description`.

### 4.3 `POST /swagger/parse`  → right panel
Request:
```json
{ "swagger": { /* the client's OpenAPI/Swagger JSON */ } }
```
Response:
```json
{
  "title": "Acme Shop API",
  "version": "1.0.0",
  "endpoints": [
    {
      "operationId": "createCart",
      "method": "POST",
      "path": "/api/cart",
      "summary": "Create a shopping cart with products",
      "request_fields":  [ { "path": "products[].sku", "type": "string", "required": true } ],
      "response_fields": [ { "path": "cart_id", "type": "string" }, { "path": "products[].unit_price", "type": "number", "unit": "major_units" } ]
    }
  ]
}
```

### 4.4 `POST /map/endpoints`  → phase 1 (endpoint routing)
Request (`api_key` required; `ucp_version` defaults to `2026-04-08`):
```json
{ "client_swagger": { /* OpenAPI JSON */ }, "ucp_version": "2026-04-08", "provider": "openai", "api_key": "sk-..." }
```
Response:
```json
{
  "ucp_version": "2026-04-08",
  "provider": "openai",
  "endpoint_mappings": [
    {
      "id": "ep_create_checkout",
      "capability": "CHECKOUT",
      "ucp_operation": "create_checkout",
      "ucp_method": "POST",
      "ucp_path": "/checkout-sessions",
      "status": "mapped",
      "confidence": 0.9,
      "client_calls": [ { "operationId": "createCart", "method": "POST", "path": "/api/cart", "when": null } ],
      "notes": null
    },
    {
      "id": "ep_search_catalog", "capability": "CATALOG.SEARCH", "ucp_operation": "search_catalog",
      "ucp_method": "POST", "ucp_path": "/catalog/search",
      "status": "unmapped", "confidence": 0.0, "client_calls": [], "notes": "no client endpoint"
    }
  ]
}
```
- `status`: `mapped` | `partial` | `unmapped`. `client_calls` may have **0..n** entries (multi-step or none).
- The UI can let the user **edit** these (re-point `client_calls`, flip `status`), then pass the edited array to `/map/fields`.

### 4.5 `POST /map/fields`  → phase 2 (field mappings)
Request — same as `/map/endpoints` **plus** the (possibly edited) `endpoint_mappings`:
```json
{
  "client_swagger": { /* OpenAPI JSON */ },
  "ucp_version": "2026-04-08",
  "provider": "openai",
  "api_key": "sk-...",
  "endpoint_mappings": [ /* from /map/endpoints, optionally edited */ ]
}
```
Response — the **full artifact** (see §5). Only operations whose endpoint `status == mapped` (and whose
client op is resolvable) get field mappings; the rest are reported as gaps.

### 4.6 `POST /map`  → full (phase 1 + 2)
Request = same as `/map/endpoints`. Response = the full artifact (§5). Use when you don't need the
review-between-phases step. (Slower: it maps the entire UCP surface.)

---

## 5. The full mapping artifact (returned by `/map` and `/map/fields`)

```json
{
  "ucp_version": "2026-04-08",
  "provider": "openai",
  "endpoint_mappings": [ /* §4.4 shape */ ],
  "field_mappings": [
    {
      "ucp_operation": "create_checkout",
      "capability": "CHECKOUT",
      "direction": "response",
      "fields": [
        {
          "id": "create_checkout:response:0",
          "target_path": "$.id",                 // UCP side (JSONPath)
          "source_path": "$.cart_id",            // service side (null when computed/default/unmapped)
          "transform": "rename",
          "args": {},
          "status": "mapped",
          "confidence": 0.9,
          "rationale": "cart id reused as checkout id"
        }
      ]
    }
  ],
  "coverage": {
    "required_total": 70, "mapped": 18, "defaulted": 3, "computed": 11, "unmapped": 38,
    "by_capability": {
      "CHECKOUT": { "required_total": 70, "mapped": 18, "defaulted": 3, "computed": 11, "unmapped": 38 }
    }
  },
  "review_queue": [
    { "ucp_operation": "create_checkout", "direction": "response", "target_path": "$.status",
      "reason": "low-confidence match (0.55)", "confidence": 0.55 },
    { "ucp_operation": "create_checkout", "direction": null, "target_path": "$.links",
      "reason": "required UCP field has no mapping (gap)", "confidence": null }
  ]
}
```

### 5.1 Field row (`field_mappings[].fields[]`)
| key | meaning |
|---|---|
| `id` | stable row id (`<op>:<direction>:<index>`) — use as React key + for edits |
| `target_path` | UCP field (JSONPath) |
| `source_path` | service field (JSONPath) or `null` |
| `transform` | one of: `copy, rename, const, default, cents_from_major, major_from_cents, date_rfc3339, enum_map, concat, split, reshape, jsonpath_pick, computed` |
| `args` | transform parameters (e.g. `{ "scale": 100 }`, `{ "map": {...} }`) |
| `status` | `mapped` \| `computed` \| `default` \| `unmapped` |
| `confidence` | 0–1 |
| `rationale` | one-line explanation |

### 5.2 Rendering the UI buckets (matches the screenshots)
Per operation + direction:
- **AUTO-MAPPED** → `status == "mapped"` **and** `confidence >= 0.6`.
- **NEEDS REVIEW** → `status == "mapped"` **and** `confidence < 0.6` (these also appear in `review_queue`).
- **UNMAPPED REQUIRED** → required UCP fields with `status == "unmapped"` (also in `review_queue` with reason “…gap”).
- **computed / default** rows are gateway-supplied (server-authoritative or sensible defaults) — show as system/auto, not gaps.

### 5.3 Coverage
- Overall % = `(mapped + computed + defaulted) / required_total`.
- Left-panel per-capability counts come from `coverage.by_capability[<CAP>]` (e.g. `mapped / required_total`).

### 5.4 Review queue
A flat list for the “Needs Review” panel: low-confidence mapped fields **and** unmapped required gaps.
`direction` is `null` for endpoint/gap-level items, otherwise `request`/`response`.

---

## 6. Editing & re-running
1. Call `/map/endpoints`, render the endpoint matches, let the user re-point/confirm.
2. Send the **edited** `endpoint_mappings` to `/map/fields`.
3. Render field mappings; the user edits rows (change `source_path`/`transform`/`status` via dropdowns).
4. The edited **full artifact** is what you'll later POST to the (forthcoming) persistence endpoint.
   Field/endpoint **`id`s** are stable anchors for these edits.

> Persistence (Save/Load/Update mappings) and the gateway runtime (redirecting live UCP traffic using a
> saved mapping) are **not built yet** — coming next. The artifact shape above is the contract you'll save.

---

## 7. Status & error codes
| Code | When | Body |
|---|---|---|
| 200 | success | the artifact / structure |
| 400 | unknown `ucp_version`, unknown operation, unparseable swagger | `{ "detail": "..." }` |
| 422 | request body fails validation (missing field, body not raw JSON) | `{ "detail": [ { "loc": [...], "msg": "..." } ] }` |
| 502 | LLM provider error (bad/expired key, rate limit, malformed model output after repair) | `{ "detail": "LLM provider error: ..." }` |

Notes:
- A **422 with `loc: ["body", 0]` / "Expecting value"** means the request body wasn't sent as raw JSON.
- `provider` accepts `openai` | `claude` | `gemini`, but only **`openai`** is implemented today.
- Current model: **`gpt-4o`** (server default; not selectable via the API yet).

---

## 8. Quick test
Import `postman/UCP-Mapper.postman_collection.json`, set the `api_key` collection variable, and run
requests 1→5. Or open `http://localhost:8000/docs` for the live, auto-generated OpenAPI spec.
</content>
