from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def build_function_schemas(tools: Iterable[Any]) -> List[Dict[str, Any]]:
    """Convert fastmcp tools to LLM function schemas."""
    function_schemas: List[Dict[str, Any]] = []
    for tool in tools:
        if hasattr(tool, "model_json_schema"):
            parameters = tool.model_json_schema()
        else:
            parameters_attr = tool.schema
            parameters = parameters_attr() if callable(parameters_attr) else parameters_attr

        schema = {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": parameters,
        }
        function_schemas.append(schema)
    return function_schemas


def make_json_safe(value: Any) -> Any:
    """Recursively convert for JSON serialization."""
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {k: make_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [make_json_safe(v) for v in value]
        return repr(value)


def stringify(value: Any) -> str:
    """Convert value to string for logging."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return repr(value)


