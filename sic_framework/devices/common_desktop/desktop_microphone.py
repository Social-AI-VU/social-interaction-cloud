import sounddevice as sd

from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor


class MicrophoneConf(SICConfMessage):
    def __init__(self, channels=1, sample_rate=44100, device_index=None):
        self.channels = channels
        self.sample_rate = sample_rate
        self.device_index = device_index


class DesktopMicrophoneSensor(SICSensor):
    def __init__(self, *args, **kwargs):
        super(DesktopMicrophoneSensor, self).__init__(*args, **kwargs)

        self.audio_buffer = None

        # device_index is a PortAudio device index (same numbering as PyAudio);
        # None selects the default input device.
        self.stream = sd.RawInputStream(
            samplerate=self.params.sample_rate,
            channels=1,
            dtype="int16",
            device=self.params.device_index,
            blocksize=int(self.params.sample_rate // 4),  # 250ms chunks
        )
        self.stream.start()

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
            # sounddevice reports overflows via a flag instead of raising, so the
            # stream stays alive if Redis is non-local and network delays cause overflows
            data, _overflowed = self.stream.read(int(self.params.sample_rate // 4))
            return AudioMessage(bytes(data), sample_rate=self.params.sample_rate)
        except Exception as e:
            self.logger.error("Error reading audio data: {e}".format(e=e))
            # Return empty audio data to keep the stream alive
            empty_data = b'\x00' * int(self.params.sample_rate // 4) * 2  # 16-bit samples
            return AudioMessage(empty_data, sample_rate=self.params.sample_rate)

    def _cleanup(self):
        self.logger.info("Stopped microphone")
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


class DesktopMicrophone(SICConnector):
    component_class = DesktopMicrophoneSensor
    component_group = "Desktop"


if __name__ == "__main__":
    SICComponentManager([DesktopMicrophoneSensor], component_group="Desktop")
