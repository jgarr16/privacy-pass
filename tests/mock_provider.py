"""Local mock OpenAI-compatible provider for offline egress gating.

Captures every request body it receives and replies with a canned
completion containing alias tokens, so a single Hermes turn exercises the
full loop: request sanitization -> the provider sees only aliases ->
response restoration in the user-facing output.

Run standalone (stdlib only):

    PRIVACY_PASS_CAPTURE_DIR=/tmp/captures PRIVACY_PASS_MOCK_PORT=8765 \
        python3 tests/mock_provider.py

Point a sandboxed Hermes at http://127.0.0.1:8765/v1 via a custom provider.
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CAPTURE_DIR = Path(
    os.environ.get("PRIVACY_PASS_CAPTURE_DIR", "/tmp/privacy-pass-captures")
)
PORT = int(os.environ.get("PRIVACY_PASS_MOCK_PORT", "8765"))

import re

# Alias tokens found in the captured request are echoed back, so the canned
# reply is always self-consistent with what Privacy Pass actually produced
# (never a token the session registry does not know).
_ALIAS_RE = re.compile(r"<[A-Za-z]+ \d+>")


def reply_for(body: bytes) -> str:
    aliases = _ALIAS_RE.findall(body.decode("utf-8", "replace"))
    unique = list(dict.fromkeys(aliases))
    return "Noted: " + ", ".join(unique) + "."


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = f"{time.strftime('%H%M%S')}_{time.time_ns() % 1_000_000:06d}"
        (CAPTURE_DIR / f"request_{stamp}.json").write_bytes(body)
        reply = reply_for(body)

        created = int(time.time())
        base = {"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": created, "model": "mock-model"}

        def chunk(delta: dict, finish: str | None = None) -> bytes:
            payload = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return b"data: " + json.dumps(payload).encode() + b"\n\n"

        # Two content chunks: the first alias token is split across the
        # stream boundary on purpose, exercising held-stream restoration
        # over partial deltas.
        split = max(len(reply) // 2, 1)
        while split < len(reply) and reply[split] != " ":
            split += 1
        lines = [
            chunk({"role": "assistant", "content": reply[:split]}),
            chunk({"content": reply[split:]}),
            chunk({}, finish="stop"),
            b"data: [DONE]\n\n",
        ]
        data = b"".join(lines)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # keep the console quiet
        pass


if __name__ == "__main__":
    print(f"mock provider on 127.0.0.1:{PORT}, capturing to {CAPTURE_DIR}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
