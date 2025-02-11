import argparse
import os

from sic_framework import SICComponentManager
from sic_framework.devices.common_mini.mini_animation import MiniAnimation, MiniAnimationActuator
from sic_framework.devices.device import SICDevice
from sic_framework.devices.common_mini.mini_microphone import MiniMicrophone, MiniMicrophoneSensor
from sic_framework.devices.common_mini.mini_speaker import MiniSpeaker, MiniSpeakerComponent


class Alphamini(SICDevice):
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


mini_component_list = [MiniMicrophoneSensor, MiniSpeakerComponent, MiniAnimationActuator]


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    parser.add_argument(
        "--robot_id", type=str, required=True, help="Provide the last 5 digits of the robot's serial number"
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip
    os.environ["ROBOT_TYPE"] = "alphamini"
    os.environ["ROBOT_ID"] = args.robot_id
    SICComponentManager(mini_component_list)
