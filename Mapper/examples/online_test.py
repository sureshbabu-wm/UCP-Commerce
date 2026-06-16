r"""Online end-to-end test against a real provider (default: OpenAI).

Reads the API key from (in order): env var, then a local gitignored `.env` file.
Run from the Mapper/ directory:

    .\.venv\Scripts\python.exe examples\online_test.py
    .\.venv\Scripts\python.exe examples\online_test.py --provider openai --model gpt-4o
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mapper.orchestrator import run_mapping  # noqa: E402
from mapper.providers import get_adapter  # noqa: E402

_ENV_KEYS = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


def load_env_file(path: str) -> None:
    """Minimal .env loader (KEY=VALUE per line) into os.environ if not already set."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai", choices=["openai", "claude", "gemini"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--ucp-version", default="2026-01-23")
    ap.add_argument("--operation", default="create_checkout", help="UCP operation to map")
    ap.add_argument("--full", action="store_true", help="Map the full UCP surface (all operations)")
    ap.add_argument("--swagger", default=os.path.join(ROOT, "tests", "fixtures", "sample_client_swagger.json"))
    args = ap.parse_args()
    operation_id = None if args.full else args.operation

    load_env_file(os.path.join(ROOT, ".env"))
    env_key = _ENV_KEYS[args.provider]
    api_key = os.environ.get(env_key)
    if not api_key:
        print(f"ERROR: no API key. Set {env_key} in env or in Mapper/.env", file=sys.stderr)
        return 2

    swagger = json.load(open(args.swagger, encoding="utf-8"))
    adapter = get_adapter(args.provider, api_key, model=args.model) if args.model else None

    scope = "full surface" if args.full else operation_id
    print(f"Calling {args.provider} (model={args.model or 'default'}) for {scope} ...", file=sys.stderr)
    mapping = run_mapping(
        client_swagger=swagger,
        ucp_version=args.ucp_version,
        provider=args.provider,
        api_key=api_key,
        operation_id=operation_id,
        adapter=adapter,
    )

    suffix = "full" if args.full else operation_id
    out_path = os.path.join(ROOT, "examples", f"online_mapping.{args.provider}.{suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)

    print("\n=== RESULT ===")
    for ep in mapping["endpoint_mappings"]:
        calls = ", ".join(f'{c["method"]} {c["path"]}' for c in ep["client_calls"]) or "(none)"
        print(f'endpoint: {ep["ucp_operation"]} [{ep["status"]}] -> {calls} (conf={ep.get("confidence")})')
    print("coverage:", json.dumps(mapping["coverage"]))
    print("review_queue:", len(mapping["review_queue"]), "item(s)")
    for r in mapping["review_queue"]:
        print(f'  - [{r["ucp_operation"]}] {r["target_path"]} | {r["reason"]}')
    print("\nfull artifact written to:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
