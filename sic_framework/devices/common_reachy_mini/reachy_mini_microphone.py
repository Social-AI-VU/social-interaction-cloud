import numpy as np

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor


class ReachyMiniMicrophoneConf(SICConfMessage):
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate


class ReachyMiniMicrophoneSensor(SICSensor):
    """Captures audio from Reachy Mini's microphone.

    Converts the SDK's float32 stereo output to mono PCM 16-bit signed bytes
    for compatibility with SIC's AudioMessage format.
    """

    def __init__(self, *args, **kwargs):
        super(ReachyMiniMicrophoneSensor, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance
        self.mini.media.start_recording()

    @staticmethod
    def get_conf():
        return ReachyMiniMicrophoneConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return AudioMessage

    def execute(self):
        try:
            samples = self.mini.media.get_audio_sample()
        except Exception as e:
            self.logger.warning("Failed to read audio: {}".format(e))
            return None

        if samples is None:
            return None

        # SDK returns (N, 2) float32 stereo at 16kHz; mix to mono
        if samples.ndim == 2 and samples.shape[1] == 2:
            mono = np.mean(samples, axis=1)
        else:
            mono = samples.flatten()

        # Clip and convert float32 [-1.0, 1.0] to PCM 16-bit signed
        mono = np.clip(mono, -1.0, 1.0)
        pcm = (mono * 32767).astype(np.int16)
        waveform = pcm.tobytes()

        return AudioMessage(waveform, sample_rate=self.params.sample_rate)

    def _cleanup(self):
        try:
            self.mini.media.stop_recording()
        except Exception:
            pass


class ReachyMiniMicrophone(SICConnector):
    component_class = ReachyMiniMicrophoneSensor
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniMicrophoneSensor], component_group="ReachyMini")
