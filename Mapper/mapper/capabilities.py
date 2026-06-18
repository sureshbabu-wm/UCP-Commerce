"""Map UCP operations to UI-facing capability groups (left-panel grouping).

The UI groups UCP fields by capability (CHECKOUT, CART, CATALOG.*, ORDER). This module is the single
source of that operation -> capability mapping, used by the structure + mapping endpoints.
"""

from __future__ import annotations

OPERATION_CAPABILITY: dict[str, str] = {
    "create_checkout": "CHECKOUT",
    "get_checkout": "CHECKOUT",
    "update_checkout": "CHECKOUT",
    "complete_checkout": "CHECKOUT",
    "cancel_checkout": "CHECKOUT",
    "create_cart": "CART",
    "get_cart": "CART",
    "update_cart": "CART",
    "cancel_cart": "CART",
    "search_catalog": "CATALOG.SEARCH",
    "lookup_catalog": "CATALOG.LOOKUP",
    "get_product": "CATALOG.LOOKUP",
    "get_order": "ORDER",
    "order_event_webhook": "ORDER",
}


def capability_for(operation_id: str) -> str:
    """Capability group for a UCP operation (falls back to a derived label)."""
    if operation_id in OPERATION_CAPABILITY:
        return OPERATION_CAPABILITY[operation_id]
    # Fallback: e.g. "do_thing" -> "THING"
    return operation_id.rsplit("_", 1)[-1].upper()
