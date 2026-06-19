# UCP Mapper

A **provider-agnostic service** that maps a service's existing **Swagger/OpenAPI** onto the
**Universal Commerce Protocol (UCP)**, producing a machine-readable **mapping** (endpoint-level +
field-level). That mapping is what a UCP **gateway** will execute to front existing APIs with a
UCP-compliant surface. A UI (the "UCP Gateway Portal") drives it: upload swagger → generate mapping →
review/edit → (save to DB → gateway redirect — *forthcoming*).

- **Inputs:** the service `swagger` + `ucp_version` (default `2026-04-08`) + LLM provider (`openai` today) + key.
- **Output:** `endpoint_mappings` + `field_mappings` + `coverage` + `review_queue`
  (schema: [`contracts/mapping_output.schema.json`](contracts/mapping_output.schema.json)).
- **How:** **two phases** — (1) cheap **endpoint mapping** over endpoint metadata, then (2) **field
  mapping** for matched operations (run in parallel). The provider-neutral
  [`skill/SKILL.md`](skill/SKILL.md) drives the LLM; a deterministic **rules engine** + **validator**
  enforce conventions (cents, RFC 3339), repair bad rows, and compute coverage.

---

## 📄 Document index

| Document | Audience | Status |
|---|---|---|
| **[docs/UI-INTEGRATION.md](docs/UI-INTEGRATION.md)** | **UI / API consumers** — every endpoint, request/response, panel mapping, errors | ✅ current |
| this **README** | everyone — overview, run, index | ✅ current |
| [docs/01-high-level-architecture.md](docs/01-high-level-architecture.md) | newcomers — what/why, concepts | ✅ updated (see banner) |
| [docs/02-low-level-architecture.md](docs/02-low-level-architecture.md) | developers — modules, data model, flow | ✅ updated (see banner) |
| [docs/03-walkthrough-and-technical-details.md](docs/03-walkthrough-and-technical-details.md) | hands-on — run, trace, glossary | ✅ updated (see banner) |
| [contracts/mapping_output.schema.json](contracts/mapping_output.schema.json) | the output contract (validated) | ✅ current |
| [contracts/transforms.md](contracts/transforms.md) | transform vocabulary + status discipline | ✅ current |
| [skill/SKILL.md](skill/SKILL.md) | the provider-neutral LLM instruction file | ✅ current |
| [postman/UCP-Mapper.postman_collection.json](postman/UCP-Mapper.postman_collection.json) | importable API tests (QuickMobile sample pre-filled) | ✅ current |
| [ANALYSIS.md](ANALYSIS.md) · [DESIGN-AND-FEASIBILITY.md](DESIGN-AND-FEASIBILITY.md) · [VERTICAL-SLICE-PLAN.md](VERTICAL-SLICE-PLAN.md) | background / design narrative (historical) | 🕘 historical |

**Hand the UI developer:** `docs/UI-INTEGRATION.md` + the Postman collection + the live OpenAPI at `http://localhost:8000/docs`.

---

## API (v0.3)

| Method | Path | Key? | Purpose |
|---|---|---|---|
| GET | `/versions` | no | list vendored UCP versions |
| GET | `/ucp/{version}/structure` | no | UCP capabilities → fields (UI left panel + dropdowns) |
| POST | `/swagger/parse` | no | parse client swagger → endpoints + fields (UI right panel) |
| POST | `/map/endpoints` | yes | **phase 1** — endpoint mapping (review/edit) |
| POST | `/map/fields` | yes | **phase 2** — field mapping for the (edited) endpoints |
| POST | `/map` | yes | full mapping (phase 1 + 2) |

Request shape: `{ client_swagger, ucp_version?, provider, api_key, rules? }` (`/map/fields` also takes
`endpoint_mappings`). Full details in [docs/UI-INTEGRATION.md](docs/UI-INTEGRATION.md).

## Architecture (modules)

```
app.py                 FastAPI — the 6 endpoints above
orchestrator.py        two-phase: run_endpoint_mapping → run_field_mapping (parallel) → run_mapping
registry.py            load UCP spec by version
ucp_loader.py          official multi-file spec loader (2026-01-23 pre-split + 2026-04-08 ucp_request styles)
normalizer.py          client swagger → field inventory
structures.py          UCP + swagger structures for the UI panels
capabilities.py        operation → capability grouping (CHECKOUT/CART/CATALOG.*/ORDER)
prompt_builder.py      phase-1 (endpoint) and phase-2 (field) prompts around skill/SKILL.md
phase_schemas.py       per-phase JSON schemas for LLM output validation
providers/             LLM adapters (openai_adapter.py live; base.py = validate + repair loop)
rules.py               deterministic conventions + overrides (post-LLM)
validator.py           coverage + review queue + final schema validation
inventory.py           FieldDescriptor / OperationInventory / SpecInventory
```

## Status
- **Two-phase mapping** live; full surface for **UCP `2026-04-08`** (13 ops incl. catalog/cart/order) and `2026-01-23` (checkout only).
- Output enriched with **capability** groups, stable row **`id`s**, and `coverage.by_capability` for the UI.
- **OpenAI** provider wired (default model **`gpt-4o`**); Claude/Gemini are stubs.
- Verified live; offline tests pass (mock provider). Runs in **Docker**.
- **Not built yet:** persistence (Save to DB → PostgreSQL) and the gateway runtime (redirecting live UCP traffic).

## Run

**Local:**
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q                          # offline tests (mock provider)
.\.venv\Scripts\python.exe -m uvicorn mapper.app:app --reload    # serve on :8000
```

**Docker:**
```powershell
docker build -t ucp-mapper:latest .
docker run -d --name ucp-mapper -p 8000:8000 ucp-mapper:latest
```
Then open `http://localhost:8000/docs`, or import the Postman collection and set the `api_key` variable.

## Vendoring a UCP version
- **Preferred (built spec from ucp.dev):** `.\.venv\Scripts\python.exe scripts\vendor_ucp.py <version>` — downloads the OpenAPI + all `$ref`'d schemas into `ucp_specs/<version>/`. (Used for `2026-04-08`.)
- **Alternative (from the repo's built tree):** clone `release/<version>` and copy `spec/schemas` + `spec/services/shopping` into `ucp_specs/<version>/`.

The registry auto-detects `ucp_specs/<version>/services/shopping/rest.openapi.json`; the loader handles
both the `2026-01-23` (pre-split) and `2026-04-08` (`ucp_request`/absolute-ref) layouts.

## Next
Persistence (PostgreSQL) for Save/Load/Update mappings; the gateway runtime that executes a saved
mapping to redirect live UCP traffic; Claude + Gemini adapters; optional per-request `model` selection.
</content>
