"""Orchestrator (M4): drive the mapping across UCP operations.

Pipeline: load UCP inventory (by version) -> normalize client swagger -> for each target UCP
operation, build a per-operation prompt -> call provider adapter (validated JSON) -> apply
rules -> accumulate -> finalize/validate the combined artifact.

Per-operation fan-out keeps each prompt small (mitigates D1) and lets us widen from one operation
(the slice) to the full surface by iterating ``ucp_inventory.operations``.
"""

from __future__ import annotations

from typing import Any

from . import registry
from .inventory import OperationInventory
from .normalizer import normalize
from .prompt_builder import build_messages
from .providers import get_adapter
from .providers.base import LLMAdapter
from .rules import apply_rules
from .validator import finalize, validate_schema

SLICE_OPERATION = "create_checkout"


def run_mapping(
    *,
    client_swagger: dict[str, Any],
    ucp_version: str,
    provider: str,
    api_key: str,
    rules: dict | None = None,
    operation_id: str | None = SLICE_OPERATION,
    adapter: LLMAdapter | None = None,
) -> dict[str, Any]:
    """Map ``operation_id`` (or ALL UCP operations when ``operation_id`` is None)."""
    ucp_inv = registry.load_ucp_inventory(ucp_version)

    if operation_id is None:
        target_ops = list(ucp_inv.operations)
    else:
        op = ucp_inv.operation(operation_id)
        if op is None:
            raise ValueError(f"UCP operation {operation_id!r} not found in version {ucp_version}")
        target_ops = [op]

    client_inv = normalize(client_swagger)
    llm = adapter or get_adapter(provider, api_key)
    pinned_provider = provider if provider in ("openai", "claude", "gemini") else "openai"

    endpoint_mappings: list[dict] = []
    field_mappings: list[dict] = []

    for ucp_op in target_ops:
        messages = build_messages(
            ucp_version=ucp_version,
            provider=pinned_provider,
            ucp_op=ucp_op,
            client=client_inv,
            rules=rules,
        )
        partial = llm.map(messages)
        apply_rules(partial, ucp_op, rules)

        endpoint_mappings.extend(
            em for em in partial.get("endpoint_mappings", [])
            if em.get("ucp_operation") == ucp_op.operation_id
        )
        field_mappings.extend(
            fm for fm in partial.get("field_mappings", [])
            if fm.get("ucp_operation") == ucp_op.operation_id
        )
        # Note: the model's self-reported review_queue is intentionally dropped;
        # finalize() rebuilds it deterministically from coverage + confidence.

    mapping: dict[str, Any] = {
        "ucp_version": ucp_version,
        "provider": pinned_provider,
        "endpoint_mappings": endpoint_mappings,
        "field_mappings": field_mappings,
        "coverage": {"required_total": 0, "mapped": 0, "defaulted": 0, "computed": 0, "unmapped": 0},
        "review_queue": [],
    }

    mapping = finalize(mapping, target_ops)
    validate_schema(mapping)
    return mapping
