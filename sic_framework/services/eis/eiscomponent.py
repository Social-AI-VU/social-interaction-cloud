import os
import redis
import json
import numpy as np
from subprocess import call
from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import\
    (SICConfMessage, SICMessage, SICRequest, TextMessage, TextRequest)
from sic_framework.core.utils import is_sic_instance
from sic_framework.devices.desktop import Desktop
from sic_framework.devices.common_desktop.desktop_speakers import DesktopSpeakersActuator, SpeakersConf
from sic_framework.services.text2speech.text2speech_service import \
    (Text2Speech, Text2SpeechConf, GetSpeechRequest, SpeechResult)
from sic_framework.services.dialogflow.dialogflow import\
    (DialogflowConf, GetIntentRequest, StopListeningMessage, RecognitionResult, QueryResult, Dialogflow)
from sic_framework.services.webserver.webserver_pca import \
    (ButtonClicked, HtmlMessage, SwitchTurnMessage, TranscriptMessage, Webserver, WebserverConf)


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

        # Init parameters
        # TODO: remove the hard coding by implementing an EISConfig object
        # Keyfile needed for Dialogflow and Google TTS
        self.keyfile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "mas-2023-test-fkcp-f55e450fe830.json")
        # Redis channel to communicate with MARBEL agent (for sending percepts)
        self.marbel_channel = "MARBELConnector:input:127.0.1.1"

        # IP and port parameters
        self.your_ip = "localhost"
        self.port = 8080

        self._setup_hardware()
        self._setup_text_to_speech()
        self._setup_redis()
        self._setup_dialogflow()
        self.user_turn = True  # Used to keep track of who can talk, either user or agent
        self._setup_webserver()

    def _setup_hardware(self):
        """Initialize hardware components."""
        self.desktop = Desktop()
        speaker_conf = SpeakersConf(sample_rate=24000)
        self.speakers_output = DesktopSpeakersActuator(conf=speaker_conf)

    def _setup_text_to_speech(self):
        """Configure text-to-speech."""
        if not self.params.use_espeak:
            conf = Text2SpeechConf(keyfile=self.keyfile_path)
            self.tts = Text2Speech(conf=conf)

    def _setup_redis(self):
        """Set up Redis connection."""
        # TODO: hard coding of Redis config parameters port and password
        self.redis_client = redis.Redis(
            host=self.your_ip,
            port=6379,
            password='changemeplease',
            db=0
        )

    def _setup_dialogflow(self):
        """Initialize Dialogflow integration."""
        with open(self.keyfile_path, 'r') as keyfile:
            keyfile_json = json.load(keyfile)

        # TODO: hard coding of language parameter
        conf = DialogflowConf(
            keyfile_json=keyfile_json,
            sample_rate_hertz=44100,
            language="en"
        )
        self.dialogflow = Dialogflow(ip=self.your_ip, conf=conf)
        self.dialogflow.connect(self.desktop.mic)
        self.dialogflow.register_callback(self.on_dialog)
        self.conversation_id = np.random.randint(10000)

    def on_dialog(self, message):
        if is_sic_instance(message, RecognitionResult):
            # Send intermediate transcript (recognition) results to the webserver to enable live display
            self.web_server.send_message(TranscriptMessage(transcript=message.response.recognition_result.transcript))

    def _setup_webserver(self):
        """Initialize Webserver integration."""
        # webserver setup
        web_conf = WebserverConf(host="0.0.0.0", port=self.port)
        self.web_server = Webserver(ip=self.your_ip, conf=web_conf)
        # connect the output of webserver by registering it as a callback
        # the output is a flag to determine if the button has been clicked or not
        self.web_server.register_callback(self.on_button_click)

    def on_button_click(self, message):
        """
        Callback function for button click event from a web client.
        """
        if is_sic_instance(message, ButtonClicked):
            # send to MARBEL agent
            self.redis_client.publish(self.marbel_channel, "answer('"+message.button+"')")
            # special handling of microphone button
            if message.button == 'mic' and self.user_turn:
                self.logger.info("User requested microphone and it's their turn, so let's start listening.")
                self.user_turn = False  # Only agent saying something can hand back turn to user (see _handle_say below)
                self.web_server.send_message(SwitchTurnMessage())
                self._handle_start_listening_command()

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
        """Handle incoming text messages from alien (i.e. non-SIC) agents and process commands."""

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
            self.logger.info("Unknown command:", content)

    # Helper methods
    def _validate_message(self, message):
        """Ensure the message is a valid TextMessage."""
        # Currently assumes the message is a TextMessage object...
        if not is_sic_instance(message, TextMessage):
            raise TypeError(
                "Invalid message type {} for {}".format(
                    message.__class__.__name__, self.get_component_name()
                )
            )
        self.logger.info("{} received text message {}".format(
            self.get_component_name(), message.text
        ))

    def _extract_content(self, text):
        """Clean and extract the relevant part of the message text."""
        return text.replace("text:", "", 1).strip()

    def _handle_say_command(self, content):
        """Process 'say' command by synthesizing speech."""
        message_text = content.replace(
            "say(", "", 1).replace(")", "", 1).strip()
        self.logger.info("Planning to say: " + message_text)

        # Publish 'TextStarted' event
        self.redis_client.publish(self.marbel_channel, "event('TextStarted')")

        # Request speech synthesis
        if self.params.use_espeak:
            self.local_tts(text=message_text)
        else:
            reply = self.tts.request(
                GetSpeechRequest(text=message_text), block=True)
            self.on_speech_result(reply)

        # Hand back turn to user and inform webserver about this
        self.user_turn = True
        self.web_server.send_message(SwitchTurnMessage())
        # Publish 'TextDone' event
        self.redis_client.publish(self.marbel_channel, "event('TextDone')")

    def _handle_start_listening_command(self):
        """Process 'startListening' command by interacting with Dialogflow."""

        # send event to MARBEL agent
        self.redis_client.publish(
            self.marbel_channel, "event('ListeningStarted;1;48000')")

        # Prepare and perform Dialogflow request
        contexts = {"name": 1}  # Example context; adjust as needed
        reply = self.dialogflow.request(
            GetIntentRequest(self.conversation_id, contexts))

        # Send transcript to webserver (to enable displaying the transcript on a webpage)
        transcript = reply.response.query_result.query_text
        self.web_server.send_message(TranscriptMessage(transcript=transcript))

        # Extract relevant fields
        intent_name = reply.response.query_result.intent.display_name
        # TODO: extract entities
        entities = [{"recipe": "butter chicken"}]  # Example entities
        entities_str = ", ".join([f"{key}='{value}'" for entity in entities for key, value in entity.items()])
        confidence = round(float(reply.response.query_result.intent_detection_confidence), 2)
        source = "speech"

        # Format and send the intent message to the MARBEL agent and let agent know that Dialogflow stopped listening
        intent_message = f"intent({intent_name}, [{entities_str}], {confidence}, '{transcript}', {source})"
        self.redis_client.publish(
                    self.marbel_channel, intent_message)
        self.redis_client.publish(
            self.marbel_channel, "event('ListeningDone')")

    def _handle_stop_listening_command(self):
        """Process 'stopListening' command to stop Dialogflow or related service."""
        reply = self.dialogflow.request(
            StopListeningMessage(self.conversation_id))

        # Inform MARBEL agent that Dialogflow stopped listening
        self.redis_client.publish(
            self.marbel_channel, "event('ListeningDone')")

    def _handle_render_page_command(self, html):
        """"Used for implementing OLD MARBEL action 'renderPage' TODO: needs updating"""
        # the HTML file to be rendered
        web_url = f"http://{self.your_ip}:{self.port}/{html}"
        self.web_server.send_message(HtmlMessage(text="", html=html))
        self.logger.info("Open the web page at " + web_url)

    def on_request(self, request):
        """"Processing of requests; expected only from MARBELConnector and should be text based"""
        if is_sic_instance(request, TextRequest):
            if request.text.startswith("text:reqreply:handshake"):
                # handle handshake request
                self.logger.info("Received handshake request from EIS interface")
                input_channel = "{}:input:{}".format(
                    self.get_component_name(), self._ip)
                # TODO: set request id in reply
                message = EISReply("text:"+input_channel)
                message._previous_component_name = self.get_component_name()
                return message
            else:
                # We currently only handle a handshake on the reqreply channel...
                # This will cause problems...
                self.logger.info("Unknown request, this will cause problems...")

    def on_speech_result(self, wav_audio):
        self.logger.info("Receiving audio at sample rate:" + str(wav_audio.sample_rate))
        self.speakers_output.stream.write(wav_audio.waveform)

    def local_tts(self, text):
        call(["espeak", "-s140 -ven+18 -z", text])


class EISConnector(SICConnector):
    component_class = EISComponent


if __name__ == "__main__":
    # Request the service to start using the SICServiceManager on this device
    SICComponentManager([EISComponent])