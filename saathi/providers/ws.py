"""A minimal RFC 6455 WebSocket client using only the standard library.

Needed because browsers cannot set the `x-api-key-id` header that Prisma's
realtime endpoint expects, so the server opens the socket on the caller's
behalf. Supports text/binary frames, masking, fragmentation, ping/pong and
close. Not a general-purpose library: just enough for streaming STT.
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocketError(Exception):
    pass


def encode_frame(opcode: int, payload: bytes, mask: bool = True, fin: bool = True,
                 mask_key: Optional[bytes] = None) -> bytes:
    head = bytearray()
    head.append((0x80 if fin else 0) | opcode)
    n = len(payload)
    mbit = 0x80 if mask else 0
    if n < 126:
        head.append(mbit | n)
    elif n < 65536:
        head.append(mbit | 126)
        head += struct.pack("!H", n)
    else:
        head.append(mbit | 127)
        head += struct.pack("!Q", n)
    if mask:
        key = mask_key or os.urandom(4)
        head += key
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return bytes(head) + payload


def decode_frame(read_exact) -> Tuple[bool, int, bytes]:
    """Read one frame using read_exact(n) -> bytes. Returns (fin, opcode, payload)."""
    b1, b2 = read_exact(2)
    fin = bool(b1 & 0x80)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    n = b2 & 0x7F
    if n == 126:
        (n,) = struct.unpack("!H", read_exact(2))
    elif n == 127:
        (n,) = struct.unpack("!Q", read_exact(8))
    key = read_exact(4) if masked else None
    payload = read_exact(n) if n else b""
    if key:
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
    return fin, opcode, payload


class WebSocket:
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 15.0):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._buf = b""

    def connect(self):
        u = urlparse(self.url)
        secure = u.scheme == "wss"
        port = u.port or (443 if secure else 80)
        raw = socket.create_connection((u.hostname, port), timeout=self.timeout)
        if secure:
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=u.hostname)
        self.sock = raw
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        host = u.hostname if port in (80, 443) else f"{u.hostname}:{port}"
        lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket",
                 "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        lines += [f"{k}: {v}" for k, v in self.headers.items()]
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WebSocketError("connection closed during handshake")
            resp += chunk
        head, self._buf = resp.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status + " ":
            raise WebSocketError(f"handshake failed: {status}")
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        hdrs = {}
        for line in head.split(b"\r\n")[1:]:
            if b":" in line:
                k, v = line.split(b":", 1)
                hdrs[k.strip().lower().decode()] = v.strip().decode()
        if hdrs.get("sec-websocket-accept") != expected:
            raise WebSocketError("bad Sec-WebSocket-Accept")
        return self

    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise WebSocketError("connection closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send_text(self, text: str):
        self.sock.sendall(encode_frame(OP_TEXT, text.encode("utf-8")))

    def send_binary(self, data: bytes):
        self.sock.sendall(encode_frame(OP_BINARY, data))

    def recv(self) -> Tuple[int, bytes]:
        """Return (opcode, payload) for the next complete text/binary message."""
        parts = []
        first_op = None
        while True:
            fin, op, payload = decode_frame(self._read_exact)
            if op == OP_PING:
                self.sock.sendall(encode_frame(OP_PONG, payload))
                continue
            if op == OP_PONG:
                continue
            if op == OP_CLOSE:
                return OP_CLOSE, payload
            if op != OP_CONT:
                first_op = op
            parts.append(payload)
            if fin:
                return first_op or op, b"".join(parts)

    def settimeout(self, t: float):
        if self.sock:
            self.sock.settimeout(t)

    def close(self):
        if self.sock:
            try:
                self.sock.sendall(encode_frame(OP_CLOSE, struct.pack("!H", 1000)))
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
