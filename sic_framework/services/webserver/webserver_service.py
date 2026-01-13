import os
import threading
import logging
import time

from flask import Flask, render_template, render_template_string
from flask_socketio import SocketIO, emit

from sic_framework import SICComponentManager
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage
from sic_framework.core.utils import is_sic_instance


# -----------------------------------------------------------------------------
# Messages (consolidated from other files)
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

class WebserverConf(SICConfMessage):
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        templates_dir: str = None,
        static_dir: str = None,
        ssl_cert: str = None,
        ssl_key: str = None
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
        super(WebserverConf, self).__init__()
        self.host = host
        self.port = port
        self.templates_dir = templates_dir
        self.static_dir = static_dir
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key


# -----------------------------------------------------------------------------
# Component
# -----------------------------------------------------------------------------

class WebserverComponent(SICService):
    def __init__(self, *args, **kwargs):
        super(WebserverComponent, self).__init__(*args, **kwargs)

        # 1. Path Configuration
        cwd = os.getcwd()
        template_folder = self.params.templates_dir if self.params.templates_dir else os.path.join(cwd, "templates")
        static_folder = self.params.static_dir if self.params.static_dir else os.path.join(cwd, "static")

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
        )
        
        # Suppress default Flask logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)

        # Initialize SocketIO (async_mode='threading' is usually safest for integration)
        self.socketio = SocketIO(self.app, async_mode='threading', cors_allowed_origins="*")

        # Internal state
        self.input_text = ""
        self.transcript = ""

        # 3. Register SocketIO Events
        self.register_socket_events()

        # 4. Start Server Thread
        self.server_thread = threading.Thread(target=self.start_web_app)
        self.server_thread.daemon = True
        self.server_thread.start()

    def start_web_app(self):
        """Start the Flask-SocketIO server."""
        self.register_routes()
        
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
            # If input_text is set (legacy behavior), render it
            if self.input_text:
                return render_template_string(self.input_text)
            try:
                return render_template("index.html")
            except Exception:
                return "<h1>SIC Webserver Running</h1><p>No index.html found.</p>"

        @self.app.route("/<path:filename>")
        def serve_page(filename):
            try:
                # Security check could go here
                return render_template(filename)
            except Exception:
                return f"Page not found: {filename}", 404

    def register_socket_events(self):
        """Register SocketIO event handlers."""
        
        @self.socketio.on("connect")
        def handle_connect():
            self.logger.info("Client connected")
            # Send current state on connection if needed
            if self.transcript:
                emit("update_textbox", self.transcript)

        @self.socketio.on("disconnect")
        def handle_disconnect():
            self.logger.info("Client disconnected")

        @self.socketio.on("buttonClick")
        def handle_button(data):
            self.logger.info(f"Button clicked: {data}")
            self.output_message(ButtonClicked(button=data))

        # Legacy support for PCA webserver
        @self.socketio.on("clicked_flag")
        def handle_flag(flag):
            if flag:
                self.logger.info(f"Flag clicked: {flag}")
                self.output_message(ButtonClicked(button=flag))

    def stop(self, *args):
        """Stop the web server."""
        self.logger.info("Stopping web server...")
        try:
            self.socketio.stop()
        except Exception:
            pass # Often fails if already stopped or not started
        super(WebserverComponent, self).stop(*args)

    # -------------------------------------------------------------------------
    # SIC Inputs/Outputs
    # -------------------------------------------------------------------------

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

    def execute(self, inputs):
        # We process inputs immediately in on_message (reactive), 
        # so execute is just a placeholder for SICService compliance.
        return None

    def on_message(self, message):
        """Handle incoming SIC messages and forward to Web via SocketIO."""
        
        if is_sic_instance(message, HtmlMessage):
            # Update internal state
            if message.text:
                self.input_text = message.text
            if message.html:
                self.logger.info(f"Received HTML update request: {message.html}")
                # Could trigger a reload or content update here
                self.socketio.emit("update_html", message.html)

        elif is_sic_instance(message, TranscriptMessage):
            self.transcript = message.transcript
            self.logger.debug(f"Transcript: {self.transcript}")
            # 'update_textbox' is the legacy event name used in app.js
            self.socketio.emit("update_textbox", self.transcript)
            # Also emit generic 'transcript' event
            self.socketio.emit("transcript", self.transcript)

        elif is_sic_instance(message, WebInfoMessage):
            self.logger.info(f"WebInfo {message.label}: {message.message}")
            self.socketio.emit(message.label, message.message)

        elif is_sic_instance(message, SetTurnMessage):
            self.logger.info(f"SetTurn: {message.user_turn}")
            self.socketio.emit("set_turn", message.user_turn)


class Webserver(SICConnector):
    component_class = WebserverComponent


def main():
    SICComponentManager([WebserverComponent])


if __name__ == "__main__":
    main()
