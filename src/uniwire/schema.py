"""JSON Schema (draft 2020-12) export from the pydantic models."""

from __future__ import annotations

import json
from typing import Any

from .model import FORMAT_VERSION, SCHEMA_ID, Document


def json_schema() -> dict[str, Any]:
    """The JSON Schema (draft 2020-12) of the format, generated from the pydantic models."""
    schema = Document.model_json_schema(mode="validation", by_alias=True)
    out: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "uniwire: electrical installation",
        "description": f"uniwire {FORMAT_VERSION} exchange format for describing electrical installations, drawn as "
                       "single-line and multi-line diagrams (tree topology + links, characteristics, rendering "
                       "preferences).",
    }
    schema.pop("title", None)
    schema.pop("description", None)  # the Document docstring: the description above is used instead
    _discriminate(schema)
    out.update(schema)
    return out


def _discriminate(schema: dict[str, Any]) -> None:
    """Replace the ``oneOf`` union of nodes with an ``if/then`` dispatch on ``type``.

    A ``oneOf`` over a recursive tree forces generic validators to try every branch
    at every level (exponential cost); the dispatch validates only one.
    """
    node = schema["$defs"]["Node"]
    mapping: dict[str, str] = node.get("discriminator", {}).get("mapping", {})
    schema["$defs"]["Node"] = {
        "type": "object",
        "description": "Node of the power tree; 'type' selects the applicable definition.",
        "required": ["type"],
        "properties": {"type": {"enum": sorted(mapping)}},
        "allOf": [
            {"if": {"properties": {"type": {"const": t}}}, "then": {"$ref": ref}}
            for t, ref in sorted(mapping.items())
        ],
    }


def schema_text() -> str:
    """The JSON Schema as formatted text (what ``uniwire schema`` writes)."""
    return json.dumps(json_schema(), ensure_ascii=False, indent=2) + "\n"
