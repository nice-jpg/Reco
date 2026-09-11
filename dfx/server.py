"""Read-only localhost HTTP adapter around PageSession's existing public tools."""
import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import uuid

from model_interface import PageSession


STATIC = Path(__file__).parent / "static"


class Debugger:
    def __init__(self, runs):
        self.runs = Path(runs).resolve()
        self.sessions = OrderedDict()
        self.lock = threading.Lock()

    def cases(self):
        cases = []
        for path in sorted(self.runs.rglob("tree.json")):
            directory = path.parent.resolve()
            try:
                relative = directory.relative_to(self.runs)
            except ValueError:
                continue
            if all((directory / name).is_file() for name in ("index.json", "payload.json")):
                cases.append({"id": relative.as_posix(), "name": relative.as_posix()})
        return cases

    def start(self, case):
        if case not in {c["id"] for c in self.cases()}:
            raise ValueError("Unknown run case")
        session = PageSession.load(self.runs / case)
        token = uuid.uuid4().hex
        with self.lock:
            self.sessions[token] = session
            while len(self.sessions) > 32:
                self.sessions.popitem(last=False)
        # Transport token is not inserted into the public tool responses.
        return {"session": token, "initial": session.start()}

    def call(self, token, name, arguments):
        with self.lock:
            session = self.sessions.get(token)
        if session is None:
            raise ValueError("Session expired; reload this case")
        return session.call(name, arguments)


def handler_for(debugger):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/cases":
                return self.send(200, {"cases": debugger.cases()})
            files = {"/": ("index.html", "text/html"), "/app.mjs": ("app.mjs", "text/javascript"),
                     "/core.mjs": ("core.mjs", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if path not in files:
                return self.send(404, {"error": "Not found"})
            name, mime = files[path]
            self.send(200, (STATIC / name).read_bytes(), mime + "; charset=utf-8")

        def do_POST(self):
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                return self.send(403, {"error": "Cross-origin request rejected"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected JSON object")
                if self.path == "/api/session":
                    result = debugger.start(body["case"])
                elif self.path == "/api/tool":
                    result = debugger.call(body["session"], body["name"], body["arguments"])
                else:
                    return self.send(404, {"error": "Not found"})
                self.send(200, result)
            except (ValueError, TypeError, KeyError, OSError) as error:
                self.send(400, {"error": str(error)})

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path(__file__).resolve().parents[1] / "runs")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Debugger(args.runs)))
    print(f"DFX http://127.0.0.1:{server.server_port}  runs={args.runs.resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
