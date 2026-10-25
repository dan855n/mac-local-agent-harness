from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .base import ToolContext, register
from ..safety import resolve_user_path

def _path(ctx: ToolContext, path: str) -> Path:
    return resolve_user_path(path, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)

@register("list_files", "List files and directories with sizes and modification dates.", {"path": {"type": "string"}, "recursive": {"type": "boolean"}, "limit": {"type": "integer"}}, ["path"], group="files")
def list_files(ctx: ToolContext, path: str, recursive: bool = False, limit: int = 100) -> str:
    root = _path(ctx, path)
    if not root.is_dir():
        return f"Error: Not a directory: {root}"
    limit = max(1, min(int(limit), 500))
    if recursive:
        def walk_items():
            for base, dirs, names in os.walk(root, followlinks=False):
                if not ctx.settings.allow_sensitive_paths:
                    dirs[:] = [d for d in dirs if d.lower() not in {".ssh", ".aws", ".gnupg", ".config", ".codex", "keychains", "maclocalharness"}]
                for name in dirs + names:
                    yield Path(base) / name
        iterator = walk_items()
    else:
        iterator = root.iterdir()
    rows = []
    try:
        for item in iterator:
            if not ctx.settings.allow_sensitive_paths and any(part.lower() in {".ssh", ".aws", ".gnupg", ".config", ".codex", "keychains", "maclocalharness"} for part in item.parts):
                continue
            try:
                stat = item.stat()
                size = "DIR" if item.is_dir() else f"{stat.st_size:,} B"
                rows.append(f"{item}\t{size}\t{datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='minutes')}")
            except OSError:
                continue
            if len(rows) >= limit:
                break
        return "\n".join(rows) if rows else "No entries found."
    except OSError as exc:
        return f"List failed: {exc}"

@register("read_text_file", "Read a bounded amount of UTF-8 text from a file.", {"path": {"type": "string"}, "max_chars": {"type": "integer"}}, ["path"], group="files")
def read_text_file(ctx: ToolContext, path: str, max_chars: int = 20000) -> str:
    target = _path(ctx, path)
    if not target.is_file():
        return f"Error: Not a regular file: {target}"
    if target.stat().st_size > 2_000_000:
        return "Error: File is larger than 2 MB; narrow the request or use search_text."
    max_chars = max(500, min(int(max_chars), 50000))
    try:
        data = target.read_text(encoding="utf-8", errors="replace")
        return data[:max_chars] + ("\n… [truncated]" if len(data) > max_chars else "")
    except OSError as exc:
        return f"Read failed: {exc}"

@register("search_text", "Search file contents using ripgrep when installed, otherwise a bounded Python scan.", {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}, "limit": {"type": "integer"}}, ["pattern", "path"], group="files")
def search_text(ctx: ToolContext, pattern: str, path: str, glob: str = "*", limit: int = 60) -> str:
    root = _path(ctx, path)
    if not root.exists():
        return f"Error: Path does not exist: {root}"
    pattern = str(pattern)[:500]
    limit = max(1, min(int(limit), 200))
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "--line-number", "--no-heading", "--color", "never", "--max-count", "20", "--glob", glob or "*", "--glob", "!.git/**", "--glob", "!node_modules/**", "--glob", "!.venv/**", "--glob", "!Library/**", pattern, str(root)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode not in (0, 1):
                return f"Search error: {result.stderr.strip()[:1500]}"
            lines = result.stdout.splitlines()
            return "\n".join(lines[:limit]) or "No matches."
        except subprocess.TimeoutExpired:
            return "Search timed out after 20 seconds."
    matches = []
    if root.is_file():
        files = [root]
    else:
        def walk_files():
            for base, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if d.lower() not in {".git", "node_modules", ".venv", "venv", "__pycache__", "library"} and (ctx.settings.allow_sensitive_paths or d.lower() not in {".ssh", ".aws", ".gnupg", ".config", ".codex", "keychains", "maclocalharness"})]
                for name in names:
                    yield Path(base) / name
        files = walk_files()
    for file in files:
        if len(matches) >= limit:
            break
        if not file.is_file() or not fnmatch.fnmatch(file.name, glob) or file.stat().st_size > 1_000_000:
            continue
        if any(part.lower() in {".git", "node_modules", ".venv", "venv", "__pycache__", "library", ".ssh", ".aws", ".gnupg", ".config", ".codex", "keychains", "maclocalharness"} for part in file.parts):
            continue
        try:
            for number, line in enumerate(file.read_text(errors="replace").splitlines(), 1):
                if pattern.casefold() in line.casefold():
                    matches.append(f"{file}:{number}:{line[:500]}")
                    if len(matches) >= limit:
                        break
        except OSError:
            pass
    return "\n".join(matches) or "No matches."

@register("write_text_file", "Create or replace a UTF-8 text file. Existing files receive a timestamped backup first.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], risk="write", group="files")
def write_text_file(ctx: ToolContext, path: str, content: str) -> str:
    target = _path(ctx, path)
    if len(content.encode("utf-8")) > 2_000_000:
        return "Error: One write is limited to 2 MB."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target.with_name(target.name + f".backup-{stamp}")
            shutil.copy2(target, backup)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_name = tmp.name
        os.replace(temp_name, target)
        return f"Wrote {len(content)} characters to {target}." + (f" Backup: {backup}" if backup else "")
    except OSError as exc:
        return f"Write failed: {exc}"

@register("move_to_trash", "Move a file or folder into the user's Trash so it can be recovered.", {"path": {"type": "string"}}, ["path"], risk="write", group="files")
def move_to_trash(ctx: ToolContext, path: str) -> str:
    target = _path(ctx, path)
    if not target.exists():
        return f"Error: Does not exist: {target}"
    if target == Path.home() or target == Path("/") or target in ctx.settings.resolved_roots():
        return "Refused: cannot move a configured access root or the filesystem root to Trash."
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    destination = trash / target.name
    if destination.exists():
        destination = trash / f"{target.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{target.suffix}"
    try:
        shutil.move(str(target), str(destination))
        return f"Moved to Trash: {destination}"
    except OSError as exc:
        return f"Move to Trash failed: {exc}"

@register("copy_path", "Copy a file or folder to a destination inside the configured allowed roots.", {"source": {"type": "string"}, "destination": {"type": "string"}}, ["source", "destination"], risk="write", group="files")
def copy_path(ctx: ToolContext, source: str, destination: str) -> str:
    src, dst = _path(ctx, source), _path(ctx, destination)
    if not src.exists():
        return f"Error: Source does not exist: {src}"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return f"Copied {src} to {dst}"
    except OSError as exc:
        return f"Copy failed: {exc}"
