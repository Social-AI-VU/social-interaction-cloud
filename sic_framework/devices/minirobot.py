import argparse
import os

import atexit
import threading
from sic_framework import SICComponentManager
from sic_framework.devices.common_mini.mini_animation import MiniAnimation, MiniAnimationActuator
from sic_framework.devices.device import SICDevice
from sic_framework.devices.common_mini.mini_microphone import MiniMicrophone, MiniMicrophoneSensor
from sic_framework.devices.common_mini.mini_speaker import MiniSpeaker, MiniSpeakerComponent


class MiniRobot(SICDevice):
    def __init__(self, ip="127.0.0.1", mic_conf=None, speaker_conf=None):
        super().__init__(ip=ip)
        self.configs[MiniMicrophone] = mic_conf
        self.configs[MiniSpeaker] = speaker_conf

    @property
    def mic(self):
        return self._get_connector(MiniMicrophone)
    
    @property
    def speaker(self):
        return self._get_connector(MiniSpeaker)

    @property
    def animation(self):
        return self._get_connector(MiniAnimation)


# mini_component_list = [MiniMicrophoneComponent, MiniSpeakerComponent]
mini_component_list = [MiniSpeakerComponent, MiniAnimationActuator]


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip
    SICComponentManager(mini_component_list)
