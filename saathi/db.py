"""SQLite persistence (standard library): cases, officers, sessions, audit trail, OTPs, SMS outbox, feedback."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT, priority REAL,
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, salt TEXT NOT NULL, iterations INTEGER NOT NULL,
  role TEXT NOT NULL DEFAULT 'officer', created_at TEXT, disabled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, case_id TEXT, detail TEXT, ip TEXT);
CREATE TABLE IF NOT EXISTS verifications (
  case_id TEXT PRIMARY KEY, code_hash TEXT, salt TEXT, expires_at TEXT, attempts INTEGER DEFAULT 0,
  verified_at TEXT, channel TEXT);
CREATE TABLE IF NOT EXISTS sms_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, to_number TEXT, body TEXT, provider TEXT, status TEXT, case_id TEXT);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, case_id TEXT, role TEXT, rating INTEGER, comment TEXT);
CREATE INDEX IF NOT EXISTS audit_case ON audit(case_id);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def all(self, sql: str, params: Iterable = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    # -------------------------------------------------------------- cases
    def upsert_case(self, case_dict: Dict):
        ts = now_iso()
        self.execute(
            "INSERT INTO cases(id, data, status, priority, created_at, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, status=excluded.status, "
            "priority=excluded.priority, updated_at=excluded.updated_at",
            (case_dict["id"], json.dumps(case_dict, ensure_ascii=False), case_dict.get("status"),
             case_dict.get("priority", 0), case_dict.get("call_started_at", ts), ts))

    def load_cases(self) -> List[Dict]:
        return [json.loads(r["data"]) for r in self.all("SELECT data FROM cases ORDER BY created_at")]

    def delete_case(self, case_id: str):
        for table in ("cases", "verifications"):
            col = "id" if table == "cases" else "case_id"
            self.execute(f"DELETE FROM {table} WHERE {col}=?", (case_id,))

    def purge_older_than(self, days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        rows = self.all("SELECT id FROM cases WHERE updated_at < ?", (cutoff,))
        for r in rows:
            self.delete_case(r["id"])
        self.execute("DELETE FROM sms_outbox WHERE ts < ?", (cutoff,))
        return len(rows)

    # -------------------------------------------------------------- audit
    def audit(self, actor: str, action: str, case_id: Optional[str] = None, detail: str = "", ip: str = ""):
        self.execute("INSERT INTO audit(ts, actor, action, case_id, detail, ip) VALUES (?,?,?,?,?,?)",
                     (now_iso(), actor, action, case_id, detail[:500], ip))

    def audit_for(self, case_id: str) -> List[Dict]:
        return [dict(r) for r in self.all("SELECT ts, actor, action, detail FROM audit WHERE case_id=? ORDER BY id",
                                          (case_id,))]

    # ---------------------------------------------------------------- sms
    def outbox(self, to_number: str, body: str, provider: str, status: str, case_id: Optional[str]):
        self.execute("INSERT INTO sms_outbox(ts, to_number, body, provider, status, case_id) VALUES (?,?,?,?,?,?)",
                     (now_iso(), to_number, body, provider, status, case_id))

    def outbox_list(self, limit: int = 20) -> List[Dict]:
        return [dict(r) for r in self.all("SELECT * FROM sms_outbox ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------ feedback
    def add_feedback(self, case_id: Optional[str], role: str, rating: int, comment: str):
        self.execute("INSERT INTO feedback(ts, case_id, role, rating, comment) VALUES (?,?,?,?,?)",
                     (now_iso(), case_id, role, rating, comment[:1000]))

    def feedback_summary(self) -> Dict:
        rows = self.all("SELECT role, COUNT(*) n, AVG(rating) avg FROM feedback GROUP BY role")
        recent = [dict(r) for r in self.all("SELECT ts, role, rating, comment, case_id FROM feedback ORDER BY id DESC LIMIT 20")]
        return {"by_role": {r["role"]: {"count": r["n"], "avg_rating": round(r["avg"] or 0, 2)} for r in rows},
                "recent": recent}
