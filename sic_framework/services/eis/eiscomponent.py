import os
import wave
import redis
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
        keyfile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mas-2023-test-fkcp-f55e450fe830.json")
        conf = Text2SpeechConf(keyfile = keyfile_path)
        self.tts = Text2Speech(conf=conf)
        # Redis connection setup with authentication
        self.redis_client = redis.Redis(
            host='localhost',       # Redis server address
            port=6379,              # Redis server port
            password='changemeplease',  # Redis authentication password
            db=0                    # Database index (default is 0)
        )
        # Define the channel and message
        self.marbel_channel = "MARBELConnector:input:127.0.1.1"


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
            content = content.replace("say(", "", 1).replace(")", "", 1)
            print("I would like to say " + content)
            self.redis_client.publish(self.marbel_channel, "event('TextStarted')")
            reply = self.tts.request(GetSpeechRequest(text=content), block=True)
            self.on_speech_result(reply)
            # or
            # self.local_tts(content)
            self.redis_client.publish(self.marbel_channel, "event('TextDone')")
        elif content.startswith("startListening"): # implement startListening(15) using Dialogflow (or other service)
            pass
        elif content.startswith("stopListening"): # tell Dialogflow (or other service) to stop
            pass


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

    def on_speech_result(self, wav_audio):
        print("I am receiving audio!!")
        # set up output device to play audio along transcript
        p = pyaudio.PyAudio()
        output = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=wav_audio.sample_rate,
                        output=True)

        wavefile = wav_audio.waveform
        # send the audio in chunks of one second
        output.write(wavefile)
        # for i in range(len(wavefile) // (wav_audio.sample_rate*2)):
        #    # grab one second of audio data
        #    chunk = wavefile[i*(wav_audio.sample_rate*2):(i+1)*(wav_audio.sample_rate*2)-1]
        #    output.write(chunk)

    def local_tts(self, text):
        call(["espeak", "-s140 -ven+18 -z", text])


class EISConnector(SICConnector):
    component_class = EISComponent


if __name__ == "__main__":
    # Request the service to start using the SICServiceManager on this device
    SICComponentManager([EISComponent])