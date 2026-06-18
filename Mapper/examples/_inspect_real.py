"""Inspect a vendored UCP inventory. Usage: _inspect_real.py [version]"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapper import registry

version = sys.argv[1] if len(sys.argv) > 1 else "2026-01-23"
inv = registry.load_ucp_inventory(version)
print(f"version: {version} | title: {inv.title}")
print(f"operations ({len(inv.operations)}):")
for op in inv.operations:
    print(f"  {op.method:5} {op.path:35} {op.operation_id:20} "
          f"req={len(op.request_fields):3} resp={len(op.response_fields):3}")
