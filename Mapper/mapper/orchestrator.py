"""Two-phase orchestrator.

Phase 1 — endpoint mapping: ONE cheap LLM call over endpoint metadata → which client endpoint(s)
realize each UCP operation.
Phase 2 — field mapping: for each MATCHED operation, a parallel LLM call over that operation's full
field inventory → field-level mappings. Unmatched operations are skipped (reported as gaps).

Each phase has its own endpoint; ``run_mapping`` chains them. Outputs are enriched with capability
groups + stable row ids for the UI, and validated against the full contract.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

from . import registry
from .capabilities import capability_for
from .inventory import OperationInventory
from .normalizer import normalize
from .phase_schemas import ENDPOINT_PHASE_SCHEMA, FIELD_PHASE_SCHEMA
from .prompt_builder import build_endpoint_messages, build_field_messages
from .providers import get_adapter
from .providers.base import LLMAdapter
from .rules import apply_rules
from .validator import _effective_status, _required_targets, finalize, validate_schema

_MAX_PARALLEL = 8

_VALID_TRANSFORMS = {
    "copy", "rename", "const", "default", "cents_from_major", "major_from_cents",
    "date_rfc3339", "enum_map", "concat", "split", "reshape", "jsonpath_pick", "computed",
}
_VALID_STATUS = {"mapped", "computed", "default", "unmapped"}


def _pin(provider: str) -> str:
    return provider if provider in ("openai", "claude", "gemini") else "openai"


def _coerce_field(f: dict[str, Any]) -> None:
    """Repair model field-rows that put a status value in `transform` (or other invalid combos),
    so one bad row can't fail whole-artifact validation."""
    status = f.get("status")
    if status not in _VALID_STATUS:
        status = f["status"] = "unmapped" if not f.get("source_path") else "mapped"
    transform = f.get("transform")
    if transform not in _VALID_TRANSFORMS:
        if status == "computed":
            f["transform"] = "computed"
        elif status == "default":
            f["transform"] = "default"
        elif status == "mapped" and f.get("source_path"):
            f["transform"] = "rename"
        else:
            f["status"] = "unmapped"
            f["source_path"] = None
            f["transform"] = "copy"  # placeholder; unmapped rows are ignored by the runtime
    f.setdefault("args", {})


# ---------------------------------------------------------------- phase 1
def run_endpoint_mapping(
    *,
    client_swagger: dict[str, Any],
    ucp_version: str,
    provider: str,
    api_key: str,
    adapter: LLMAdapter | None = None,
) -> dict[str, Any]:
    """Phase 1: map each UCP operation to client endpoint(s) using endpoint metadata only."""
    ucp_inv = registry.load_ucp_inventory(ucp_version)
    client_inv = normalize(client_swagger)
    llm = adapter or get_adapter(provider, api_key)

    messages = build_endpoint_messages(
        ucp_version=ucp_version, ucp_ops=ucp_inv.operations, client=client_inv
    )
    result = llm.map(messages, schema=ENDPOINT_PHASE_SCHEMA)

    op_by_id = {o.operation_id: o for o in ucp_inv.operations}
    endpoint_mappings: list[dict] = []
    for em in result.get("endpoint_mappings", []):
        op_id = em.get("ucp_operation")
        op = op_by_id.get(op_id)
        em["capability"] = capability_for(op_id)
        em["id"] = f"ep_{op_id}"
        if op:
            em["ucp_method"] = op.method
            em["ucp_path"] = op.path
        em.setdefault("client_calls", [])
        endpoint_mappings.append(em)

    return {
        "ucp_version": ucp_version,
        "provider": _pin(provider),
        "endpoint_mappings": endpoint_mappings,
    }


# ---------------------------------------------------------------- phase 2
def run_field_mapping(
    *,
    client_swagger: dict[str, Any],
    ucp_version: str,
    endpoint_mappings: list[dict],
    provider: str,
    api_key: str,
    rules: dict | None = None,
    adapter: LLMAdapter | None = None,
) -> dict[str, Any]:
    """Phase 2: field mappings for matched operations (parallel), assembled + validated."""
    ucp_inv = registry.load_ucp_inventory(ucp_version)
    client_inv = normalize(client_swagger)
    llm = adapter or get_adapter(provider, api_key)

    op_by_id = {o.operation_id: o for o in ucp_inv.operations}
    client_by_id = {o.operation_id: o for o in client_inv.operations}
    client_by_path = {(o.method, o.path): o for o in client_inv.operations}

    # Build the work list: (ucp_op, client_op) for each mapped endpoint we can resolve.
    jobs: list[tuple[OperationInventory, OperationInventory]] = []
    for em in endpoint_mappings:
        if em.get("status") == "unmapped" or not em.get("client_calls"):
            continue
        ucp_op = op_by_id.get(em.get("ucp_operation"))
        if not ucp_op:
            continue
        call = em["client_calls"][0]
        client_op = client_by_id.get(call.get("operationId")) or client_by_path.get(
            (call.get("method"), call.get("path"))
        )
        if client_op:
            jobs.append((ucp_op, client_op))

    def _do(job: tuple[OperationInventory, OperationInventory]) -> tuple[OperationInventory, list[dict]]:
        ucp_op, client_op = job
        messages = build_field_messages(
            ucp_version=ucp_version, ucp_op=ucp_op, client_op=client_op, rules=rules
        )
        part = llm.map(messages, schema=FIELD_PHASE_SCHEMA)
        blocks = [
            b for b in part.get("field_mappings", []) if b.get("direction") in ("request", "response")
        ]
        for b in blocks:
            b["ucp_operation"] = ucp_op.operation_id
        return ucp_op, blocks

    field_mappings: list[dict] = []
    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL, len(jobs))) as ex:
            for ucp_op, blocks in ex.map(_do, jobs):
                apply_rules({"field_mappings": blocks}, ucp_op, rules)
                cap = capability_for(ucp_op.operation_id)
                for b in blocks:
                    b["capability"] = cap
                    for i, f in enumerate(b.get("fields", [])):
                        _coerce_field(f)
                        f["id"] = f"{ucp_op.operation_id}:{b['direction']}:{i}"
                field_mappings.extend(blocks)

    mapping: dict[str, Any] = {
        "ucp_version": ucp_version,
        "provider": _pin(provider),
        "endpoint_mappings": endpoint_mappings,
        "field_mappings": field_mappings,
        "coverage": {"required_total": 0, "mapped": 0, "defaulted": 0, "computed": 0, "unmapped": 0},
        "review_queue": [],
    }
    finalize(mapping, list(ucp_inv.operations))
    mapping["coverage"]["by_capability"] = _coverage_by_capability(mapping, ucp_inv.operations)
    validate_schema(mapping)
    return mapping


# ---------------------------------------------------------------- common
def run_mapping(
    *,
    client_swagger: dict[str, Any],
    ucp_version: str,
    provider: str,
    api_key: str,
    rules: dict | None = None,
    adapter: LLMAdapter | None = None,
) -> dict[str, Any]:
    """Run phase 1 then phase 2 and return the full artifact."""
    phase1 = run_endpoint_mapping(
        client_swagger=client_swagger, ucp_version=ucp_version,
        provider=provider, api_key=api_key, adapter=adapter,
    )
    return run_field_mapping(
        client_swagger=client_swagger, ucp_version=ucp_version,
        endpoint_mappings=phase1["endpoint_mappings"],
        provider=provider, api_key=api_key, rules=rules, adapter=adapter,
    )


def _coverage_by_capability(
    mapping: dict[str, Any], ucp_ops: list[OperationInventory]
) -> dict[str, dict[str, int]]:
    """Per-capability required-field coverage (for the UI left-panel counts)."""
    unmapped_eps = {
        em.get("ucp_operation")
        for em in mapping.get("endpoint_mappings", [])
        if em.get("status") == "unmapped" or not em.get("client_calls")
    }
    by_cap: dict[str, dict[str, int]] = {}
    for op in ucp_ops:
        cap = capability_for(op.operation_id)
        bucket = by_cap.setdefault(cap, {"required_total": 0, "mapped": 0, "defaulted": 0, "computed": 0, "unmapped": 0})
        required = _required_targets(op)
        bucket["required_total"] += len(required)
        if op.operation_id in unmapped_eps:
            bucket["unmapped"] += len(required)
            continue
        entries = [
            (f["target_path"], f.get("status", "unmapped"))
            for b in mapping.get("field_mappings", [])
            if b.get("ucp_operation") == op.operation_id
            for f in b.get("fields", [])
        ]
        for path in required:
            st = _effective_status(path, entries)
            bucket["defaulted" if st == "default" else st] += 1
    return by_cap
