# Mapper — Vertical Slice Plan (v1)

**Goal of the slice:** prove the end-to-end path for **one** UCP operation —
`create_checkout` (**request + response**) — with **one** LLM provider, through M1–M6.
This de-risks the three make-or-break pieces: context strategy (D1), provider JSON output (D2),
executable transforms (D5). Full surface + extensions + 3 providers come after.

Stack: **Python** (FastAPI service, pydantic models).

---

## Scope of the slice

In:
- UCP version param → load vendored UCP spec for that version (start with `2026-01-23`).
- Build field inventories for UCP `create_checkout` request (`CheckoutCreateRequest`) and response (`Checkout`).
- Accept a client swagger; build its inventory; map **only** the endpoint that matches `create_checkout`.
- One provider end-to-end (pick at call time; adapter interface ready for the other two).
- Rules engine applies the UCP conventions relevant to checkout (cents, RFC 3339, ISO 4217, `ucp` metadata default).
- Return the mapping JSON (+ coverage + review queue) per the output contract.

Out (deferred):
- Other endpoints (get/update/complete/cancel), extensions (discount/fulfillment/buyer_consent), discovery synthesis.
- Gateway runtime executor.
- Auth/persistence/multi-tenant concerns beyond transient key handling.

---

## Module / file layout

```
Mapper/
├─ ANALYSIS.md                      # done
├─ DESIGN-AND-FEASIBILITY.md        # done
├─ VERTICAL-SLICE-PLAN.md           # this file
├─ README.md
├─ requirements.txt
├─ contracts/
│   ├─ mapping_output.schema.json   # the output JSON contract (validated)
│   └─ transforms.md                # closed transform vocabulary (executable later)
├─ skill/
│   └─ SKILL.md                     # provider-neutral instruction file the LLM follows
├─ ucp_specs/
│   └─ 2026-01-23/                  # vendored UCP openapi + json-schemas for this version
├─ mapper/
│   ├─ __init__.py
│   ├─ app.py                       # FastAPI: POST /map
│   ├─ registry.py                  # M1: load UCP spec by version
│   ├─ normalizer.py                # M1: $ref/allOf flatten → field inventory (UCP + swagger)
│   ├─ inventory.py                 # FieldInventory / FieldDescriptor models
│   ├─ prompt_builder.py            # M2: skill file + inventories → provider-neutral prompt
│   ├─ providers/
│   │   ├─ base.py                  # LLMAdapter interface (+ JSON validate/repair loop)
│   │   ├─ openai_adapter.py
│   │   ├─ claude_adapter.py
│   │   └─ gemini_adapter.py
│   ├─ orchestrator.py              # M4: per-endpoint fan-out → assemble artifact
│   ├─ rules.py                     # M5: deterministic conventions + overrides
│   └─ validator.py                 # M6: coverage, type checks, gaps, review queue
└─ tests/
    ├─ fixtures/sample_client_swagger.json
    └─ test_slice_create_checkout.py
```

---

## Milestone order within the slice

1. **Contracts** — `mapping_output.schema.json` + `transforms.md` (done in this pass).
2. **Skill file** — `skill/SKILL.md` (done in this pass).
3. **Registry + Normalizer + Inventory** — vendor UCP `2026-01-23` checkout schemas; build inventories.
4. **Prompt builder + one Provider adapter** — produce prompt, get validated JSON back.
5. **Orchestrator** — wire create_checkout request+response; assemble artifact.
6. **Rules + Validator** — conventions, coverage, review queue.
7. **FastAPI `/map` + test** — sample client swagger fixture → mapping JSON.

---

## Acceptance for the slice

- `POST /map` with a sample client swagger + `ucp_version=2026-01-23` + a provider key returns a
  schema-valid mapping JSON that:
  - maps the client's cart-create endpoint to `create_checkout`,
  - produces field mappings for the request and response with `status` per field,
  - marks `totals`/server-`id`/`ucp` as `computed`/`default` (not hallucinated),
  - lists any gaps in `coverage` + low-confidence items in `review_queue`.
</content>
