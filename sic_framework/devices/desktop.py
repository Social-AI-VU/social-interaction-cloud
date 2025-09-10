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
from sic_framework.devices.device import SICDevice

desktop_active = False

class Desktop(SICDevice):
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
            # Create shutdown event
            self._shutdown_event = threading.Event()
            
            def managed_serve():
                try:
                    self.manager.serve()
                finally:
                    # Ensure cleanup happens even if serve exits unexpectedly
                    self.manager.stop()
            
            # Run serve in non-daemon thread but with controlled shutdown
            self.thread = threading.Thread(
                target=managed_serve,
                name="DesktopComponentManager-singleton",
                daemon=True
            )
            self.thread.start()
            
            # Register cleanup that coordinates shutdown
            def desktop_cm_cleanup():
                self.manager.stop_event.set()  # Signal serve loop to stop
                self.thread.join(timeout=5)     # Wait for clean shutdown
                if self.thread.is_alive():      # If still alive after timeout
                    self.logger.warning("Desktop manager thread did not stop cleanly")
            
            atexit.register(desktop_cm_cleanup)
            desktop_active = True

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


desktop_component_list = [
    DesktopMicrophoneSensor,
    DesktopCameraSensor,
    DesktopSpeakersActuator,
    DesktopTextToSpeechActuator,
]

if __name__ == "__main__":
    SICComponentManager(desktop_component_list, name="Desktop")
