"""Vendor a BUILT UCP spec from ucp.dev into ucp_specs/<version>/.

Starts from the shopping REST OpenAPI and transitively downloads every `$ref`'d JSON-Schema,
mirroring the URL path layout under ucp_specs/<version>/ so the relative refs resolve locally
exactly as the loader (mapper/ucp_loader.py) expects.

Usage (from the Mapper/ directory):
    .\\.venv\\Scripts\\python.exe scripts\\vendor_ucp.py 2026-04-08
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

BASE = "https://ucp.dev"
ROOT = Path(__file__).resolve().parent.parent / "ucp_specs"


def _refs(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref" and isinstance(v, str):
                out.append(v)
            else:
                out.extend(_refs(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_refs(v))
    return out


def _local_path(version: str, url: str) -> Path:
    """Map a ucp.dev URL to a local path under ucp_specs/<version>/ (strip the version segment)."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if parts and parts[0] == version:
        parts = parts[1:]
    return ROOT / version / Path(*parts)


def vendor(version: str) -> None:
    start = f"{BASE}/{version}/services/shopping/rest.openapi.json"
    seen: set[str] = set()
    queue: list[str] = [start]
    skipped: list[str] = []
    count = 0

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        while queue:
            url = queue.pop().split("#", 1)[0]
            if url in seen:
                continue
            seen.add(url)

            # Only follow ucp.dev refs; external (e.g. shopify.dev) handlers are skipped.
            if not url.startswith(BASE + "/"):
                skipped.append(url)
                continue

            resp = client.get(url)
            if resp.status_code != 200:
                skipped.append(f"{url} (HTTP {resp.status_code})")
                continue

            doc = resp.json()
            dest = _local_path(version, url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            count += 1

            for ref in _refs(doc):
                if ref.startswith("#"):  # in-document pointer
                    continue
                target = urljoin(url, ref).split("#", 1)[0]
                if target not in seen:
                    queue.append(target)

    print(f"Vendored {count} files into {ROOT / version}")
    if skipped:
        print(f"Skipped {len(skipped)} ref(s):")
        for s in skipped[:20]:
            print("  -", s)


if __name__ == "__main__":
    vendor(sys.argv[1] if len(sys.argv) > 1 else "2026-04-08")
