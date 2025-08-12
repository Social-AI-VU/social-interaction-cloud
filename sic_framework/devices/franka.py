import atexit
import threading

from sic_framework import SICComponentManager, utils
from sic_framework.devices.device import SICDevice
from sic_framework.devices.common_franka.franka_motion import (
    FrankaMotion,
    FrankaMotionActuator,
)
from sic_framework.devices.common_franka.franka_motion_recorder import (
    FrankaMotionRecorder,
    FrankaMotionRecorderActuator,
)

franka_active = False

def start_franka_components():
    manager = SICComponentManager(franka_component_list, client_id=utils.get_ip_adress(), auto_serve=False, name="Franka")

    atexit.register(manager.stop)
    from contextlib import redirect_stderr
    with redirect_stderr(None):
        manager.serve()


class Franka(SICDevice):
    def __init__(self, motion_conf=None):
        super().__init__(ip="127.0.0.1")
        self.configs[FrankaMotion] = motion_conf

        global franka_active
        if not franka_active:
            # run the component manager in a thread
            thread = threading.Thread(target=start_franka_components, name="FrankaComponentManager-singelton")
            thread.start()
            franka_active = True

    @property
    def motion_recorder(self):
        return self._get_connector(FrankaMotionRecorder)

    @property
    def motion(self):
        return self._get_connector(FrankaMotion)


franka_component_list = [FrankaMotionRecorderActuator, FrankaMotionActuator]


if __name__ == '__main__':
    SICComponentManager(franka_component_list, name="Franka")
