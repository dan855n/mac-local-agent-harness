from __future__ import annotations

import subprocess
import os
import fnmatch
from pathlib import Path

from .base import ToolContext, register
from ..safety import resolve_user_path

@register("git_status", "Show Git branch and changed-file status for a repository.", {"path": {"type": "string"}}, ["path"], group="developer")
def git_status(ctx: ToolContext, path: str) -> str:
    root = resolve_user_path(path, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)
    result = subprocess.run(["git", "-C", str(root), "status", "--short", "--branch"], capture_output=True, text=True, timeout=15)
    return result.stdout.strip() or result.stderr.strip() or "No Git status output."

@register("git_diff", "Read a bounded Git diff. Untracked files are not included.", {"path": {"type": "string"}, "staged": {"type": "boolean"}, "max_chars": {"type": "integer"}}, ["path"], group="developer")
def git_diff(ctx: ToolContext, path: str, staged: bool = False, max_chars: int = 18000) -> str:
    root = resolve_user_path(path, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)
    max_chars = max(500, min(int(max_chars), 30000))
    argv = ["git", "-C", str(root), "diff", "--no-ext-diff", "--no-color"]
    if staged:
        argv.append("--cached")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    if result.returncode:
        return f"Git diff failed: {result.stderr[:2000]}"
    return result.stdout[:max_chars] or "No diff."

@register("find_paths", "Find files and folders by glob pattern under a permitted root; skips dependency and cache directories.", {"path": {"type": "string"}, "pattern": {"type": "string"}, "limit": {"type": "integer"}}, ["path", "pattern"], group="developer")
def find_paths(ctx: ToolContext, path: str, pattern: str, limit: int = 100) -> str:
    root = resolve_user_path(path, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)
    if not root.is_dir():
        return f"Error: Not a directory: {root}"
    limit = max(1, min(int(limit), 500))
    excluded = {".git", "node_modules", ".venv", "venv", "__pycache__", "Library"}
    found = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in excluded and (ctx.settings.allow_sensitive_paths or d.lower() not in {".ssh", ".aws", ".gnupg", ".config", ".codex", "keychains", "maclocalharness"})]
        for name in dirs + names:
            if fnmatch.fnmatch(name, pattern[:200]):
                found.append(str(Path(base) / name))
                if len(found) >= limit:
                    return "\n".join(found)
    return "\n".join(found) or "No matching paths."
