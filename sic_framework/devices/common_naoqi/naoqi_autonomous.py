from sic_framework import (
    SICActuator,
    SICComponentManager,
    SICConfMessage,
    SICMessage,
    SICRequest,
    utils,
)
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi


class NaoBlinkingRequest(SICRequest):
    """
    Request to enable or disable autonomous blinking.

    :param bool value: True to enable, False to disable autonomous blinking.
    """

    def __init__(self, value):
        super(NaoBlinkingRequest, self).__init__()
        self.value = value


class NaoBackgroundMovingRequest(SICRequest):
    """
    Request to enable or disable autonomous background movement.

    :param bool value: True to enable, False to disable background movement.
    """

    def __init__(self, value):
        super(NaoBackgroundMovingRequest, self).__init__()
        self.value = value


class NaoListeningMovementRequest(SICRequest):
    """
    Request to enable or disable listening movements (small motions indicating attention).

    :param bool value: True to enable, False to disable listening movements.
    """

    def __init__(self, value):
        super(NaoListeningMovementRequest, self).__init__()
        self.value = value


class NaoSpeakingMovementRequest(SICRequest):
    """
    Request to enable or disable autonomous speaking movements.

    :param bool value: True to enable, False to disable.
    :param str mode: Speaking movement mode ("random" or "contextual").
    :raises ValueError: If mode is not one of the supported options. see http://doc.aldebaran.com/2-5/naoqi/interaction/autonomousabilities/alspeakingmovement.html#speaking-movement-mode
    """

    def __init__(self, value, mode=None):
        super(NaoSpeakingMovementRequest, self).__init__()
        self.value = value
        self.mode = mode


class NaoRestRequest(SICRequest):


    pass


class NaoWakeUpRequest(SICRequest):


    pass

class NaoSetAutonomousLifeRequest(SICRequest):
    """
    Request to set the state of the Autonomous Life module.

    For further details, see: http://doc.aldebaran.com/2-5/ref/life/state_machine_management.html#autonomouslife-states

    :param str state: Target state ("solitary", "interactive", "safeguard", or "disabled").
    """

    def __init__(self, state="solitary"):
        super(NaoSetAutonomousLifeRequest, self).__init__()
        self.state = state


class NaoBasicAwarenessRequest(SICRequest):
    """
    Request to enable or disable basic awareness and configure its parameters.

    :param bool value: True to enable, False to disable basic awareness.
    :param list[tuple[str, bool]] stimulus_detection: Optional list of (stimulus_name, enable) tuples.
    :param str engagement_mode: Engagement mode setting.
    :param str tracking_mode: Tracking mode setting.
    """

    def __init__(
        self, value, stimulus_detection=None, engagement_mode=None, tracking_mode=None
    ):
        super(NaoBasicAwarenessRequest, self).__init__()
        self.value = value
        self.stimulus_detection = stimulus_detection if stimulus_detection else []
        self.engagement_mode = engagement_mode
        self.tracking_mode = tracking_mode


class NaoqiAutonomousActuator(SICActuator):
    """
    Actuator managing NAOqi autonomous abilities.

    Provides an interface for enabling or disabling autonomous features like blinking, awareness, and background movements, as well as wakeUp and rest actions.

    :ivar qi.Session session: Connection to the NAOqi framework.
    """

    def __init__(self, *args, **kwargs):
        super(NaoqiAutonomousActuator, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        # Connect to AL proxies
        self.blinking = self.session.service("ALAutonomousBlinking")
        self.background_movement = self.session.service("ALBackgroundMovement")
        self.basic_awareness = self.session.service("ALBasicAwareness")
        self.listening_movement = self.session.service("ALListeningMovement")
        self.speaking_movement = self.session.service("ALSpeakingMovement")
        self.autonomous_life = self.session.service("ALAutonomousLife")
        self.motion = self.session.service("ALMotion")

    @staticmethod
    def get_conf():
        return SICConfMessage()

    @staticmethod
    def get_inputs():
        return [
            NaoBlinkingRequest,
            NaoBackgroundMovingRequest,
            NaoBasicAwarenessRequest,
            NaoListeningMovementRequest,
            NaoSpeakingMovementRequest,
            NaoWakeUpRequest,
            NaoRestRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, message):
        """
        Execute the given autonomous ability request.

        :param SICRequest message: Request specifying which autonomous ability to adjust.
        :returns: Acknowledgement message after execution.
        :rtype: SICMessage
        :raises Exception: If a requested service or mode is invalid.
        """
        if message == NaoRestRequest:
            self.motion.rest()
        elif message == NaoWakeUpRequest:
            self.motion.wakeUp()
        elif message == NaoBlinkingRequest:
            self.blinking.setEnabled(message.value)
        elif message == NaoBackgroundMovingRequest:
            self.background_movement.setEnabled(message.value)
        elif message == NaoListeningMovementRequest:
            self.listening_movement.setEnabled(message.value)
        elif message == NaoSpeakingMovementRequest:
            self.speaking_movement.setEnabled(message.value)
            if message.mode:
                self.speaking_movement.setMode(message.mode)
        elif message == NaoSetAutonomousLifeRequest:
            self.autonomous_life.setState(message.state)
        elif message == NaoBasicAwarenessRequest:
            self.basic_awareness.setEnabled(message.value)
            for name, val in message.stimulus_detection:
                self.basic_awareness.setStimulusDetectionEnabled(name, val)
            if message.engagement_mode:
                self.basic_awareness.setEngagementMode(message.engagement_mode)
            if message.tracking_mode:
                self.basic_awareness.setTrackingMode(message.tracking_mode)

        return SICMessage()

    def stop(self, *args):
        """
        Stop the actuator and close the NAOqi session.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiAutonomousActuator, self).stop()


class NaoqiAutonomous(SICConnector):
    component_class = NaoqiAutonomousActuator


if __name__ == "__main__":
    SICComponentManager([NaoqiAutonomousActuator])
