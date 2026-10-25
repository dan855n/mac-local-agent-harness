from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_DIR = Path.home() / "Library" / "Application Support" / "MacLocalHarness"
CONFIG_PATH = APP_DIR / "config.toml"
DB_PATH = APP_DIR / "conversations.sqlite3"
AUDIT_PATH = APP_DIR / "audit.jsonl"

DEFAULT_CONFIG = '''# Local provider: ollama, lm_studio, or custom_openai
provider = "ollama"
base_url = "http://127.0.0.1:11434/v1"
model = "qwen2.5:14b-instruct-q6_K"
api_key_env = "OPENAI_API_KEY"
temperature = 0.2
max_output_tokens = 4096
max_tool_steps = 12
request_timeout_seconds = 180

# Paths available to file tools. Expand ~ in each entry.
allowed_roots = ["~"]
# Keep sensitive paths blocked unless you knowingly opt in here.
allow_sensitive_paths = false
# Run zsh commands only after the per-command approval prompt.
allow_terminal_commands = true
# Optional maximum captured command output.
command_timeout_seconds = 90
filmcraft_cli_path = "~/filmcraft/filmcraft-cli"

[tool_groups]
files = true
mac = true
web = true
developer = true
mail = true
hardware = true
filmcraft = true
'''

@dataclass
class Settings:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen2.5:14b-instruct-q6_K"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.2
    max_output_tokens: int = 4096
    max_tool_steps: int = 12
    request_timeout_seconds: int = 180
    allowed_roots: list[str] = field(default_factory=lambda: ["~"])
    allow_sensitive_paths: bool = False
    allow_terminal_commands: bool = True
    command_timeout_seconds: int = 90
    filmcraft_cli_path: str = "~/filmcraft/filmcraft-cli"
    tool_groups: dict[str, bool] = field(default_factory=lambda: {
        "files": True, "mac": True, "web": True, "developer": True, "mail": True, "hardware": True, "filmcraft": True
    })

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Settings":
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(DEFAULT_CONFIG, encoding="utf-8")
            try:
                path.chmod(0o600)
            except OSError:
                pass
        with path.open("rb") as f:
            raw = tomllib.load(f)
        allowed = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        settings = cls(**allowed)
        settings.provider = settings.provider.strip().lower()
        if settings.provider not in {"ollama", "lm_studio", "custom_openai"}:
            raise ValueError("provider must be ollama, lm_studio, or custom_openai")
        settings.max_tool_steps = max(1, min(int(settings.max_tool_steps), 30))
        settings.max_output_tokens = max(256, min(int(settings.max_output_tokens), 32768))
        settings.request_timeout_seconds = max(10, min(int(settings.request_timeout_seconds), 900))
        settings.command_timeout_seconds = max(1, min(int(settings.command_timeout_seconds), 600))
        return settings

    def save(self, path: Path = CONFIG_PATH) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        values = asdict(self)
        lines = []
        for key, value in values.items():
            if key == "tool_groups":
                continue
            if isinstance(value, bool):
                literal = "true" if value else "false"
            elif isinstance(value, str):
                literal = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
            elif isinstance(value, list):
                literal = "[" + ", ".join('"' + str(v).replace('"', '\\"') + '"' for v in value) + "]"
            else:
                literal = str(value)
            lines.append(f"{key} = {literal}")
        lines.extend(["", "[tool_groups]"])
        lines.extend(f"{key} = {'true' if value else 'false'}" for key, value in self.tool_groups.items())
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def resolved_roots(self) -> list[Path]:
        return [Path(os.path.expandvars(os.path.expanduser(p))).resolve() for p in self.allowed_roots]

    def resolved_api_key(self) -> str:
        if self.provider == "ollama":
            return "ollama-local"
        if self.provider == "lm_studio":
            return "lm-studio-local"
        return os.environ.get(self.api_key_env, "")
