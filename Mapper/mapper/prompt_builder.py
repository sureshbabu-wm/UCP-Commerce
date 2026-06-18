"""Build the provider-neutral prompt: SKILL.md + injected inventories.

To respect context budgets (D1) the prompt is built **per UCP operation**: only the target
operation's fields and the candidate client operations are injected, not the whole specs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .inventory import OperationInventory, SpecInventory

_SKILL_PATH = Path(__file__).resolve().parent.parent / "skill" / "SKILL.md"


def load_skill() -> str:
    return _SKILL_PATH.read_text(encoding="utf-8")


def _op_payload(op: OperationInventory) -> dict:
    return {
        "operationId": op.operation_id,
        "method": op.method,
        "path": op.path,
        "summary": op.summary,
        "request_fields": [f.model_dump(exclude_none=True) for f in op.request_fields],
        "response_fields": [f.model_dump(exclude_none=True) for f in op.response_fields],
    }


def _op_meta(op: OperationInventory) -> dict:
    """Lightweight endpoint metadata (no field inventories) for phase-1 triage."""
    return {
        "operationId": op.operation_id,
        "method": op.method,
        "path": op.path,
        "summary": op.summary,
    }


def build_endpoint_messages(
    *,
    ucp_version: str,
    ucp_ops: list[OperationInventory],
    client: SpecInventory,
) -> list[dict]:
    """Phase 1 — endpoint mapping. Metadata only (small prompt) → endpoint_mappings."""
    user_inputs = {
        "UCP_VERSION": ucp_version,
        "TASK": "endpoint_mapping",
        "UCP_OPERATIONS": [_op_meta(o) for o in ucp_ops],
        "CLIENT_ENDPOINTS": [_op_meta(o) for o in client.operations],
    }
    user = (
        "PHASE 1 - ENDPOINT MAPPING. Using ONLY the endpoint metadata below, decide which client "
        "endpoint(s) realize each UCP operation (match by intent, not name). Return ONLY a JSON "
        "object whose single key is endpoint_mappings: a list where each item has ucp_operation, "
        "status (mapped|partial|unmapped), confidence, client_calls (a list of objects with "
        "operationId, method, path, when), and notes. Use status unmapped with empty client_calls "
        "when no client endpoint fits. No field mappings, no prose.\n\nINPUTS:\n"
        + json.dumps(user_inputs, indent=2)
    )
    return [{"role": "system", "content": load_skill()}, {"role": "user", "content": user}]


def build_field_messages(
    *,
    ucp_version: str,
    ucp_op: OperationInventory,
    client_op: OperationInventory,
    rules: dict | None = None,
) -> list[dict]:
    """Phase 2 — field mapping for ONE matched (UCP op, client op) pair → field_mappings."""
    user_inputs = {
        "UCP_VERSION": ucp_version,
        "TASK": "field_mapping",
        "UCP_OPERATION": _op_payload(ucp_op),
        "CLIENT_OPERATION": _op_payload(client_op),
        "RULES": rules or {},
    }
    user = (
        "PHASE 2 - FIELD MAPPING. The UCP operation below has already been matched to the client "
        "operation below. Produce field mappings for BOTH directions. Return ONLY a JSON object "
        "whose single key is field_mappings: a list of blocks, each with ucp_operation, direction "
        "(request|response), and fields (each field has target_path, source_path, transform, args, "
        "status, confidence, rationale). Follow the skill's transform vocabulary and status "
        "discipline. No prose.\n\nINPUTS:\n"
        + json.dumps(user_inputs, indent=2)
    )
    return [{"role": "system", "content": load_skill()}, {"role": "user", "content": user}]
