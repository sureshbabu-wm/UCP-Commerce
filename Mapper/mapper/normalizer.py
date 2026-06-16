"""Normalize an OpenAPI/JSON-Schema document into a SpecInventory.

Responsibilities:
- resolve local ``$ref`` (``#/components/schemas/...``),
- flatten ``allOf`` (UCP extensions compose via allOf),
- walk object/array schemas into flat JSONPath-addressed field descriptors,
- attach unit/format hints (cents vs major units, date-time, uri).

Scope note (vertical slice): handles a single self-contained OpenAPI 3.x document with
internal refs. External multi-file ``$ref`` resolution and Swagger 2.0 up-conversion are
documented follow-ups (D6).
"""

from __future__ import annotations

import re
from typing import Any

from .inventory import FieldDescriptor, OperationInventory, SpecInventory

_MONEY_NAME = re.compile(r"(price|amount|total|subtotal|cost|fee)", re.IGNORECASE)
_CENTS_DESC = re.compile(r"(minor unit|cents)", re.IGNORECASE)
_MAJOR_DESC = re.compile(r"(major unit|dollars)", re.IGNORECASE)
_MAX_DEPTH = 8


def detect_hints(name: str, prop: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (unit_hint, format_hint) for a property. Shared by the swagger and UCP loaders."""
    fmt = prop.get("format")
    unit = None
    desc = prop.get("description", "") or ""
    ptype = prop.get("type")
    if isinstance(ptype, list):
        ptype = next((t for t in ptype if t != "null"), ptype[0] if ptype else None)
    if ptype in ("integer", "number") and (_MONEY_NAME.search(name) or _MONEY_NAME.search(desc)):
        if _CENTS_DESC.search(desc) or ptype == "integer":
            unit = "cents"
        elif _MAJOR_DESC.search(desc) or ptype == "number":
            unit = "major_units"
    return unit, fmt


class Normalizer:
    def __init__(self, doc: dict[str, Any]):
        self.doc = doc
        self._schemas: dict[str, Any] = doc.get("components", {}).get("schemas", {})

    # -- ref / allOf resolution ------------------------------------------------
    def _resolve(self, schema: dict[str, Any], _seen: tuple[str, ...] = ()) -> dict[str, Any]:
        """Resolve a single $ref one level (guards against ref cycles)."""
        ref = schema.get("$ref")
        if not ref:
            return schema
        name = ref.split("/")[-1]
        if name in _seen:  # cycle guard
            return {"type": "object"}
        target = self._schemas.get(name, {})
        return self._resolve(target, _seen + (name,)) if "$ref" in target else target

    def _merge_all_of(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Flatten allOf members into a single object schema (shallow merge)."""
        if "allOf" not in schema:
            return schema
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for sub in schema["allOf"]:
            sub = self._resolve(sub)
            sub = self._merge_all_of(sub)
            merged["properties"].update(sub.get("properties", {}))
            merged["required"].extend(sub.get("required", []))
        # keep any sibling properties on the schema itself
        merged["properties"].update(schema.get("properties", {}))
        merged["required"].extend(schema.get("required", []))
        return merged

    # -- field walking ---------------------------------------------------------
    def _hints(self, name: str, prop: dict[str, Any]) -> tuple[str | None, str | None]:
        return detect_hints(name, prop)

    def _walk(
        self, schema: dict[str, Any], path: str, required: bool, out: list[FieldDescriptor], depth: int
    ) -> None:
        if depth > _MAX_DEPTH:
            return
        schema = self._resolve(schema)
        schema = self._merge_all_of(schema)
        stype = schema.get("type")
        if isinstance(stype, list):  # e.g. ["string", "null"]
            stype = next((t for t in stype if t != "null"), stype[0])

        if stype == "object" or "properties" in schema:
            props = schema.get("properties", {})
            req = set(schema.get("required", []))
            for name, prop in props.items():
                child_path = f"{path}.{name}"
                resolved = self._resolve(prop)
                resolved = self._merge_all_of(resolved)
                rtype = resolved.get("type")
                if isinstance(rtype, list):
                    rtype = next((t for t in rtype if t != "null"), rtype[0])
                is_req = name in req
                # Emit a descriptor for the field itself (leaf or container).
                if rtype in ("object", "array") or "properties" in resolved or "items" in resolved:
                    unit, fmt = self._hints(name, resolved)
                    out.append(
                        FieldDescriptor(
                            path=child_path,
                            type=rtype or "object",
                            required=is_req,
                            enum=resolved.get("enum"),
                            description=resolved.get("description"),
                            unit_hint=unit,
                            format_hint=fmt,
                        )
                    )
                    self._walk(resolved, child_path, is_req, out, depth + 1)
                else:
                    unit, fmt = self._hints(name, resolved)
                    out.append(
                        FieldDescriptor(
                            path=child_path,
                            type=rtype or "string",
                            required=is_req,
                            enum=resolved.get("enum"),
                            description=resolved.get("description"),
                            unit_hint=unit,
                            format_hint=fmt,
                        )
                    )
        elif stype == "array":
            items = self._resolve(schema.get("items", {}))
            self._walk(items, f"{path}[*]", required, out, depth + 1)

    # -- public API ------------------------------------------------------------
    def _body_schema(self, operation: dict[str, Any]) -> dict[str, Any] | None:
        body = operation.get("requestBody", {})
        content = body.get("content", {}).get("application/json", {})
        return content.get("schema")

    def _response_schema(self, operation: dict[str, Any]) -> dict[str, Any] | None:
        responses = operation.get("responses", {})
        for code in ("200", "201", "default"):
            if code in responses:
                content = responses[code].get("content", {}).get("application/json", {})
                if content.get("schema"):
                    return content["schema"]
        # fall back to first 2xx
        for code, resp in responses.items():
            if str(code).startswith("2"):
                content = resp.get("content", {}).get("application/json", {})
                if content.get("schema"):
                    return content["schema"]
        return None

    def build(self) -> SpecInventory:
        info = self.doc.get("info", {})
        inv = SpecInventory(title=info.get("title"), version=str(info.get("version")) if info.get("version") else None)
        for path, methods in self.doc.get("paths", {}).items():
            for method, op in methods.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                op_id = op.get("operationId") or f"{method.lower()}_{path}"
                req_fields: list[FieldDescriptor] = []
                resp_fields: list[FieldDescriptor] = []
                rb = self._body_schema(op)
                if rb:
                    self._walk(rb, "$", True, req_fields, 0)
                rs = self._response_schema(op)
                if rs:
                    self._walk(rs, "$", True, resp_fields, 0)
                inv.operations.append(
                    OperationInventory(
                        operation_id=op_id,
                        method=method.upper(),
                        path=path,
                        summary=op.get("summary"),
                        request_fields=req_fields,
                        response_fields=resp_fields,
                    )
                )
        return inv


def normalize(doc: dict[str, Any]) -> SpecInventory:
    return Normalizer(doc).build()
