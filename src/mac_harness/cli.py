from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .agent import Agent, system_message
from .config import APP_DIR, CONFIG_PATH, Settings
from .provider import LocalProvider
from .store import ConversationStore
from .tools import available_tools

console = Console()

def say(text: str, dim: bool = False):
    if dim:
        console.print(text, style="dim")
    else:
        console.print(Markdown(text))

def _new_messages() -> list[dict]:
    return [system_message()]

def _title(prompt: str) -> str:
    return " ".join(prompt.split())[:88] or "New conversation"

def _usage():
    console.print(Panel("""[bold]Chat[/bold] — type a request and press Return
[bold]/help[/bold]   show commands
[bold]/models[/bold] list models served by the selected provider
[bold]/model ID[/bold] change the active model
[bold]/provider[/bold] switch Ollama / LM Studio / compatible endpoint
[bold]/threads[/bold] list saved conversations; [bold]/use ID[/bold] opens one
[bold]/new[/bold] start a conversation; [bold]/clear[/bold] starts fresh; [bold]/delete ID[/bold] removes a saved conversation
[bold]/tools[/bold] show enabled tools and their approval level
[bold]/doctor[/bold] check provider connection and local tool availability
[bold]/settings[/bold] show configuration location
[bold]/export PATH[/bold] export the current conversation after confirmation
[bold]/quit[/bold] exit""", title="Mac Local Harness"))

def _provider_setup(settings: Settings):
    current = settings.provider
    choice = console.input(f"Provider [ollama/lm_studio/custom_openai] ({current}): ").strip().lower() or current
    if choice not in {"ollama", "lm_studio", "custom_openai"}:
        console.print("Unknown provider; keeping current setting.", style="yellow")
        return
    settings.provider = choice
    defaults = {"ollama": "http://127.0.0.1:11434/v1", "lm_studio": "http://127.0.0.1:1234/v1", "custom_openai": settings.base_url}
    settings.base_url = console.input(f"OpenAI-compatible base URL ({defaults[choice]}): ").strip() or defaults[choice]
    if choice == "custom_openai":
        settings.api_key_env = console.input(f"Environment variable for API key ({settings.api_key_env}): ").strip() or settings.api_key_env
    try:
        provider = LocalProvider(settings)
        models = provider.list_models()
        if models:
            console.print("Available models:")
            for i, name in enumerate(models[:30], 1):
                console.print(f"  {i}. {name}")
            selected = console.input(f"Model identifier ({settings.model}): ").strip()
            if selected:
                settings.model = selected
        else:
            console.print("No models were listed. You can set the model later with /model.", style="yellow")
    except Exception as exc:
        console.print(f"Could not list models yet: {exc}", style="yellow")
    settings.save()
    console.print(f"Saved provider settings to {CONFIG_PATH}.")

def _export(messages: list[dict], settings: Settings, path_text: str):
    try:
        from .safety import approve_action, resolve_user_path
        path = resolve_user_path(path_text, settings.resolved_roots(), settings.allow_sensitive_paths)
        if not approve_action("export_conversation", {"path": str(path), "message_count": len(messages)}, "write"):
            console.print("Export cancelled.")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(messages[1:], ensure_ascii=False, indent=2)
        path.write_text(payload, encoding="utf-8")
        console.print(f"Exported conversation to {path}.")
    except Exception as exc:
        console.print(f"Export failed: {exc}", style="red")

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="mac-harness", description="Local-first Mac assistant for Ollama, LM Studio, and compatible APIs.")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        settings = Settings.load()
    except Exception as exc:
        console.print(f"Config error: {exc}", style="red")
        raise SystemExit(2)
    store = ConversationStore()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    existing = store.list(1)
    if existing:
        current_id = existing[0][0]
        messages = store.load(current_id) or _new_messages()
        if not messages or messages[0].get("role") != "system":
            messages = _new_messages() + messages
        else:
            messages[0] = system_message()
    else:
        current_id = store.create()
        messages = _new_messages()
    console.print(Panel(f"[bold]Mac Local Harness v{__version__}[/bold]\nProvider: {settings.provider} · Model: {settings.model}\nEndpoint: {settings.base_url}\nSaved data: {APP_DIR}\nType /help for commands. Risky operations ask before they run.", border_style="blue"))

    while True:
        try:
            prompt = console.input("\n[bold cyan]You › [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nSession saved.")
            break
        if not prompt:
            continue
        command, _, remainder = prompt.partition(" ")
        command = command.lower()
        if command in {"/quit", "/exit"}:
            console.print("Session saved.")
            break
        if command == "/help":
            _usage(); continue
        if command == "/settings":
            console.print(f"Config: {CONFIG_PATH}\nConversations: {APP_DIR / 'conversations.sqlite3'}\nAudit log: {APP_DIR / 'audit.jsonl'}")
            continue
        if command == "/doctor":
            console.print(f"Python: {sys.version.split()[0]}\nProvider: {settings.provider} at {settings.base_url}")
            for program in ("ollama", "lms", "git", "rg", "adb", "esptool.py"):
                console.print(f"{program}: {shutil.which(program) or 'not found'}")
            try:
                models = LocalProvider(settings).list_models()
                console.print(f"Provider connected. Models visible: {len(models)}")
                if settings.model not in models:
                    console.print(f"Configured model ID '{settings.model}' was not in the model list.", style="yellow")
            except Exception as exc:
                console.print(f"Provider connection failed: {exc}", style="red")
            continue
        if command == "/provider":
            _provider_setup(settings); continue
        if command == "/models":
            try:
                for model in LocalProvider(settings).list_models():
                    console.print(model)
                console.print("Set one with /model MODEL_ID.")
            except Exception as exc:
                console.print(f"Model listing failed: {exc}", style="red")
            continue
        if command == "/model":
            if not remainder.strip():
                console.print(f"Current model: {settings.model}. Use /models to list available IDs.")
            else:
                settings.model = remainder.strip()
                settings.save()
                console.print(f"Saved model: {settings.model}")
            continue
        if command == "/threads":
            table = Table("ID", "Updated", "Title")
            for ident, title, updated in store.list():
                table.add_row(ident, updated.replace("T", " ")[:19], title)
            console.print(table)
            continue
        if command == "/new":
            current_id = store.create()
            messages = _new_messages()
            console.print(f"Started conversation {current_id}.")
            continue
        if command == "/use":
            ident = remainder.strip()
            loaded = store.load(ident)
            if loaded is None:
                console.print("No saved conversation with that ID.", style="yellow")
            else:
                current_id, messages = ident, loaded
                if not messages or messages[0].get("role") != "system":
                    messages = _new_messages() + messages
                else:
                    messages[0] = system_message()
                console.print(f"Opened conversation {ident}.")
            continue
        if command == "/delete":
            ident = remainder.strip()
            if not ident:
                console.print("Usage: /delete CONVERSATION_ID")
                continue
            if console.input(f"Permanently delete conversation {ident}? Type yes: ").strip().lower() != "yes":
                console.print("Cancelled.")
                continue
            if store.delete(ident):
                console.print("Conversation deleted.")
                if ident == current_id:
                    current_id = store.create()
                    messages = _new_messages()
            else:
                console.print("No saved conversation with that ID.", style="yellow")
            continue
        if command == "/clear":
            current_id = store.create("Cleared conversation")
            messages = _new_messages()
            console.print("Started a fresh conversation; the old one remains saved.")
            continue
        if command == "/tools":
            table = Table("Tool", "Group", "Approval", "Purpose")
            risk_names = {"read": "none", "write": "yes", "execute": "yes", "device": "yes", "private_read": "yes", "external_action": "yes"}
            for spec in available_tools(settings):
                table.add_row(spec.name, spec.group, risk_names.get(spec.risk, spec.risk), spec.description)
            console.print(table)
            continue
        if command == "/export":
            if remainder.strip():
                _export(messages, settings, remainder.strip())
            else:
                console.print("Usage: /export ~/Documents/conversation.json")
            continue

        messages.append({"role": "user", "content": prompt})
        title = _title(prompt) if len(messages) <= 2 else None
        agent = Agent(settings, store, say)
        agent.run_turn(messages)
        store.save(current_id, messages, title)

if __name__ == "__main__":
    main()
