"""A local stand-in for Gnani's API that checks our requests match the documented format.

It does not do speech recognition; it echoes a fixed transcript so the client
code paths (multipart upload, auth header, JSON TTS body, WebSocket streaming
with commit) can be tested offline.
"""
import base64
import hashlib
import io
import json
import socketserver
import struct
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from saathi.providers.ws import OP_BINARY, OP_CLOSE, OP_TEXT, decode_frame, encode_frame

API_KEY = "test-key"
TRANSCRIPT = "मेरे 45 हज़ार रुपये कट गए"
SEEN = {}


def tiny_wav(seconds=0.2, sr=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(seconds * sr))
    return buf.getvalue()


class HTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.headers.get("X-API-Key-ID") != API_KEY:
            self.send_response(401)
            self.end_headers()
            return
        if self.path == "/stt/v3":
            ctype = self.headers.get("Content-Type", "")
            SEEN["stt_ctype"] = ctype
            SEEN["stt_has_audio_file"] = b'name="audio_file"' in body
            SEEN["stt_has_language"] = b'name="language_code"' in body
            out = json.dumps({"success": True, "request_id": "r1", "transcript": TRANSCRIPT,
                              "model": "prisma-v2.5"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        elif self.path == "/api/v1/tts/inference":
            SEEN["tts_body"] = json.loads(body)
            wav = tiny_wav()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)
        else:
            self.send_response(404)
            self.end_headers()


class WSHandler(socketserver.BaseRequestHandler):
    """Prisma realtime stand-in: checks headers, counts PCM frames, replies after commit."""

    def handle(self):
        sock = self.request
        data = b""
        while b"\r\n\r\n" not in data:
            data += sock.recv(4096)
        head, rest = data.split(b"\r\n\r\n", 1)
        hdrs = {}
        for line in head.split(b"\r\n")[1:]:
            k, v = line.split(b":", 1)
            hdrs[k.strip().lower().decode()] = v.strip().decode()
        SEEN["ws_headers"] = hdrs
        key = hdrs["sec-websocket-key"]
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        buf = [rest]

        def read_exact(n):
            while len(buf[0]) < n:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError
                buf[0] += chunk
            out, buf[0] = buf[0][:n], buf[0][n:]
            return out

        frames = 0
        max_frame = 0
        try:
            while True:
                fin, op, payload = decode_frame(read_exact)
                if op == OP_BINARY:
                    frames += 1
                    max_frame = max(max_frame, len(payload))
                elif op == OP_TEXT and json.loads(payload).get("type") == "commit":
                    SEEN["ws_frames"] = frames
                    SEEN["ws_max_frame"] = max_frame
                    for seg, text in (("0", "मेरे 45"), ("0", "मेरे 45 हज़ार"), ("1", "रुपये कट गए")):
                        msg = json.dumps({"type": "transcript", "text": text, "segment_id": seg, "latency": 120})
                        sock.sendall(encode_frame(OP_TEXT, msg.encode(), mask=False))
                    sock.sendall(encode_frame(OP_CLOSE, struct.pack("!H", 1000), mask=False))
                    return
                elif op == OP_CLOSE:
                    return
        except ConnectionError:
            return


def start():
    http = ThreadingHTTPServer(("127.0.0.1", 0), HTTPHandler)
    ws = socketserver.ThreadingTCPServer(("127.0.0.1", 0), WSHandler)
    ws.daemon_threads = True
    for srv in (http, ws):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return http, ws
