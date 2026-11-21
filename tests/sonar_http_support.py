"""A bounded loopback Web API double for Sonar lifecycle and evidence contracts."""

from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs
from urllib.parse import urlsplit


class SonarHttpServer:
    """Serve real HTTP requests while keeping all account/project state in memory."""

    def __init__(self):
        """Create a fresh simulated installation with no persistent credentials."""
        self.password = "admin"
        self.project = False
        self.status = "UP"
        self.calls = []
        self.fail_token = False
        self.forbidden_project = False
        self.ce_status = "SUCCESS"
        self.analysis = "analysis-current"
        self.latest_analysis = "analysis-current"
        self.revision = "analyzed-revision"
        self.issue_count = 501
        self.reference = "2026-11-21T16:46:16+0000"
        self.redirect = "/must-not-receive-credentials"
        self.server = None
        self.thread = None

    def __enter__(self):
        """Bind only an OS-assigned loopback port and start the owned thread."""
        def respond(handler):
            length = int(handler.headers.get("Content-Length", 0))
            data = parse_qs(handler.rfile.read(length).decode()) if length else {}
            path = urlsplit(handler.path)
            query = parse_qs(path.query)
            authorization = handler.headers.get("Authorization", "")
            self.calls.append((handler.command, path.path, data, authorization, query))
            authorized = authorization == "Basic " + base64.b64encode(f"admin:{self.password}".encode()).decode()
            code, body = 200, {}
            if path.path == "/redirect":
                handler.send_response(302)
                handler.send_header("Location", self.redirect)
                handler.end_headers()
                return
            if path.path == "/invalid-json":
                handler.send_response(200)
                handler.end_headers()
                handler.wfile.write(b"not-json")
                return
            if path.path == "/api/system/status":
                body = {"status": self.status, "version": "test-only"}
            elif path.path == "/api/authentication/validate":
                body = {"valid": authorized}
            elif not authorized:
                code, body = 401, {"errors": [{"msg": "private response must not be logged"}]}
            elif path.path == "/api/users/change_password":
                if data.get("previousPassword") != [self.password]:
                    code = 400
                else:
                    self.password = data["password"][0]
            elif path.path == "/api/components/show":
                code = 403 if self.forbidden_project else 200 if self.project else 404
                body = {"component": {"key": "mathmongo-local"}} if code == 200 else {}
            elif path.path == "/api/projects/create":
                self.project = True
            elif path.path == "/api/user_tokens/generate":
                if self.fail_token:
                    self.fail_token = False
                    code = 503
                else:
                    body = {"token": "test-project-analysis-token"}
            elif path.path == "/api/ce/task":
                body = {"task": {"id": query["id"][0], "status": self.ce_status, "analysisId": self.analysis}}
            elif path.path == "/api/project_analyses/search":
                body = {"analyses": [{"key": self.latest_analysis, "revision": self.revision}]}
            elif path.path == "/api/metrics/search":
                body = {"metrics": [{"key": "coverage"}, {"key": "ncloc"}]}
            elif path.path == "/api/measures/component":
                body = {"component": {"measures": [{"metric": "coverage", "value": "31.2"}]}}
            elif path.path == "/api/qualitygates/project_status":
                body = {"projectStatus": {"status": "ERROR", "period": {"mode": "PREVIOUS_VERSION", "date": self.reference}}}
            elif path.path == "/api/new_code_periods/show":
                body = {"type": "PREVIOUS_VERSION", "inherited": True}
            elif path.path == "/api/issues/search":
                page = int(query["p"][0])
                start = (page - 1) * 500
                body = {"paging": {"total": self.issue_count},
                        "issues": [{"key": f"issue-{index}"} for index in range(start, min(start + 500, self.issue_count))]}
            elif path.path == "/api/qualityprofiles/search":
                body = {"profiles": []}
            elif path.path == "/api/hotspots/search":
                body = {"hotspots": []}
            else:
                code = 404
            payload = json.dumps(body).encode()
            handler.send_response(code)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)

        handler = type("LocalHandler", (BaseHTTPRequestHandler,), {
            "do_GET": respond, "do_POST": respond, "log_message": lambda *_args: None,
        })
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self):
        """Return the actual loopback endpoint rather than a configured default."""
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *_args):
        """Release the listener and join only the thread owned by this double."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
