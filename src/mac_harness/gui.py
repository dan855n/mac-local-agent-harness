from __future__ import annotations

import json
import secrets
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .agent import Agent, system_message
from .config import APP_DIR, Settings
from .provider import LocalProvider
from .store import ConversationStore

STATIC = Path(__file__).parent / "static"
TOKEN = secrets.token_urlsafe(32)
app = FastAPI(title="Mac Local Harness", docs_url=None, redoc_url=None)
_lock = threading.RLock()
_runs: dict[str, dict[str, Any]] = {}
_active_run: str | None = None


def _settings() -> Settings:
    return Settings.load()


def _store() -> ConversationStore:
    return ConversationStore()


def _check_host(request: Request) -> None:
    host = request.headers.get("host", "").split(":", 1)[0].lower()
    if host not in {"127.0.0.1", "localhost", "[::1]"}:
        raise HTTPException(400, "This app only accepts local connections.")


def _secure(request: Request, token: str | None) -> None:
    _check_host(request)
    if not token or not secrets.compare_digest(token, TOKEN):
        raise HTTPException(403, "This local session token is missing or invalid. Reload the app.")
    origin = request.headers.get("origin")
    if origin and origin != f"http://{request.headers.get('host')}":
        raise HTTPException(403, "Cross-origin requests are not accepted.")


def _public_message(message: dict) -> dict | None:
    role = message.get("role")
    if role in {"assistant", "user"} and not message.get("tool_calls"):
        return {"role": role, "content": message.get("content") or ""}
    return None


@app.middleware("http")
async def local_only(request: Request, call_next):
    _check_host(request)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__SESSION_TOKEN__", TOKEN))


@app.get("/api/state")
def state(request: Request):
    _check_host(request)
    settings, store = _settings(), _store()
    with _lock:
        busy = _active_run is not None
    return {"provider": settings.provider, "model": settings.model, "base_url": settings.base_url,
            "conversations": [{"id": i, "title": t, "updated": u} for i, t, u in store.list(100)],
            "busy": busy, "app_dir": str(APP_DIR)}


@app.get("/api/conversations/{ident}")
def get_conversation(ident: str, request: Request):
    _check_host(request)
    messages = _store().load(ident)
    if messages is None:
        raise HTTPException(404, "Conversation not found")
    return {"id": ident, "messages": [m for item in messages if (m := _public_message(item)) is not None]}


class NewConversation(BaseModel):
    title: str = "New conversation"


@app.post("/api/conversations")
def create_conversation(body: NewConversation, request: Request, x_harness_token: str | None = Header(default=None)):
    _secure(request, x_harness_token)
    store = _store()
    ident = store.create(body.title[:100] or "New conversation")
    store.save(ident, [system_message()])
    return {"id": ident}


@app.delete("/api/conversations/{ident}")
def delete_conversation(ident: str, request: Request, x_harness_token: str | None = Header(default=None)):
    _secure(request, x_harness_token)
    with _lock:
        if _active_run and _runs.get(_active_run, {}).get("conversation_id") == ident:
            raise HTTPException(409, "Wait for the current response to finish before deleting this conversation.")
    return {"deleted": _store().delete(ident)}


class ChatRequest(BaseModel):
    conversation_id: str
    prompt: str


def _short_args(args: dict) -> dict:
    result = {}
    for key, value in args.items():
        raw = json.dumps(value, ensure_ascii=False, indent=2, default=str) if not isinstance(value, str) else value
        result[key] = raw if len(raw) <= 8000 else raw[:4000] + "\n… [content clipped for display] …\n" + raw[-1000:]
    return result


@app.post("/api/chat")
def start_chat(body: ChatRequest, request: Request, x_harness_token: str | None = Header(default=None)):
    global _active_run
    _secure(request, x_harness_token)
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Write a message first.")
    store = _store()
    messages = store.load(body.conversation_id)
    if messages is None:
        raise HTTPException(404, "Conversation not found")
    if not messages or messages[0].get("role") != "system":
        messages = [system_message(), *messages]
    else:
        messages[0] = system_message()
    with _lock:
        if _active_run is not None:
            raise HTTPException(409, "The assistant is already working. Wait for it to finish.")
        run_id = secrets.token_urlsafe(12)
        run = {"events": [], "pending": None, "decision": None, "conversation_id": body.conversation_id, "done": False}
        _runs[run_id] = run
        _active_run = run_id

    def emit(kind: str, **data):
        with _lock:
            run["events"].append({"seq": len(run["events"]), "type": kind, **data})

    def approve(name: str, args: dict, risk: str) -> bool:
        gate = threading.Event()
        with _lock:
            run["pending"] = gate
            run["decision"] = None
        emit("approval", tool=name, risk=risk, arguments=_short_args(args))
        allowed = gate.wait(timeout=600)
        with _lock:
            decision = run.get("decision") if allowed else False
            run["pending"] = None
            run["decision"] = None
        emit("approval_result", approved=bool(decision), tool=name)
        return bool(decision)

    def say(text: str, dim: bool = False):
        emit("activity" if dim else "assistant", text=str(text))

    def worker():
        global _active_run
        try:
            messages.append({"role": "user", "content": prompt})
            title = " ".join(prompt.split())[:88]
            store.save(body.conversation_id, messages, title=title)
            emit("user", text=prompt)
            Agent(_settings(), store, say, approve=approve).run_turn(messages)
            store.save(body.conversation_id, messages)
            emit("complete")
        except Exception as exc:
            emit("error", text=f"{type(exc).__name__}: {exc}")
        finally:
            with _lock:
                run["done"] = True
                _active_run = None

    threading.Thread(target=worker, name="mac-harness-agent", daemon=True).start()
    return {"run_id": run_id}


@app.get("/api/events/{run_id}")
def events(run_id: str, request: Request, after: int = 0):
    _check_host(request)
    with _lock:
        run = _runs.get(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return {"events": run["events"][max(0, after):], "done": run["done"]}


class Approval(BaseModel):
    run_id: str
    approved: bool


@app.post("/api/approve")
def decide(body: Approval, request: Request, x_harness_token: str | None = Header(default=None)):
    _secure(request, x_harness_token)
    with _lock:
        run = _runs.get(body.run_id)
        if not run or not run.get("pending"):
            raise HTTPException(409, "There is no pending approval.")
        run["decision"] = body.approved
        run["pending"].set()
    return {"ok": True}


class SettingsInput(BaseModel):
    provider: str
    model: str
    base_url: str | None = None


@app.post("/api/settings")
def save_settings(body: SettingsInput, request: Request, x_harness_token: str | None = Header(default=None)):
    _secure(request, x_harness_token)
    provider = body.provider.strip().lower()
    if provider not in {"ollama", "lm_studio", "custom_openai"}:
        raise HTTPException(400, "Choose Ollama, LM Studio, or a compatible OpenAI server.")
    settings = _settings()
    settings.provider = provider
    settings.base_url = {"ollama": "http://127.0.0.1:11434/v1", "lm_studio": "http://127.0.0.1:1234/v1"}.get(provider, settings.base_url)
    if provider == "custom_openai" and body.base_url and body.base_url.strip():
        settings.base_url = body.base_url.strip()[:500]
    if body.model.strip():
        settings.model = body.model.strip()[:200]
    settings.save()
    return {"provider": settings.provider, "model": settings.model, "base_url": settings.base_url}


@app.get("/api/models")
def models(request: Request):
    _check_host(request)
    try:
        return {"models": LocalProvider(_settings()).list_models()}
    except Exception as exc:
        raise HTTPException(503, f"Could not reach local model server: {type(exc).__name__}: {exc}") from exc


def main():
    import uvicorn
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    threading.Timer(0.8, lambda: webbrowser.open(url, new=1)).start()
    print(f"Mac Local Harness GUI is available at {url} (local machine only). Press Ctrl-C to stop.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
