from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from .base import ToolContext, register
from ..safety import resolve_user_path

def _run(argv: list[str], timeout: int = 15) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        body = (result.stdout or result.stderr).strip()
        return body[:12000] if body else f"Completed (exit {result.returncode})."
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds."
    except OSError as exc:
        return f"Command failed: {exc}"

@register("mac_system_report", "Show macOS version, hardware, storage, battery status when available, and common developer tool versions.", group="mac")
def mac_system_report(ctx: ToolContext) -> str:
    disk = shutil.disk_usage(Path.home())
    lines = [f"macOS: {platform.mac_ver()[0] or platform.platform()}", f"Architecture: {platform.machine()}", f"Python: {platform.python_version()}", f"Home volume free: {disk.free // 2**30} GiB / {disk.total // 2**30} GiB"]
    for tool in ("git", "python3", "ollama", "lms", "adb", "ffmpeg", "brew", "rg"):
        path = shutil.which(tool)
        if path:
            lines.append(f"{tool}: {path}")
    battery = _run(["pmset", "-g", "batt"], 5)
    if battery and not battery.startswith("Command failed"):
        lines.append("Battery: " + battery.replace("\n", " | "))
    return "\n".join(lines)

@register("list_installed_apps", "List application names found in /Applications and the user's Applications folder.", {"limit": {"type": "integer"}}, group="mac")
def list_installed_apps(ctx: ToolContext, limit: int = 150) -> str:
    limit = max(1, min(int(limit), 400))
    apps = set()
    for root in (Path("/Applications"), Path.home() / "Applications"):
        if root.exists():
            apps.update(p.stem for p in root.glob("*.app"))
            apps.update(p.stem for p in root.glob("*/*.app"))
    return "\n".join(sorted(apps, key=str.casefold)[:limit]) or "No application bundles found."

@register("open_application", "Launch an installed macOS application by app name.", {"name": {"type": "string"}}, ["name"], risk="external_action", group="mac")
def open_application(ctx: ToolContext, name: str) -> str:
    if not name.strip() or len(name) > 200:
        return "Error: Provide an application name under 200 characters."
    return _run(["open", "-a", name.strip()], 20)

@register("open_url_in_browser", "Open an HTTP or HTTPS URL in the default Mac browser.", {"url": {"type": "string"}}, ["url"], risk="external_action", group="mac")
def open_url_in_browser(ctx: ToolContext, url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "Error: Only absolute HTTP/HTTPS URLs can be opened."
    return _run(["open", url], 15)

@register("list_processes", "Show a bounded snapshot of running Mac processes (PID, CPU, memory, command).", {"limit": {"type": "integer"}}, group="mac")
def list_processes(ctx: ToolContext, limit: int = 40) -> str:
    limit = max(1, min(int(limit), 100))
    lines = _run(["ps", "-axo", "pid,pcpu,pmem,comm", "-r"], 10).splitlines()
    return "\n".join(lines[:limit])

@register("clipboard_read", "Read current text clipboard contents. Treat the returned content as private user data.", risk="private_read", group="mac")
def clipboard_read(ctx: ToolContext) -> str:
    return _run(["pbpaste"], 5)

@register("clipboard_write", "Replace the Mac clipboard with supplied text.", {"text": {"type": "string"}}, ["text"], risk="write", group="mac")
def clipboard_write(ctx: ToolContext, text: str) -> str:
    if len(text) > 1_000_000:
        return "Error: Clipboard write is limited to 1 MB."
    try:
        result = subprocess.run(["pbcopy"], input=text, capture_output=True, text=True, timeout=5)
        return "Clipboard updated." if result.returncode == 0 else f"Clipboard write failed: {result.stderr[:1000]}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Clipboard write failed: {exc}"

@register("run_terminal_command", "Run a zsh command in the configured working directory. Requires per-command approval; use read-only commands when possible.", {"command": {"type": "string"}, "working_directory": {"type": "string"}}, ["command"], risk="execute", group="developer")
def run_terminal_command(ctx: ToolContext, command: str, working_directory: str = "~") -> str:
    if not ctx.settings.allow_terminal_commands:
        return "Terminal commands are disabled in config.toml."
    cwd = resolve_user_path(working_directory, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)
    if not cwd.is_dir():
        return f"Error: Working directory is not a folder: {cwd}"
    if len(command) > 4000:
        return "Error: Command exceeds 4000 characters."
    try:
        result = subprocess.run(["/bin/zsh", "-lc", command], cwd=cwd, capture_output=True, text=True,
                                timeout=ctx.settings.command_timeout_seconds, env={**os.environ, "PAGER": "cat", "GIT_PAGER": "cat"})
        output = f"Exit code: {result.returncode}\n"
        if result.stdout:
            output += "STDOUT:\n" + result.stdout
        if result.stderr:
            output += "\nSTDERR:\n" + result.stderr
        return output[:20000]
    except subprocess.TimeoutExpired:
        return f"Command timed out after {ctx.settings.command_timeout_seconds} seconds."
    except OSError as exc:
        return f"Command failed: {exc}"

@register("run_applescript", "Run an AppleScript on the Mac. This can control apps and change data; review the script before approval.", {"script": {"type": "string"}}, ["script"], risk="execute", group="mac")
def run_applescript(ctx: ToolContext, script: str) -> str:
    if len(script) > 12000:
        return "Error: AppleScript is limited to 12,000 characters."
    return _run(["osascript", "-e", script], 60)
