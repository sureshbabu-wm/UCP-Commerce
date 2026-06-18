"""FastAPI service: POST /map.

Accepts a client swagger + ucp_version + provider/key, returns the mapping JSON.
The API key is used transiently and never logged or persisted (D9).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import registry
from .orchestrator import run_endpoint_mapping, run_field_mapping, run_mapping
from .providers.base import LLMError
from .structures import build_swagger_structure, build_ucp_structure

app = FastAPI(title="UCP Mapper", version="0.3.0")


class MapRequest(BaseModel):
    client_swagger: dict[str, Any] = Field(description="The client's OpenAPI/Swagger document (parsed JSON).")
    ucp_version: str = Field(default="2026-04-08", description="UCP spec version to target.")
    provider: Literal["openai", "claude", "gemini"] = "openai"
    api_key: str = Field(description="Provider API key (transient; not stored).")
    rules: dict[str, Any] | None = None


class FieldMapRequest(MapRequest):
    endpoint_mappings: list[dict[str, Any]] = Field(
        description="endpoint_mappings from POST /map/endpoints (possibly edited by the user)."
    )


class SwaggerParseRequest(BaseModel):
    swagger: dict[str, Any] = Field(description="The client's OpenAPI/Swagger document (parsed JSON).")


@app.get("/versions")
def versions() -> dict[str, list[str]]:
    return {"ucp_versions": registry.available_versions()}


@app.get("/ucp/{version}/structure")
def ucp_structure(version: str) -> dict[str, Any]:
    """UCP capabilities -> operations + fields (left panel + field dropdowns)."""
    try:
        return build_ucp_structure(version)
    except registry.UnknownUcpVersionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/swagger/parse")
def swagger_parse(req: SwaggerParseRequest) -> dict[str, Any]:
    """Parse a client swagger into endpoints + fields (right panel)."""
    try:
        return build_swagger_structure(req.swagger)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Could not parse swagger: {e}") from e


@app.post("/map/endpoints")
def map_endpoints(req: MapRequest) -> dict[str, Any]:
    """Phase 1 — endpoint mapping (cheap; review/edit before field mapping)."""
    try:
        return run_endpoint_mapping(
            client_swagger=req.client_swagger,
            ucp_version=req.ucp_version,
            provider=req.provider,
            api_key=req.api_key,
        )
    except registry.UnknownUcpVersionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/map/fields")
def map_fields(req: FieldMapRequest) -> dict[str, Any]:
    """Phase 2 — field mapping for the (possibly edited) endpoint mappings."""
    try:
        return run_field_mapping(
            client_swagger=req.client_swagger,
            ucp_version=req.ucp_version,
            endpoint_mappings=req.endpoint_mappings,
            provider=req.provider,
            api_key=req.api_key,
            rules=req.rules,
        )
    except registry.UnknownUcpVersionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/map")
def map_endpoint(req: MapRequest) -> dict[str, Any]:
    """Full mapping — runs phase 1 then phase 2."""
    try:
        return run_mapping(
            client_swagger=req.client_swagger,
            ucp_version=req.ucp_version,
            provider=req.provider,
            api_key=req.api_key,
            rules=req.rules,
        )
    except registry.UnknownUcpVersionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
