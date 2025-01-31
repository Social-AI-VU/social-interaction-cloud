import asyncio
import os
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

        # # Create the directory tmp directory in the home folder if it doesn't exist
        tmp_path = "/data/data/com.termux/files/home/tmp/"
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        # # Define the file path for the temp audio file
        tmp_file = tmp_path + f"tmp{self.i}.wav"

        # Set the parameters for the WAV file
        channels = 1  # 1 for mono audio
        sample_width = 2  # 2 bytes for 16-bit audio
        num_frames = len(bytestream) // (channels * sample_width)

        with wave.open(tmp_file, "wb") as wav_file:
            wav_file.setparams(
                (channels, sample_width, frame_rate, num_frames, "NONE", "not compressed")
            )
            wav_file.writeframes(bytestream)
        self.i += 1

        # Ensure an event loop exists in the current thread
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Play the audio file
        Tool.run_py_pkg(f'play {tmp_file}', robot_id="00167", debug=True)


class MiniSpeaker(SICConnector):
    component_class = MiniSpeakerComponent


if __name__ == "__main__":
    SICComponentManager([MiniSpeakerComponent])
