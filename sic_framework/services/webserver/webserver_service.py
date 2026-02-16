"""
Webserver service for the Social Interaction Cloud.

This service provides a web server that can be used to serve static files and dynamic content.
It also provides a SocketIO server that can be used to communicate with the frontend.
"""

import os
import threading
import logging
import time
import subprocess
import re
import importlib
import socket
import importlib.metadata
from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file, Blueprint
from flask_socketio import SocketIO, emit
from typing import Any, Dict, List, Optional, Tuple

from sic_framework import SICComponentManager
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage
from sic_framework.core.utils import is_sic_instance


class TranscriptMessage(SICMessage):
    """Message containing speech transcript to be displayed."""
    def __init__(self, transcript):
        self.transcript = transcript

class HtmlMessage(SICMessage):
    """Message for requesting the rendering of specific HTML content or text."""
    def __init__(self, text="", html=""):
        self.text = text
        self.html = html

class WebInfoMessage(SICMessage):
    """Generic message to send labeled data to the frontend."""
    def __init__(self, label, message):
        self.label = label
        self.message = message

class SetTurnMessage(SICMessage):
    """Message to indicate turn-taking state."""
    def __init__(self, user_turn):
        self.user_turn = user_turn

class ButtonClicked(SICMessage):
    """Output message when a button is clicked on the frontend."""
    def __init__(self, button):
        self.button = button

class WebserverConf(SICConfMessage):
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        templates_dir: str = None,
        static_dir: str = None,
        static_url_path: str = "/static",
        ssl_cert: str = None,
        ssl_key: str = None,
        ephemeral: bool = False,
        # Pages registry: route -> template name (rendered via Jinja).
        pages: Optional[Dict[str, str]] = None,
        # Extension loading: list of import specs like "pkg.module:ExtensionClass".
        extensions: Optional[List[str]] = None,
        # CORS configuration for Socket.IO (see Flask-SocketIO docs).
        cors_allowed_origins: Any = None,
        tunnel_enable: bool = False,
        tunnel_provider: str = "cloudflared",
        tunnel_executable: str = None,
        tunnel_args: list = None,
    ):
        """
        Configuration for the unified Webserver Component.

        :param host: Hostname to listen on (default 0.0.0.0).
        :param port: Port to listen on.
        :param templates_dir: Path to HTML templates directory.
        :param static_dir: Path to static files directory.
        :param ssl_cert: Path to SSL certificate file (optional).
        :param ssl_key: Path to SSL private key file (optional).
        """
        super(WebserverConf, self).__init__(ephemeral=ephemeral)
        self.host = host
        self.port = port
        self.templates_dir = templates_dir
        self.static_dir = static_dir
        self.static_url_path = static_url_path
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        self.pages = pages or {}
        self.extensions = extensions or []
        self.cors_allowed_origins = cors_allowed_origins
        # Optional public tunnel for cross-network access.
        # Requires an installed tunnel binary (e.g., `cloudflared` or `ngrok`) on the machine running the component.
        self.tunnel_enable = tunnel_enable
        self.tunnel_provider = tunnel_provider
        self.tunnel_executable = tunnel_executable
        self.tunnel_args = tunnel_args

class WebserverComponent(SICService):
    EVENT_STATE = "sic/state"
    EVENT_TRANSCRIPT = "sic/transcript"
    EVENT_WEBINFO = "sic/webinfo"
    EVENT_TURN = "sic/turn"
    EVENT_HTML = "sic/html"
    EVENT_BUTTON_CLICKED = "sic/button_clicked"

    def __init__(self, *args, **kwargs):
        super(WebserverComponent, self).__init__(*args, **kwargs)

        # 1. Path Configuration
        base_dir = os.path.dirname(os.path.abspath(__file__))
        template_folder = self.params.templates_dir if self.params.templates_dir else os.path.join(base_dir, "templates")
        static_folder = self.params.static_dir if self.params.static_dir else os.path.join(base_dir, "static")
        static_url_path = getattr(self.params, "static_url_path", "/static")

        if not os.path.exists(template_folder):
            self.logger.warning(f"Templates directory not found: {template_folder}")
        if not os.path.exists(static_folder):
             self.logger.warning(f"Static directory not found: {static_folder}")

        self.logger.info(f"Templates: {template_folder}")
        self.logger.info(f"Static: {static_folder}")

        # 2. Flask & SocketIO Setup
        self.app = Flask(
            __name__,
            template_folder=template_folder,
            static_folder=static_folder,
            static_url_path=static_url_path,
        )

        # Fail-loudly for the most common "stuck connecting" issue:
        # browser blocks Socket.IO due to CORS mismatch (origin not allowlisted).
        self._register_socketio_cors_guard()
        
        # Suppress default Flask logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)

        # Log Socket.IO / Engine.IO versions to help diagnose client mismatches.
        try:
            sio_v = importlib.metadata.version("python-socketio")
        except Exception:
            sio_v = "unknown"
        try:
            eio_v = importlib.metadata.version("python-engineio")
        except Exception:
            eio_v = "unknown"
        try:
            fsio_v = importlib.metadata.version("Flask-SocketIO")
        except Exception:
            fsio_v = "unknown"
        self.logger.info(f"Socket.IO versions: Flask-SocketIO={fsio_v}, python-socketio={sio_v}, python-engineio={eio_v}")

        # Initialize SocketIO (async_mode='threading' is usually safest for integration)
        cors_allowed_origins = getattr(self.params, "cors_allowed_origins", None)
        if cors_allowed_origins is None:
            # Flask-SocketIO matches full origins (scheme + host + port). Since most demos run
            # from the same host/port as the server, include the configured port by default.
            port = int(getattr(self.params, "port", 5000))
            cors_allowed_origins = [
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
                # Also allow default ports (e.g. when proxied) if needed.
                "http://localhost",
                "http://127.0.0.1",
            ]
        # Enable server-side Socket.IO/Engine.IO logs so common client mismatches
        # (e.g., outdated Socket.IO JS -> EIO=3) are visible in the component logs.
        logging.getLogger("engineio").setLevel(logging.INFO)
        logging.getLogger("socketio").setLevel(logging.INFO)
        self.socketio = SocketIO(
            self.app,
            async_mode="threading",
            cors_allowed_origins=cors_allowed_origins,
            logger=True,
            engineio_logger=True,
        )

        # Internal state
        self._state_lock = threading.Lock()
        self.transcript = ""
        self._latest_webinfo: Dict[str, Any] = {}
        self.public_url = None
        self._tunnel_process = None
        self._tunnel_thread = None
        self._extensions: List[Any] = []
        self._ready_event = threading.Event()
        self._shutdown_event = threading.Event()

        # 2.5 Load extensions (if any)
        self._load_extensions()

        # 3. Register SocketIO Events
        self.register_socket_events()
        self._register_extension_socket_events()

        # 4. Start Server Thread
        self.server_thread = threading.Thread(target=self.start_web_app)
        self.server_thread.daemon = True
        self.server_thread.start()

        # 4.5 Readiness monitor thread
        self._ready_monitor_thread = threading.Thread(target=self._monitor_readiness, daemon=True)
        self._ready_monitor_thread.start()

        # 5. Optional tunnel thread
        if getattr(self.params, "tunnel_enable", False):
            self._tunnel_thread = threading.Thread(target=self._start_tunnel, daemon=True)
            self._tunnel_thread.start()

    def _is_origin_allowed(self, origin: str) -> bool:
        """
        Best-effort origin allowlist check to provide a clear server-side error message
        when Socket.IO is blocked by CORS.
        """
        allowed = getattr(self.params, "cors_allowed_origins", None)
        if allowed is None:
            # Match Flask-SocketIO default we set.
            port = int(getattr(self.params, "port", 5000))
            allowed = [
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
                "http://localhost",
                "http://127.0.0.1",
            ]

        try:
            if allowed == "*" or allowed is True:
                return True
            if callable(allowed):
                return bool(allowed(origin))
            if isinstance(allowed, str):
                return allowed == origin
            if isinstance(allowed, (list, tuple, set)):
                return origin in allowed
        except Exception:
            # If something about the config is unusual, don't block the request here.
            return True
        return False

    def _register_socketio_cors_guard(self) -> None:
        @self.app.before_request
        def _guard_socketio_origin():
            # Only guard Socket.IO engine endpoint; normal HTTP endpoints can be served cross-origin.
            if not request.path.startswith("/socket.io"):
                return None

            # Extra diagnostics for the "Connecting..." symptom:
            # - CORS mismatch
            # - Client/server Engine.IO version mismatch (often old socket.io JS bundle)
            origin = request.headers.get("Origin")
            ua = request.headers.get("User-Agent", "")
            eio = request.args.get("EIO")
            transport = request.args.get("transport")
            self.logger.warning(
                "Socket.IO handshake: path=%s origin=%r eio=%r transport=%r ua=%r",
                request.path,
                origin,
                eio,
                transport,
                ua,
            )

            # Flask-SocketIO / python-socketio v5+ expects Engine.IO protocol 4 (EIO=4).
            if eio is not None and str(eio) != "4":
                self.logger.error(
                    "Unsupported Engine.IO version from client (EIO=%r). "
                    "This usually means the browser loaded an outdated Socket.IO JS client (v2). "
                    "Fix: ensure your page loads the server-provided client at '/socket.io/socket.io.js' "
                    "(or use Socket.IO JS v3/v4), and avoid bundling old 'socket.io.min.js'.",
                    eio,
                )
                return (
                    jsonify(
                        {
                            "error": "unsupported_engineio_version",
                            "detail": f"Client used EIO={eio}, but this server expects EIO=4 (Socket.IO JS v3/v4).",
                            "fix": "Load /socket.io/socket.io.js (served by this server) or upgrade your Socket.IO JS client.",
                        }
                    ),
                    400,
                )

            if not origin:
                return None

            if self._is_origin_allowed(origin):
                return None

            allowed = getattr(self.params, "cors_allowed_origins", None)
            self.logger.error(
                "Socket.IO CORS rejected origin '%s' (allowed=%r). "
                "This usually shows up in the browser as 'Connecting…' forever. "
                "Fix by setting WebserverConf(cors_allowed_origins=[...]) to include the page origin (scheme+host+port).",
                origin,
                allowed,
            )
            return (
                jsonify(
                    {
                        "error": "socketio_cors_rejected",
                        "detail": f"Origin '{origin}' is not allowed to connect to Socket.IO.",
                        "allowed": allowed,
                    }
                ),
                403,
            )

    def _import_from_spec(self, spec: str) -> Any:
        s = (spec or "").strip()
        if not s:
            raise ValueError("Empty extension spec")
        if ":" in s:
            module_name, attr = s.split(":", 1)
            mod = importlib.import_module(module_name)
            return getattr(mod, attr)
        return importlib.import_module(s)

    def _load_extensions(self) -> None:
        specs = getattr(self.params, "extensions", None) or []
        loaded: List[Any] = []
        for spec in specs:
            try:
                obj = self._import_from_spec(spec)
                # Blueprint
                if isinstance(obj, Blueprint):
                    loaded.append(obj)
                    continue
                # Class / callable -> instance/object
                if isinstance(obj, type):
                    try:
                        inst = obj(component=self)  # type: ignore[call-arg]
                    except Exception:
                        inst = obj()  # type: ignore[call-arg]
                    loaded.append(inst)
                    continue
                if callable(obj):
                    try:
                        inst = obj(component=self)  # type: ignore[misc]
                    except Exception:
                        inst = obj()  # type: ignore[misc]
                    loaded.append(inst)
                    continue
                loaded.append(obj)
            except Exception as e:
                self.logger.error(f"Failed to load webserver extension '{spec}': {e}")
        self._extensions = loaded

    def _register_extension_routes(self) -> None:
        for ext in getattr(self, "_extensions", []) or []:
            try:
                if isinstance(ext, Blueprint):
                    self.app.register_blueprint(ext)
                elif hasattr(ext, "register_routes"):
                    ext.register_routes(self.app)  # type: ignore[attr-defined]
            except Exception as e:
                self.logger.error(f"Extension route registration failed: {e}")

    def _register_extension_socket_events(self) -> None:
        for ext in getattr(self, "_extensions", []) or []:
            try:
                if hasattr(ext, "register_socketio"):
                    ext.register_socketio(self.socketio)  # type: ignore[attr-defined]
            except Exception as e:
                self.logger.error(f"Extension socket registration failed: {e}")

    def _monitor_readiness(self) -> None:
        # Poll localhost port reachability; works even when host="0.0.0.0".
        start = time.time()
        while not self._shutdown_event.is_set():
            if self._is_port_open("127.0.0.1", int(self.params.port)):
                self._ready_event.set()
                return
            if time.time() - start > 15.0:
                # Don't spin forever; remain not-ready but alive.
                return
            time.sleep(0.1)

    def _is_port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except Exception:
            return False

    def _start_tunnel(self):
        # Give Flask a moment to bind the port.
        time.sleep(1.0)

        provider = (getattr(self.params, "tunnel_provider", None) or "cloudflared").strip().lower()
        exe = getattr(self.params, "tunnel_executable", None)
        args = getattr(self.params, "tunnel_args", None)

        if provider == "cloudflared":
            exe = exe or "cloudflared"
            default_args = ["tunnel", "--url", f"http://localhost:{self.params.port}", "--no-autoupdate"]
            cmd = [exe] + (args if isinstance(args, list) and args else default_args)
        elif provider == "ngrok":
            exe = exe or "ngrok"
            default_args = ["http", str(self.params.port), "--log", "stdout"]
            cmd = [exe] + (args if isinstance(args, list) and args else default_args)
        else:
            self.logger.error(f"Unknown tunnel_provider: {provider}")
            return

        try:
            self.logger.info(f"Starting tunnel: {' '.join(cmd)}")
            self._tunnel_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            self.logger.error(f"Failed to start tunnel process: {e}")
            self._tunnel_process = None
            return

        # NOTE: tunnel tools often print unrelated URLs (docs/terms/etc).
        # Only accept URLs that look like actual public tunnel endpoints.
        url_regex = re.compile(r"(https?://[^\s]+)")
        trycloudflare_regex = re.compile(r"(https?://[a-z0-9-]+\.trycloudflare\.com)", re.IGNORECASE)
        ngrok_regex = re.compile(r"(https?://[a-z0-9-]+\.(?:ngrok-free\.app|ngrok\.app|ngrok\.io))", re.IGNORECASE)
        try:
            assert self._tunnel_process.stdout is not None
            for line in self._tunnel_process.stdout:
                line = line.strip()
                if not line:
                    continue
                self.logger.info(f"[tunnel] {line}")

                if self.public_url is None:
                    candidate = None
                    if provider == "cloudflared":
                        m = trycloudflare_regex.search(line)
                        if m:
                            candidate = m.group(1).rstrip(").,;\"'")
                    elif provider == "ngrok":
                        m = ngrok_regex.search(line)
                        if m:
                            candidate = m.group(1).rstrip(").,;\"'")
                        else:
                            # Fallback: take the first URL, but only if it looks like an ngrok domain.
                            m2 = url_regex.search(line)
                            if m2 and "ngrok" in m2.group(1).lower():
                                candidate = m2.group(1).rstrip(").,;\"'")

                    if candidate:
                        with self._state_lock:
                            self.public_url = candidate

                    with self._state_lock:
                        pub = self.public_url
                        if pub:
                            self._latest_webinfo["tunnel_url"] = pub
                    if pub:
                        self.logger.info(f"Tunnel public URL: {pub}")
        except Exception as e:
            self.logger.error(f"Tunnel monitoring failed: {e}")

    def start_web_app(self):
        """Start the Flask-SocketIO server."""
        self.register_routes()
        self._register_extension_routes()
        
        ssl_context = None
        if self.params.ssl_cert and self.params.ssl_key:
            if os.path.exists(self.params.ssl_cert) and os.path.exists(self.params.ssl_key):
                ssl_context = (self.params.ssl_cert, self.params.ssl_key)
                self.logger.info("SSL enabled.")
            else:
                self.logger.error("SSL cert/key files not found. Starting without SSL.")

        self.logger.info(f"Starting web server on {self.params.host}:{self.params.port}")
        
        try:
            # socketio.run handles the server loop and WebSocket upgrade
            self.socketio.run(
                self.app,
                host=self.params.host,
                port=self.params.port,
                ssl_context=ssl_context,
                debug=False,
                use_reloader=False
            )
        except Exception as e:
            self.logger.error(f"Web server failed: {e}")

    def register_routes(self):
        """Register Flask routes."""
        @self.app.route("/")
        def index():
            try:
                return render_template("index.html")
            except Exception:
                return "<h1>SIC Webserver Running</h1><p>No index.html found.</p>"

        @self.app.route("/healthz", methods=["GET"])
        def healthz():
            return jsonify({"status": "ok"})

        @self.app.route("/readyz", methods=["GET"])
        def readyz():
            return (jsonify({"ready": True}), 200) if self._ready_event.is_set() else (jsonify({"ready": False}), 503)

        @self.app.route("/api/webinfo/<label>", methods=["GET"])
        def api_webinfo(label):
            # Simple polling endpoint for clients that don't use Socket.IO.
            with self._state_lock:
                msg = self._latest_webinfo.get(label)
            return jsonify({"label": label, "message": msg})

        @self.app.route("/api/tunnel", methods=["GET"])
        def api_tunnel():
            with self._state_lock:
                pub = self.public_url
            return jsonify(
                {
                    "enabled": bool(getattr(self.params, "tunnel_enable", False)),
                    "provider": getattr(self.params, "tunnel_provider", None),
                    "url": pub,
                }
            )

        @self.app.route("/api/qr", methods=["GET"])
        def api_qr():
            """
            Generate a QR code PNG for the provided data or latest WebInfo label.

            Query params:
              - data: string to encode (preferred)
              - label: key in latest webinfo dict (fallback)
              - scale: integer scale factor (optional, default 6)
            """
            data = request.args.get("data", default=None, type=str)
            if not data:
                label = request.args.get("label", default=None, type=str)
                if label:
                    with self._state_lock:
                        val = self._latest_webinfo.get(label)
                    if val is not None:
                        data = str(val)

            if not data:
                return jsonify({"error": "missing data"}), 400

            try:
                import qrcode  # type: ignore
            except Exception:
                return jsonify({"error": "missing python package: qrcode"}), 503

            scale = request.args.get("scale", default=6, type=int)
            if scale < 1:
                scale = 1
            if scale > 20:
                scale = 20

            try:
                qr = qrcode.QRCode(box_size=scale, border=2)
                qr.add_data(data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                return send_file(buf, mimetype="image/png", download_name="qr.png", max_age=0)
            except Exception as e:
                return jsonify({"error": f"qr generation failed: {e}"}), 500

        @self.app.route("/api/buttonClick", methods=["POST"])
        def api_button_click():
            data = request.get_json(silent=True)
            if data is None:
                data = request.form.to_dict() if request.form else {}
            self.logger.info(f"API button click: {data}")
            self.output_message(ButtonClicked(button=data))
            return ("", 204)

        # Configurable page registry (safe allowlist).
        pages = getattr(self.params, "pages", None) or {}
        for route, template_name in pages.items():
            try:
                if not isinstance(route, str) or not route:
                    continue
                if not route.startswith("/"):
                    route = "/" + route
                if not isinstance(template_name, str) or not template_name:
                    continue

                def _make_page_handler(_template: str):
                    def _handler():
                        return render_template(_template)
                    return _handler

                endpoint = f"page_{route.strip('/').replace('/', '_') or 'root'}"
                self.app.add_url_rule(route, endpoint, _make_page_handler(template_name))
            except Exception as e:
                self.logger.error(f"Failed to register page route {route} -> {template_name}: {e}")

    def register_socket_events(self):
        """Register SocketIO event handlers."""
        
        @self.socketio.on("connect")
        def handle_connect():
            self.logger.info("Client connected")
            with self._state_lock:
                transcript = self.transcript
                webinfo = dict(self._latest_webinfo)
                public_url = self.public_url

            emit(self.EVENT_STATE, {"transcript": transcript, "webinfo": webinfo, "tunnel_url": public_url})

        @self.socketio.on("disconnect")
        def handle_disconnect():
            self.logger.info("Client disconnected")

        @self.socketio.on(self.EVENT_BUTTON_CLICKED)
        def handle_button_namespaced(data):
            self.logger.info(f"Button clicked (namespaced): {data}")
            self.output_message(ButtonClicked(button=data))

    def stop(self, *args):
        """Stop the web server."""
        self.logger.info("Stopping web server...")
        self._shutdown_event.set()
        try:
            self.socketio.stop()
        except Exception:
            pass # Often fails if already stopped or not started

        if self._tunnel_process is not None:
            try:
                self._tunnel_process.terminate()
            except Exception:
                pass
            self._tunnel_process = None

        super(WebserverComponent, self).stop(*args)

    @staticmethod
    def get_conf():
        return WebserverConf()

    @staticmethod
    def get_inputs():
        # Supports all message types from previous implementations
        return [HtmlMessage, TranscriptMessage, WebInfoMessage, SetTurnMessage]

    @staticmethod
    def get_output():
        return ButtonClicked

    def on_message(self, message):
        """Handle incoming SIC messages and forward to Web via SocketIO."""
        
        if is_sic_instance(message, HtmlMessage):
            if message.html:
                self.logger.info("Received HTML update request.")
                self.socketio.emit(self.EVENT_HTML, {"html": message.html})

        elif is_sic_instance(message, TranscriptMessage):
            with self._state_lock:
                self.transcript = message.transcript
                transcript = self.transcript
            self.logger.debug(f"Transcript: {transcript}")
            self.socketio.emit(self.EVENT_TRANSCRIPT, {"transcript": transcript})

        elif is_sic_instance(message, WebInfoMessage):
            self.logger.info(f"WebInfo {message.label}: {message.message}")
            with self._state_lock:
                self._latest_webinfo[message.label] = message.message
            self.socketio.emit(self.EVENT_WEBINFO, {"label": message.label, "message": message.message})

        elif is_sic_instance(message, SetTurnMessage):
            self.logger.info(f"SetTurn: {message.user_turn}")
            self.socketio.emit(self.EVENT_TURN, {"user_turn": message.user_turn})


class Webserver(SICConnector):
    component_class = WebserverComponent


def main():
    SICComponentManager([WebserverComponent])


if __name__ == "__main__":
    main()
