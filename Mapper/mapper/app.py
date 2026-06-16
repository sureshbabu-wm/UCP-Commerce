"""FastAPI service: POST /map.

Accepts a client swagger + ucp_version + provider/key, returns the mapping JSON.
The API key is used transiently and never logged or persisted (D9).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import registry
from .orchestrator import run_mapping
from .providers.base import LLMError

app = FastAPI(title="UCP Mapper", version="0.1.0")


class MapRequest(BaseModel):
    client_swagger: dict[str, Any] = Field(description="The client's OpenAPI/Swagger document (parsed JSON).")
    ucp_version: str = Field(default="2026-01-23", description="UCP spec version to target.")
    provider: Literal["openai", "claude", "gemini"] = "openai"
    api_key: str = Field(description="Provider API key (transient; not stored).")
    rules: dict[str, Any] | None = None
    operation_id: str | None = Field(
        default=None,
        description="Specific UCP operation to map; null (default) maps the full surface.",
    )


@app.get("/versions")
def versions() -> dict[str, list[str]]:
    return {"ucp_versions": registry.available_versions()}


@app.post("/map")
def map_endpoint(req: MapRequest) -> dict[str, Any]:
    try:
        return run_mapping(
            client_swagger=req.client_swagger,
            ucp_version=req.ucp_version,
            provider=req.provider,
            api_key=req.api_key,
            rules=req.rules,
            operation_id=req.operation_id,
        )
    except registry.UnknownUcpVersionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
