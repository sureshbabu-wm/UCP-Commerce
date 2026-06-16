"""Deterministic rules engine (M5).

Runs AFTER the LLM and wins over it. Enforces UCP conventions the model may have missed and
applies explicit overrides. This is what makes output consistent regardless of provider (D3)
and prevents hallucinated sources for server-authoritative fields (D4).
"""

from __future__ import annotations

from typing import Any

from .inventory import OperationInventory

# Response fields that are ALWAYS server-authoritative / derived — never client-sourced.
_ALWAYS_COMPUTED = {"$.ucp", "$.totals", "$.order.id", "$.line_items[*].totals"}

# Identity fields: PREFER reusing the client's own id (correlation key) when the model found one;
# fall back to computed (gateway-generated) only when there is no client source.
_ID_CORRELATION = {"$.id", "$.line_items[*].id"}

# Server/gateway-authoritative containers. If the model omits them entirely, INJECT a computed
# entry (covers descendants via the validator's ancestor logic) so they aren't reported as gaps.
# Deliberately excludes client-sourced response-only fields like item.title/price, links, payment.
_INJECT_COMPUTED = ("$.ucp", "$.id", "$.status", "$.totals", "$.line_items[*].totals", "$.order")

_CENTS_TRANSFORMS = {"cents_from_major", "major_from_cents"}


def apply_rules(
    mapping: dict[str, Any],
    ucp_op: OperationInventory,
    rules: dict | None = None,
) -> dict[str, Any]:
    """Mutate + return the mapping with conventions enforced (for one operation's blocks)."""
    rules = rules or {}
    unit_by_path = {f.path: f.unit_hint for f in ucp_op.response_fields if f.unit_hint}
    fmt_by_path = {f.path: f.format_hint for f in ucp_op.response_fields if f.format_hint}

    for block in mapping.get("field_mappings", []):
        if block.get("ucp_operation") != ucp_op.operation_id:
            continue
        for field in block.get("fields", []):
            tpath = field.get("target_path")
            src = field.get("source_path")

            # R1a: always-computed server-authoritative fields -> computed, no source.
            if block["direction"] == "response" and tpath in _ALWAYS_COMPUTED:
                _force_computed(field, "server-authoritative (rule R1)")
                continue

            # R1b: id correlation -> reuse client id when present, else computed.
            if block["direction"] == "response" and tpath in _ID_CORRELATION:
                if src:
                    field["status"] = "mapped"
                    if field.get("transform") not in ("copy", "rename"):
                        field["transform"] = "rename"
                    field.setdefault("rationale", "reuse client id as UCP correlation key")
                else:
                    _force_computed(field, "no client id; gateway-generated (rule R1)")
                continue

            # R2: cents convention — money targets must use a cents transform when sourced.
            if (
                field.get("status") == "mapped"
                and unit_by_path.get(tpath) == "cents"
                and field.get("transform") in ("copy", "rename")
            ):
                field["transform"] = "cents_from_major"
            # Ensure cents transforms carry an explicit scale.
            if field.get("transform") in _CENTS_TRANSFORMS:
                field.setdefault("args", {}).setdefault("scale", 100)

            # R3: date-time targets must normalize to RFC 3339 when sourced.
            if (
                field.get("status") == "mapped"
                and fmt_by_path.get(tpath) == "date-time"
                and field.get("transform") in ("copy", "rename")
            ):
                field["transform"] = "date_rfc3339"
                field.setdefault("args", {}).setdefault("from", "auto")

            # R5: reconcile status <-> transform/source consistency.
            _reconcile(field)

    # R6: inject computed entries for omitted server-authoritative fields (response side).
    _inject_computed(mapping, ucp_op)

    # R4: explicit overrides — pin a target's transform/source from the rules file.
    for ov in rules.get("overrides", []):
        _apply_override(mapping, ov)

    return mapping


def _inject_computed(mapping: dict[str, Any], ucp_op: OperationInventory) -> None:
    """Add computed entries for server-authoritative containers the model didn't address."""
    resp_paths = {f.path for f in ucp_op.response_fields}
    block = next(
        (b for b in mapping.get("field_mappings", [])
         if b.get("ucp_operation") == ucp_op.operation_id and b.get("direction") == "response"),
        None,
    )
    if block is None:
        return
    present = {f["target_path"] for f in block["fields"]}
    for path in _INJECT_COMPUTED:
        if path in resp_paths and path not in present:
            block["fields"].append({
                "target_path": path,
                "source_path": None,
                "transform": "computed",
                "args": {"note": "server/gateway-authoritative (rule R6)"},
                "status": "computed",
                "confidence": 1.0,
                "rationale": "server-authoritative; not mapped from client",
            })


def _force_computed(field: dict[str, Any], note: str) -> None:
    field["status"] = "computed"
    field["transform"] = "computed"
    field["source_path"] = None
    field.setdefault("args", {})["note"] = note


def _reconcile(field: dict[str, Any]) -> None:
    """Fix contradictory (status, transform, source) combinations the model can emit."""
    status = field.get("status")
    src = field.get("source_path")
    transform = field.get("transform")
    args = field.get("args") or {}

    # A "default"/"const" with a value but flagged unmapped is really a default.
    if status == "unmapped" and transform in ("default", "const") and "value" in args:
        field["status"] = "default"
        return
    # "mapped" with no source is not a mapping — demote.
    if status == "mapped" and not src:
        field["status"] = "unmapped"


def _apply_override(mapping: dict[str, Any], ov: dict) -> None:
    for block in mapping.get("field_mappings", []):
        if block["ucp_operation"] != ov.get("ucp_operation") or block["direction"] != ov.get("direction"):
            continue
        for field in block["fields"]:
            if field["target_path"] == ov.get("target_path"):
                field.update({k: v for k, v in ov.items() if k in
                              ("source_path", "transform", "args", "status", "rationale", "confidence")})
