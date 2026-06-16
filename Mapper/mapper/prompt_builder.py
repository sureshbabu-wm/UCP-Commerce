"""Build the provider-neutral prompt: SKILL.md + injected inventories.

To respect context budgets (D1) the prompt is built **per UCP operation**: only the target
operation's fields and the candidate client operations are injected, not the whole specs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .inventory import OperationInventory, SpecInventory

_SKILL_PATH = Path(__file__).resolve().parent.parent / "skill" / "SKILL.md"


def load_skill() -> str:
    return _SKILL_PATH.read_text(encoding="utf-8")


def _op_payload(op: OperationInventory) -> dict:
    return {
        "operationId": op.operation_id,
        "method": op.method,
        "path": op.path,
        "summary": op.summary,
        "request_fields": [f.model_dump(exclude_none=True) for f in op.request_fields],
        "response_fields": [f.model_dump(exclude_none=True) for f in op.response_fields],
    }


def build_messages(
    *,
    ucp_version: str,
    provider: str,
    ucp_op: OperationInventory,
    client: SpecInventory,
    rules: dict | None = None,
) -> list[dict]:
    """Return chat-style messages (system = skill, user = injected inputs)."""
    skill = load_skill()
    user_inputs = {
        "UCP_VERSION": ucp_version,
        "PROVIDER": provider,
        "UCP_INVENTORY": {ucp_op.operation_id: _op_payload(ucp_op)},
        "CLIENT_INVENTORY": [_op_payload(o) for o in client.operations],
        "RULES": rules or {},
    }
    user = (
        "Here are the injected inputs. Map the single UCP operation onto the client API and "
        "return ONLY the JSON object defined in the skill (no prose).\n\n"
        + json.dumps(user_inputs, indent=2)
    )
    return [
        {"role": "system", "content": skill},
        {"role": "user", "content": user},
    ]
