"""Load the REAL official UCP spec (vendored under ucp_specs/<version>/) into a SpecInventory.

The official spec is multi-file: the REST OpenAPI (`services/shopping/rest.openapi.json`) points
at per-operation variant schemas (`schemas/shopping/checkout.create_req.json`, `checkout_resp.json`,
…) which reference type schemas by **relative path** (`types/line_item.json`, `../ucp.json#/$defs/…`).
Extensions are separate files (`discount_resp.json`, `fulfillment_resp.json`, `buyer_consent_resp.json`)
each exposing a `$defs.checkout` that `allOf`-composes its delta onto the base checkout.

Strategy: **bundle then walk**. ``_bundle`` recursively inlines every ``$ref`` (across files,
tracking the base path so relative refs resolve correctly) and flattens ``allOf`` into a single
self-contained schema with no refs; ``_walk`` then turns that into FieldDescriptors — the same
inventory shape the swagger normalizer produces, so everything downstream is unchanged.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .inventory import FieldDescriptor, OperationInventory, SpecInventory
from .normalizer import detect_hints

_MAX_DEPTH = 14
_KEEP = ("type", "description", "format", "enum")

# Checkout extensions composed onto the base checkout surface (declared in the sample discovery
# profile). Each maps the "checkout" filename stem -> "<ext>".
_CHECKOUT_EXTENSIONS = ("discount", "fulfillment", "buyer_consent")


class UcpSpecLoader:
    def __init__(self, version_dir: Path):
        self.root = Path(version_dir)
        self.openapi_path = (self.root / "services" / "shopping" / "rest.openapi.json").resolve()
        self.shopping_dir = (self.root / "schemas" / "shopping").resolve()
        self._files: dict[Path, Any] = {}

    # -- file + ref resolution -------------------------------------------------
    def _load(self, path: Path) -> Any:
        path = path.resolve()
        if path not in self._files:
            self._files[path] = json.loads(path.read_text(encoding="utf-8"))
        return self._files[path]

    @staticmethod
    def _pointer(doc: Any, pointer: str) -> Any:
        node = doc
        for tok in pointer.strip("/").split("/"):
            if tok == "":
                continue
            node = node[tok.replace("~1", "/").replace("~0", "~")]
        return node

    def _resolve_ref(self, ref: str, base: Path) -> tuple[Any, Path]:
        file_part, _, pointer = ref.partition("#")
        if file_part:
            base = (base.parent / file_part).resolve()
        doc = self._load(base)
        node = self._pointer(doc, pointer) if pointer else doc
        return node, base

    # -- bundling (recursive inline) -------------------------------------------
    def _bundle(self, schema: Any, base: Path, seen: frozenset, depth: int) -> dict:
        if depth > _MAX_DEPTH or not isinstance(schema, dict):
            return {"type": "object"} if depth > _MAX_DEPTH else (schema or {})

        # Follow $ref chains, merging sibling keywords (description/ucp_request live alongside $ref).
        while "$ref" in schema:
            ref = schema["$ref"]
            key = (str(base), ref)
            if key in seen:
                return {"type": "object"}  # cycle guard
            seen = seen | {key}
            target, base = self._resolve_ref(ref, base)
            siblings = {k: v for k, v in schema.items() if k != "$ref"}
            schema = {**(target if isinstance(target, dict) else {}), **siblings}

        if "allOf" in schema:
            merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
            for sub in schema["allOf"]:
                b = self._bundle(sub, base, seen, depth + 1)
                merged["properties"].update(b.get("properties", {}))
                merged["required"].extend(b.get("required", []))
            for name, prop in (schema.get("properties") or {}).items():
                merged["properties"][name] = self._bundle(prop, base, seen, depth + 1)
            merged["required"].extend(schema.get("required", []))
            for k in _KEEP:
                if k in schema and k != "type":
                    merged[k] = schema[k]
            return merged

        stype = schema.get("type")
        if isinstance(stype, list):
            stype = next((t for t in stype if t != "null"), stype[0] if stype else None)

        if stype == "object" or "properties" in schema:
            out = {k: schema[k] for k in _KEEP if k in schema}
            out["type"] = "object"
            if "required" in schema:
                out["required"] = schema["required"]
            out["properties"] = {
                name: self._bundle(prop, base, seen, depth + 1)
                for name, prop in (schema.get("properties") or {}).items()
            }
            return out

        if stype == "array":
            out = {k: schema[k] for k in _KEEP if k in schema}
            out["type"] = "array"
            out["items"] = self._bundle(schema.get("items", {}), base, seen, depth + 1)
            return out

        return {k: schema[k] for k in _KEEP if k in schema}

    # -- walking a bundled (ref-free) schema -----------------------------------
    def _walk(self, schema: dict, path: str, out: list[FieldDescriptor], depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        stype = schema.get("type")
        if stype == "object" or "properties" in schema:
            req = set(schema.get("required", []))
            for name, prop in (schema.get("properties") or {}).items():
                cp = f"{path}.{name}"
                rtype = prop.get("type")
                if isinstance(rtype, list):
                    rtype = next((t for t in rtype if t != "null"), rtype[0] if rtype else None)
                container = rtype in ("object", "array") or "properties" in prop or "items" in prop
                unit, fmt = detect_hints(name, prop)
                out.append(FieldDescriptor(
                    path=cp,
                    type=rtype or ("object" if container else "string"),
                    required=name in req,
                    enum=prop.get("enum"),
                    description=prop.get("description"),
                    unit_hint=unit,
                    format_hint=fmt,
                ))
                if container:
                    self._walk(prop, cp, out, depth + 1)
        elif stype == "array":
            self._walk(schema.get("items", {}), f"{path}[*]", out, depth + 1)

    # -- composition + public API ---------------------------------------------
    def _compose(self, base_file: Path, extensions: tuple[str, ...]) -> dict:
        """allOf of the base variant schema + each extension's $defs/checkout (when present)."""
        members: list[dict] = [{"$ref": str(base_file)}]
        for ext in extensions:
            ext_file = self.shopping_dir / base_file.name.replace("checkout", ext, 1)
            if ext_file.exists() and "checkout" in self._load(ext_file).get("$defs", {}):
                members.append({"$ref": f"{ext_file}#/$defs/checkout"})
        return {"allOf": members}

    def _variant_file(self, component_ref: str) -> Path | None:
        """'#/components/schemas/x' -> the external variant file it points to (absolute path)."""
        comp = self._pointer(self._load(self.openapi_path), component_ref.lstrip("#"))
        if not (isinstance(comp, dict) and comp.get("$ref")):
            return None
        return (self.openapi_path.parent / comp["$ref"]).resolve()

    def build(self) -> SpecInventory:
        openapi = self._load(self.openapi_path)
        info = openapi.get("info", {})
        inv = SpecInventory(title=info.get("title"), version=info.get("version"))

        for path, methods in openapi.get("paths", {}).items():
            for method, op in methods.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                inv.operations.append(OperationInventory(
                    operation_id=op.get("operationId") or f"{method.lower()}_{path}",
                    method=method.upper(),
                    path=path,
                    summary=op.get("summary"),
                    request_fields=self._fields_for(self._request_ref(op)),
                    response_fields=self._fields_for(self._response_ref(op)),
                ))
        return inv

    def _fields_for(self, component_ref: str | None) -> list[FieldDescriptor]:
        if not component_ref:
            return []
        base_file = self._variant_file(component_ref)
        if not base_file:
            return []
        composed = self._compose(base_file, _CHECKOUT_EXTENSIONS)
        bundled = self._bundle(composed, self.openapi_path.parent, frozenset(), 0)
        out: list[FieldDescriptor] = []
        self._walk(bundled, "$", out, 0)
        return _dedupe(out)

    @staticmethod
    def _request_ref(op: dict) -> str | None:
        s = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
        return s.get("$ref") if isinstance(s, dict) else None

    @staticmethod
    def _response_ref(op: dict) -> str | None:
        responses = op.get("responses", {})
        for code in ("200", "201", "default"):
            if code in responses:
                s = responses[code].get("content", {}).get("application/json", {}).get("schema")
                if isinstance(s, dict) and s.get("$ref"):
                    return s["$ref"]
        for code, resp in responses.items():
            if str(code).startswith("2"):
                s = resp.get("content", {}).get("application/json", {}).get("schema")
                if isinstance(s, dict) and s.get("$ref"):
                    return s["$ref"]
        return None


def _dedupe(fields: list[FieldDescriptor]) -> list[FieldDescriptor]:
    """Collapse duplicate paths (extensions re-include base props); first occurrence wins."""
    seen: set[str] = set()
    out: list[FieldDescriptor] = []
    for f in fields:
        if f.path not in seen:
            seen.add(f.path)
            out.append(f)
    return out


@lru_cache(maxsize=8)
def load_real_ucp_inventory(version_dir_str: str) -> SpecInventory:
    return UcpSpecLoader(Path(version_dir_str)).build()
