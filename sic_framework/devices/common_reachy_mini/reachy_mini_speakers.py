from math import gcd

import numpy as np
from scipy.signal import resample_poly

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICMessage
from sic_framework.core.actuator_python2 import SICActuator


class ReachyMiniSpeakersConf(SICConfMessage):
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate


class ReachyMiniSpeakersActuator(SICActuator):
    """Plays audio through Reachy Mini's speaker.

    Accepts SIC AudioMessage (PCM 16-bit signed bytes) and converts to
    the SDK's expected float32 format before pushing to the speaker.
    """

    def __init__(self, *args, **kwargs):
        super(ReachyMiniSpeakersActuator, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance
        self._sdk_rate = self.mini.media.get_output_audio_samplerate()
        self.mini.media.start_playing()

    @staticmethod
    def get_conf():
        return ReachyMiniSpeakersConf()

    @staticmethod
    def get_inputs():
        return [AudioMessage]

    @staticmethod
    def get_output():
        return SICMessage

    def on_request(self, request):
        self._play_audio(request.waveform, request.sample_rate)
        return SICMessage()

    def on_message(self, message):
        if hasattr(message, "waveform"):
            rate = getattr(message, "sample_rate", self.params.sample_rate)
            self._play_audio(message.waveform, rate)
        else:
            self.logger.warning("Expected message with waveform attribute")

    def _play_audio(self, waveform, source_rate):
        pcm = np.frombuffer(waveform, dtype=np.int16)
        samples = pcm.astype(np.float32) / 32767.0

        if source_rate != self._sdk_rate:
            d = gcd(source_rate, self._sdk_rate)
            samples = resample_poly(samples, self._sdk_rate // d, source_rate // d)

        samples = samples.reshape(-1, 1)
        try:
            self.mini.media.push_audio_sample(samples)
        except Exception as e:
            self.logger.warning("Failed to push audio: {}".format(e))

    def _cleanup(self):
        try:
            self.mini.media.stop_playing()
        except Exception:
            pass


class ReachyMiniSpeakers(SICConnector):
    component_class = ReachyMiniSpeakersActuator
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniSpeakersActuator], component_group="ReachyMini")
