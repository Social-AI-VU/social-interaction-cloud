import pyaudio

from sic_framework import SICActuator, SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICMessage


class SpeakersConf(SICConfMessage):
    """
    Parameters for speakers go here.
    """

    def __init__(self, sample_rate=44100, channels=1, device_index=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index


class DesktopSpeakersActuator(SICActuator):

    def __init__(self, *args, **kwargs):
        super(DesktopSpeakersActuator, self).__init__(*args, **kwargs)

        self.device = pyaudio.PyAudio()

        # open stream using callback (3)
        self.stream = self.device.open(
            format=pyaudio.paInt16,
            channels=self.params.channels,
            rate=self.params.sample_rate,
            input=False,
            output=True,
            output_device_index=self.params.device_index,
        )

    @staticmethod
    def get_conf():
        return SpeakersConf()

    @staticmethod
    def get_inputs():
        return [AudioMessage]

    @staticmethod
    def get_output():
        return SICMessage

    def on_request(self, request):
        self.stream.write(request.waveform)
        return SICMessage()

    def on_message(self, message):
        if hasattr(message, 'waveform'):
            self.stream.write(message.waveform)
        else:
            self.logger.warning("Expecting a message with a waveform attribute but received none")

    def stop(self, *args):
        super(DesktopSpeakersActuator, self).stop(*args)
        self.logger.info("Stopped speakers")

        self.stream.close()
        self.device.terminate()


class DesktopSpeakers(SICConnector):
    component_class = DesktopSpeakersActuator


if __name__ == "__main__":
    SICComponentManager([DesktopSpeakersActuator])
