import argparse
import os

import atexit
import threading
from sic_framework import SICComponentManager
from sic_framework.devices.device import SICDevice
from sic_framework.devices.common_mini.mini_microphone import MiniMicrophone, MiniMicrophoneSensor
from sic_framework.devices.common_mini.mini_speaker import MiniSpeaker, MiniSpeakerComponent

mini_active = False

def start_mini_components():
    manager = SICComponentManager(mini_component_list,
                                  auto_serve=False)
    atexit.register(manager.stop)
    from contextlib import redirect_stderr
    with redirect_stderr(None):
        manager.serve()


class MiniRobot(SICDevice):
    def __init__(self, mic_conf=None, speaker_conf=None):
        super().__init__(ip="127.0.0.1")
        self.configs[MiniMicrophone] = mic_conf
        self.configs[MiniSpeaker] = speaker_conf

        global mini_active
        if not mini_active:
            # run the component manager in a thread
            thread = threading.Thread(target=start_mini_components, name="MiniComponentManager-singelton")
            thread.start()
            mini_active = True

    @property
    def mic(self):
        return self._get_connector(MiniMicrophone)
    
    @property
    def speaker(self):
        return self._get_connector(MiniSpeaker)


# mini_component_list = [MiniMicrophoneComponent, MiniSpeakerComponent]
mini_component_list = [MiniSpeakerComponent]


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip
    SICComponentManager(mini_component_list)
