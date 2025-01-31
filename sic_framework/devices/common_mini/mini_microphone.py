import threading

from sic_framework import SICComponentManager, utils
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor

# if utils.PYTHON_VERSION_IS_2:
#     import qi
#     from naoqi import ALProxy


class MiniMicrophoneConf(SICConfMessage):
    def __init__(self):
        self.channel_index = 3  # front microphone
        self.no_channels = 1
        self.sample_rate = 16000
        self.index = -1


class MiniMicrophoneSensor(SICSensor):
    COMPONENT_STARTUP_TIMEOUT = 4

    def __init__(self, *args, **kwargs):
        super(MiniMicrophoneSensor, self).__init__(*args, **kwargs)
        self.module_name = "SICMicrophoneService"

    @staticmethod
    def get_conf():
        return MiniMicrophoneConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return AudioMessage

    def execute(self):

        return AudioMessage(self.audio_buffer, sample_rate=self.params.sample_rate)

    def stop(self, *args):
        super(MiniMicrophoneSensor, self).stop(*args)

    def processRemote(self, nbOfChannels, nbOfSamplesByChannel, timeStamp, inputBuffer):
        """
        This function is registered by the self.session.registerService(self) call.
        :param nbOfChannels:
        :param nbOfSamplesByChannel:
        :param timeStamp:
        :param inputBuffer:
        """
        self.audio_buffer = inputBuffer
        self.naoqi_timestamp = timeStamp


class MiniMicrophone(SICConnector):
    component_class = MiniMicrophoneSensor


if __name__ == "__main__":
    SICComponentManager([MiniMicrophoneSensor])
