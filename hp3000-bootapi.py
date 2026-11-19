#!/usr/bin/env python3
"""HP3000 boot-API -- send_keys/read_screen bridge for the HP3000 Hacker
Replicant (see README.md for the full picture). A small stdlib-only HTTP
server that exposes exactly two actions on an existing `screen` session:

  GET  /api/hp3000/screen   -> {"text": "..."} hardcopy of the 'hp3000' screen session
  POST /api/hp3000/keys     body {"text": "..."} -> types into that same session

Deliberately limited to reading and typing in the already-visible terminal
session (the same session your web console attaches to): no shell, no
filesystem access. Runs as whichever user owns the `screen` session. Listens
on :8092, CORS open -- this is meant to be reachable from the chat backend
only; don't expose it to the public internet without adding your own auth
layer.

Why a SESSIONS dict instead of one hardcoded session name: on the machine
this was originally written for, the same little HTTP server happened to
also bridge a second, unrelated simulator (a VAX) running on the same
physical host, under /api/vax/... -- same `screen -X stuff`/`hardcopy`
pattern, just a different session name. Nothing about this script is
HP3000-specific beyond the one entry below; if you ever co-locate another
SIMH-based replica on the same Pi, you can add it as another {name: session}
pair and it gets its own /api/<name>/screen and /api/<name>/keys for free.
For a single-machine HP3000 setup, the 'hp3000' entry is all you need --
leave the rest of this file alone.
"""
import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

SESSIONS = {"hp3000": "hp3000"}  # {url-namespace: screen session name} -- add more entries here for co-located machines
HARDCOPY_TMPL = "/tmp/hp3000-bootapi-hardcopy-{}.txt"


def send_keys(machine, text):
    session = SESSIONS[machine]
    literal = text.replace("\\r", "\r").replace("\\n", "\r")
    subprocess.run(["screen", "-S", session, "-X", "stuff", literal],
                   capture_output=True, timeout=10, check=True)


def read_screen(machine):
    session = SESSIONS[machine]
    hardcopy = HARDCOPY_TMPL.format(machine)
    try:
        os.remove(hardcopy)
    except OSError:
        pass
    subprocess.run(["screen", "-S", session, "-X", "hardcopy", hardcopy],
                   capture_output=True, timeout=10, check=True)
    for _ in range(10):
        if os.path.exists(hardcopy):
            break
        time.sleep(0.1)
    try:
        with open(hardcopy, errors="replace") as f:
            return f.read()
    except OSError:
        return "(could not read hardcopy)"


class Handler(BaseHTTPRequestHandler):
    def _respond(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _parse_machine(self, path):
        parts = path.strip("/").split("/")
        # expected: api/<machine>/<action>
        if len(parts) != 3 or parts[0] != "api" or parts[1] not in SESSIONS:
            return None, None
        return parts[1], parts[2]

    def do_GET(self):
        path = urlparse(self.path).path
        machine, action = self._parse_machine(path)
        if machine and action == "screen":
            try:
                self._respond(200, {"text": read_screen(machine)})
            except Exception as e:
                self._respond(500, {"error": str(e)})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        machine, action = self._parse_machine(path)
        if machine and action == "keys":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._respond(400, {"error": "invalid JSON"})
                return
            text = payload.get("text", "")
            if not isinstance(text, str) or not text:
                self._respond(400, {"error": "'text' (string) is required"})
                return
            try:
                send_keys(machine, text)
                self._respond(200, {"ok": True})
            except Exception as e:
                self._respond(500, {"error": str(e)})
        else:
            self._respond(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8092), Handler).serve_forever()
