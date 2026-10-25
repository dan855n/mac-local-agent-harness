from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .base import ToolContext, register
from ..safety import resolve_user_path

_READ_TOOLS = {"doc_inspect", "project_inspect", "sequence_inspect", "command_list", "mcp_tools"}
_EDIT_TOOLS = {"media_import", "command_run", "command_batch"}


def _project_command(ctx: ToolContext, project_path: str, save: bool) -> list[str]:
    cli = Path(os.path.expandvars(os.path.expanduser(ctx.settings.filmcraft_cli_path))).resolve()
    if not cli.is_file() or not os.access(cli, os.X_OK):
        raise ValueError(f"FilmCraft CLI is missing or not executable: {cli}")
    project = resolve_user_path(project_path, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)
    if project.suffix.lower() != ".fcproj":
        raise ValueError("project_path must name a FilmCraft .fcproj file")
    if not project.parent.is_dir():
        raise ValueError(f"Project folder does not exist: {project.parent}")
    if project.exists():
        return [str(cli), "--project", str(project), *( ["--save"] if save else [] ), "mcp"]
    if not save:
        raise ValueError("That project file does not exist yet. Create it with filmcraft_edit first.")
    return [str(cli), "--save-as", str(project), "mcp"]


def _validate_paths(value: Any, ctx: ToolContext) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _validate_paths(nested, ctx)
    elif isinstance(value, list):
        for nested in value:
            _validate_paths(nested, ctx)
    elif isinstance(value, str) and (value.startswith("/") or value.startswith("~")):
        resolve_user_path(value, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)


def _rpc(ctx: ToolContext, project_path: str | None, tool_name: str, arguments: dict[str, Any], save: bool) -> str:
    _validate_paths(arguments, ctx)
    if tool_name == "mcp_tools" and project_path is None:
        cli = Path(os.path.expandvars(os.path.expanduser(ctx.settings.filmcraft_cli_path))).resolve()
        if not cli.is_file() or not os.access(cli, os.X_OK):
            raise ValueError(f"FilmCraft CLI is missing or not executable: {cli}")
        command = [str(cli), "mcp"]
    elif project_path is not None:
        command = _project_command(ctx, project_path, save)
    else:
        raise ValueError("A saved FilmCraft project path is required for this action")
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "mac-local-harness", "version": "0.1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
         if tool_name == "mcp_tools" else
         {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
             "name": tool_name, "arguments": arguments}}),
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        {"jsonrpc": "2.0", "method": "notifications/exit"},
    ]
    payload = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)
    workdir = (Path(os.path.expandvars(os.path.expanduser(project_path))).resolve().parent
               if project_path else Path.home())
    try:
        proc = subprocess.run(command, input=payload, text=True, capture_output=True,
                              timeout=900, check=False, cwd=str(workdir))
    except subprocess.TimeoutExpired:
        raise RuntimeError("FilmCraft MCP timed out after 15 minutes") from None
    responses = []
    for line in proc.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("id") == 2:
            responses.append(value)
    if not responses:
        detail = proc.stderr.strip()[-3000:] or proc.stdout.strip()[-3000:] or f"process exited {proc.returncode} without an MCP result"
        raise RuntimeError(f"FilmCraft MCP returned no tool result: {detail}")
    result = responses[-1]
    if "error" in result:
        raise RuntimeError(f"FilmCraft MCP error: {result['error']}")
    body = result.get("result", {})
    parts = [item.get("text", "") for item in body.get("content", []) if item.get("type") == "text"]
    rendered = "\n".join(part for part in parts if part).strip()
    if body.get("isError"):
        raise RuntimeError(rendered or "FilmCraft reported an error")
    return rendered or json.dumps(body, ensure_ascii=False)[:18000]


@register(
    "filmcraft_inspect",
    "Inspect FilmCraft MCP tools or a project. Read-only: use mcp_tools without a project path to list available MCP tool schemas; otherwise choose doc_inspect, project_inspect, sequence_inspect, or command_list and supply an existing .fcproj path.",
    properties={
        "action": {"type": "string", "enum": sorted(_READ_TOOLS)},
        "project_path": {"type": "string", "description": "Absolute or ~/ path to an existing FilmCraft .fcproj file; omit only for mcp_tools."},
    },
    required=["action"], risk="read", group="filmcraft")
def filmcraft_inspect(ctx: ToolContext, action: str, project_path: str | None = None) -> str:
    if action not in _READ_TOOLS:
        raise ValueError("Unsupported read-only FilmCraft action")
    if action != "mcp_tools" and not project_path:
        raise ValueError("Supply project_path for project inspection actions")
    return _rpc(ctx, project_path, action, {}, save=False)


@register(
    "filmcraft_edit",
    "Make one FilmCraft project change through MCP. This action always requires approval. Supported actions: media_import, command_run, command_batch. Pass the action-specific arguments as a JSON object. The .fcproj is saved after the operation.",
    properties={
        "action": {"type": "string", "enum": sorted(_EDIT_TOOLS)},
        "project_path": {"type": "string", "description": "Absolute or ~/ path to the .fcproj project to edit; a new project can be created at this path."},
        "arguments": {"type": "object", "description": "Arguments for the selected FilmCraft MCP tool."},
    },
    required=["action", "project_path", "arguments"], risk="write", group="filmcraft")
def filmcraft_edit(ctx: ToolContext, action: str, project_path: str, arguments: dict[str, Any]) -> str:
    if action not in _EDIT_TOOLS:
        raise ValueError("Unsupported FilmCraft edit action")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    return _rpc(ctx, project_path, action, arguments, save=True)
