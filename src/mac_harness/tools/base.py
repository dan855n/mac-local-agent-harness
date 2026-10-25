from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..config import Settings

@dataclass
class ToolContext:
    settings: Settings

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str
    group: str
    function: Callable[..., str]

    def schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }}

TOOLS: dict[str, ToolSpec] = {}

def register(name: str, description: str, properties: dict[str, Any] | None = None,
             required: list[str] | None = None, risk: str = "read", group: str = "mac"):
    def decorator(function: Callable[..., str]):
        TOOLS[name] = ToolSpec(
            name, description,
            {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False},
            risk, group, function,
        )
        return function
    return decorator

def available_tools(settings: Settings) -> list[ToolSpec]:
    return [spec for spec in TOOLS.values() if settings.tool_groups.get(spec.group, True)]
