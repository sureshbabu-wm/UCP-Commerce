"""Provider-agnostic LLM adapter interface + shared JSON extraction/repair (D2).

Each concrete adapter implements ``_complete(messages) -> str`` (raw text). The base class
handles: extracting a JSON object from the text, validating it against the output schema, and
re-prompting once with the validation error to repair invalid output.
"""

from __future__ import annotations

import abc
import json
import re
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "contracts" / "mapping_output.schema.json"
)
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMError(RuntimeError):
    pass


def _load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of model text (handles stray prose / code fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") : text.rfind("}") + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if not m:
            raise LLMError("No JSON object found in model output")
        return json.loads(m.group(0))


class LLMAdapter(abc.ABC):
    provider: str = "base"

    def __init__(self, api_key: str, model: str | None = None, temperature: float = 0.0):
        self.api_key = api_key
        self.model = model or self.default_model
        self.temperature = temperature
        self._schema = _load_schema()

    @property
    def default_model(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    @abc.abstractmethod
    def _complete(self, messages: list[dict]) -> str:
        """Provider-specific call returning raw assistant text."""

    def map(self, messages: list[dict], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call the model, extract + validate JSON, repair once on failure.

        ``schema`` overrides the default full-artifact schema (used for the per-phase calls in
        the two-step pipeline, which return partial objects).
        """
        schema = schema or self._schema
        raw = self._complete(messages)
        try:
            obj = extract_json(raw)
            jsonschema.validate(obj, schema)
            return obj
        except (LLMError, jsonschema.ValidationError) as err:
            repair = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        "Your previous output was invalid: "
                        f"{err}. Return ONLY a corrected JSON object that conforms to the schema."
                    ),
                },
            ]
            raw2 = self._complete(repair)
            obj = extract_json(raw2)
            jsonschema.validate(obj, schema)
            return obj
