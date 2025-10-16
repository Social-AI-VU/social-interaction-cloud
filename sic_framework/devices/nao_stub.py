"""
NaoStub: A stub implementation of the NAO robot interface for testing and development.

This device provides the same interface as the real NAO robot but uses Desktop sensors/actuators
where possible. For NAO-specific actuators (motion, LEDs, stiffness, etc.), it logs the actions
instead of executing them.

Useful for:
- Testing NAO applications without a physical robot
- Developing NAO applications on a desktop/laptop
- Rapid prototyping of NAO behaviors
"""

import threading

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core import utils, sic_logging
from sic_framework.devices.device import SICDeviceManager
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
from sic_framework.devices.common_nao_stub import (
    NaoStubMotion,
    NaoStubMotionRecorder,
    NaoStubTTS,
    NaoStubStiffness,
    NaoStubAutonomous,
    NaoStubLEDs,
    NaoStubButtons,
    NaoStubTracker,
    NaoStubLookAt,
    # Actuator/Sensor classes
    NaoStubMotionActuator,
    NaoStubMotionRecorderActuator,
    NaoStubTTSActuator,
    NaoStubStiffnessActuator,
    NaoStubAutonomousActuator,
    NaoStubLEDsActuator,
    NaoStubButtonsSensor,
    NaoStubTrackerActuator,
    NaoStubLookAtActuator,
)

# Global flag to ensure only one Desktop component manager is started
_nao_stub_active = False


class NaoStub(SICDeviceManager):
    """
    NAO robot stub implementation.
    
    Provides the same interface as the real NAO robot but uses Desktop sensors/actuators
    where possible. NAO-specific actuators are stubbed with logging.
    
    Mappings:
    - top_camera, bottom_camera -> Desktop camera
    - mic -> Desktop microphone
    - speaker -> Desktop speakers
    - tts -> Desktop text-to-speech (with actual functionality)
    - motion, stiffness, autonomous, leds, buttons, tracker, look_at, motion_record -> Stub (logging only)
    
    Example usage:
        nao = NaoStub()
        nao.tts.request(NaoqiTextToSpeechRequest("Hello!"))  # Will use Desktop TTS
        nao.motion.request(NaoPostureRequest("Stand", 0.5))  # Will log the action
    """
    
    def __init__(self, ip="", sic_version=None, dev_test=False, test_repo=None, top_camera_conf=None, bottom_camera_conf=None, mic_conf=None, speakers_conf=None, tts_conf=None):
        """
        Initialize the NaoStub device.
        
        Args:
            camera_conf: Configuration for the desktop camera (optional)
            mic_conf: Configuration for the desktop microphone (optional)
            speakers_conf: Configuration for the desktop speakers (optional)
            tts_conf: Configuration for the desktop text-to-speech (optional)
        """
        # Initialize as a local device (like Desktop)
        super(NaoStub, self).__init__(ip="127.0.0.1")
        
        # Store configurations
        if top_camera_conf is not None:
            self.configs[DesktopCamera] = top_camera_conf
        if bottom_camera_conf is not None:
            self.configs[DesktopCamera] = bottom_camera_conf

        self.configs[DesktopMicrophone] = mic_conf
        self.configs[DesktopSpeakers] = speakers_conf
        self.configs[DesktopTextToSpeech] = tts_conf
        
        # Get logger
        self.logger = sic_logging.get_sic_logger(
            "NaoStub",
            client_id=self.device_ip,
            redis=self._redis,
            client_logger=False
        )
        
        global _nao_stub_active
        
        # Start component manager if not already running
        if not _nao_stub_active:
            # Create manager with both Desktop and Stub components
            stub_components = [
                # Desktop components
                DesktopMicrophoneSensor,
                DesktopCameraSensor,
                DesktopSpeakersActuator,
                # Stub components (use custom TTS instead of Desktop TTS)
                NaoStubTTSActuator,
                NaoStubMotionActuator,
                NaoStubMotionRecorderActuator,
                NaoStubStiffnessActuator,
                NaoStubAutonomousActuator,
                NaoStubLEDsActuator,
                NaoStubButtonsSensor,
                NaoStubTrackerActuator,
                NaoStubLookAtActuator,
            ]
            
            self.manager = SICComponentManager(
                stub_components,
                client_id=utils.get_ip_adress(),
                auto_serve=False,
                name="NaoStub"
            )
            
            def managed_serve():
                try:
                    self.manager.serve()
                finally:
                    # Ensure cleanup happens even if serve exits unexpectedly
                    self.manager.stop_component_manager()
            
            # Run serve in a thread
            self.thread = threading.Thread(
                target=managed_serve,
                name="NaoStubComponentManager-singleton",
                daemon=True
            )
            self.thread.start()
            
            _nao_stub_active = True
        
        self.logger.info("NaoStub initialized - using Desktop sensors/actuators with NAO interface")
    
    # Desktop-backed properties (actual functionality)
    @property
    def top_camera(self):
        """Top camera (maps to Desktop camera)."""
        return self._get_connector(DesktopCamera)
    
    @property
    def bottom_camera(self):
        """Bottom camera (maps to Desktop camera - same as top)."""
        return self._get_connector(DesktopCamera)
    
    @property
    def mic(self):
        """Microphone (maps to Desktop microphone)."""
        return self._get_connector(DesktopMicrophone)
    
    @property
    def speaker(self):
        """Speaker (maps to Desktop speakers)."""
        return self._get_connector(DesktopSpeakers)
    
    @property
    def tts(self):
        """Text-to-speech (uses stub TTS with actual pyttsx3 functionality)."""
        return self._get_connector(NaoStubTTS)
    
    # Stub properties (logging only)
    @property
    def motion(self):
        """Motion actuator (stub - logs actions)."""
        return self._get_connector(NaoStubMotion)
    
    @property
    def motion_record(self):
        """Motion recorder (stub - logs actions)."""
        return self._get_connector(NaoStubMotionRecorder)
    
    @property
    def stiffness(self):
        """Stiffness actuator (stub - logs actions)."""
        return self._get_connector(NaoStubStiffness)
    
    @property
    def autonomous(self):
        """Autonomous behavior (stub - logs actions)."""
        return self._get_connector(NaoStubAutonomous)
    
    @property
    def leds(self):
        """LED actuator (stub - logs actions)."""
        return self._get_connector(NaoStubLEDs)
    
    @property
    def buttons(self):
        """Button sensor (stub - logs registrations)."""
        return self._get_connector(NaoStubButtons)
    
    @property
    def tracker(self):
        """Tracker actuator (stub - logs actions)."""
        return self._get_connector(NaoStubTracker)
    
    @property
    def look_at(self):
        """Look-at actuator (stub - logs actions)."""
        return self._get_connector(NaoStubLookAt)
    
    def motion_streaming(self, input_source=None):
        """
        Motion streaming (stub - logs action).
        
        Args:
            input_source: The input source for motion streaming (optional).
        
        Returns:
            None - motion streaming not supported in stub.
        """
        self.logger.info("NaoStub.motion_streaming: Streaming requested (stub - no actual streaming)")
        self.logger.warning("Motion streaming is not supported in NaoStub")
        return None

