import io
import socket
import threading
import wave

import numpy as np

from sic_framework import SICActuator, SICComponentManager, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICMessage
from sic_framework.core.sensor_python2 import SICSensor

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class NaoqiSpeakersConf(SICConfMessage):
    def __init__(self):
        self.no_channels = 1
        self.sample_rate = 16000
        self.index = -1


class NaoqiSpeakerComponent(SICComponent):
    def __init__(self, *args, **kwargs):
        super(NaoqiSpeakerComponent, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        self.audio_service = self.session.service("ALAudioDevice")
        self.audio_player_service = self.session.service("ALAudioPlayer")

        self.i = 0

    @staticmethod
    def get_conf():
        return NaoqiSpeakersConf()

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
        self.audio_player_service.playFile(tmp_file)

    def stop(self, *args):
        """
        Stop the Naoqi speaker component.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiSpeakerComponent, self).stop()


class NaoqiSpeaker(SICConnector):
    component_class = NaoqiSpeakerComponent


if __name__ == "__main__":
    SICComponentManager([NaoqiSpeakerComponent])
