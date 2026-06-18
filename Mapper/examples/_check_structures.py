"""Quick check of the UCP + swagger structure builders."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapper.structures import build_swagger_structure, build_ucp_structure

ucp = build_ucp_structure("2026-04-08")
print("=== UCP structure (2026-04-08) ===")
for c in ucp["capabilities"]:
    print(f'  {c["capability"]:16} ops={c["operations"]}  fields={len(c["fields"])}')

sw = json.load(open("tests/fixtures/sample_client_swagger.json", encoding="utf-8"))
s = build_swagger_structure(sw)
print("\n=== swagger structure (Acme sample) ===")
print("  title:", s["title"])
for ep in s["endpoints"]:
    print(f'  {ep["method"]:5} {ep["path"]:20} req={len(ep["request_fields"])} resp={len(ep["response_fields"])}')
print("\n  sample fields of", s["endpoints"][0]["operationId"], ":",
      [f["path"] for f in s["endpoints"][0]["request_fields"][:5]])
