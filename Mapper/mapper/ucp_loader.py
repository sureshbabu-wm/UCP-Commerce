"""Load the official UCP spec (vendored under ucp_specs/<version>/) into a SpecInventory.

Supports BOTH vendored structures:

* **2026-01-23 style** — pre-split per-operation variant files (`checkout.create_req.json`,
  `checkout_resp.json`), separate extension files (`discount_resp.json` …) composed via `$defs.checkout`,
  relative `$ref`s.
* **2026-04-08+ style** — a single `checkout.json`/`cart.json` with per-field `ucp_request`
  annotations (`omit` | `optional` | `required` | `{create|update|complete: …}`) that derive the
  request variant per operation; `oneOf` (success|error) responses; catalog/cart/order via `$defs`
  sub-schemas; absolute `https://ucp.dev/...` `$ref`s.

Strategy: resolve each operation's request/response component to a target schema ref, optionally
compose checkout extensions, **bundle** (recursively inline every `$ref`, across files, with cycle/
depth guards), then **walk** to FieldDescriptors. For request fields, `ucp_request` is honored for
the operation's mode (create/update/complete); response fields include the full object.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .inventory import FieldDescriptor, OperationInventory, SpecInventory
from .normalizer import detect_hints

_MAX_DEPTH = 14
_KEEP = ("type", "description", "format", "enum")
_CHECKOUT_EXTENSIONS = ("discount", "fulfillment", "buyer_consent")


class UcpSpecLoader:
    def __init__(self, version_dir: Path):
        self.root = Path(version_dir).resolve()
        self.version = self.root.name  # e.g. "2026-04-08"
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

    def _url_to_local(self, url: str) -> Path:
        """Map an absolute ucp.dev URL to its vendored local path (strip host + version segment)."""
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts and parts[0] == self.version:
            parts = parts[1:]
        return self.root.joinpath(*parts).resolve()

    def _resolve_ref(self, ref: str, base: Path) -> tuple[Any, Path]:
        file_part, _, pointer = ref.partition("#")
        if file_part:
            if file_part.startswith(("http://", "https://")):
                base = self._url_to_local(file_part)
            else:
                base = (base.parent / file_part).resolve()
        doc = self._load(base)
        node = self._pointer(doc, pointer) if pointer else doc
        return node, base

    # -- bundling (recursive inline) -------------------------------------------
    def _bundle(self, schema: Any, base: Path, seen: frozenset, depth: int) -> dict:
        if depth > _MAX_DEPTH or not isinstance(schema, dict):
            return {"type": "object"} if depth > _MAX_DEPTH else (schema or {})

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
                merged["properties"][name] = self._bundle_prop(prop, base, seen, depth)
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
                name: self._bundle_prop(prop, base, seen, depth)
                for name, prop in (schema.get("properties") or {}).items()
            }
            return out

        if stype == "array":
            out = {k: schema[k] for k in _KEEP if k in schema}
            out["type"] = "array"
            out["items"] = self._bundle(schema.get("items", {}), base, seen, depth + 1)
            return out

        return {k: schema[k] for k in _KEEP if k in schema}

    def _bundle_prop(self, prop: Any, base: Path, seen: frozenset, depth: int) -> dict:
        """Bundle a property and preserve its ``ucp_request`` annotation (sibling of $ref)."""
        b = self._bundle(prop, base, seen, depth + 1)
        if isinstance(prop, dict) and "ucp_request" in prop:
            b["ucp_request"] = prop["ucp_request"]
        return b

    # -- walking a bundled (ref-free) schema -----------------------------------
    def _walk(self, schema: dict, path: str, out: list[FieldDescriptor], depth: int, mode: str | None) -> None:
        if depth > _MAX_DEPTH:
            return
        stype = schema.get("type")
        if stype == "object" or "properties" in schema:
            req = set(schema.get("required", []))
            for name, prop in (schema.get("properties") or {}).items():
                ucpr = prop.get("ucp_request")
                if mode and ucpr is not None:  # request side: honor ucp_request
                    val = ucpr.get(mode, "omit") if isinstance(ucpr, dict) else ucpr
                    if val == "omit":
                        continue
                    required = val == "required"
                else:
                    required = name in req
                cp = f"{path}.{name}"
                rtype = prop.get("type")
                if isinstance(rtype, list):
                    rtype = next((t for t in rtype if t != "null"), rtype[0] if rtype else None)
                container = rtype in ("object", "array") or "properties" in prop or "items" in prop
                unit, fmt = detect_hints(name, prop)
                out.append(FieldDescriptor(
                    path=cp,
                    type=rtype or ("object" if container else "string"),
                    required=required,
                    enum=prop.get("enum"),
                    description=prop.get("description"),
                    unit_hint=unit,
                    format_hint=fmt,
                ))
                if container:
                    self._walk(prop, cp, out, depth + 1, mode)
        elif stype == "array":
            self._walk(schema.get("items", {}), f"{path}[*]", out, depth + 1, mode)

    # -- component resolution + composition ------------------------------------
    def _component_target_ref(self, component_ref: str) -> str | None:
        """Resolve an OpenAPI '#/components/schemas/x' to the underlying schema $ref string.

        Handles a direct ``$ref`` and a ``oneOf`` (picks the non-error / success branch).
        """
        comp = self._pointer(self._load(self.openapi_path), component_ref.lstrip("#"))
        if not isinstance(comp, dict):
            return None
        if comp.get("$ref"):
            return comp["$ref"]
        if "oneOf" in comp:
            refs = [m.get("$ref") for m in comp["oneOf"] if isinstance(m, dict) and m.get("$ref")]
            for r in refs:
                if "error" not in r.lower():
                    return r
            return refs[0] if refs else None
        return None

    def _local_file_of(self, ref: str) -> Path:
        file_part = ref.split("#", 1)[0]
        if file_part.startswith(("http://", "https://")):
            return self._url_to_local(file_part)
        return (self.openapi_path.parent / file_part).resolve()

    def _maybe_compose(self, target_ref: str) -> dict:
        """Compose checkout extensions onto a checkout base (2026-01-23 style); else pass through.

        The primary member is anchored to the resolved ABSOLUTE file path (keeping any #-pointer) so
        the bundler resolves it regardless of relative-vs-absolute origin.
        """
        base_file = self._local_file_of(target_ref)
        _, _, pointer = target_ref.partition("#")
        abs_ref = f"{base_file}#{pointer}" if pointer else str(base_file)
        members: list[dict] = [{"$ref": abs_ref}]
        if "checkout" in base_file.name:
            for ext in _CHECKOUT_EXTENSIONS:
                ext_file = self.shopping_dir / base_file.name.replace("checkout", ext, 1)
                if ext_file.exists() and "checkout" in self._load(ext_file).get("$defs", {}):
                    members.append({"$ref": f"{ext_file}#/$defs/checkout"})
        return {"allOf": members} if len(members) > 1 else {"$ref": abs_ref}

    def _fields_for(self, component_ref: str | None, mode: str | None) -> list[FieldDescriptor]:
        if not component_ref:
            return []
        target_ref = self._component_target_ref(component_ref)
        if not target_ref:
            return []
        composed = self._maybe_compose(target_ref)
        bundled = self._bundle(composed, self.openapi_path.parent, frozenset(), 0)
        out: list[FieldDescriptor] = []
        self._walk(bundled, "$", out, 0, mode)
        return _dedupe(out)

    # -- public API ------------------------------------------------------------
    @staticmethod
    def _mode_for(op_id: str) -> str:
        if op_id.startswith("create_") or op_id.startswith("search_") or op_id.startswith("lookup_") or op_id.startswith("get_product"):
            return "create"
        if op_id.startswith("update_"):
            return "update"
        if op_id.startswith("complete_"):
            return "complete"
        return "create"

    def build(self) -> SpecInventory:
        openapi = self._load(self.openapi_path)
        info = openapi.get("info", {})
        inv = SpecInventory(title=info.get("title"), version=info.get("version"))

        for path, methods in openapi.get("paths", {}).items():
            for method, op in methods.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                op_id = op.get("operationId") or f"{method.lower()}_{path}"
                inv.operations.append(OperationInventory(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=op.get("summary"),
                    request_fields=self._fields_for(self._request_ref(op), self._mode_for(op_id)),
                    response_fields=self._fields_for(self._response_ref(op), None),
                ))
        return inv

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
