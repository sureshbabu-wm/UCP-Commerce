"""Inspect the real UCP inventory produced from the vendored official schemas."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapper import registry

inv = registry.load_ucp_inventory("2026-01-23")
print("title:", inv.title, "| version:", inv.version)
print("operations:", [o.operation_id for o in inv.operations])

op = inv.operation("create_checkout")
print(f"\ncreate_checkout: {len(op.request_fields)} request fields, {len(op.response_fields)} response fields")

print("\n-- request fields (path | type | req | unit/fmt) --")
for f in op.request_fields:
    extra = f.unit_hint or f.format_hint or ""
    print(f"  {f.path:48} {f.type:8} {'REQ' if f.required else '   '} {extra}")

print("\n-- response fields (first 40) --")
for f in op.response_fields[:40]:
    extra = f.unit_hint or f.format_hint or ""
    print(f"  {f.path:52} {f.type:8} {'REQ' if f.required else '   '} {extra}")

print("\n-- extension fields present in response? --")
for needle in ("discount", "fulfillment", "consent"):
    hits = [f.path for f in op.response_fields if needle in f.path]
    print(f"  {needle}: {hits[:6]}")
