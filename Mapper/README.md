# UCP Mapper

A **provider-agnostic service** that maps a client's existing **Swagger/OpenAPI** onto the
**Universal Commerce Protocol (UCP)** specification, producing a machine-readable **mapping JSON**
(endpoint-level **and** field-level). The mapping is the contract a UCP **gateway** executes to front
the client's existing APIs with a UCP-compliant surface.

- **Input:** client swagger + `ucp_version` (parameterized) + LLM provider (`openai` | `claude` | `gemini`) + key.
- **Output:** mapping JSON conforming to [`contracts/mapping_output.schema.json`](contracts/mapping_output.schema.json).
- **How:** the service normalizes both specs into compact field inventories, feeds them with the
  provider-neutral [`skill/SKILL.md`](skill/SKILL.md) to the chosen LLM, then applies a deterministic
  **rules engine** and **validator**. The LLM does fuzzy semantic matching; rules guarantee
  correctness, units, and auditability.

## Docs
**Integrating the UI / calling the API?** → [docs/UI-INTEGRATION.md](docs/UI-INTEGRATION.md) — the API
reference for the UI developer (every endpoint, request/response shapes, panel mapping, error codes).
Pair it with the Postman collection (`postman/UCP-Mapper.postman_collection.json`) and the live OpenAPI
at `http://localhost:8000/docs`.

**New here? Start with these three** (written for a reader new to the UCP gateway):
- [docs/01-high-level-architecture.md](docs/01-high-level-architecture.md) — what it is, why it exists, the flow at a glance.
- [docs/02-low-level-architecture.md](docs/02-low-level-architecture.md) — module-by-module design, data model, control flow.
- [docs/03-walkthrough-and-technical-details.md](docs/03-walkthrough-and-technical-details.md) — run it, trace a real example, ops details, glossary.

Background/design:
- [ANALYSIS.md](ANALYSIS.md) — how UCP works and what "mapping" really involves (evidence from the samples).
- [DESIGN-AND-FEASIBILITY.md](DESIGN-AND-FEASIBILITY.md) — service architecture + difficulties (D1–D10) + build plan.
- [VERTICAL-SLICE-PLAN.md](VERTICAL-SLICE-PLAN.md) — the first slice (`create_checkout`, one provider, M1–M6).

## Contracts (stable interfaces)
- [`contracts/mapping_output.schema.json`](contracts/mapping_output.schema.json) — output shape.
- [`contracts/transforms.md`](contracts/transforms.md) — closed transform vocabulary + status discipline.
- [`skill/SKILL.md`](skill/SKILL.md) — provider-neutral instruction file the LLM follows.

## Status
**Full UCP checkout surface working against the REAL official schemas**, verified **live against
OpenAI** (`gpt-4o`): registry → UCP loader / swagger normalizer → prompt builder → provider adapter
(OpenAI + offline mock) → per-operation orchestrator → rules engine → validator/coverage → FastAPI
`/map`. All tests pass.

The vendored UCP spec (`ucp_specs/2026-01-23/`) is the **official multi-file spec** from the
`Universal-Commerce-Protocol/ucp` `release/2026-01-23` branch (OpenAPI + ~80 JSON-Schemas).
`mapper/ucp_loader.py` resolves cross-file `$ref`s and composes the `discount` / `fulfillment` /
`buyer_consent` extensions, yielding the real surface (e.g. `create_checkout` = 57 request / 103
response fields).

Live run highlights (sample Acme swagger → UCP `2026-01-23`, real schema):
- `create_checkout → POST /api/cart`, `get_checkout → GET /api/cart/{cartId}` mapped; `update/complete/cancel` correctly flagged as **endpoint gaps** (the sample API lacks them).
- Field mappings incl. `sku→item.id`, `unit_price→item.price` (dollars→cents), `state→status` (enum_map), `cart_id→id` (id correlation); `ucp`/`totals`/`order`/`status` marked `computed`.
- Coverage honestly reports what a trivial cart API can't satisfy (payment instruments, fulfillment groups/options, discount allocations) as real gaps in the review queue.

Samples: [examples/sample_mapping.create_checkout.json](examples/sample_mapping.create_checkout.json) (offline),
`examples/online_mapping.openai.*.json` (live).

## Vendoring a UCP version
```powershell
git clone --depth 1 -b release/<version> https://github.com/Universal-Commerce-Protocol/ucp .ucp_src
# copy .ucp_src/spec/schemas  -> ucp_specs/<version>/schemas
# copy .ucp_src/spec/services/shopping -> ucp_specs/<version>/services/shopping
```
The registry auto-detects `ucp_specs/<version>/services/shopping/rest.openapi.json` and uses the
real loader; a single self-contained `openapi.json` is still accepted as a compact fallback.

### Run
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q            # offline tests (mock provider)
.\.venv\Scripts\python.exe -m uvicorn mapper.app:app --reload   # serve POST /map
```
`POST /map` body: `{ client_swagger, ucp_version, provider, api_key, rules? }`.

### Next
Add Claude + Gemini adapters; richer extension schemas (discount/fulfillment/buyer_consent) in
the vendored UCP spec; external multi-file `$ref` + Swagger 2.0 up-conversion in the normalizer;
then the gateway runtime that executes the artifact.
</content>
