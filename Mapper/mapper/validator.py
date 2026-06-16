"""Validator / reporter (M6).

Recomputes coverage against the UCP **required** target fields across ALL mapped operations,
surfaces gaps (required fields with no mapping) and low-confidence *mapped* fields into the
review queue, and validates the final artifact against the output JSON schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from .inventory import OperationInventory

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "contracts" / "mapping_output.schema.json"
_LOW_CONFIDENCE = 0.6


def _required_targets(ucp_op: OperationInventory) -> set[str]:
    return {f.path for f in ucp_op.response_fields if f.required} | {
        f.path for f in ucp_op.request_fields if f.required
    }


def _on_branch(a: str, b: str) -> bool:
    """True if paths a and b are on the same JSONPath branch (one is the other or an ancestor).

    Respects segment boundaries so ``$.line_items`` does not match ``$.line_items_extra``.
    """
    if a == b:
        return True
    lo, hi = (a, b) if len(a) < len(b) else (b, a)
    return hi.startswith(lo) and hi[len(lo)] in (".", "[")


def _effective_status(target: str, entries: list[tuple[str, str]]) -> str:
    """Resolve the status of a required ``target`` given mapping entries (path, status).

    Precedence: exact match > nearest ancestor (computed/default/mapped propagate down) >
    any mapped/computed/default descendant (a container realized by its children) > unmapped.
    """
    good = {"mapped", "computed", "default"}
    for path, status in entries:
        if path == target:
            return status
    ancestors = [(p, s) for p, s in entries if len(p) < len(target) and _on_branch(p, target)]
    if ancestors:
        ancestors.sort(key=lambda e: len(e[0]), reverse=True)
        return ancestors[0][1]
    for path, status in entries:
        if len(path) > len(target) and _on_branch(target, path) and status in good:
            return "mapped"
    return "unmapped"


def finalize(mapping: dict[str, Any], ucp_ops: list[OperationInventory]) -> dict[str, Any]:
    """Aggregate coverage + review queue across one or more UCP operations.

    The review queue is rebuilt deterministically here (the model's self-reported queue is
    discarded) so output is consistent regardless of provider (D3).
    """
    review: list[dict] = []
    seen_review: set = set()
    counts = {"mapped": 0, "defaulted": 0, "computed": 0, "unmapped": 0}
    required_total = 0

    # Low-confidence review: only for fields that are actually MAPPED (uncertain match worth a look).
    for block in mapping.get("field_mappings", []):
        for field in block.get("fields", []):
            conf = field.get("confidence")
            if (
                field.get("status") == "mapped"
                and conf is not None
                and conf < _LOW_CONFIDENCE
            ):
                key = (field["target_path"], block["direction"], block["ucp_operation"])
                if key not in seen_review:
                    review.append({
                        "ucp_operation": block["ucp_operation"],
                        "direction": block["direction"],
                        "target_path": field["target_path"],
                        "reason": f"low-confidence match ({conf})",
                        "confidence": conf,
                    })
                    seen_review.add(key)

    # Operations whose endpoint itself is unmapped (no client operation realizes them).
    unmapped_endpoints = {
        em.get("ucp_operation")
        for em in mapping.get("endpoint_mappings", [])
        if em.get("status") == "unmapped" or not em.get("client_calls")
    }

    # Coverage + gaps, per operation.
    for ucp_op in ucp_ops:
        required = _required_targets(ucp_op)
        required_total += len(required)

        # If the endpoint is unmapped, every field is uncovered — but emit ONE endpoint-level
        # gap instead of flooding the queue with each field.
        if ucp_op.operation_id in unmapped_endpoints:
            counts["unmapped"] += len(required)
            key = (ucp_op.operation_id, "endpoint")
            if key not in seen_review:
                review.append({
                    "ucp_operation": ucp_op.operation_id,
                    "direction": None,
                    "target_path": "(endpoint)",
                    "reason": "no client operation maps to this UCP operation",
                    "confidence": None,
                })
                seen_review.add(key)
            continue

        entries = [
            (f["target_path"], f.get("status", "unmapped"))
            for b in mapping.get("field_mappings", [])
            if b.get("ucp_operation") == ucp_op.operation_id
            for f in b.get("fields", [])
        ]
        for path in required:
            st = _effective_status(path, entries)
            if st == "mapped":
                counts["mapped"] += 1
            elif st == "default":
                counts["defaulted"] += 1
            elif st == "computed":
                counts["computed"] += 1
            else:
                counts["unmapped"] += 1
                key = (path, None, ucp_op.operation_id)
                if key not in seen_review:
                    review.append({
                        "ucp_operation": ucp_op.operation_id,
                        "direction": None,
                        "target_path": path,
                        "reason": "required UCP field has no mapping (gap)",
                        "confidence": None,
                    })
                    seen_review.add(key)

    mapping["coverage"] = {"required_total": required_total, **counts}
    mapping["review_queue"] = review
    return mapping


def validate_schema(mapping: dict[str, Any]) -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(mapping, schema)
