"""1930 Saathi HTTP server (standard library only).

    python -m saathi.server            # http://127.0.0.1:8930
    python -m saathi.admin create-user officer1 --role officer

Public (caller side)
  GET  /api/health
  POST /api/calls        {lang?, caller_number?}       start a call
  POST /api/calls/<id>/turn {text | audio_b64}         one caller turn
  POST /api/verify       {case_id, code}                caller confirms the OTP sent by SMS
  POST /api/feedback     {case_id?, role, rating, comment}
  POST /api/login        {username, password}  ->  HttpOnly session cookie
  POST /api/logout       GET /api/me

Officers only (session cookie)
  GET  /api/queue  /api/cases/<id>  /api/clusters  /api/events (SSE)  /api/outbox  /api/feedback
  POST /api/cases/<id>/action {action, note}   POST /api/demo/seed

Telephony (see saathi/telephony.py)
  POST /twilio/voice   TwiML that connects the call to   wss://<host>/twilio/stream
  GET  /twilio/stream  (WebSocket)        GET /exotel/stream  (WebSocket)
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import threading
import time
import traceback
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

from . import outputs as O
from .config import ROOT, settings
from .providers.gnani import MockSTT, ProviderError, make_stt, make_tts
from .providers.llm import make_llm
from .security import Auth, CallerVerification, RateLimiter
from .sms import OutboxSMS
from .store import Store
from .validators import check_mobile

WEB = ROOT / "web"
COOKIE = "saathi_session"
PUBLIC_PAGES = {"/", "/index.html", "/caller.html", "/login.html", "/verify.html", "/feedback.html",
                "/console.html", "/collect.html"}


class App:
    def __init__(self, store: Optional[Store] = None, stt=None, tts=None, llm=None, sms=None,
                 require_login: bool = True, rate_limits: Optional[Dict] = None):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = store or Store(str(settings.data_dir / "saathi.db"))
        self.db = self.store.db
        self.stt = stt or make_stt()
        self.tts = tts or make_tts()
        self.llm = llm or make_llm()
        self.sms = sms or OutboxSMS(self.db)
        self.auth = Auth(self.db)
        self.verifier = CallerVerification(self.db)
        self.limiter = RateLimiter(rate_limits)
        self.require_login = require_login
        self.first_password: Optional[str] = None
        if require_login and not self.auth.has_users():
            import secrets
            self.first_password = os.environ.get("SAATHI_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            self.auth.create_user("admin", self.first_password, "admin")

    # ---------------------------------------------------------------- voice
    def speak(self, text: str, lang: str) -> Dict:
        code = {"hi": "hi-IN", "en": "en-IN", "pa": "pa-IN", "ta": "ta-IN"}.get(lang, "hi-IN")
        try:
            out = self.tts.synthesize(text, language=code)
        except ProviderError as e:
            return {"audio_b64": None, "tts_provider": "error", "tts_error": str(e), "tts_ms": 0}
        audio = out.get("audio")
        return {"audio_b64": base64.b64encode(audio).decode() if audio else None,
                "tts_provider": out.get("provider"), "tts_ms": round(out.get("latency_ms", 0), 1),
                "tts_note": out.get("note")}

    def health(self) -> Dict:
        return {
            "ok": True,
            "stt": getattr(self.stt, "name", "?"),
            "tts": getattr(self.tts, "name", "?"),
            "llm": getattr(self.llm, "name", "?"),
            "sms": getattr(self.sms, "name", "?"),
            "mock": isinstance(self.stt, MockSTT),
            "login_required": self.require_login,
            "synthetic_data_only": True,
            "languages": ["hi", "en", "pa", "ta"],
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    # ---------------------------------------------------------------- calls
    def start_call(self, body: Dict, channel: str = "web") -> Dict:
        lang = body.get("lang") or None
        if lang not in (None, "hi", "en", "pa", "ta"):
            lang = None
        d = self.store.new_call(lang, llm=self.llm if getattr(self.llm, "name", "rules") != "rules" else None)
        d.case.channel = channel
        if body.get("caller_label"):
            d.case.caller_label = str(body["caller_label"])[:60]
        num = body.get("caller_number")
        if num:
            chk = check_mobile(str(num))
            if chk.ok:
                d.case.caller_number = chk.value
                d.case.caller_number_source = body.get("caller_number_source", "entered")
        r = d.greeting()
        self.store.bus.publish({"type": "call_started", "case_id": d.case.id, "channel": channel})
        # the caller page gets the case here, so it never needs the officer-only GET
        return {"call_id": d.case.id, "reply": r.text, "state": r.state, "lang": d.lang,
                "case": self.store.case_detail(d.case.id), **self.speak(r.text, d.lang)}

    def turn(self, call_id: str, body: Dict, with_voice: bool = True) -> Dict:
        d = self.store.get_call(call_id)
        if not d:
            raise KeyError("call not found")
        stt_info = {}
        text = (body.get("text") or "").strip()[:2000]
        if not text and body.get("audio_b64"):
            wav = base64.b64decode(body["audio_b64"])
            lang_code = {"hi": "hi-IN", "en": "en-IN", "pa": "pa-IN", "ta": "ta-IN"}.get(d.lang, "hi-IN")
            if d.state == "open" and not d.lang_locked and settings.prisma_model == "prisma-v3.0":
                lang_code = "indic-auto"     # Prisma v3 detects the language on the first turn
            res = self.stt.transcribe(wav, language=lang_code)
            detected = (res.detected_language or "").split("-")[0]
            if d.state == "open" and not d.lang_locked and detected in ("hi", "en", "pa", "ta"):
                d.case.lang = detected
                d.lang_locked = True
            stt_info = {"stt_provider": res.provider, "stt_ms": round(res.latency_ms, 1),
                        "stt_error": res.error, "transcript": res.text}
            text = res.text
            if not text and res.error:
                return {"reply": None, "state": d.state, **stt_info}
        t0 = time.perf_counter()
        r = d.step(text, meta={k: v for k, v in stt_info.items() if k in ("stt_provider", "stt_ms")})
        nlu_ms = (time.perf_counter() - t0) * 1000
        if r.done:
            self._on_filed(d)
        voice = self.speak(r.text, d.lang) if with_voice else {}
        for ev in r.events:
            if ev.get("type") != "case_filed":   # _on_filed already announced it
                self.store.bus.publish(dict(ev, case_id=d.case.id))
        self.store.bus.publish({"type": "call_turn", "case_id": d.case.id, "state": r.state})
        self.store.save(d.case)
        return {"reply": r.text, "state": r.state, "done": r.done, "events": r.events,
                "heard": text, "nlu_ms": round(nlu_ms, 2), **stt_info, **voice,
                "case": self.store.case_detail(d.case.id)}

    def _on_filed(self, d):
        case = d.case
        case.summary = O.rule_summary(case)
        case.summary_source = "rules"
        if case.fraud_type == "other":
            key = self.llm.classify(case.narrative) if case.narrative else None
            if key:
                d._set_fraud(key, ["llm:" + getattr(self.llm, "name", "llm")])
                case.field_sources["fraud_type"] = "llm"
        out = self.llm.summarize(case.to_dict())
        if out and out.get("summary"):
            case.summary = out["summary"]
            case.summary_source = out["source"]
        # SMS acknowledgement + OTP so the officer knows the number really belongs to the caller
        if case.caller_number:
            code = self.verifier.issue(case.id)
            word = {"hi": "कोड", "pa": "ਕੋਡ", "ta": "குறியீடு"}.get(case.lang, "Code")
            body = O.sms_ack(case) + f" {word} {code}"
            self.sms.send(case.caller_number, body, case.id)
        self.db.audit("saathi", "case_filed", case.id, case.fraud_type)
        self.store.save(case)
        clusters = self.store.rescore()
        self.store.bus.publish({"type": "case_filed", "case_id": case.id})
        for cl in clusters:
            if cl["is_ring"] and case.id in cl["cases"]:
                self.store.bus.publish({"type": "mule_ring", "cluster": cl, "case_id": case.id})

    # ------------------------------------------------------------- officers
    def action(self, case_id: str, body: Dict, actor: str) -> Dict:
        c = self.store.cases.get(case_id)
        if not c:
            raise KeyError("case not found")
        act = body.get("action")
        if act not in ("freeze_requested", "closed", "filed", "note"):
            raise ValueError("unknown action")
        if act != "note":
            c.status = act
        note = (body.get("note") or "").strip()[:500]
        c.officer_notes.append({"ts": datetime.now().isoformat(timespec="seconds"), "by": actor,
                                "action": act, "note": note})
        self.db.audit(actor, act, case_id, note)
        self.store.save(c)
        self.store.bus.publish({"type": "case_updated", "case_id": case_id, "status": c.status})
        return self.store.case_detail(case_id)

    def seed(self, actor: str = "system") -> Dict:
        from .demo import SCRIPTS, seed_cases
        labels = {label for label, _ in SCRIPTS}
        for cid in [c.id for c in list(self.store.cases.values()) if c.caller_label in labels]:
            self.store.delete(cid)
        ids = seed_cases(self.store)
        for cid in ids:
            self.store.cases[cid].summary = O.rule_summary(self.store.cases[cid])
        self.store.rescore()
        self.store.save()
        self.db.audit(actor, "seed_demo", None, f"{len(ids)} cases")
        self.store.bus.publish({"type": "seeded", "count": len(ids)})
        return {"seeded": ids}

    def verify(self, body: Dict) -> Dict:
        case_id = str(body.get("case_id", "")).strip().upper()
        if not re.fullmatch(r"S1930-\d{6}", case_id):
            raise ValueError("complaint number looks like S1930-123456")
        ok, msg = self.verifier.verify(case_id, str(body.get("code", "")))
        self.db.audit("caller", "otp_verify_" + ("ok" if ok else "fail"), case_id, msg)
        if ok:
            self.store.bus.publish({"type": "case_updated", "case_id": case_id, "verification": "otp_verified"})
        return {"ok": ok, "message": msg}

    def collect(self, body: Dict) -> Dict:
        """Store one volunteer recording of a SYNTHETIC prompt card, for real-voice evaluation."""
        key = os.environ.get("COLLECT_KEY")
        if not key or body.get("key") != key:
            raise PermissionError("collection is disabled (set COLLECT_KEY and share it with volunteers)")
        if body.get("consent") is not True:
            raise ValueError("consent is required")
        import uuid
        rec_dir = settings.data_dir / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex[:12]
        wav = base64.b64decode(body.get("audio_b64") or "")
        if len(wav) < 1000 or len(wav) > 5 * 1024 * 1024:
            raise ValueError("recording too short or too long")
        (rec_dir / f"{rid}.wav").write_bytes(wav)
        meta = {"id": rid, "ts": datetime.now().isoformat(timespec="seconds"), "field": body.get("field"),
                "lang": body.get("lang"), "expected": body.get("expected"), "card": body.get("card"),
                "phone_mode": bool(body.get("phone_mode")), "volunteer": str(body.get("volunteer", ""))[:20]}
        with open(rec_dir / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        return {"ok": True, "id": rid}

    def feedback(self, body: Dict) -> Dict:
        role = body.get("role") if body.get("role") in ("caller", "officer", "tester") else "tester"
        try:
            rating = max(1, min(5, int(body.get("rating", 0))))
        except (TypeError, ValueError):
            raise ValueError("rating must be 1-5")
        self.db.add_feedback(body.get("case_id"), role, rating, str(body.get("comment", "")))
        return {"ok": True}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Saathi1930/2.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            if "/api/events" not in (self.path or "") and "/stream" not in (self.path or ""):
                super().log_message(fmt, *args)

        # ------------------------------------------------------------ utils
        @property
        def ip(self) -> str:
            fwd = self.headers.get("X-Forwarded-For") if os.environ.get("TRUST_PROXY") == "1" else None
            return (fwd.split(",")[0].strip() if fwd else self.client_address[0])

        def _send(self, code: int, payload, ctype="application/json; charset=utf-8", headers=None):
            data = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> Dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 25 * 1024 * 1024:
                raise ValueError("request too large")
            raw = self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def _token(self) -> Optional[str]:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c[COOKIE].value if COOKIE in c else None

        def _user(self) -> Optional[Dict]:
            if not app.require_login:
                return {"username": "dev", "role": "admin"}
            return app.auth.session_user(self._token())

        def _limited(self, group: str) -> bool:
            if not app.limiter.allow(self.ip, group):
                self._send(429, {"error": "too many requests, slow down"}, headers={"Retry-After": "30"})
                return True
            return False

        def _officer(self) -> Optional[Dict]:
            u = self._user()
            if not u:
                self._send(401, {"error": "login required"})
            return u

        # -------------------------------------------------------------- GET
        def do_GET(self):
            url = urlparse(self.path)
            path = url.path
            try:
                if path in ("/twilio/stream", "/exotel/stream"):
                    from .telephony import handle_media_stream
                    if self._limited("telephony"):
                        return
                    return handle_media_stream(self, app, "twilio" if path.startswith("/twilio") else "exotel")
                if path == "/api/health":
                    return self._send(200, app.health())
                if path == "/api/me":
                    u = self._user()
                    return self._send(200, {"user": u}) if u else self._send(401, {"error": "not logged in"})
                if path.startswith("/api/"):
                    if self._limited("public"):
                        return
                    u = self._officer()
                    if not u:
                        return
                    if path == "/api/queue":
                        return self._send(200, {"queue": app.store.queue_view(),
                                                "now": datetime.now().isoformat(timespec="seconds")})
                    if path == "/api/clusters":
                        app.store.rescore()
                        return self._send(200, {"clusters": app.store.clusters()})
                    if path == "/api/outbox":
                        return self._send(200, {"outbox": app.db.outbox_list()})
                    if path == "/api/feedback":
                        return self._send(200, app.db.feedback_summary())
                    m = re.fullmatch(r"/api/cases/(S1930-\d{6})", path)
                    if m:
                        d = app.store.case_detail(m.group(1))
                        if not d:
                            return self._send(404, {"error": "not found"})
                        app.db.audit(u["username"], "view_case", m.group(1), "", self.ip)
                        return self._send(200, d)
                    m = re.fullmatch(r"/api/calls/(S1930-\d{6})", path)
                    if m:
                        dlg = app.store.get_call(m.group(1))
                        if not dlg:
                            return self._send(404, {"error": "not found"})
                        return self._send(200, {"state": dlg.state, "case": app.store.case_detail(m.group(1))})
                    if path == "/api/events":
                        return self._sse()
                    return self._send(404, {"error": "not found"})
                return self._static(path)
            except Exception as e:  # pragma: no cover
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

        # ------------------------------------------------------------- POST
        def do_POST(self):
            path = urlparse(self.path).path
            try:
                if path == "/twilio/voice":
                    from .telephony import twiml_response
                    n = int(self.headers.get("Content-Length") or 0)
                    form = parse_qs(self.rfile.read(n).decode()) if n else {}
                    host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host")
                    token = os.environ.get("TWILIO_AUTH_TOKEN")
                    if token:
                        from .telephony import twilio_signature_ok
                        if not twilio_signature_ok(f"https://{host}/twilio/voice", form,
                                                   self.headers.get("X-Twilio-Signature", ""), token):
                            return self._send(403, {"error": "bad Twilio signature"})
                    return self._send(200, twiml_response(host, form).encode(), "text/xml; charset=utf-8")
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
                if ctype != "application/json":
                    # browsers cannot send cross-site JSON without a CORS preflight, which we never allow
                    return self._send(415, {"error": "send application/json"})
                body = self._body()
                if path == "/api/login":
                    if self._limited("login"):
                        return
                    token = app.auth.login(str(body.get("username", "")), str(body.get("password", "")))
                    app.db.audit(str(body.get("username", ""))[:40], "login_" + ("ok" if token else "fail"), None, "", self.ip)
                    if not token:
                        return self._send(401, {"error": "wrong username or password"})
                    secure = "; Secure" if os.environ.get("HTTPS") == "1" else ""
                    cookie = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={8 * 3600}{secure}"
                    return self._send(200, {"ok": True, "user": app.auth.session_user(token)}, headers={"Set-Cookie": cookie})
                if path == "/api/logout":
                    app.auth.logout(self._token())
                    return self._send(200, {"ok": True}, headers={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})
                if path == "/api/calls":
                    if self._limited("call_start"):
                        return
                    return self._send(200, app.start_call(body))
                m = re.fullmatch(r"/api/calls/(S1930-\d{6})/turn", path)
                if m:
                    if self._limited("turn"):
                        return
                    return self._send(200, app.turn(m.group(1), body))
                if path == "/api/verify":
                    if self._limited("verify"):
                        return
                    return self._send(200, app.verify(body))
                if path == "/api/feedback":
                    if self._limited("verify"):
                        return
                    return self._send(200, app.feedback(body))
                if path == "/api/collect":
                    if self._limited("turn"):
                        return
                    try:
                        return self._send(200, app.collect(body))
                    except PermissionError as e:
                        return self._send(403, {"error": str(e)})
                # officer-only below
                u = self._officer()
                if not u:
                    return
                m = re.fullmatch(r"/api/cases/(S1930-\d{6})/action", path)
                if m:
                    return self._send(200, app.action(m.group(1), body, u["username"]))
                if path == "/api/demo/seed":
                    return self._send(200, app.seed(u["username"]))
                return self._send(404, {"error": "not found"})
            except KeyError as e:
                return self._send(404, {"error": str(e)})
            except ProviderError as e:
                return self._send(502, {"error": str(e)})
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # pragma: no cover
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

        # ----------------------------------------------------------- static
        def _static(self, path: str):
            if path in ("/", ""):
                path = "/index.html"
            target = (WEB / path.lstrip("/")).resolve()
            if WEB.resolve() not in target.parents:
                return self._send(403, {"error": "forbidden"})
            if not target.is_file():
                return self._send(404, {"error": "not found"})
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._send(200, target.read_bytes(), ctype)

        def _sse(self):
            q = app.store.bus.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=15)
                        data = json.dumps(ev, ensure_ascii=False)
                        self.wfile.write(f"event: {ev.get('type', 'message')}\ndata: {data}\n\n".encode("utf-8"))
                    except Exception:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.store.bus.unsubscribe(q)
                self.close_connection = True

    return Handler


def serve(host: Optional[str] = None, port: Optional[int] = None, app: Optional[App] = None):
    app = app or App()
    httpd = ThreadingHTTPServer((host or settings.host, settings.port if port is None else port), make_handler(app))
    httpd.daemon_threads = True
    return httpd, app


def main():
    httpd, app = serve()
    h = app.health()
    print(f"1930 Saathi running at http://{settings.host}:{settings.port}")
    print(f"  STT: {h['stt']}   TTS: {h['tts']}   LLM: {h['llm']}   SMS: {h['sms']}   mock={h['mock']}")
    if app.first_password:
        print(f"  First run: officer console login  ->  username: admin   password: {app.first_password}")
        print("  (set SAATHI_ADMIN_PASSWORD to choose it; add officers with: python -m saathi.admin create-user NAME)")
    if h["mock"]:
        print("  Mock mode: set GNANI_API_KEY in .env to use Gnani Prisma + Timbre.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
