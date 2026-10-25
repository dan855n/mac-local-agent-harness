from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import APP_DIR, AUDIT_PATH, DB_PATH

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class ConversationStore:
    def __init__(self, path: Path = DB_PATH):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._init()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init(self):
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, messages TEXT NOT NULL)")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def create(self, title: str = "New conversation") -> str:
        ident = uuid.uuid4().hex[:12]
        with self._connect() as db:
            db.execute("INSERT INTO conversations VALUES (?, ?, ?, ?, ?)", (ident, title, now(), now(), "[]"))
        return ident

    def save(self, ident: str, messages: list[dict], title: str | None = None):
        encoded = json.dumps(messages, ensure_ascii=False)
        with self._connect() as db:
            if title:
                db.execute("UPDATE conversations SET title=?, updated=?, messages=? WHERE id=?", (title[:100], now(), encoded, ident))
            else:
                db.execute("UPDATE conversations SET updated=?, messages=? WHERE id=?", (now(), encoded, ident))

    def load(self, ident: str) -> list[dict] | None:
        with self._connect() as db:
            row = db.execute("SELECT messages FROM conversations WHERE id=?", (ident,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit: int = 30) -> list[tuple[str, str, str]]:
        with self._connect() as db:
            return db.execute("SELECT id, title, updated FROM conversations ORDER BY updated DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()

    def delete(self, ident: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM conversations WHERE id=?", (ident,))
            deleted = cursor.rowcount > 0
        if deleted:
            with self._connect() as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.execute("VACUUM")
        return deleted

    def audit(self, event: str, tool: str = "", risk: str = "", approved: bool | None = None, result: str = ""):
        # Keep only event metadata; tool output can contain private file, email, or device data.
        record = {"time": now(), "event": event, "tool": tool, "risk": risk, "approved": approved}
        try:
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            AUDIT_PATH.chmod(0o600)
        except OSError:
            # An audit-write failure must not prevent a user-approved tool from returning its result.
            pass
