import pyaudio

from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor


class MicrophoneConf(SICConfMessage):
    def __init__(self):
        self.no_channels = 1
        self.sample_rate = 44100


class DesktopMicrophoneSensor(SICSensor):
    def __init__(self, *args, **kwargs):
        super(DesktopMicrophoneSensor, self).__init__(*args, **kwargs)

        self.audio_buffer = None

        self.device = pyaudio.PyAudio()

        # open stream using callback (3)
        self.stream = self.device.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.params.sample_rate,
            input=True,
            output=False,
            frames_per_buffer=int(self.params.sample_rate // 4),  # 250ms chunks
        )

    @staticmethod
    def get_conf():
        return MicrophoneConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return AudioMessage

    def execute(self):
        try:
            # read without exception on overflow to prevent the stream from closing
            # if Redis is non-local, delays in network communication can cause overflows
            # this is a workaround to keep the stream alive
            data = self.stream.read(int(self.params.sample_rate // 4), exception_on_overflow=False)
            return AudioMessage(data, sample_rate=self.params.sample_rate)
        except Exception as e:
            self.logger.error("Error reading audio data: {e}".format(e=e))
            # Return empty audio data to keep the stream alive
            empty_data = b'\x00' * int(self.params.sample_rate // 4) * 2  # 16-bit samples
            return AudioMessage(empty_data, sample_rate=self.params.sample_rate)

    def stop(self, *args):
        super(DesktopMicrophoneSensor, self).stop(*args)
        self.logger.info("Stopped microphone")
        self.stream.close()
        self.device.terminate()


class DesktopMicrophone(SICConnector):
    component_class = DesktopMicrophoneSensor


if __name__ == "__main__":
    SICComponentManager([DesktopMicrophoneSensor])
