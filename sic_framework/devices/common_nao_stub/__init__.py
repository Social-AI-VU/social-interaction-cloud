"""
NAO stub components - provides the same interface as the real NAO robot but uses 
Desktop sensors/actuators where possible. NAO-specific actuators are stubbed with logging.
"""

from .nao_stub_motion import (
    NaoStubMotion,
    NaoStubMotionRecorder,
    NaoStubMotionActuator,
    NaoStubMotionRecorderActuator,
)
from .nao_stub_tts import NaoStubTTS, NaoStubTTSActuator
from .nao_stub_stiffness import NaoStubStiffness, NaoStubStiffnessActuator
from .nao_stub_autonomous import NaoStubAutonomous, NaoStubAutonomousActuator
from .nao_stub_leds import NaoStubLEDs, NaoStubLEDsActuator
from .nao_stub_buttons import NaoStubButtons, NaoStubButtonsSensor
from .nao_stub_tracker import (
    NaoStubTracker,
    NaoStubLookAt,
    NaoStubTrackerActuator,
    NaoStubLookAtActuator,
)

__all__ = [
    # Connectors
    'NaoStubMotion',
    'NaoStubMotionRecorder',
    'NaoStubTTS',
    'NaoStubStiffness',
    'NaoStubAutonomous',
    'NaoStubLEDs',
    'NaoStubButtons',
    'NaoStubTracker',
    'NaoStubLookAt',
    # Actuators/Sensors
    'NaoStubMotionActuator',
    'NaoStubMotionRecorderActuator',
    'NaoStubTTSActuator',
    'NaoStubStiffnessActuator',
    'NaoStubAutonomousActuator',
    'NaoStubLEDsActuator',
    'NaoStubButtonsSensor',
    'NaoStubTrackerActuator',
    'NaoStubLookAtActuator',
]

