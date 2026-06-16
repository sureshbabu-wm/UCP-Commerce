"""Generate a sample mapping artifact using the offline MockAdapter."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapper.orchestrator import run_mapping
from tests.mock_adapter import MockAdapter

sw = json.load(open("tests/fixtures/sample_client_swagger.json", encoding="utf-8"))
m = run_mapping(
    client_swagger=sw,
    ucp_version="2026-01-23",
    provider="openai",
    api_key="unused",
    adapter=MockAdapter(api_key="unused"),
)
os.makedirs("examples", exist_ok=True)
with open("examples/sample_mapping.create_checkout.json", "w", encoding="utf-8") as f:
    json.dump(m, f, indent=2)

print("COVERAGE:", json.dumps(m["coverage"]))
ep = m["endpoint_mappings"][0]
print("ENDPOINT:", ep["ucp_operation"], "->", ep["client_calls"][0]["path"])
print("REVIEW_QUEUE_ITEMS:", len(m["review_queue"]))
for r in m["review_queue"]:
    print("  -", r["target_path"], "|", r["reason"])
