# UCP ↔ Client-Swagger Mapper — Analysis

> Goal: a **gateway** that accepts (1) the **UCP specification** and (2) a **client's existing Swagger/OpenAPI**, and produces an AI-assisted, rule-augmented **mapping** between them — at both the **endpoint level** and the **field level** — so the client's existing APIs can be exposed as a UCP-compliant surface.
>
> This document is the analysis phase only. It records how UCP works (from the online docs + the `samples/` reference implementation) and what the mapper actually has to solve. Planning/skill design follows separately.

---

## 1. What UCP is (the *target* side of the mapping)

UCP = **Universal Commerce Protocol** (ucp.dev) — an open standard for interoperability between commerce "platforms" (capability **consumers**, e.g. an AI shopping agent) and "businesses" (capability **providers**, e.g. a merchant). It defines a common vocabulary so the two sides interoperate **without bespoke integrations**.

Core building blocks:

| Concept | Meaning | Naming |
|---|---|---|
| **Service** | A vertical grouping of operations | `dev.ucp.shopping` |
| **Capability** | A discrete, versioned feature ("verb") | `dev.ucp.shopping.checkout` |
| **Extension** | Optional augmentation of a capability's schema via JSON-Schema `allOf` | `dev.ucp.shopping.discount` *extends* `…checkout` |
| **Transport** | How a service is invoked | `rest` (OpenAPI 3.1), `mcp` (OpenRPC), `a2a`, `embedded` |
| **Discovery profile** | Machine-readable manifest at `/.well-known/ucp` declaring services, capabilities, payment handlers, signing keys | — |
| **Version** | Date-based `YYYY-MM-DD`, bumps only on breaking change | `2026-01-23` |

Key conventions the mapping must honor (from spec + samples):
- **Amounts** are integers in **minor units (cents)**.
- **Dates** are **RFC 3339**.
- **Currency** is **ISO 4217**.
- Responses carry a mandatory **`ucp` metadata object** (`version` + active `capabilities`).
- Required request headers: `Request-Signature`, `Idempotency-Key`, `Request-Id`, plus `UCP-Agent` (platform profile URL).
- Reverse-domain identifiers prevent collisions across vendors.

### 1.1 The UCP REST surface (the endpoints to be mapped *to*)

From the canonical OpenAPI (`https://ucp.dev/2026-01-23/services/shopping/openapi.json`) and the reference routes in
`samples/rest/python/server/generated_routes/ucp_routes.py`:

| operationId | Method + Path | Request body | Response body |
|---|---|---|---|
| `create_checkout` | `POST /checkout-sessions` | `CheckoutCreateRequest` | `Checkout` |
| `get_checkout` | `GET /checkout-sessions/{id}` | — | `Checkout` |
| `update_checkout` | `PUT /checkout-sessions/{id}` | `CheckoutUpdateRequest` | `Checkout` |
| `complete_checkout` | `POST /checkout-sessions/{id}/complete` | payment + risk_signals | `Checkout` |
| `cancel_checkout` | `POST /checkout-sessions/{id}/cancel` | — | `Checkout` |
| `order_event_webhook` | `POST /webhooks/partners/{partner_id}/events/order` | `Order` | `{}` |

Important structural facts about the UCP OpenAPI:
- Schemas are **referenced by external URI** (`checkout.json`, `order.json`, `payment.json`, `ucp.json`), *not* inlined. Transport defs "MUST reference base schemas only" — the real field shapes live in the **JSON-Schema files**, composed with extensions via `allOf`.
- A small fixed set of **endpoints** (checkout lifecycle), but **rich, deeply-nested payloads**.

### 1.2 The UCP data model (the fields to be mapped *to*)

From the SDK models the samples depend on (e.g. `python-sdk/.../shopping/checkout.py`, `checkout_create_request.py`). Representative shape of `Checkout`:

```
Checkout
├─ ucp: UcpMetadata            # version + capabilities (server-generated)
├─ id: str                     # session id (server-generated)
├─ line_items: [LineItem]
│   ├─ id                      # server-generated
│   ├─ item: { id, title, price(cents), image_url }
│   ├─ quantity
│   └─ totals: [ {type, amount} ]   # computed
├─ buyer: { first_name, last_name, full_name, email, phone_number, consent }
├─ status: enum(incomplete | requires_escalation | ready_for_complete |
│                complete_in_progress | completed | canceled)
├─ currency: ISO-4217
├─ totals: [ {type: subtotal|discount|fulfillment|total, amount(cents)} ]   # computed
├─ links / messages / expires_at / continue_url
├─ payment: { handlers[], instruments[], selected_instrument_id }
├─ order: { id, permalink_url }                # on completion
└─ (extensions) discounts, fulfillment, fulfillment_address, ap2, platform …
```

`CheckoutCreateRequest` is a **subset** (line_items, buyer, context, payment) — i.e. request and response schemas differ, so the mapper handles **request mappings and response mappings separately**.

---

## 2. What the client Swagger is (the *source* side)

An arbitrary existing e-commerce API. It will differ from UCP on every axis:
- **Endpoint names**: e.g. `POST /api/cart`, `PATCH /api/cart/{id}`, `POST /api/orders` instead of `/checkout-sessions`.
- **Field names**: `sku` vs `item.id`, `name` vs `full_name`, `state` vs `address_region`, `price_usd` vs `price`(cents).
- **Structure**: flat vs nested; different array groupings; wrapper objects.
- **Units / formats**: dollars vs cents; epoch millis vs RFC 3339.
- **Enums / status vocab**: client's own cart/order statuses vs UCP's checkout lifecycle.
- **Cardinality**: one UCP operation may correspond to several client calls, or vice-versa.

---

## 3. What the gateway must actually do

```
   UCP Agent / Platform                Gateway (NEW)                 Client's existing backend
   ──────────────────       ┌────────────────────────────┐         ───────────────────────
   speaks UCP  ───request──▶ │ 1. route UCP op → client op │ ──────▶ speaks client API
                             │ 2. transform UCP req → client req      │
                             │ 3. call client API                     │
                             │ 4. transform client resp → UCP resp    │
   speaks UCP  ◀──response── │ 5. inject ucp metadata / defaults      │ ◀────── client resp
                             └────────────────────────────┘
                                        ▲
                                        │ driven by
                              ┌───────────────────────┐
                              │  MAPPING ARTIFACT      │  ← produced by the skill (this project)
                              │  (endpoint + field     │     from UCP spec + client swagger
                              │   mappings + rules)    │     using AI + rules
                              └───────────────────────┘
```

The skill we will build produces the **mapping artifact**. The gateway **runtime** that executes it against live traffic is a later phase. There are two distinct mapping levels:

1. **Endpoint mapping** — UCP operation → client operation(s), incl. ordering & conditions.
2. **Field mapping** — per operation, per direction (request / response): source path → target path **with a transform**.

---

## 4. The hard part — what "mapping" really means (evidence from `samples/`)

`samples/rest/python/server/services/checkout_service.py` is effectively a **hand-written mapper** between the merchant's internal product DB and the UCP schema. It is the single best guide to what the *automated* mapper must generate. Patterns observed:

| # | Transform type | Concrete example in samples | Implication for the mapper |
|---|---|---|---|
| 1 | **Rename** | `region = addr.state` (UCP `address_region` ← internal `state`) | Field names rarely match 1:1 — needs semantic matching. |
| 2 | **Unit conversion** | prices/totals in **cents** everywhere | Must detect & convert dollars↔cents, date formats, etc. |
| 3 | **Structural reshape** | flat product row → nested `line_item.item.{id,title,price}`; `RootModel` wrappers; nested method→group→option arrays | Mapping is path-to-path over trees, not column-to-column. |
| 4 | **Constant / default injection** | `status=IN_PROGRESS`, `links=[]`, `ucp` metadata object | Some UCP fields have **no client source** → default/const. |
| 5 | **Computed / server-authoritative** | `_recalculate_totals` computes `subtotal/discount/fulfillment/total`; UUIDs generated for ids | Some UCP fields are **computed**, not mapped — the mapper must mark them, not invent a source. |
| 6 | **Enum / status mapping** | checkout lifecycle vs internal states | Needs enum dictionaries (rule-driven). |
| 7 | **One-to-many endpoints** | `complete_checkout` = process payment **+** reserve stock **+** create order **+** webhook | Endpoint mapping is not 1:1; needs orchestration/sequence. |
| 8 | **Conditional / extension-gated** | discount & fulfillment logic only when those extensions are present | Mappings must be conditional on negotiated capabilities. |
| 9 | **Stateful correlation** | checkout-session is stateful; internally split across products/transactions DBs + idempotency | Gateway may need session/id correlation & idempotency handling. |
| 10 | **Discovery synthesis** | `discovery_profile.json` declares which capabilities exist | Gateway must emit `/.well-known/ucp` reflecting what it can actually map. |

**Takeaway:** a field mapping entry is richer than `source → target`. It is:
`{ target_path, source_path?, transform, args, confidence, rationale, status(mapped|computed|default|unmapped) }`.

---

## 5. Why AI **and** rules (both, not either)

- **AI is needed** for the fuzzy, semantic part: matching `sku ↔ item.id`, `name ↔ full_name`, `shipping_state ↔ address_region`, and recognizing structural correspondences using the **descriptions** present in both OpenAPI/JSON-Schema docs. Pure heuristics miss these.
- **Rules are needed** for determinism and correctness:
  - **Convention rules** that are always true for UCP (cents, RFC 3339, ISO 4217, `ucp` metadata).
  - **Override/pin rules** to lock a mapping the AI got wrong, or encode org-specific naming.
  - **Enum dictionaries** (status vocab translation).
  - **Guardrails**: required-field coverage, type compatibility, confidence thresholds, human-in-the-loop review for low-confidence matches.

Rules also make the output **reproducible and auditable** — important because money/orders are involved.

---

## 6. Skill I/O contract (proposed)

**Inputs**
1. **UCP specification** — the UCP OpenAPI (endpoints + operationIds) **plus** the referenced JSON-Schemas (field shapes) **plus** extension schemas; pinned to a version (e.g. `2026-01-23`). Endpoint names + I/O structure come from here.
2. **Client Swagger/OpenAPI** — the existing API to be fronted.
3. **(Optional) Rules file** — explicit hints, transforms, enum dictionaries, overrides, conventions.

**Output — the mapping artifact** (machine-readable JSON/YAML), containing:
- `endpoint_mappings[]`: `ucp_operation` → `client_operation(s)` (+ sequence/conditions).
- `field_mappings[]`: per operation & direction, list of
  `{ target_path, source_path?, transform, args, confidence, rationale, status }`.
- `coverage_report`: required UCP fields satisfied / defaulted / computed / **unmapped (gaps)**; client fields left **unused**.
- `review_queue`: low-confidence or ambiguous items needing human confirmation.

This artifact is the contract the future gateway runtime consumes.

---

## 7. Proposed phased approach for the skill (to refine in planning)

- **Phase A — Parse & normalize both specs.** Resolve `$ref`, flatten UCP `allOf`/extensions, build canonical **field inventories** (path, type, required, enum, description, unit/format hints) for source and target, per operation & direction.
- **Phase B — Endpoint mapping.** AI matches UCP operations ↔ client operations (method/path/summary/semantics); rules can pin or exclude.
- **Phase C — Field-level mapping.** Per matched endpoint & direction, AI proposes `path → path + transform` with confidence + rationale.
- **Phase D — Rules engine.** Apply deterministic rules: conventions (cents/RFC3339), name conventions, enum dictionaries, required-field defaults, explicit overrides; rules win over AI.
- **Phase E — Validate & report.** Check required-UCP-field coverage & type compatibility; flag gaps and low-confidence; emit review-ready artifact.
- **Phase F — (Later) Runtime executor.** The gateway that consumes the artifact to translate live UCP traffic to/from the client API.

---

## 8. Open questions for planning

1. **Form factor**: is the skill a *Claude Code skill* that generates the artifact, a standalone library/CLI, or both?
2. **Spec acquisition**: pin a fixed UCP version & vendor the schemas, or fetch from `ucp.dev` at runtime?
3. **Scope of v1**: cover the full checkout lifecycle + 3 extensions, or start with `create_checkout` (request + response) end-to-end as a vertical slice?
4. **Transform language**: how transforms are expressed in the artifact (declarative DSL vs JSONPath + named functions vs embedded expressions) — must be executable by the future gateway.
5. **Rules format**: YAML/JSON rule files; precedence model; how AI confidence interacts with rule overrides.
6. **Human-in-the-loop**: how the review queue is surfaced and fed back in.
7. **Relationship to the existing validator**: should the mapper reuse/align with the compliance checks already prototyped, or stay independent?
</content>
</invoke>
