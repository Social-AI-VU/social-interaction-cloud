"""
franka.py

This module provides the Franka device class and starts Franka-related components automatically.
"""

import atexit
import threading

from sic_framework import SICComponentManager, utils
from sic_framework.devices.device import SICDeviceManager
from sic_framework.devices.common_franka.franka_motion import (
    FrankaMotion,
    FrankaMotionActuator,
)
from sic_framework.devices.common_franka.franka_motion_recorder import (
    FrankaMotionRecorder,
    FrankaMotionRecorderActuator,
)

franka_active = False

class Franka(SICDeviceManager):
    """
    Franka device interface that automatically starts the component manager
    in a background thread on first initialization.
    """

    def __init__(self, motion_conf=None):
        """
        Initialize the Franka device with the given motion configuration
        :param motion_conf: Configuration for the Franka motion component
        """
        super().__init__(ip="127.0.0.1")
        self.configs[FrankaMotion] = motion_conf

        global franka_active
        if not franka_active:
            self.manager = SICComponentManager(
                franka_component_list,
                client_id=utils.get_ip_adress(),
                auto_serve=False,
                name="Franka",
            )
            # Prevent this embedded manager from force-exiting the whole process.
            self.manager.is_main_thread = False
            
            def managed_serve():
                try:
                    self.manager.serve()
                finally:
                    # Ensure cleanup happens even if serve exits unexpectedly
                    self.manager.stop_component_manager()
            
            # Run serve in a thread
            self.thread = threading.Thread(
                target=managed_serve,
                name="FrankaComponentManager-singleton",
                daemon=True
            )
            self.thread.start()

            franka_active = True

    @property
    def motion_recorder(self):
        """
        Get the Franka motion recorder connector.
        :return: The FrankaMotionRecorder connector.
        """
        return self._get_connector(FrankaMotionRecorder)

    @property
    def motion(self):
        """
        Get the Franka motion connector.
        :return: The FrankaMotion connector.
        """

        return self._get_connector(FrankaMotion)


franka_component_list = [FrankaMotionRecorderActuator, FrankaMotionActuator]


if __name__ == '__main__':
    SICComponentManager(franka_component_list, name="Franka")
