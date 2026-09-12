"""Flask REST API: same endpoints and JSON shape as the Windows SMTC Bridge."""

import logging
import sys
import threading

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.serving import make_server

from .media_source import MediaSource


def create_app(source: MediaSource) -> Flask:
    app = Flask(__name__)
    CORS(app)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/now-playing")
    def now_playing():
        try:
            return jsonify(source.payload())
        except Exception as e:
            return jsonify({"current_session_id": None, "sessions": [], "error": str(e)})

    @app.route("/sessions", methods=["GET"])
    def get_sessions():
        try:
            sessions = source.session_ids()
            html = (
                "<body style='background-color: #121212; color: white; font-family: sans-serif; padding: 20px;'>"
                "<h3 style='margin-top: 0;'>Active Audio Sources:</h3><ul>"
            )
            if not sessions:
                html += "<li style='color: #888;'>No active audio sources found.</li>"
            for s in sessions:
                html += f"<li style='margin-bottom: 8px; font-size: 1.1em;'>{s}</li>"
            return html + "</ul></body>"
        except Exception as e:
            return f"<body style='background-color: #121212; color: #ff5555;'>Error: {e}</body>"

    return app


def bind_addresses(host: str) -> list[str]:
    """Listen on both IPv4 and IPv6 for loopback/wildcard hosts.

    Browsers resolve `localhost` to ::1 first on macOS, and Control Center's AirPlay Receiver
    squats on *:5000 (IPv4 + IPv6) whenever the port is free, so binding only 127.0.0.1 leaves
    `http://localhost:5000` answered by AirPlay with a 403.
    """
    if host in ("127.0.0.1", "localhost"):
        return ["127.0.0.1", "::1"]
    if host in ("0.0.0.0", ""):
        return ["0.0.0.0", "::"]
    return [host]


def run_server(app: Flask, host: str, port: int) -> None:
    """Serve on every address for `host`; runs until the process exits. Raises if nothing could bind."""
    servers = []
    for addr in bind_addresses(host):
        try:
            servers.append(make_server(addr, port, app, threaded=True))
        except OSError as e:
            print(f"Could not bind {addr}:{port}: {e}", file=sys.stderr)
    if not servers:
        raise OSError(f"Could not bind port {port} on any address for host '{host}'")
    threads = [threading.Thread(target=s.serve_forever, name=f"http-{s.host}", daemon=True) for s in servers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
