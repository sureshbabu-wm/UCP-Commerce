"""Generate a Postman v2.1 collection for the UCP Mapper API.

Embeds the sample Acme swagger, uses collection variables for base_url / ucp_version / provider /
api_key, and chains phase 1 -> phase 2 (the /map/endpoints response is saved into the
`endpoint_mappings` variable that /map/fields consumes).

Run:  .\.venv\Scripts\python.exe scripts\gen_postman.py
Output: postman/UCP-Mapper.postman_collection.json
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWAGGER = json.load(open(os.path.join(ROOT, "tests", "fixtures", "sample_client_swagger.json"), encoding="utf-8"))

EP_TOKEN = "__ENDPOINT_MAPPINGS__"  # replaced with the unquoted {{endpoint_mappings}} variable


def url(*segments: str) -> dict:
    return {
        "raw": "{{base_url}}/" + "/".join(segments),
        "host": ["{{base_url}}"],
        "path": list(segments),
    }


def raw_body(obj: dict) -> dict:
    text = json.dumps(obj, indent=2)
    text = text.replace(f'"{EP_TOKEN}"', "{{endpoint_mappings}}")  # inject as JSON array, unquoted
    return {"mode": "raw", "raw": text, "options": {"raw": {"language": "json"}}}


def post(name, path_segments, body, desc, events=None):
    item = {
        "name": name,
        "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": raw_body(body),
            "url": url(*path_segments),
            "description": desc,
        },
        "response": [],
    }
    if events:
        item["event"] = events
    return item


def get(name, path_segments, desc):
    return {
        "name": name,
        "request": {"method": "GET", "header": [], "url": url(*path_segments), "description": desc},
        "response": [],
    }


map_req = {
    "client_swagger": SWAGGER,
    "ucp_version": "{{ucp_version}}",
    "provider": "{{provider}}",
    "api_key": "{{api_key}}",
}
fields_req = {**map_req, "endpoint_mappings": EP_TOKEN}

save_eps_event = [{
    "listen": "test",
    "script": {
        "type": "text/javascript",
        "exec": [
            "// Save phase-1 endpoint_mappings so '2b. Field Mapping' can reuse (and you can edit) them",
            "if (pm.response.code === 200) {",
            "  pm.collectionVariables.set('endpoint_mappings', JSON.stringify(pm.response.json().endpoint_mappings));",
            "  console.log('Saved endpoint_mappings for the field-mapping step.');",
            "}",
        ],
    },
}]

collection = {
    "info": {
        "_postman_id": "ucp-mapper-collection-0001",
        "name": "UCP Mapper API",
        "description": (
            "Test the UCP Mapper service.\n\n"
            "Set the `api_key` collection variable to your real OpenAI key before running the "
            "mapping requests. `/versions`, `/ucp/.../structure` and `/swagger/parse` need no key.\n\n"
            "Recommended order: 1) Versions 2) UCP Structure 3) Parse Swagger 4) Endpoint Mapping "
            "(saves endpoint_mappings) 5) Field Mapping (reuses them) — or just run Full Mapping."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "base_url", "value": "http://localhost:8000"},
        {"key": "ucp_version", "value": "2026-04-08"},
        {"key": "provider", "value": "openai"},
        {"key": "api_key", "value": ""},
        {"key": "endpoint_mappings", "value": "[]"},
    ],
    "item": [
        get("1. Versions", ["versions"], "List vendored UCP versions. No key needed."),
        get("2. UCP Structure", ["ucp", "{{ucp_version}}", "structure"],
            "UCP capabilities -> operations + fields (left panel + dropdowns). No key needed."),
        post("3. Parse Swagger", ["swagger", "parse"], {"swagger": SWAGGER},
             "Parse the client swagger into endpoints + fields (right panel). No key needed."),
        post("4a. Endpoint Mapping (phase 1)", ["map", "endpoints"], map_req,
             "Phase 1: map UCP operations to client endpoints (cheap). Saves endpoint_mappings "
             "into a collection variable for the next step. Needs api_key.",
             events=save_eps_event),
        post("4b. Field Mapping (phase 2)", ["map", "fields"], fields_req,
             "Phase 2: field mappings for the (possibly edited) endpoint_mappings from phase 1. "
             "Run 4a first. Needs api_key."),
        post("5. Full Mapping (phase 1 + 2)", ["map"], map_req,
             "Runs both phases and returns the full artifact. Needs api_key."),
    ],
}

out_dir = os.path.join(ROOT, "postman")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, "UCP-Mapper.postman_collection.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(collection, f, indent=2)
print("wrote", out)
