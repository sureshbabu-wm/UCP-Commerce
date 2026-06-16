"""End-to-end test of the create_checkout slice using the offline MockAdapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mapper import registry  # noqa: E402
from mapper.normalizer import normalize  # noqa: E402
from mapper.orchestrator import run_mapping  # noqa: E402
from tests.mock_adapter import MockAdapter  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample_client_swagger.json"


@pytest.fixture
def client_swagger() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_ucp_inventory_loads_create_checkout():
    inv = registry.load_ucp_inventory("2026-01-23")
    op = inv.operation("create_checkout")
    assert op is not None
    req_paths = {f.path for f in op.request_fields}
    resp_paths = {f.path for f in op.response_fields}
    assert "$.line_items[*].item.id" in req_paths
    assert "$.id" in resp_paths
    assert "$.totals" in resp_paths
    # cents unit hint detected on the price field
    price = next(f for f in op.response_fields if f.path == "$.line_items[*].item.price")
    assert price.unit_hint == "cents"


def test_client_swagger_normalizes(client_swagger):
    inv = normalize(client_swagger)
    op = inv.operation("createCart")
    assert op is not None
    assert op.method == "POST" and op.path == "/api/cart"
    assert {"$.products[*].sku", "$.products[*].qty"} <= {f.path for f in op.request_fields}


def test_run_mapping_slice(client_swagger):
    mapping = run_mapping(
        client_swagger=client_swagger,
        ucp_version="2026-01-23",
        provider="openai",
        api_key="unused",
        adapter=MockAdapter(api_key="unused"),
    )

    # endpoint mapping picked the cart-create op
    ep = mapping["endpoint_mappings"][0]
    assert ep["ucp_operation"] == "create_checkout"
    assert ep["client_calls"][0]["operationId"] == "createCart"

    # rule R1: server-authoritative fields forced to computed (no source)
    resp = next(b for b in mapping["field_mappings"] if b["direction"] == "response")
    by_path = {f["target_path"]: f for f in resp["fields"]}
    for sa in ("$.id", "$.ucp", "$.totals"):
        assert by_path[sa]["status"] == "computed"
        assert by_path[sa]["source_path"] is None

    # rule R2: dollars -> cents enforced for price
    assert by_path["$.line_items[*].item.price"]["transform"] == "cents_from_major"

    # coverage recomputed against required UCP fields; no required gaps in this fixture
    cov = mapping["coverage"]
    assert cov["required_total"] > 0
    assert cov["mapped"] + cov["computed"] + cov["defaulted"] + cov["unmapped"] == cov["required_total"]

    # low-confidence status mapping (0.6 boundary not included) and any gaps surface in review queue
    assert isinstance(mapping["review_queue"], list)


def test_full_surface_maps_all_operations(client_swagger):
    mapping = run_mapping(
        client_swagger=client_swagger,
        ucp_version="2026-01-23",
        provider="openai",
        api_key="unused",
        operation_id=None,  # full surface
        adapter=MockAdapter(api_key="unused"),
    )
    mapped_ops = {em["ucp_operation"] for em in mapping["endpoint_mappings"]}
    assert {"create_checkout", "get_checkout", "update_checkout", "complete_checkout", "cancel_checkout"} <= mapped_ops
    # coverage aggregates required fields across all operations
    assert mapping["coverage"]["required_total"] > 0
    cov = mapping["coverage"]
    assert cov["mapped"] + cov["computed"] + cov["defaulted"] + cov["unmapped"] == cov["required_total"]


def test_unknown_version_raises(client_swagger):
    with pytest.raises(registry.UnknownUcpVersionError):
        run_mapping(
            client_swagger=client_swagger,
            ucp_version="1999-01-01",
            provider="openai",
            api_key="unused",
            adapter=MockAdapter(api_key="unused"),
        )
