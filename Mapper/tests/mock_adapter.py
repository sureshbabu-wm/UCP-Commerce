"""A deterministic mock adapter for offline tests (no network / no key).

It ignores the LLM and returns a hand-crafted, schema-valid mapping for the
create_checkout slice, exercising the full pipeline (extract/validate/rules/validator).
"""

from __future__ import annotations

import json

from mapper.providers.base import LLMAdapter


class MockAdapter(LLMAdapter):
    provider = "mock"

    @property
    def default_model(self) -> str:
        return "mock-1"

    def _operation_in(self, messages: list[dict]) -> str:
        """Extract the injected UCP operation id from the user message JSON."""
        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        try:
            payload = json.loads(user[user.index("{"):])
            return next(iter(payload.get("UCP_INVENTORY", {})), "")
        except (ValueError, StopIteration):
            return ""

    def _complete(self, messages: list[dict]) -> str:
        op = self._operation_in(messages)
        if op != "create_checkout":
            # Minimal valid skeleton for non-slice operations (offline full-surface coverage).
            return json.dumps({
                "ucp_version": "2026-01-23",
                "provider": "openai",
                "endpoint_mappings": [
                    {"ucp_operation": op, "status": "unmapped", "confidence": 0.0,
                     "client_calls": [], "notes": "mock: not mapped offline"}
                ],
                "field_mappings": [],
                "coverage": {"required_total": 0, "mapped": 0, "defaulted": 0, "computed": 0, "unmapped": 0},
                "review_queue": [],
            })
        mapping = {
            "ucp_version": "2026-01-23",
            "provider": "openai",
            "endpoint_mappings": [
                {
                    "ucp_operation": "create_checkout",
                    "status": "mapped",
                    "confidence": 0.9,
                    "client_calls": [
                        {"operationId": "createCart", "method": "POST", "path": "/api/cart", "when": None}
                    ],
                    "notes": None,
                }
            ],
            "field_mappings": [
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
                        {"target_path": "$.buyer.email", "source_path": "$.customer.email_address",
                         "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.85,
                         "rationale": "email_address maps to buyer email"},
                        {"target_path": "$.currency", "source_path": "$.currency_code",
                         "transform": "copy", "args": {}, "status": "mapped", "confidence": 0.7,
                         "rationale": "currency_code is the ISO currency"},
                    ],
                },
                {
                    "ucp_operation": "create_checkout",
                    "direction": "response",
                    "fields": [
                        {"target_path": "$.id", "source_path": None, "transform": "computed",
                         "args": {"note": "server-generated session id"}, "status": "computed",
                         "confidence": 1.0, "rationale": "checkout id is server-authoritative"},
                        {"target_path": "$.ucp", "source_path": None, "transform": "computed",
                         "args": {"note": "ucp metadata"}, "status": "computed", "confidence": 1.0,
                         "rationale": "ucp metadata is generated"},
                        {"target_path": "$.line_items[*].item.id", "source_path": "$.products[*].sku",
                         "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.88,
                         "rationale": "sku -> item id"},
                        {"target_path": "$.line_items[*].item.title", "source_path": "$.products[*].name",
                         "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.82,
                         "rationale": "product name -> title"},
                        {"target_path": "$.line_items[*].item.price", "source_path": "$.products[*].unit_price",
                         "transform": "cents_from_major", "args": {"scale": 100}, "status": "mapped",
                         "confidence": 0.8, "rationale": "dollars -> cents"},
                        {"target_path": "$.line_items[*].quantity", "source_path": "$.products[*].qty",
                         "transform": "rename", "args": {}, "status": "mapped", "confidence": 0.9,
                         "rationale": "qty -> quantity"},
                        {"target_path": "$.status", "source_path": "$.state",
                         "transform": "enum_map",
                         "args": {"map": {"open": "ready_for_complete", "ordered": "completed",
                                          "abandoned": "canceled"}, "default": "incomplete"},
                         "status": "mapped", "confidence": 0.6, "rationale": "cart state -> checkout status"},
                        {"target_path": "$.currency", "source_path": "$.currency_code",
                         "transform": "copy", "args": {}, "status": "mapped", "confidence": 0.7,
                         "rationale": "currency_code -> currency"},
                        {"target_path": "$.totals", "source_path": None, "transform": "computed",
                         "args": {"note": "derived from line items"}, "status": "computed",
                         "confidence": 1.0, "rationale": "totals are computed"},
                        {"target_path": "$.links", "source_path": None, "transform": "const",
                         "args": {"value": []}, "status": "default", "confidence": 0.5,
                         "rationale": "no client links; default empty"},
                    ],
                },
            ],
            "coverage": {"required_total": 0, "mapped": 0, "defaulted": 0, "computed": 0, "unmapped": 0},
            "review_queue": [],
        }
        return json.dumps(mapping)
