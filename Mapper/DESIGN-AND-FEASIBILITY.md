# Mapper — Service Design & Feasibility

> Decisions taken (from review):
> - **Deliverable (v1):** a **service**. Input = client **Swagger** (+ **UCP version** + chosen **LLM provider/key**). Output = **UCP→API mapping JSON**. A UI already exists.
> - **Scope:** full UCP surface **+ extensions**.
> - **UCP version:** **parameterized** — the service loads that version's UCP spec and maps against it.
> - **Form factor:** **provider-agnostic**. A **skill file that *any* LLM can follow** drives the work; the service supports **Gemini / Claude / OpenAI** keys. Not tied to Claude.

---

## 1. Target architecture

```
            ┌──────────────────────────── Mapper Service ────────────────────────────┐
  UI  ─────▶│  POST /map                                                              │
 (exists)   │   body: { client_swagger, ucp_version, provider, api_key, rules? }      │
            │                                                                         │
            │  1. UCP Spec Registry ──load(ucp_version)──▶ OpenAPI + JSON-Schemas     │
            │  2. Normalizer ── flatten $ref/allOf, build compact FIELD INVENTORIES   │
            │       for both UCP (target) and client swagger (source)                 │
            │  3. Prompt Builder ── [SKILL FILE] + [UCP inventory] + [client inventory]│
            │  4. LLM Adapter ──(provider, key)──▶ Gemini | Claude | OpenAI           │
            │       └─ enforce JSON output, validate, repair-loop on invalid          │
            │  5. Rules Engine ── apply deterministic conventions & overrides          │
            │  6. Validator/Reporter ── coverage, gaps, confidence, review queue       │
            │                                                                         │
  UI  ◀─────│  200: { endpoint_mappings, field_mappings, coverage, review_queue }      │
            └─────────────────────────────────────────────────────────────────────────┘
```

**The "skill file"** = a provider-neutral Markdown/JSON instruction doc that tells *any* LLM:
the task, the input format it will receive, the **transform taxonomy** (closed vocabulary),
the **output JSON schema** it must return, the rules discipline (mapped/computed/default/unmapped),
and worked examples. The service injects the real specs around it.

---

## 2. Will it work? — Yes, with three make-or-break pieces

The service shape is sound and buildable. Success hinges on three engineering pieces, **not** on the LLM alone:

1. **Spec normalization → compact field inventories** (so it fits context & maps reliably).
2. **A provider adapter layer** with strict JSON output + validate/repair.
3. **A deterministic rules engine + closed transform vocabulary** (so output is correct, auditable, and *executable* by the future gateway).

If those three are solid, the LLM does the fuzzy semantic matching well and the system is trustworthy.

---

## 3. Difficulties / risks (what to design for up front)

| # | Difficulty | Why it bites | Mitigation |
|---|---|---|---|
| **D1** | **Context-window blowout** | Full UCP surface + all extension schemas + a real-world swagger (often 10k–100k+ lines) won't fit one prompt; quality degrades ("lost in the middle"). | Don't feed raw JSON. **Pre-normalize** both specs into compact inventories (path, type, required, enum, 1-line description, unit/format hint). **Map per-endpoint / per-direction** with fan-out, not whole-spec-at-once. |
| **D2** | **Provider-agnostic structured output** | OpenAI, Claude, Gemini each have *different* JSON/structured-output mechanisms; plain "return JSON" instructions are unreliable across all three. | **LLM Adapter** per provider, each using that provider's native JSON mode when available; strict output schema in the skill file; service-side **validate + re-prompt repair loop**. |
| **D3** | **Non-determinism / cross-provider variance** | Same input → different mappings; Gemini vs GPT vs Claude give different quality. Money/orders make this risky. | `temperature=0`; **rules engine pins** deterministic conventions post-LLM; **confidence scores** + **human review queue**; the rules layer is what makes results consistent regardless of provider. |
| **D4** | **No-source / computed fields** | UCP fields like `totals`, server-generated `id`, `ucp` metadata have **no client source**; LLM may hallucinate a mapping. | Skill file teaches the **status discipline** (`mapped \| computed \| default \| unmapped`); rules engine + validator catch invented sources. |
| **D5** | **Transforms must be executable** | A mapping is useless to the gateway if transforms are free-form prose. | Constrain to a **closed transform vocabulary** (rename, cents↔major, date-format, enum-map, constant, concat/split, reshape, jsonpath-pick). Service validates every transform name. |
| **D6** | **Swagger variability** | OpenAPI 2.0/3.0/3.1, heavy `$ref`, oneOf/allOf polymorphism, missing descriptions → weak matches. | Normalizer that **upconverts 2.0→3.0**, resolves `$ref`, and routes low-information fields to the review queue. |
| **D7** | **1→many endpoint orchestration & gaps** | `complete_checkout` ≈ payment + reserve + create-order; some UCP ops may have **no** client equivalent. | Endpoint-mapping schema must express **sequence, conditions, and gaps**, not just 1:1. |
| **D8** | **Versioning** | "Parameterized version" means storing & selecting each supported UCP version's spec. | **UCP Spec Registry**: vendor each version's OpenAPI + schemas; build inventory per version; select by param. |
| **D9** | **Key handling & data privacy** | User-supplied provider keys; sending client swaggers to 3rd-party LLMs may be sensitive. | Keys **in-memory/transient**, never logged; document that swaggers leave to the chosen provider; allow self-hosted/no-op provider later. |
| **D10** | **Cost & latency** | Per-endpoint fan-out × large specs × full surface = many/large calls. | Batch endpoints; cache UCP inventory per version; surface est. cost; allow scope subset. |

**Net:** none of these are blockers. D1, D2, D5 are the ones that, if skipped, make a demo that "works once" but fails on real swaggers. Design them in from the start.

---

## 4. The mapping JSON (output contract) — shape

```jsonc
{
  "ucp_version": "2026-01-23",
  "endpoint_mappings": [
    {
      "ucp_operation": "create_checkout",          // POST /checkout-sessions
      "client_calls": [                              // 1..n, ordered
        { "operationId": "createCart", "method": "POST", "path": "/api/cart", "when": null }
      ],
      "status": "mapped",                            // mapped | partial | unmapped
      "confidence": 0.9,
      "notes": "..."
    }
  ],
  "field_mappings": [
    {
      "ucp_operation": "create_checkout",
      "direction": "request",                        // request | response
      "fields": [
        {
          "target_path": "$.line_items[*].item.id",  // UCP side
          "source_path": "$.items[*].sku",           // client side (null if computed/default)
          "transform": "rename",                      // closed vocabulary
          "args": {},
          "status": "mapped",                         // mapped | computed | default | unmapped
          "confidence": 0.86,
          "rationale": "sku is the product identifier; matches item.id semantics"
        }
      ]
    }
  ],
  "coverage": { "required_total": 42, "mapped": 30, "defaulted": 6, "computed": 4, "unmapped": 2 },
  "review_queue": [ /* low-confidence or ambiguous items */ ]
}
```

This is the contract the existing UI consumes and the future gateway runtime executes.

---

## 5. Proposed build plan (milestones)

- **M0 — Skeleton & contracts.** Define the output JSON schema + the **closed transform vocabulary**; stub the service endpoint and the provider-adapter interface.
- **M1 — UCP Spec Registry + Normalizer.** Vendor one UCP version; build the **field-inventory** builder (resolve `$ref`, flatten `allOf`/extensions) for UCP target. Then the same for arbitrary client swaggers (incl. 2.0→3.0 upconvert).
- **M2 — Skill file v1.** Provider-neutral instruction doc: task, input format, transform taxonomy, output schema, status discipline, examples.
- **M3 — LLM Adapter (3 providers).** Gemini / Claude / OpenAI behind one interface, each with JSON-output enforcement + validate/repair loop.
- **M4 — Orchestrator.** Per-endpoint fan-out: build prompt → call LLM → collect field mappings; assemble full artifact.
- **M5 — Rules Engine.** Deterministic conventions (cents, RFC 3339, ISO 4217, ucp metadata), enum dictionaries, explicit overrides; rules win over LLM.
- **M6 — Validator/Reporter.** Coverage, type compatibility, gap & low-confidence flags, review queue. Wire response to the UI.
- **M7 — Extensions + full surface.** Discount / fulfillment / buyer_consent, all checkout endpoints, discovery-profile awareness.
- **(Later) Gateway runtime** that executes the artifact against live traffic.

**Recommended first vertical slice to de-risk:** `create_checkout` request+response, single provider, end-to-end through M1–M6 — proves context strategy (D1), JSON output (D2), and executable transforms (D5) before widening to full surface.
</content>
