"""Read-only localhost HTTP adapter around PageSession's existing public tools."""
import argparse
from copy import deepcopy
import xml.etree.ElementTree as ET
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import uuid

from .. import PageSession


STATIC = Path(__file__).parent / "static"


class Debugger:
    def __init__(self, examples):
        self.examples = Path(examples).resolve()
        self.sessions = OrderedDict()
        self.lock = threading.Lock()

    def cases(self):
        cases = []
        for path in sorted(self.examples.rglob("*.xml")):
            if not path.is_file() or not path.resolve().is_relative_to(self.examples):
                continue
            relative = path.relative_to(self.examples).as_posix()
            cases.append({"id": relative, "name": relative})
        return cases

    @staticmethod
    def snapshot(session):
        p = session.bundle.presentation
        result = {}
        for key, region in p.regions.items():
            own = [p.payload[i] for i in p._entries[key] if p.owner[p.payload[i]["node"]] == key]
            result[key] = {**session.bundle.node(key),
                           "text": " ".join(e["value"] for e in own if e["attribute"] == "text")}
        return result

    def start(self, case, previous=None):
        if case not in {c["id"] for c in self.cases()}:
            raise ValueError("Unknown XML case")
        incoming = PageSession.build_tree((self.examples / case).read_text(encoding="utf-8"))
        diff = {"nodes": {}, "deleted": [], "root": None}
        if previous is not None:
            with self.lock:
                baseline = self.sessions.get(previous)
                if baseline is None:
                    raise ValueError("Session expired; disable Sync and reload")
                session = deepcopy(baseline)
            before = self.snapshot(session)
            session.sync(incoming)
            after = self.snapshot(session)
            diff["root"] = session.last_change_root
            replaced = {c["id"] for c in session.last_changes if c["kind"] == "replaced"}
            changed_ids = {c["id"] for c in session.last_changes if c["kind"] == "updated"}
            for key, node in after.items():
                old = before.get(key)
                fields = {name: {"before": (old or {}).get(name), "after": node.get(name)}
                          for name in set(node) | set(old or {}) if (old or {}).get(name) != node.get(name)}
                if old is None or fields or key in changed_ids:
                    diff["nodes"][key] = {"kind": "replaced" if key in replaced else "added" if old is None else "updated",
                                           "attributes": fields}
            diff["deleted"] = [node for key, node in before.items() if key not in after]
        else:
            session = incoming
        token = uuid.uuid4().hex
        with self.lock:
            self.sessions[token] = session
            while len(self.sessions) > 32:
                self.sessions.popitem(last=False)
        # Each request branches from the last displayed snapshot. Aborted loads
        # cannot mutate the baseline for a later selection.
        return {"session": token, "initial": session.start(), "diff": diff}

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
                elif self.path == "/api/sync":
                    result = debugger.start(body["case"], body["session"])
                elif self.path == "/api/tool":
                    result = debugger.call(body["session"], body["name"], body["arguments"])
                else:
                    return self.send(404, {"error": "Not found"})
                self.send(200, result)
            except (ValueError, TypeError, KeyError, OSError, ET.ParseError) as error:
                self.send(400, {"error": str(error)})

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, default=Path(__file__).resolve().parents[1] / "examples")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Debugger(args.examples)))
    print(f"DFX http://127.0.0.1:{server.server_port}  examples={args.examples.resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
