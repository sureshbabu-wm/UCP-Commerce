"""Lenient JSON-Schemas for the per-phase LLM calls in the two-step pipeline.

Phase 1 (endpoint) returns ``{endpoint_mappings: [...]}``; phase 2 (field) returns
``{field_mappings: [...]}``. The orchestrator enriches (capability, ids, coverage) and validates the
assembled artifact against the full contract afterwards.
"""

from __future__ import annotations

ENDPOINT_PHASE_SCHEMA = {
    "type": "object",
    "required": ["endpoint_mappings"],
    "properties": {
        "endpoint_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ucp_operation", "status", "client_calls"],
                "properties": {
                    "ucp_operation": {"type": "string"},
                    "status": {"type": "string", "enum": ["mapped", "partial", "unmapped"]},
                    "confidence": {"type": "number"},
                    "client_calls": {"type": "array"},
                    "notes": {"type": ["string", "null"]},
                },
            },
        }
    },
}

FIELD_PHASE_SCHEMA = {
    "type": "object",
    "required": ["field_mappings"],
    "properties": {
        "field_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ucp_operation", "direction", "fields"],
                "properties": {
                    "ucp_operation": {"type": "string"},
                    "direction": {"type": "string", "enum": ["request", "response"]},
                    "fields": {"type": "array"},
                },
            },
        }
    },
}
