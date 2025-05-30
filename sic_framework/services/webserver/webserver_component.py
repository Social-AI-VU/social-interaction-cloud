import logging
import os
import threading

from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

from sic_framework import SICComponentManager, SICService
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage
from sic_framework.core.utils import is_sic_instance


class TranscriptMessage(SICMessage):
    def __init__(self, transcript):
        self.transcript = transcript


class HtmlMessage(SICMessage):
    def __init__(self, text):
        self.text = text


class ButtonClicked(SICMessage):
    def __init__(self, button):
        self.button = button


class WebserverConf(SICConfMessage):
    def __init__(self, host: str, port: int):
        """
        :param host         the hostname that a server listens on
        :param port         the port to listen on
        """
        super(WebserverConf, self).__init__()
        self.host = host
        self.port = port


class WebserverComponent(SICComponent):

    def __init__(self, *args, **kwargs):

        super(WebserverComponent, self).__init__(*args, **kwargs)
        self.app = Flask(__name__)

        self.transcript = None

        self.socketio = SocketIO(self.app)
        #  disable logging
        # log = logging.getLogger('werkzeug')
        # log.setLevel(logging.ERROR)

        thread = threading.Thread(target=self.start_web_app)
        # app should be terminated automatically when the main thread exits
        thread.daemon = True
        thread.start()

    def start_web_app(self):
        """
        start the web server
        """
        self.render_template_string_routes()
        # maybe use ssl_context to run app over https, the key and cert files need to be passed by users
        self.app.run(host=self.params.host, port=self.params.port)

    @staticmethod
    def get_conf():
        return WebserverConf()

    @staticmethod
    def get_inputs():
        return [HtmlMessage, TranscriptMessage]

    # when the HtmlMessage message arrives, feed it to self.input_text
    def on_message(self, message):

        if is_sic_instance(message, HtmlMessage):
            self.logger.info("receiving text...")
            self.logger.info("receiving text...")
            self.input_text = message.text

        if is_sic_instance(message, TranscriptMessage):
            self.transcript = message.transcript
            self.logger.info(f"receiving transcript: {self.transcript}-------")
            self.socketio.emit("update_textbox", self.transcript)

    def render_template_string_routes(self):
        # render a html with bootstrap and a css file once a client is connected
        @self.app.route("/")
        def index():
            self.logger.info("render function")
            return render_template_string(self.input_text)

        @self.socketio.on("connect")
        def handle_connect():
            self.logger.info("Client connected")

        @self.socketio.on("disconnect")
        def handle_disconnect():
            self.disconnected = True
            self.logger.info("Client disconnected")

        # register clicked_flag event handler
        @self.socketio.on("clicked_flag")
        def handle_flag(flag):
            if flag:
                self.output_message(ButtonClicked(button=flag))


class Webserver(SICConnector):
    component_class = WebserverComponent


def main():
    SICComponentManager([WebserverComponent])


if __name__ == "__main__":
    main()
