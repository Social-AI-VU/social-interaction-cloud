import os
import redis
import json
import numpy as np
import time
from subprocess import call
from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    SICConfMessage,
    SICMessage,
    SICRequest,
    TextMessage,
    TextRequest
)
from sic_framework.core.utils import is_sic_instance
from sic_framework.devices.desktop import Desktop
from sic_framework.devices.common_desktop.desktop_speakers import DesktopSpeakersActuator, SpeakersConf
from sic_framework.services.text2speech.text2speech_service import Text2Speech, Text2SpeechConf, GetSpeechRequest, SpeechResult
from sic_framework.services.dialogflow.dialogflow import (DialogflowConf, GetIntentRequest, StopListeningMessage, RecognitionResult,
                                                          QueryResult, Dialogflow)
from sic_framework.services.webserver.webserver_component import (
    ButtonClicked,
    HtmlMessage,
    TranscriptMessage,
    Webserver,
    WebserverConf,
)


class EISConf(SICConfMessage):
    """
    EIS SICConfMessage
    """

    def __init__(self, use_espeak=False):
        self.use_espeak = use_espeak


class EISRequest(SICRequest):
    """
    EIS request
    """

    def __init__(self):
        super(SICRequest, self).__init__()


class EISMessage(SICMessage):
    """
    EIS input message
    """

    def __init__(self):
        super(SICMessage, self).__init__()


class EISOutputMessage(SICMessage):
    """
    EIS input message
    """

    def __init__(self):
        super(SICMessage, self).__init__()


class EISReply(SICMessage):
    """
    See text
    """

    def __init__(self, text):
        super(SICMessage, self).__init__()
        self.text = text


class EISComponent(SICComponent):
    """
    EIS SICAction
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_hardware()
        self._setup_text_to_speech()
        self._setup_redis()
        self._setup_dialogflow()
        self._setup_webserver()

    def _setup_hardware(self):
        """Initialize hardware components."""
        self.desktop = Desktop()
        speaker_conf = SpeakersConf(sample_rate=24000)
        self.speakers_output = DesktopSpeakersActuator(conf=speaker_conf)

    def _setup_text_to_speech(self):
        """Configure text-to-speech."""
        keyfile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "mas-2023-test-fkcp-f55e450fe830.json")
        self.keyfile_path = keyfile_path  # Save for reuse in Dialogflow
        if not self.params.use_espeak:
            conf = Text2SpeechConf(keyfile=keyfile_path)
            self.tts = Text2Speech(conf=conf)

    def _setup_redis(self):
        """Set up Redis connection."""
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            password='changemeplease',
            db=0
        )
        self.marbel_channel = "MARBELConnector:input:127.0.1.1"

    def _setup_dialogflow(self):
        """Initialize Dialogflow integration."""
        with open(self.keyfile_path, 'r') as keyfile:
            keyfile_json = json.load(keyfile)

        conf = DialogflowConf(
            keyfile_json=keyfile_json,
            sample_rate_hertz=44100,
            language="en"
        )
        self.dialogflow = Dialogflow(ip='localhost', conf=conf)
        self.dialogflow.connect(self.desktop.mic)
        self.dialogflow.register_callback(self.on_dialog)
        self.conversation_id = np.random.randint(10000)

    def _setup_webserver(self):
        """Initialize Webserver integration."""
        self.port = 8080
        self.your_ip = "localhost"
        # webserver setup
        web_conf = WebserverConf(host="0.0.0.0", port=self.port)
        self.web_server = Webserver(ip=self.your_ip, conf=web_conf)
        # connect the output of webserver by registering it as a callback.
        # the output is a flag to determine if the button has been clicked or not
        self.web_server.register_callback(self.on_button_click)
        self._handle_render_page_command("index.html")

    def on_button_click(self, message):
        """
        Callback function for button click event from a web client.
        """
        print(message)
        if is_sic_instance(message, ButtonClicked):
            if message.button:
                print("start listening")
                self._handle_render_page_command("index.html")

    def on_dialog(message):
        if message.response:
            if message.response.recognition_result.is_final:
                print("Transcript:", message.response.recognition_result.transcript)

    @staticmethod
    def get_inputs():
        return [EISRequest]

    @staticmethod
    def get_output():
        return EISOutputMessage

    # This function is optional
    @staticmethod
    def get_conf():
        return EISConf()

    def on_message(self, message):
        """Handle incoming text messages and process commands."""

        # Validate the message type
        self._validate_message(message)

        # Extract and process message content
        content = self._extract_content(message.text)
        if content.startswith("say"):
            self._handle_say_command(content)
        elif content.startswith("startListening"):
            self._handle_start_listening_command()
        elif content.startswith("stopListening"):
            self._handle_stop_listening_command()
        elif content.startswith("renderPage"):
            self._handle_render_page_command(content)
        else:
            print("Unknown command:", content)

    # Helper methods
    def _validate_message(self, message):
        """Ensure the message is a valid TextMessage."""
        if not is_sic_instance(message, TextMessage):
            raise TypeError(
                "Invalid message type {} for {}".format(
                    message.__class__.__name__, self.get_component_name()
                )
            )
        print("{} received text message {}".format(
            self.get_component_name(), message.text
        ))

    def _extract_content(self, text):
        """Clean and extract the relevant part of the message text."""
        return text.replace("text:", "", 1).strip()

    def _handle_say_command(self, content):
        """Process 'say' command by synthesizing speech."""
        message_text = content.replace(
            "say(", "", 1).replace(")", "", 1).strip()
        print("I would like to say", message_text)

        # Publish 'TextStarted' event
        self.redis_client.publish(self.marbel_channel, "event('TextStarted')")

        # Request speech synthesis
        if self.params.use_espeak:
            self.local_tts(text=message_text)
        else:
            reply = self.tts.request(
                GetSpeechRequest(text=message_text), block=True)
            self.on_speech_result(reply)

        # Publish 'TextDone' event
        self.redis_client.publish(self.marbel_channel, "event('TextDone')")

    def _handle_start_listening_command(self):
        """Process 'startListening' command by interacting with Dialogflow."""
        self.redis_client.publish(
            self.marbel_channel, "event('ListeningStarted;1;48000')")
        contexts = {"name": 1}  # Example context; adjust as needed
        reply = self.dialogflow.request(
            GetIntentRequest(self.conversation_id, contexts))
        self._process_dialogflow_reply(reply)
        # Extract relevant fields
        intent_name = reply.response.query_result.intent.display_name
        entities = [{"recipe": "butter chicken"}]  # Example entities
        entities_str = ", ".join([f"{key}='{value}'" for entity in entities for key, value in entity.items()])
        confidence = round(float(reply.response.query_result.intent_detection_confidence), 2)
        transcript = reply.response.query_result.query_text
        source = "speech"

        # Format the intent message
        intent_message = f"intent({intent_name}, [{entities_str}], {confidence}, '{transcript}', {source})"
        self.redis_client.publish(
                    self.marbel_channel, intent_message)
        self.redis_client.publish(
            self.marbel_channel, "event('ListeningDone')")

    def _handle_stop_listening_command(self):
        """Process 'stopListening' command to stop Dialogflow or related service."""
        reply = self.dialogflow.request(
            StopListeningMessage(self.conversation_id))
        self._process_dialogflow_reply(reply)
        print("Stopped listening.")
        self.redis_client.publish(
            self.marbel_channel, "event('ListeningDone')")

    def _handle_render_page_command(self, content):
        # the HTML file to be rendered
        html_file = content
        web_url = f"http://{self.your_ip}:{self.port}/"
        with open(html_file) as file:
            data = file.read()
            print("sending html content-------------")
            self.web_server.send_message(HtmlMessage(text=data))
            print("now you can open the web page at", web_url)

    def _process_dialogflow_reply(self, reply):
        """Handle the common logic for processing a Dialogflow reply."""
        print("Full reply is:", reply)
        print("The detected intent:", reply.intent)
        if reply.fulfillment_message:
            print("Reply:", reply.fulfillment_message)

    def on_request(self, request):
        if is_sic_instance(request, TextRequest):
            if request.text.startswith("text:reqreply:handshake"):
                # handle handshake request
                print("Received handshake request from EIS interface")
                input_channel = "{}:input:{}".format(
                    self.get_component_name(), self._ip)
                # TODO set request id in reply
                message = EISReply("text:"+input_channel)
                message._previous_component_name = self.get_component_name()
                return message
            else:
                # We currently only handle a handshake on the reqreply channel...
                # This will cause problems...
                print("Unknown request, this will cause problems...")

    def on_speech_result(self, wav_audio):
        print("I am receiving audio at sample rate:" + str(wav_audio.sample_rate))
        self.speakers_output.stream.write(wav_audio.waveform)

    def local_tts(self, text):
        call(["espeak", "-s140 -ven+18 -z", text])


class EISConnector(SICConnector):
    component_class = EISComponent


if __name__ == "__main__":
    # Request the service to start using the SICServiceManager on this device
    SICComponentManager([EISComponent])
