import pyaudio
from subprocess import call

from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICIgnoreRequestMessage,
    SICMessage,
    SICRequest,
    TextMessage,
    TextRequest
)
from sic_framework.core.utils import is_sic_instance

from sic_framework.devices.common_desktop.desktop_text_to_speech import TextToSpeechConf
from sic_framework.devices.desktop import Desktop

from sic_framework.services.text2speech.text2speech_service import Text2Speech, Text2SpeechConf, GetSpeechRequest, \
    SpeechResult

""""
INSTALLATION INSTRUCTIONS

ESPEAK
[Windows]
download and install espeak: http://espeak.sourceforge.net/
add eSpeak/command-line to PATH
[Linux]
`sudo apt-get install espeak libespeak-dev`
[MacOS]
brew install espeak
"""

class DummyConf(SICConfMessage):
    """
    Dummy SICConfMessage
    """

    def __init__(self):
        super(SICConfMessage, self).__init__()


class DummyRequest(SICRequest):
    """
    Dummy request
    """

    def __init__(self):
        super(SICRequest, self).__init__()


class DummyMessage(SICMessage):
    """
    Dummy input message
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
    Dummy SICAction
    """

    def __init__(self, *args, **kwargs):
        super(EISComponent, self).__init__(*args, **kwargs)

        # Do component initialization

        # Setup desktop device... eSpeak does not work (pip install espeak fails...)
        # tts_conf = TextToSpeechConf(rate=160, pitch=55)
        # self.desktop = Desktop(tts_conf=tts_conf)

        # Start text to speech service
        # does not seem to work yet...
        # conf = Text2SpeechConf(keyfile = "C:/Users/khs650/Git/social-interaction-cloud"
        #                                 "/sic_framework/services/eis/mas-2023-test-fkcp-f55e450fe830.json")
        # self.tts = Text2Speech(conf=conf)
        # Route the output of tts to EISComponent
        # self.tts.register_callback(self.on_speech_result)

    @staticmethod
    def get_inputs():
        return [DummyRequest]

    @staticmethod
    def get_output():
        return DummyOutputMessage

    # This function is optional
    @staticmethod
    def get_conf():
        return DummyConf()

    def on_message(self, message):
        # We're expecting text messages here...
        if is_sic_instance(message, TextMessage):
            print("{} received text message {}".format(self.get_component_name(), message.text))
        else:
            raise TypeError(
                "Invalid message type {} for {}".format(message.__class__.__name__, self.get_component_name())
            )

        content = message.text.replace("text:", "", 1)

        if content.startswith("say"):
            # Get rid of action label and brackets to obtain parameter
            content = content.replace("say(", "", 1).replace(")", "", 1)
            print("I would like to say " + content)
            # Make the tts request; let's not block on it...
            self.local_tts(content)
            # Would be nice to also be able to use Google tts service
            # self.tts.request(GetSpeechRequest(text=content), block=False)

    def on_request(self, request):
        if is_sic_instance(request, TextRequest):
            if request.text.startswith("text:reqreply:handshake"):
                # handle handshake request
                print("Received handshake request from EIS interface")
                input_channel = "{}:input:{}".format(self.get_component_name(), self._ip)
                # TODO set request id in reply
                message = EISReply("text:"+input_channel)
                message._previous_component_name = self.get_component_name()
                return message
            else:
                # We currently only handle a handshake on the reqreply channel...
                # This will cause problems...
                print("Unknown request, this will cause problems...")

    def on_speech_result(self, message):
        print("I am receiving audio!!")
        # set up output device to play audio along transcript
        p = pyaudio.PyAudio()
        output = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=samplerate,
                        output=True)

        wavefile = message.wav_audio
        # send the audio in chunks of one second
        for i in range(wavefile.getnframes() // wavefile.getframerate()):
            # grab one second of audio data
            chunk = wavefile.readframes(samplerate)
            output.write(chunk)

    def local_tts(self, text):
        call(["espeak", "-s140 -ven+18 -z", text])


class EISConnector(SICConnector):
    component_class = EISComponent


if __name__ == "__main__":
    # Request the service to start using the SICServiceManager on this device
    SICComponentManager([EISComponent])