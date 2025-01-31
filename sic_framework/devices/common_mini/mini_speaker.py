
import wave

from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICMessage

from mini import mini_sdk as MiniSdk
import mini.pkg_tool as Tool



class MiniSpeakersConf(SICConfMessage):
    def __init__(self, sample_rate=44100, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels


class MiniSpeakerComponent(SICComponent):
    def __init__(self, *args, **kwargs):
        super(MiniSpeakerComponent, self).__init__(*args, **kwargs)
        MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
        self.i = 0

    @staticmethod
    def get_conf():
        return MiniSpeakersConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return SICMessage

    def on_message(self, message):
        self.play_sound(message)

    def on_request(self, request):
        self.play_sound(request)
        return SICMessage()

    def play_sound(self, message):
        bytestream = message.waveform
        frame_rate = message.sample_rate

        # Set the parameters for the WAV file
        channels = 1  # 1 for mono audio
        sample_width = 2  # 2 bytes for 16-bit audio
        num_frames = len(bytestream) // (channels * sample_width)

        # Create a WAV file in memory
        tmp_file = "/tmp/tmp{}.wav".format(self.i)

        wav_file = wave.open(tmp_file, "wb")
        self.i += 1
        wav_file.setparams(
            (channels, sample_width, frame_rate, num_frames, "NONE", "not compressed")
        )
        # Write the bytestream to the WAV file
        wav_file.writeframes(bytestream)
        # Launchs the playing of a file
        Tool.run_py_pkg(f'play {tmp_file}', robot_id="00167", debug=True)


class MiniSpeaker(SICConnector):
    component_class = MiniSpeakerComponent


if __name__ == "__main__":
    SICComponentManager([MiniSpeakerComponent])
