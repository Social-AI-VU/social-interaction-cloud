import sounddevice as sd

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

        # device_index is a PortAudio device index (same numbering as PyAudio);
        # None selects the default output device.
        self.stream = sd.RawOutputStream(
            samplerate=self.params.sample_rate,
            channels=self.params.channels,
            dtype="int16",
            device=self.params.device_index,
        )
        self.stream.start()

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

    def _cleanup(self):
        self.logger.info("Stopped speakers")
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


class DesktopSpeakers(SICConnector):
    component_class = DesktopSpeakersActuator
    component_group = "Desktop"


if __name__ == "__main__":
    SICComponentManager([DesktopSpeakersActuator], component_group="Desktop")
