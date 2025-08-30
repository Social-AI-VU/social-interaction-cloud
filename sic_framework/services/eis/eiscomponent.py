import os
import redis
from google.protobuf.json_format import MessageToDict
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
from sic_framework.services.google_tts.google_tts import \
    (Text2Speech, Text2SpeechConf, GetSpeechRequest, SpeechResult)
from sic_framework.services.dialogflow.dialogflow import\
    (DialogflowConf, GetIntentRequest, StopListeningMessage, RecognitionResult, QueryResult, Dialogflow)
from sic_framework.services.webserver.webserver_pca import \
    (ButtonClicked, HtmlMessage, SetTurnMessage, TranscriptMessage, WebInfoMessage, Webserver, WebserverConf)


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
        # ASSUMPTION: Google TTS service will be used
        self.params.use_espeak = False
        # Keyfile needed for Dialogflow and Google TTS
        # ASSUMPTION: This file is named 'dialogflow-keyfile.json' and added to the services/eis folder
        self.keyfile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dialogflow-keyfile.json")

        # IP and port parameters
        # ASSUMPTION: code is run locally on a single machine, where Redis also runs
        self.your_ip = "localhost"
        self.port = 8080

        # Redis channel to communicate with (a single) MARBEL agent (for sending percepts)
        # The channel name below illustrates the structure that we assume (by convention, in line with SIC conventions)
        # Is set to correct channel in first handshake with a MARBEL agent
        self.marbel_channel = "MARBELConnector:input:127.0.1.1"

        # Flag used to keep track of who can talk, either user or agent; initially, the agent does the talking
        self.user_turn = False

        # Setup SIC components that we want to use
        self._setup_redis()  # Setup a Redis client
        self._setup_hardware()
        self._setup_text_to_speech()
        self._setup_dialogflow()
        self._setup_webserver()

        # self.web_server.send_message(SetTurnMessage(user_turn=self.user_turn))

    def _setup_redis(self):
        """Set up Redis connection."""
        self.redis_client = redis.Redis(
            host=self.your_ip,
            port=6379,  # TODO: hard coding of Redis config parameters port and password
            password='changemeplease',
            db=0
        )

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

    def _setup_dialogflow(self):
        """Initialize Dialogflow integration."""
        with open(self.keyfile_path, 'r') as keyfile:
            keyfile_json = json.load(keyfile)

        conf = DialogflowConf(
            keyfile_json=keyfile_json,
            sample_rate_hertz=44100,
            language="en"  # TODO: hard coding of language parameter
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
            # if self.user_turn:
            #    self.logger.info("Received " + content + ", but ignoring this as it is not the agent's turn")
            #    self.logger.info("Sending event: TextDone")  # Inform agent that we are done with their request...
            #    self.redis_client.publish(self.marbel_channel, "event('TextDone')")
            # else:
                self._handle_say_command(content)
        elif content.startswith("webinfo"):
            self._handle_web_info_command(content)
        # What follows is OLD
        elif content.startswith("startListening"):
            self._handle_start_listening_command()
        elif content.startswith("stopListening"):
            self._handle_stop_listening_command()
        elif content.startswith("renderPage"):
            self._handle_render_page_command(content)
        else:
            self.logger.info("Unknown command: " + content)

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
        self.logger.info(f"Received text message: {message.text}")

    def _extract_content(self, text):
        """Clean and extract the relevant part of the message text."""
        return text.replace("text:", "", 1).strip()

    def _handle_say_command(self, content):
        """Process 'say' command by synthesizing speech."""
        message_text = content.replace(
            "say(", "", 1).replace(")", "", 1).strip()
        self.logger.info("Planning to say: " + message_text)

        # Publish 'TextStarted' event
        self.logger.info("Sending event: TextStarted")
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
        self.web_server.send_message(SetTurnMessage(user_turn=self.user_turn))
        self.redis_client.publish(self.marbel_channel, "event('UserTurn')")
        # Publish 'TextDone' event
        self.logger.info("Sending event: TextDone")
        self.redis_client.publish(self.marbel_channel, "event('TextDone')")

    def _handle_web_info_command(self, command):
        # remove command and initial and ending brackets
        parameter_text = command.replace("webinfo(", "", 1)[:-1]
        label = parameter_text[:parameter_text.find(",")]
        message = parameter_text.replace(label+",", "", 1)
        self.logger.info(f"Sending message {message} for label {label} to server")
        self.web_server.send_message(WebInfoMessage(label, message))

    def _handle_start_listening_command(self):
        """Process 'startListening' command by interacting with Dialogflow."""

        # send event to MARBEL agent
        self.logger.info("Sending event: ListeningStarted")
        self.redis_client.publish(self.marbel_channel, "event('ListeningStarted')")

        # Prepare and perform Dialogflow request
        contexts = {"name": 1}  # Example context; adjust as needed
        reply = self.dialogflow.request(
            GetIntentRequest(self.conversation_id, contexts))

        # Send transcript to webserver (to enable displaying the transcript on a webpage)
        transcript = reply.response.query_result.query_text
        self.web_server.send_message(TranscriptMessage(transcript=transcript))
        # Send transcript to MARBEL agent
        self.redis_client.publish(self.marbel_channel, f"transcript({transcript})")

        # Send intent percept to MARBEL agent
        intent_str = self._intent_string(reply)
        self.logger.info(f"Sending intent: {intent_str}")
        self.redis_client.publish(self.marbel_channel, intent_str)

        # Inform agent that Dialogflow stopped listening and webserver that it is the agent's turn now
        self.logger.info("Sending event: ListeningDone")
        self.redis_client.publish(self.marbel_channel, "event('ListeningDone')")
        self.user_turn = False  # Only agent saying something can hand back turn to user (see _handle_say below)
        self.redis_client.publish(self.marbel_channel, "event('AgentTurn')")
        self.web_server.send_message(SetTurnMessage(user_turn=self.user_turn))

    def _intent_string(self, query_result: QueryResult) -> str:
        """"Process QueryResult(SICMessage) from Dialogflow component"""
        # TODO: this is Dialogflow specific code and needs to be moved to that component...
        # TODO: probably best to rework the QueryResult object (and rename it to something like NLUResult too)
        intent_name = query_result.response.query_result.action
        entities_str = ""
        if "query_result" in query_result.response and query_result.response.query_result.parameters:
            entities = MessageToDict(query_result.response._pb).get('queryResult').get('parameters')  # E.g., [{"recipe": "butter chicken"}]
            entities_str = self._process_parameters(entities)
        confidence = round(float(query_result.response.query_result.intent_detection_confidence), 2)
        transcript = query_result.response.query_result.query_text
        source = "speech"  # Simply assume that speech has been used to get NLU results
        if entities_str:
            self.logger.info(f"Received entities: {entities_str}")
        # Use double quotes around transcript, as transcript might include single quotes
        return f"intent({intent_name}#1#[{entities_str}]#1#{confidence}#1#\"{transcript}\"#1#{source})"

    def _process_parameters(self, parameters) -> str:
        processed_entities = []
        # Remove empty values
        for key, value in parameters.items():
            if isinstance(value, list) and value:
                list_values = "#3#".join(value)
                processed_entities.append(f"{key}=[{list_values}]")  # Turn list into string
            elif isinstance(value, str) and value:
                processed_entities.append(f"{key}={value}")
        return "#2#".join(processed_entities)

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
        """"
        Processing of requests received (on the Redis reqreply channel);
        Expects only requests from MARBELConnector, which should be 'text based'.
        The requests that we expect to handle here are related to the initial handshake between
        this component and the MARBELConnector.
        """
        if is_sic_instance(request, TextRequest):
            content = request.text.replace("text:reqreply:", "", 1).strip()
            if content.startswith("handshake"):
                # handle handshake request
                self.logger.info("Received handshake request from MARBEL Connector")
                # Expecting MARBEL input channel on Redis after 'handshake:' (by convention)
                self.marbel_channel = content.replace("handshake:", "", 1).strip()
                # Prepare reply message
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
    SICComponentManager([EISComponent], name="EIS")