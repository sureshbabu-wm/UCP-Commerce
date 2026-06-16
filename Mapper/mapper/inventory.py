"""Canonical field-inventory models.

Both the UCP target spec and the client swagger are normalized into these structures
so the LLM receives a compact, uniform view instead of raw, deeply-nested specs (mitigates D1).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldDescriptor(BaseModel):
    """One leaf/branch field of a request or response body, addressed by JSONPath."""

    path: str = Field(description="JSONPath of the field, e.g. $.line_items[*].item.id")
    type: str = Field(description="JSON type: string|integer|number|boolean|object|array")
    required: bool = False
    enum: list[str] | None = None
    description: str | None = None
    unit_hint: str | None = Field(
        default=None, description="e.g. 'cents' | 'major_units' when detectable"
    )
    format_hint: str | None = Field(
        default=None, description="e.g. 'date-time' | 'uri' when present"
    )


class OperationInventory(BaseModel):
    """One API operation with its request/response field inventories."""

    operation_id: str
    method: str
    path: str
    summary: str | None = None
    request_fields: list[FieldDescriptor] = Field(default_factory=list)
    response_fields: list[FieldDescriptor] = Field(default_factory=list)


class SpecInventory(BaseModel):
    """A whole spec (UCP target or client source) reduced to operations + fields."""

    title: str | None = None
    version: str | None = None
    operations: list[OperationInventory] = Field(default_factory=list)

    def operation(self, operation_id: str) -> OperationInventory | None:
        return next((o for o in self.operations if o.operation_id == operation_id), None)
