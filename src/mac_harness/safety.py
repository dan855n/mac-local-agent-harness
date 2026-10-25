from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SENSITIVE_PARTS = {
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".config", ".codex",
    "keychains", "credentials", "login.keychain-db", "maclocalharness",
}
SENSITIVE_SUFFIXES = {".pem", ".p12", ".pfx", ".key", ".asc"}
SENSITIVE_NAMES = {".env", ".netrc", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials.json"}

class SafetyError(ValueError):
    pass

def resolve_user_path(raw_path: str, roots: list[Path], allow_sensitive: bool = False) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(str(raw_path)))).resolve()
    if not any(path == root or root in path.parents for root in roots):
        raise SafetyError(f"Path is outside configured roots: {path}")
    if not allow_sensitive:
        parts = {part.lower() for part in path.parts}
        name = path.name.lower()
        if parts.intersection(SENSITIVE_PARTS) or path.suffix.lower() in SENSITIVE_SUFFIXES or name in SENSITIVE_NAMES or name.startswith(".env."):
            raise SafetyError("Sensitive path blocked by default. Review allow_sensitive_paths in config.toml if you intentionally want to permit it.")
    return path

def needs_approval(risk: str) -> bool:
    return risk in {"write", "execute", "device", "private_read", "external_action"}

def approve_action(name: str, args: dict[str, Any], risk: str) -> bool:
    print(f"\nAction requested [{risk}]: {name}")
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 5000 and key in {"content", "code"}:
            value = value[:2500] + f"\n… <{len(value)} characters; middle omitted from approval preview> …\n" + value[-1000:]
        elif isinstance(value, str) and len(value) > 12000:
            value = value[:12000] + f"\n… <{len(value)} characters total; truncated>"
        print(f"  {key}: {value}")
    try:
        return input("Type yes to approve this one action: ").strip().lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False
