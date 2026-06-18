"""A deterministic, phase-aware mock adapter for offline tests (no network / no key).

Recognizes the two-phase prompts:
- TASK=endpoint_mapping -> returns {endpoint_mappings: [...]} (maps create/get_checkout to the
  first POST/GET client endpoint; everything else unmapped).
- TASK=field_mapping    -> returns {field_mappings: [...]} for the single injected UCP operation
  (rich blocks for create_checkout; a minimal block otherwise).
"""

from __future__ import annotations

import json

from mapper.providers.base import LLMAdapter


def _user_json(messages: list[dict]) -> dict:
    user = next((m["content"] for m in messages if m["role"] == "user"), "")
    try:
        return json.loads(user[user.index("{"):])
    except (ValueError, json.JSONDecodeError):
        return {}


_CREATE_CHECKOUT_BLOCKS = [
    {
        "ucp_operation": "create_checkout",
        "direction": "request",
        "fields": [
            {"target_path": "$.line_items[*].item.id", "source_path": "$.products[*].sku",
             "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.88,
             "rationale": "sku is the product identifier"},
            {"target_path": "$.line_items[*].quantity", "source_path": "$.products[*].qty",
             "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.9,
             "rationale": "qty maps to quantity"},
            {"target_path": "$.buyer.full_name", "source_path": "$.customer.name",
             "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.8,
             "rationale": "customer name is the buyer full name"},
            {"target_path": "$.currency", "source_path": "$.currency_code",
             "transform": "copy", "args": {}, "status": "mapped", "confidence": 0.7,
             "rationale": "currency_code is the ISO currency"},
        ],
    },
    {
        "ucp_operation": "create_checkout",
        "direction": "response",
        "fields": [
            {"target_path": "$.id", "source_path": "$.cart_id", "transform": "rename", "args": {},
             "status": "mapped", "confidence": 0.9, "rationale": "cart id -> checkout id"},
            {"target_path": "$.line_items[*].item.id", "source_path": "$.products[*].sku",
             "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.88,
             "rationale": "sku -> item id"},
            {"target_path": "$.line_items[*].item.price", "source_path": "$.products[*].unit_price",
             "transform": "cents_from_major", "args": {"scale": 100}, "status": "mapped",
             "confidence": 0.8, "rationale": "dollars -> cents"},
            {"target_path": "$.status", "source_path": "$.state", "transform": "enum_map",
             "args": {"map": {"open": "ready_for_complete", "ordered": "completed"}, "default": "incomplete"},
             "status": "mapped", "confidence": 0.6, "rationale": "cart state -> checkout status"},
            {"target_path": "$.currency", "source_path": "$.currency_code", "transform": "copy",
             "args": {}, "status": "mapped", "confidence": 0.7, "rationale": "currency_code -> currency"},
        ],
    },
]


class MockAdapter(LLMAdapter):
    provider = "mock"

    @property
    def default_model(self) -> str:
        return "mock-1"

    def _complete(self, messages: list[dict]) -> str:
        payload = _user_json(messages)

        if payload.get("TASK") == "endpoint_mapping":
            client = payload.get("CLIENT_ENDPOINTS", [])
            first_post = next((c for c in client if c.get("method") == "POST"), None)
            first_get = next((c for c in client if c.get("method") == "GET"), None)
            eps = []
            for o in payload.get("UCP_OPERATIONS", []):
                op_id = o.get("operationId")
                if op_id == "create_checkout" and first_post:
                    eps.append({"ucp_operation": op_id, "status": "mapped", "confidence": 0.9,
                                "client_calls": [{"operationId": first_post.get("operationId"),
                                                  "method": first_post.get("method"),
                                                  "path": first_post.get("path"), "when": None}],
                                "notes": None})
                elif op_id == "get_checkout" and first_get:
                    eps.append({"ucp_operation": op_id, "status": "mapped", "confidence": 0.85,
                                "client_calls": [{"operationId": first_get.get("operationId"),
                                                  "method": first_get.get("method"),
                                                  "path": first_get.get("path"), "when": None}],
                                "notes": None})
                else:
                    eps.append({"ucp_operation": op_id, "status": "unmapped", "confidence": 0.0,
                                "client_calls": [], "notes": "mock: no match"})
            return json.dumps({"endpoint_mappings": eps})

        # field_mapping phase
        op_id = payload.get("UCP_OPERATION", {}).get("operationId")
        if op_id == "create_checkout":
            return json.dumps({"field_mappings": _CREATE_CHECKOUT_BLOCKS})
        return json.dumps({"field_mappings": [
            {"ucp_operation": op_id, "direction": "response", "fields": [
                {"target_path": "$.id", "source_path": None, "transform": "computed", "args": {},
                 "status": "computed", "confidence": 1.0, "rationale": "server id"},
            ]},
        ]})
