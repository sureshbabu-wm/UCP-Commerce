"""Two-phase mapping tests using the offline phase-aware MockAdapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mapper import registry  # noqa: E402
from mapper.normalizer import normalize  # noqa: E402
from mapper.orchestrator import run_endpoint_mapping, run_field_mapping, run_mapping  # noqa: E402
from mapper.structures import build_swagger_structure, build_ucp_structure  # noqa: E402
from tests.mock_adapter import MockAdapter  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample_client_swagger.json"
VERSION = "2026-01-23"


@pytest.fixture
def client_swagger() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def mock() -> MockAdapter:
    return MockAdapter(api_key="unused")


# -- inventories / structures ----------------------------------------------
def test_ucp_inventory_loads_create_checkout():
    op = registry.load_ucp_inventory(VERSION).operation("create_checkout")
    assert op is not None
    assert "$.line_items[*].item.id" in {f.path for f in op.request_fields}
    price = next(f for f in op.response_fields if f.path == "$.line_items[*].item.price")
    assert price.unit_hint == "cents"


def test_client_swagger_normalizes(client_swagger):
    op = normalize(client_swagger).operation("createCart")
    assert op is not None and op.method == "POST" and op.path == "/api/cart"


def test_structures_for_ui(client_swagger):
    ucp = build_ucp_structure(VERSION)
    assert {c["capability"] for c in ucp["capabilities"]} >= {"CHECKOUT"}
    sw = build_swagger_structure(client_swagger)
    assert any(e["operationId"] == "createCart" for e in sw["endpoints"])


# -- phase 1 ---------------------------------------------------------------
def test_endpoint_phase(client_swagger, mock):
    res = run_endpoint_mapping(
        client_swagger=client_swagger, ucp_version=VERSION,
        provider="openai", api_key="unused", adapter=mock,
    )
    by_op = {e["ucp_operation"]: e for e in res["endpoint_mappings"]}
    assert by_op["create_checkout"]["status"] == "mapped"
    assert by_op["create_checkout"]["capability"] == "CHECKOUT"
    assert by_op["create_checkout"]["id"]  # stable row id for UI
    assert by_op["create_checkout"]["client_calls"][0]["operationId"] == "createCart"
    assert by_op["cancel_checkout"]["status"] == "unmapped"


# -- phase 2 + full --------------------------------------------------------
def test_field_phase_and_full(client_swagger, mock):
    mapping = run_mapping(
        client_swagger=client_swagger, ucp_version=VERSION,
        provider="openai", api_key="unused", adapter=mock,
    )
    resp = next(b for b in mapping["field_mappings"]
                if b["ucp_operation"] == "create_checkout" and b["direction"] == "response")
    assert resp["capability"] == "CHECKOUT"
    by_path = {f["target_path"]: f for f in resp["fields"]}

    # id reuses the client cart id (rule R1b)
    assert by_path["$.id"]["status"] == "mapped" and by_path["$.id"]["source_path"] == "$.cart_id"
    # server-authoritative fields injected as computed (rule R6)
    assert by_path["$.ucp"]["status"] == "computed"
    assert by_path["$.totals"]["status"] == "computed"
    # dollars -> cents (rule R2)
    assert by_path["$.line_items[*].item.price"]["transform"] == "cents_from_major"
    # every row carries a stable id
    assert all("id" in f for f in resp["fields"])

    cov = mapping["coverage"]
    assert cov["required_total"] > 0
    assert cov["mapped"] + cov["computed"] + cov["defaulted"] + cov["unmapped"] == cov["required_total"]
    assert "CHECKOUT" in cov["by_capability"]


def test_field_phase_respects_edited_endpoints(client_swagger, mock):
    """User edits in phase 1 flow into phase 2: an unmapped endpoint yields no field mappings."""
    edited = run_endpoint_mapping(
        client_swagger=client_swagger, ucp_version=VERSION,
        provider="openai", api_key="unused", adapter=mock,
    )["endpoint_mappings"]
    for em in edited:  # user unmaps create_checkout
        if em["ucp_operation"] == "create_checkout":
            em["status"], em["client_calls"] = "unmapped", []
    mapping = run_field_mapping(
        client_swagger=client_swagger, ucp_version=VERSION, endpoint_mappings=edited,
        provider="openai", api_key="unused", adapter=mock,
    )
    assert not any(b["ucp_operation"] == "create_checkout" for b in mapping["field_mappings"])


def test_unknown_version_raises(client_swagger, mock):
    with pytest.raises(registry.UnknownUcpVersionError):
        run_mapping(
            client_swagger=client_swagger, ucp_version="1999-01-01",
            provider="openai", api_key="unused", adapter=mock,
        )
