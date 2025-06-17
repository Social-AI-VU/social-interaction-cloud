import argparse
import atexit
import threading
import time
import sys
import signal

from sic_framework import SICComponentManager
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
desktop_manager = None
desktop_thread = None

def start_desktop_components():
    global desktop_manager
    desktop_manager = SICComponentManager(desktop_component_list, auto_serve=False)

    from contextlib import redirect_stderr

    with redirect_stderr(None):
        desktop_manager.serve()


def cleanup_desktop():
    """Clean up desktop resources when exceptions occur."""
    print("Cleaning up desktop")
    global desktop_active, desktop_manager, desktop_thread
    
    if desktop_active and desktop_manager:
        try:
            desktop_manager.stop_event.set()
            desktop_active = False
            desktop_manager = None
            desktop_thread = None
        except Exception as e:
            print(f"Error during desktop cleanup: {e}")

    # print("desktop cleanup complete")
    # print("LEFT OVER THREADS: ", threading.enumerate())


def signal_handler(signum, frame):
    """Handle signals to ensure clean shutdown."""
    # Check if Python is shutting down to avoid interference
    if sys.meta_path is None:
        return
        
    cleanup_desktop()
    sys.exit(0)


def exception_handler(exc_type, exc_value, exc_traceback):
    """Handle unhandled exceptions to ensure clean shutdown."""
    print("\n" + "="*60)
    print("UNHANDLED EXCEPTION DETECTED:")
    print("="*60)
    print(f"Exception type: {exc_type}")
    print(f"Exception value: {exc_value}")
    print(f"Exception traceback: {exc_traceback}")
    
    # Call the original exception handler first
    sys.__excepthook__(exc_type, exc_value, exc_traceback)
    
    print("="*60)
    print("INITIATING CLEANUP AFTER EXCEPTION:")
    print("="*60)
    
    # Then clean up desktop resources
    cleanup_desktop()


# Register signal handlers for clean shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Register exception handler for unhandled exceptions
sys.excepthook = exception_handler

class Desktop(SICDevice):
    def __init__(
        self, camera_conf=None, mic_conf=None, speakers_conf=None, tts_conf=None
    ):
        super(Desktop, self).__init__(ip="127.0.0.1")

        self.configs[DesktopCamera] = camera_conf
        self.configs[DesktopMicrophone] = mic_conf
        self.configs[DesktopSpeakers] = speakers_conf
        self.configs[DesktopTextToSpeech] = tts_conf

        global desktop_active, desktop_thread


        if not desktop_active:
            self.logger.info("Starting Desktop ComponentManager")

            # run the component manager in a thread
            desktop_thread = threading.Thread(
                daemon=True,
                target=start_desktop_components,
                name="DesktopComponentManager-singelton",
            )
            desktop_thread.start()

            desktop_active = True

    def stop(self):
        """Stop the desktop component manager and clean up resources."""
        cleanup_desktop()

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
    SICComponentManager(desktop_component_list)
