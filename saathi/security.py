"""Officer authentication, sessions, caller OTP verification and rate limiting.

* passwords: PBKDF2-HMAC-SHA256, 200k iterations, per-user salt, constant-time compare
* sessions: random 32-byte token in an HttpOnly, SameSite=Strict cookie; only its SHA-256 is stored
* caller verification: 6-digit OTP sent by SMS after the complaint is filed (non-blocking for the
  victim: the complaint is acted on immediately, and the badge tells the officer whether the
  caller's number was confirmed)
* rate limiting: token bucket per client IP and route group
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from .db import DB, now_iso

PBKDF2_ITERATIONS = 200_000
SESSION_HOURS = 8
OTP_MINUTES = 30
OTP_MAX_ATTEMPTS = 5


def hash_password(password: str, salt: Optional[str] = None, iterations: int = PBKDF2_ITERATIONS) -> Tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    return dk.hex(), salt


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class Auth:
    def __init__(self, db: DB):
        self.db = db

    def has_users(self) -> bool:
        return self.db.one("SELECT 1 FROM users LIMIT 1") is not None

    def create_user(self, username: str, password: str, role: str = "officer"):
        if len(password) < 10:
            raise ValueError("password must be at least 10 characters")
        if role not in ("officer", "admin"):
            raise ValueError("role must be officer or admin")
        h, salt = hash_password(password)
        self.db.execute("INSERT OR REPLACE INTO users(username, pw_hash, salt, iterations, role, created_at) "
                        "VALUES (?,?,?,?,?,?)", (username, h, salt, PBKDF2_ITERATIONS, role, now_iso()))

    def check_password(self, username: str, password: str) -> Optional[str]:
        row = self.db.one("SELECT * FROM users WHERE username=? AND disabled=0", (username,))
        if not row:
            hash_password(password)  # same work either way: no username probing by timing
            return None
        h, _ = hash_password(password, row["salt"], row["iterations"])
        return row["role"] if hmac.compare_digest(h, row["pw_hash"]) else None

    def login(self, username: str, password: str) -> Optional[str]:
        if not self.check_password(username, password):
            return None
        token = secrets.token_urlsafe(32)
        exp = (datetime.now() + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
        self.db.execute("INSERT INTO sessions(token_hash, username, created_at, expires_at) VALUES (?,?,?,?)",
                        (_sha(token), username, now_iso(), exp))
        return token

    def session_user(self, token: Optional[str]) -> Optional[Dict]:
        if not token:
            return None
        row = self.db.one("SELECT s.username, s.expires_at, u.role FROM sessions s JOIN users u ON u.username=s.username "
                          "WHERE s.token_hash=? AND u.disabled=0", (_sha(token),))
        if not row or row["expires_at"] < now_iso():
            return None
        return {"username": row["username"], "role": row["role"]}

    def logout(self, token: Optional[str]):
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_sha(token),))


class CallerVerification:
    """OTP to the caller's mobile after filing; the officer sees verified / pending / failed."""

    def __init__(self, db: DB):
        self.db = db

    def issue(self, case_id: str, channel: str = "sms") -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(8)
        exp = (datetime.now() + timedelta(minutes=OTP_MINUTES)).isoformat(timespec="seconds")
        self.db.execute("INSERT OR REPLACE INTO verifications(case_id, code_hash, salt, expires_at, attempts, "
                        "verified_at, channel) VALUES (?,?,?,?,0,NULL,?)",
                        (case_id, _sha(salt + code), salt, exp, channel))
        return code

    def verify(self, case_id: str, code: str) -> Tuple[bool, str]:
        row = self.db.one("SELECT * FROM verifications WHERE case_id=?", (case_id,))
        if not row:
            return False, "no verification pending for this complaint"
        if row["verified_at"]:
            return True, "already verified"
        if row["attempts"] >= OTP_MAX_ATTEMPTS:
            return False, "too many attempts"
        if row["expires_at"] < now_iso():
            return False, "code expired"
        self.db.execute("UPDATE verifications SET attempts=attempts+1 WHERE case_id=?", (case_id,))
        if hmac.compare_digest(_sha(row["salt"] + code.strip()), row["code_hash"]):
            self.db.execute("UPDATE verifications SET verified_at=? WHERE case_id=?", (now_iso(), case_id))
            return True, "verified"
        return False, "wrong code"

    def status(self, case_id: str) -> str:
        row = self.db.one("SELECT verified_at, attempts, expires_at FROM verifications WHERE case_id=?", (case_id,))
        if not row:
            return "none"
        if row["verified_at"]:
            return "verified"
        if row["attempts"] >= OTP_MAX_ATTEMPTS:
            return "failed"
        if row["expires_at"] < now_iso():
            return "expired"
        return "pending"


class RateLimiter:
    """Token bucket per (ip, group). Defaults are per minute."""

    LIMITS = {"login": 10, "call_start": 20, "turn": 120, "verify": 15, "public": 240, "telephony": 600}

    def __init__(self, limits: Optional[Dict[str, int]] = None):
        self.limits = dict(self.LIMITS, **(limits or {}))
        self.buckets: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, ip: str, group: str) -> bool:
        cap = self.limits.get(group, self.limits["public"])
        rate = cap / 60.0
        now = time.monotonic()
        with self.lock:
            tokens, last = self.buckets.get((ip, group), (float(cap), now))
            tokens = min(cap, tokens + (now - last) * rate)
            if tokens < 1:
                self.buckets[(ip, group)] = (tokens, now)
                return False
            self.buckets[(ip, group)] = (tokens - 1, now)
            return True
