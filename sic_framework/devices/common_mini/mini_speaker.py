import pyaudio

from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage, SICConfMessage, SICMessage
)


class MiniSpeakersConf(SICConfMessage):
    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels


class MiniSpeakerComponent(SICComponent):
    COMPONENT_STARTUP_TIMEOUT = 5

    def __init__(self, *args, **kwargs):
        super(MiniSpeakerComponent, self).__init__(*args, **kwargs)


        self.device = pyaudio.PyAudio()
        # open an audio stream
        self.stream = self.device.open(
            format=pyaudio.paInt16,
            channels=self.params.channels,
            rate=self.params.sample_rate,
            input=False,
            output=True,
        )

    @staticmethod
    def get_conf():
        return MiniSpeakersConf()

    @staticmethod
    def get_inputs():
        return [AudioMessage]

    @staticmethod
    def get_output():
        return SICMessage

    def on_message(self, message):
        self.stream.write(message.waveform)

    def on_request(self, request):
        self.stream.write(request.waveform)
        return SICMessage()

    def stop(self, *args):
        super(MiniSpeakerComponent, self).stop(*args)
        self.logger.info("Stopped speakers")

        self.stream.close()
        self.device.terminate()


class MiniSpeaker(SICConnector):
    component_class = MiniSpeakerComponent


if __name__ == "__main__":
    SICComponentManager([MiniSpeakerComponent])
