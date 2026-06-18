"""Build the UCP + swagger structures the UI renders (left panel, right panel, dropdowns).

Both are deterministic (no LLM): the UCP structure comes from the vendored spec inventory grouped by
capability; the swagger structure comes from the normalizer. Field paths are emitted in clean
dot-notation (`line_items[].item.id`) for display.
"""

from __future__ import annotations

from typing import Any

from .capabilities import capability_for
from .inventory import FieldDescriptor, SpecInventory
from .normalizer import normalize
from .registry import load_ucp_inventory


def to_dot(path: str) -> str:
    """JSONPath ($.line_items[*].item.id) -> dot notation (line_items[].item.id)."""
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    return path.replace("[*]", "[]")


def _field(f: FieldDescriptor) -> dict[str, Any]:
    out: dict[str, Any] = {"path": to_dot(f.path), "type": f.type, "required": f.required}
    if f.enum:
        out["enum"] = f.enum
    if f.unit_hint:
        out["unit"] = f.unit_hint
    if f.format_hint:
        out["format"] = f.format_hint
    if f.description:
        out["description"] = f.description
    return out


def build_ucp_structure(version: str) -> dict[str, Any]:
    """UCP capabilities -> operations + (deduped) fields, for the left panel and field dropdowns."""
    inv = load_ucp_inventory(version)
    caps: dict[str, dict[str, Any]] = {}
    for op in inv.operations:
        cap = capability_for(op.operation_id)
        entry = caps.setdefault(cap, {"capability": cap, "operations": [], "fields": {}})
        entry["operations"].append(op.operation_id)
        for f in list(op.request_fields) + list(op.response_fields):
            dot = to_dot(f.path)
            existing = entry["fields"].get(dot)
            if existing is None:
                entry["fields"][dot] = _field(f)
            elif f.required:  # required if required in any operation
                existing["required"] = True

    capabilities = [
        {
            "capability": c["capability"],
            "operations": sorted(set(c["operations"])),
            "fields": list(c["fields"].values()),
        }
        for c in caps.values()
    ]
    capabilities.sort(key=lambda c: c["capability"])
    return {"ucp_version": version, "title": inv.title, "capabilities": capabilities}


def build_swagger_structure(swagger: dict[str, Any]) -> dict[str, Any]:
    """Parsed swagger -> endpoints + fields, for the right panel."""
    inv: SpecInventory = normalize(swagger)
    endpoints = [
        {
            "operationId": op.operation_id,
            "method": op.method,
            "path": op.path,
            "summary": op.summary,
            "request_fields": [_field(f) for f in op.request_fields],
            "response_fields": [_field(f) for f in op.response_fields],
        }
        for op in inv.operations
    ]
    return {"title": inv.title, "version": inv.version, "endpoints": endpoints}
