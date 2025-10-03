import argparse
import atexit
import threading
import time

from sic_framework import SICComponentManager, utils
from sic_framework.devices.common_desktop.desktop_camera import (
    DesktopCamera,
    DesktopCameraSensor,
)
from sic_framework.devices.common_desktop.desktop_microphone import (
    DesktopMicrophone,
    DesktopMicrophoneSensor,
)
from sic_framework.devices.common_desktop.desktop_speakers import (
    DesktopSpeakers,
    DesktopSpeakersActuator,
)
from sic_framework.devices.common_desktop.desktop_text_to_speech import (
    DesktopTextToSpeech,
    DesktopTextToSpeechActuator,
)
from sic_framework.devices.common_desktop.desktop_spacemouse import (
    DesktopSpaceMouse,
    DesktopSpaceMouseSensor
)
from sic_framework.devices.device import SICDeviceManager

desktop_active = False

class Desktop(SICDeviceManager):
    def __init__(
        self, camera_conf=None, mic_conf=None, speakers_conf=None, tts_conf=None
    ):
        super(Desktop, self).__init__(ip="127.0.0.1")

        self.configs[DesktopCamera] = camera_conf
        self.configs[DesktopMicrophone] = mic_conf
        self.configs[DesktopSpeakers] = speakers_conf
        self.configs[DesktopTextToSpeech] = tts_conf

        global desktop_active

        if not desktop_active:
            # Create manager in main thread
            self.manager = SICComponentManager(desktop_component_list, client_id=utils.get_ip_adress(), auto_serve=False, name="Desktop")
            
            def managed_serve():
                try:
                    self.manager.serve()
                finally:
                    # Ensure cleanup happens even if serve exits unexpectedly
                    self.manager.stop_component_manager()
            
            # Run serve in a thread
            self.thread = threading.Thread(
                target=managed_serve,
                name="DesktopComponentManager-singleton",
                daemon=True
            )
            self.thread.start()
            
            desktop_active = True

    def stop_device(self):
        """
        Stops the desktop device and all its components.
        """
        self.manager.stop_component_manager()
        desktop_active = False

    @property
    def camera(self):
        return self._get_connector(DesktopCamera)

    @property
    def mic(self):
        return self._get_connector(DesktopMicrophone)

    @property
    def speakers(self):
        return self._get_connector(DesktopSpeakers)

    @property
    def tts(self):
        return self._get_connector(DesktopTextToSpeech)

    @property
    def spacemouse(self):
        return self._get_connector(DesktopSpaceMouse)

desktop_component_list = [
    DesktopMicrophoneSensor,
    DesktopCameraSensor,
    DesktopSpeakersActuator,
    DesktopTextToSpeechActuator,
    DesktopSpaceMouseSensor
]

if __name__ == "__main__":
    SICComponentManager(desktop_component_list, name="Desktop")
