"""Extract the client_swagger object from the local test doc and save it as a fixture.

Usage: python scripts/extract_swagger.py "<path-to-doc.txt>" [out.json]
"""

from __future__ import annotations

import json
import os
import sys

doc_path = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\sureshbabum_500214\Downloads\Request_Response_Business_Scenario.txt"
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "tests", "fixtures", "quickmobile_swagger.json")

text = open(doc_path, encoding="utf-8").read()

i = text.find('"client_swagger"')
if i == -1:
    raise SystemExit("No client_swagger found in the doc")
colon = text.index(":", i)
brace = text.index("{", colon)
# raw_decode is JSON-string-aware (braces inside string values won't fool it)
swagger, _ = json.JSONDecoder().raw_decode(text, brace)

os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(swagger, f, indent=2)

ops = []
for path, methods in swagger.get("paths", {}).items():
    for m, op in methods.items():
        if m.lower() in ("get", "post", "put", "patch", "delete"):
            ops.append(f"{m.upper()} {path} ({op.get('operationId')})")
print("title:", swagger.get("info", {}).get("title"))
print("servers:", [s.get("url") for s in swagger.get("servers", [])])
print("operations:", ops)
print("schemas:", list(swagger.get("components", {}).get("schemas", {}).keys()))
print("wrote", out_path)
