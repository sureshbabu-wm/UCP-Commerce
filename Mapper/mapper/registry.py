"""UCP spec registry — load a vendored UCP spec by version and normalize it.

The version is parameterized: specs live under ``ucp_specs/<version>/``. Two layouts are supported:
- **Official multi-file spec** (preferred): ``services/shopping/rest.openapi.json`` + ``schemas/**``
  vendored from the ``Universal-Commerce-Protocol/ucp`` ``release/<version>`` branch. Loaded via
  the multi-file resolver in :mod:`mapper.ucp_loader`.
- **Single self-contained ``openapi.json``** (legacy/compact fallback) handled by the normalizer.
"""

from __future__ import annotations

import json
from pathlib import Path

from .inventory import SpecInventory
from .normalizer import normalize
from .ucp_loader import load_real_ucp_inventory

_SPECS_DIR = Path(__file__).resolve().parent.parent / "ucp_specs"


class UnknownUcpVersionError(ValueError):
    pass


def available_versions() -> list[str]:
    if not _SPECS_DIR.exists():
        return []
    return sorted(p.name for p in _SPECS_DIR.iterdir() if p.is_dir())


def load_ucp_inventory(version: str) -> SpecInventory:
    """Return the normalized UCP target inventory for ``version``."""
    version_dir = _SPECS_DIR / version
    official = version_dir / "services" / "shopping" / "rest.openapi.json"
    if official.exists():
        inv = load_real_ucp_inventory(str(version_dir))
        inv.version = version
        return inv

    legacy = version_dir / "openapi.json"
    if legacy.exists():
        inv = normalize(json.loads(legacy.read_text(encoding="utf-8")))
        inv.version = version
        return inv

    raise UnknownUcpVersionError(
        f"UCP version {version!r} not vendored. Available: {available_versions()}"
    )
