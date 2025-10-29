import numpy as np
import six

from sic_framework import SICComponentManager, SICService, utils
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class NaoqiMoveRequest(SICRequest):
    """
    Request to move with given velocities in the robot frame.

    :param float x: Velocity along X (forward) in m/s. Negative for backward.
    :param float y: Velocity along Y (left) in m/s. Positive to move left.
    :param float theta: Rotational velocity around Z in rad/s. Negative for clockwise.
    """

    def __init__(self, x, y, theta):
        super(NaoqiMoveRequest, self).__init__()
        self.x = x
        self.y = y
        self.theta = theta


class NaoqiMoveToRequest(NaoqiMoveRequest):
    """
    Request to move to a relative pose (x, y, theta) from the robot frame.

    :ivar float x: Distance along X (forward) in meters.
    :ivar float y: Distance along Y (left) in meters.
    :ivar float theta: Rotation around Z in radians [-3.1415, 3.1415].
    """

    pass


class NaoqiMoveTowardRequest(NaoqiMoveRequest):
    """
    Request to move with normalized velocities (unitless in [-1, 1]).

    :ivar float x: Normalized velocity along X. +1 and -1 correspond to the maximum velocity in the forward and backward directions, respectively.
    :ivar float y: Normalized velocity along Y. +1 and -1 correspond to the maximum velocity in the left and right directions, respectively.
    :ivar float theta: Normalized rotational velocity around Z.  +1 and -1 correspond to the maximum velocity in the counterclockwise and clockwise directions, respectively.
    """

    pass


class NaoqiIdlePostureRequest(SICRequest):
    """
    Control idle behaviour. This is the robot behaviour when no user commands are sent.
    There are three idle control modes:
          No idle control: in this mode, when no user command is sent to the robot, it does not move.
          Idle posture control: in this mode, the robot automatically comes back to a reference posture, then stays at that posture until a user command is sent.
          Breathing control: in this mode, the robot plays a breathing animation in loop.

        See also NaoqiIdlePostureRequest.

        http://doc.aldebaran.com/2-4/naoqi/motion/idle.html
    """

    def __init__(self, joints, value):
        """
        Initialize an idle posture request.

        Chains: "Body", "Legs", "Arms", "LArm", "RArm", or "Head".

        :param str joints: Chain name (e.g., "Body", "LArm").
        :param bool value: True to enable, False to disable.
        :raises AssertionError: If joints is empty.
        """
        super(NaoqiIdlePostureRequest, self).__init__()
        self.joints = joints
        self.value = value


class NaoqiBreathingRequest(SICRequest):
    """
    Control idle Breathing. This is the robot behaviour when no user commands are sent.
    There are three idle control modes:
          No idle control: in this mode, when no user command is sent to the robot, it does not move.
          Idle posture control: in this mode, the robot automatically comes back to a reference posture, then stays at that posture until a user command is sent.
          Breathing control: in this mode, the robot plays a breathing animation in loop.

        See also NaoqiBreathingRequest.

        http://doc.aldebaran.com/2-4/naoqi/motion/idle.html
    """
    def __init__(self, joints, value):
        """
        Initialize a breathing request.
        
        :param str joints: Chain name (e.g., "Body", "Head").
        :param bool value: True to enable, False to disable.
        """
        super(NaoqiBreathingRequest, self).__init__()
        self.joints = joints
        self.value = value


class NaoPostureRequest(SICRequest):
    """
    Request to go to a predefined NAO posture.

    Options: "Crouch", "LyingBack", "LyingBelly", "Sit", "SitRelax", "Stand", "StandInit", "StandZero".
    """

    def __init__(self, target_posture, speed=0.4):
        """
        Create a posture request.

        :param str target_posture: Target posture name.
        :param float speed: Interpolation speed fraction [0-1].
        :raises AssertionError: If `target_posture` is not a supported option.
        """
        super(NaoPostureRequest, self).__init__()
        options = [
            "Crouch",
            "LyingBack",
            "LyingBelly",
            "Sit",
            "SitRelax",
            "Stand",
            "StandInit",
            "StandZero",
        ]
        assert target_posture in options, "Invalid pose {}".format(target_posture)
        self.target_posture = target_posture
        self.speed = speed


class NaoqiAnimationRequest(SICRequest):
    """
    Request to play a predefined animation via ALAnimationPlayer.

    See: http://doc.aldebaran.com/2-4/naoqi/motion/alanimationplayer-advanced.html#animationplayer-list-behaviors-nao
    """

    def __init__(self, animation_path):
        """
        Initialize an animation request.

        :param str animation_path: Animation behavior name or full path.
        """
        super(NaoqiAnimationRequest, self).__init__()
        self.animation_path = animation_path


class NaoqiSmartStiffnessRequest(SICRequest):
    """
    Request to enable or disable Smart Stiffness reflex for all joints.

    See: http://doc.aldebaran.com/2-4/naoqi/motion/reflexes-smart-stiffness.html
    """
    def __init__(self, enable=True):
        """
        Initialize a Smart Stiffness request.

        :param bool enable: True to enable, False to disable.
        """
        super(NaoqiSmartStiffnessRequest, self).__init__()
        self.enable = enable


class PepperPostureRequest(SICRequest):
    """
    Request to go to a predefined Pepper posture.

    Options: "Crouch", "Stand", "StandInit", "StandZero".
    """

    def __init__(self, target_posture, speed=0.4):
        """
        Create a Pepper posture request.

        :param str target_posture: Target posture name.
        :param float speed: Interpolation speed fraction [0-1].
        :raises AssertionError: If `target_posture` is not a supported option.
        """
        super(PepperPostureRequest, self).__init__()
        options = ["Crouch", "Stand", "StandInit", "StandZero"]
        assert target_posture in options, "Invalid pose {}".format(target_posture)
        self.target_posture = target_posture
        self.speed = speed


class NaoqiMotionActuator(SICActuator):
    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        self.motion = self.session.service("ALMotion")
        self.posture = self.session.service("ALRobotPosture")
        self.animation = self.session.service("ALAnimationPlayer")

    @staticmethod
    def get_inputs():
        return [
            NaoPostureRequest,
            NaoqiMoveRequest,
            NaoqiMoveToRequest,
            NaoqiMoveTowardRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        if request == NaoPostureRequest or request == PepperPostureRequest:
            self.goToPosture(request)
        if request == NaoqiAnimationRequest:
            self.run_animation(request)
        elif request == NaoqiIdlePostureRequest:
            self.motion.setIdlePostureEnabled(request.joints, request.value)
        elif request == NaoqiBreathingRequest:
            self.motion.setBreathEnabled(request.joints, request.value)
        elif request == NaoqiSmartStiffnessRequest:
            self.motion.setSmartStiffnessEnabled(request.enable)
            # sometimes it doesn't work in the first try, so doueble check
            if self.motion.getSmartStiffnessEnabled() != request.enable:
                self.motion.setSmartStiffnessEnabled(request.enable)
        elif request == NaoqiMoveRequest:
            self.move(request)
        elif request == NaoqiMoveToRequest:
            self.moveTo(request)
        elif request == NaoqiMoveTowardRequest:
            self.moveToward(request)

        return SICMessage()

    def goToPosture(self, motion):
        self.posture.goToPosture(motion.target_posture, motion.speed)

    def run_animation(self, motion):
        self.animation.run(motion.animation_path)

    def move(self, motion):
        self.motion.move(motion.x, motion.y, motion.theta)

    def moveTo(self, motion):
        self.motion.moveTo(motion.x, motion.y, motion.theta)

    def moveToward(self, motion):
        self.motion.moveToward(motion.x, motion.y, motion.theta)

    def stop(self, *args):
        """
        Stop the Naoqi motion actuator.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiMotionActuator, self).stop()


class NaoqiMotion(SICConnector):
    component_class = NaoqiMotionActuator


if __name__ == "__main__":
    SICComponentManager([NaoqiMotionActuator])
