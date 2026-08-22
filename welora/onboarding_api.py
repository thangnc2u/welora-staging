"""
Welora — S1-05: Onboarding HTTP adapter

  POST   /onboarding/session
  PATCH  /onboarding/session/{id}/step/{n}
  POST   /onboarding/session/{id}/complete
  GET    /users/{id}/dna?source=self
  GET    /users/{id}/personal-constitution
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

import welora.onboarding as ob


def service_create_session(body: dict) -> tuple[int, dict]:
    user_id = body.get("user_id")
    if not user_id:
        return 400, {"error": "user_id is required"}
    s = ob.create_session(str(user_id))
    return 201, s.to_dict()


def service_patch_step(session_id: str, step: int, body: dict) -> tuple[int, dict]:
    try:
        s = ob.patch_step(session_id, step, body)
        out = s.to_dict()
        if step == 4 and "articles" not in body:
            out["proposed_articles"] = ob.propose_constitution(s)
        return 200, out
    except KeyError:
        return 404, {"error": "session not found"}
    except ValueError as e:
        return 400, {"error": str(e)}


def service_complete(session_id: str) -> tuple[int, dict]:
    try:
        result = ob.complete_session(session_id)
        return 200, result
    except KeyError:
        return 404, {"error": "session not found"}
    except ValueError as e:
        return 400, {"error": str(e)}


def service_get_dna(user_id: str) -> tuple[int, dict]:
    dna = ob.get_dna(user_id)
    if not dna:
        return 404, {"error": "dna not found"}
    return 200, dna


def service_get_constitution(user_id: str) -> tuple[int, dict]:
    c = ob.get_constitution(user_id)
    if not c:
        return 404, {"error": "personal constitution not found"}
    return 200, c


class OnboardingHandler(BaseHTTPRequestHandler):
    server_version = "WeloraOnboarding/0.1"

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/onboarding/session":
            code, body = service_create_session(self._read_json())
            self._json(code, body)
            return
        m = re.fullmatch(r"/onboarding/session/([^/]+)/complete", path)
        if m:
            code, body = service_complete(m.group(1))
            self._json(code, body)
            return
        self._json(404, {"error": "not found"})

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        m = re.fullmatch(r"/onboarding/session/([^/]+)/step/(\d+)", path)
        if m:
            code, body = service_patch_step(m.group(1), int(m.group(2)), self._read_json())
            self._json(code, body)
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        m = re.fullmatch(r"/users/([^/]+)/dna", path)
        if m:
            code, body = service_get_dna(m.group(1))
            self._json(code, body)
            return
        m = re.fullmatch(r"/users/([^/]+)/personal-constitution", path)
        if m:
            code, body = service_get_constitution(m.group(1))
            self._json(code, body)
            return
        if path in ("/health", "/"):
            self._json(200, {"ok": True, "service": "welora-onboarding"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[onboarding_api] {args[0]}")


def run_server(host: str = "127.0.0.1", port: int = 8788) -> None:
    httpd = HTTPServer((host, port), OnboardingHandler)
    print(f"Welora Onboarding API on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
