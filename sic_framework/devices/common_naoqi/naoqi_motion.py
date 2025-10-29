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
    Make the robot move at the given velocity, in the specified direction vector in m/s, where theta indicates rotation.
    x - velocity along X-axis (forward), in meters per second. Use negative values for backward motion
    y - velocity along Y-axis (side), in meters per second. Use positive values to go to the left
    theta - velocity around Z-axis, in radians per second. Use negative values to turn clockwise.
    """

    def __init__(self, x, y, theta):
        super(NaoqiMoveRequest, self).__init__()
        self.x = x
        self.y = y
        self.theta = theta


class NaoqiMoveToRequest(NaoqiMoveRequest):
    """
    Make the robot move to a given point in space relative to the robot, where theta indicates rotation.
    x -  Distance along the X axis (forward) in meters.
    y - Distance along the Y axis (side) in meters.
    theta - Rotation around the Z axis in radians [-3.1415 to 3.1415].
    """

    pass


class NaoqiMoveTowardRequest(NaoqiMoveRequest):
    """
    Makes the robot move at the given normalized velocity.
    x - normalized, unitless, velocity along X-axis. +1 and -1 correspond to the maximum velocity in the forward and backward directions, respectively.
    y - normalized, unitless, velocity along Y-axis. +1 and -1 correspond to the maximum velocity in the left and right directions, respectively.
    theta - normalized, unitless, velocity around Z-axis. +1 and -1 correspond to the maximum velocity in the counterclockwise and clockwise directions, respectively.
    """

    def __init__(self, x=0.0, y=0.0, theta=0.0):
        super(NaoqiMoveTowardRequest, self).__init__(x, y, theta)

    def _execute(self, session):
        session.service("ALMotion").moveToward(
            self.x, self.y, self.theta
        )


class NaoqiGetRobotVelocityRequest(SICRequest):
    """Return (vx [m/s], vy [m/s], vth [rad/s]) in the world frame."""
    def _execute(self, session):
        return session.service("ALMotion").getRobotVelocity()


class NaoqiCollisionProtectionRequest(SICRequest):
    """
    Enable / disable Pepper's external-collision protection.
    target in {"Move","Arms","All","LArm","RArm"}
    """
    def __init__(self, target="All", enable=True):
        super(NaoqiCollisionProtectionRequest, self).__init__()
        self.target, self.enable = target, enable

    def _execute(self, session):
        session.service("ALMotion")\
               .setExternalCollisionProtectionEnabled(self.target, self.enable)


class NaoqiMoveArmsEnabledRequest(SICRequest):
    """
    Tell NAOqi's walking controller to (not) move the arms.
    On NAOqi >= 2.4 the method is setMoveArmsEnabled; on older firmware it is
    setWalkArmsEnabled, so we try both.
    """
    def __init__(self, left_enable=False, right_enable=False):
        super(NaoqiMoveArmsEnabledRequest, self).__init__()
        self.left_enable, self.right_enable = left_enable, right_enable

    def _execute(self, session):
        try:  # NAOqi >= 2.4
            session.service("ALMotion")\
                   .setMoveArmsEnabled(self.left_enable, self.right_enable)
        except RuntimeError:  # NAOqi 2.3 / 2.1
            session.service("ALMotion")\
                   .setWalkArmsEnabled(self.left_enable, self.right_enable)


class NaoqiIdlePostureRequest(SICRequest):
    def __init__(self, joints, value):
        """
        Control idle behaviour. This is the robot behaviour when no user commands are sent.
        There are three idle control modes:
          No idle control: in this mode, when no user command is sent to the robot, it does not move.
          Idle posture control: in this mode, the robot automatically comes back to a reference posture, then stays at
                                that posture until a user command is sent.
          Breathing control: in this mode, the robot plays a breathing animation in loop.

        See also NaoqiBreathingRequest.

        http://doc.aldebaran.com/2-4/naoqi/motion/idle.html
        :param joints: The chain name, one of ["Body", "Legs", "Arms", "LArm", "RArm" or "Head"].
        :type joints: str
        :param value: True or False
        :type value: bool
        """
        super(NaoqiIdlePostureRequest, self).__init__()
        self.joints = joints
        self.value = value


class NaoqiBreathingRequest(SICRequest):
    def __init__(self, joints, value):
        """
        Control Breathing behaviour. This is the robot behaviour when no user commands are sent.
        There are three idle control modes:
          No idle control: in this mode, when no user command is sent to the robot, it does not move.
          Idle posture control: in this mode, the robot automatically comes back to a reference posture, then stays at
                                that posture until a user command is sent.
          Breathing control: in this mode, the robot plays a breathing animation in loop.

        See also NaoqiIdlePostureRequest.

        http://doc.aldebaran.com/2-4/naoqi/motion/idle.html
        :param joints: The chain name, one of ["Body", "Legs", "Arms", "LArm", "RArm" or "Head"].
        :type joints: str
        :param value: True or False
        :type value: bool
        """
        super(NaoqiBreathingRequest, self).__init__()
        self.joints = joints
        self.value = value


class NaoPostureRequest(SICRequest):
    """
    Make the robot go to a predefined posture.
    Options:
    ["Crouch", "LyingBack" "LyingBelly", "Sit", "SitRelax", "Stand", "StandInit", "StandZero"]
    """

    def __init__(self, target_posture, speed=0.4):
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
    Make the robot play predefined animation. Either the short or full name as a string will work.
    See: http://doc.aldebaran.com/2-4/naoqi/motion/alanimationplayer-advanced.html#animationplayer-list-behaviors-nao

    Nao Examples:
        animations/Sit/BodyTalk/BodyTalk_1
        animations/Stand/Gestures/Hey_1
        Enthusiastic_4

    Pepper Examples:
        Hey_3
        animations/Stand/Gestures/ShowSky_5
    """

    def __init__(self, animation_path):
        """
        :param animation_path: the animation name or path
        :type animation_path: str
        """
        super(NaoqiAnimationRequest, self).__init__()
        self.animation_path = animation_path


class NaoqiSmartStiffnessRequest(SICRequest):
    """
    Enable or Disable the smart stiffness reflex for all the joints (True by default).
    see: http://doc.aldebaran.com/2-4/naoqi/motion/reflexes-smart-stiffness.html
    """
    def __init__(self, enable=True):
        """
        :param enable: True or False
        :type enable: bool
        """
        super(NaoqiSmartStiffnessRequest, self).__init__()
        self.enable = enable


class PepperPostureRequest(SICRequest):
    """
    Make the robot go to a predefined posture.
    Options:
    ["Crouch", "LyingBack" "LyingBelly", "Sit", "SitRelax", "Stand", "StandInit", "StandZero"]
    """

    def __init__(self, target_posture, speed=0.4):
        super(PepperPostureRequest, self).__init__()
        options = ["Crouch", "Stand", "StandInit", "StandZero"]
        assert target_posture in options, "Invalid pose {}".format(target_posture)
        self.target_posture = target_posture
        self.speed = speed


class NaoqiGetAnglesRequest(SICRequest):
    """
    Request the current angles of specified joints from the robot.

    Args:
        names (list of str): List of joint names to query (e.g., ["LShoulderPitch", "RShoulderRoll"]).
        use_sensors (bool): If True, return the actual sensor values; if False, return the commanded values.

    Returns:
        list of float: The angles (in radians) for the specified joints, in the same order as 'names'.
    """
    def __init__(self, names, use_sensors=True):
        super(NaoqiGetAnglesRequest, self).__init__()
        self.names = names
        self.use_sensors = use_sensors

    def _execute(self, session):
        return session.service("ALMotion").getAngles(self.names, self.use_sensors)


class NaoqiSetAnglesRequest(SICRequest):
    """
    Set the angles of specified joints on the robot.

    Args:
        names (list of str): List of joint names to set (e.g., ["LShoulderPitch", "RShoulderRoll"]).
        angles (list of float): List of target angles (in radians) for the specified joints, in the same order as 'names'.
        speed (float): Fraction of maximum speed to use (0.0 to 1.0). Default is 0.5.
    """
    def __init__(self, names, angles, speed=0.5):
        super(NaoqiSetAnglesRequest, self).__init__()
        self.names = names
        self.angles = angles
        self.speed = speed

    def _execute(self, session):
        return session.service("ALMotion").setAngles(self.names, self.angles, self.speed)


class NaoqiVelocityResponse(SICMessage):
    """Response message containing robot velocity."""
    def __init__(self, x, y, theta):
        super(NaoqiVelocityResponse, self).__init__()
        self.x = x
        self.y = y
        self.theta = theta


class NaoqiAnglesResponse(SICMessage):
    """Response message containing joint angles."""
    def __init__(self, names, angles):
        super(NaoqiAnglesResponse, self).__init__()
        self.names = names
        self.angles = angles


class NaoqiSetAnglesResponse(SICMessage):
    """Response message confirming joint angles were set."""
    def __init__(self, names, angles, speed):
        super(NaoqiSetAnglesResponse, self).__init__()
        self.names = names
        self.angles = angles
        self.speed = speed


class NaoqiMotionActuator(SICActuator):
    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        self.motion = self.session.service("ALMotion")
        self.posture = self.session.service("ALRobotPosture")
        self.animation = self.session.service("ALAnimationPlayer")

    def moveToward(self, motion):
        cfg = getattr(motion, "move_config", None)

        if cfg is not None:            # collision protection / custom options
            self.motion.moveToward(motion.x, motion.y, motion.theta, cfg)
        else:                          # simple 3-argument call
            self.motion.moveToward(motion.x, motion.y, motion.theta)

    @staticmethod
    def get_inputs():
        return [
            NaoPostureRequest,
            NaoqiMoveRequest,
            NaoqiMoveToRequest,
            NaoqiMoveTowardRequest,
            NaoqiGetRobotVelocityRequest,
            NaoqiCollisionProtectionRequest,
            NaoqiGetAnglesRequest,
            NaoqiSetAnglesRequest,
            NaoqiMoveArmsEnabledRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        # locomotion
        if isinstance(request, NaoqiMoveTowardRequest):
            self.moveToward(request)
        elif isinstance(request, NaoqiMoveToRequest):
            self.moveTo(request)
        elif isinstance(request, NaoqiMoveRequest):
            self.move(request)

        # posture & animation
        elif isinstance(request, (NaoPostureRequest, PepperPostureRequest)):
            self.goToPosture(request)
        elif isinstance(request, NaoqiAnimationRequest):
            self.run_animation(request)

        # misc
        elif isinstance(request, NaoqiIdlePostureRequest):
            self.motion.setIdlePostureEnabled(request.joints, request.value)
        elif isinstance(request, NaoqiBreathingRequest):
            self.motion.setBreathEnabled(request.joints, request.value)
        elif isinstance(request, NaoqiSmartStiffnessRequest):
            self.motion.setSmartStiffnessEnabled(request.enable)
            # sometimes it doesn't work in the first try, so double check
            if self.motion.getSmartStiffnessEnabled() != request.enable:
                self.motion.setSmartStiffnessEnabled(request.enable)
        elif isinstance(request, NaoqiGetRobotVelocityRequest):
            return self.getRobotVelocity()
        elif isinstance(request, NaoqiCollisionProtectionRequest):
            self.setCollisionProtection(request)
        elif isinstance(request, NaoqiMoveArmsEnabledRequest):
            self.setMoveArmsEnabled(request)
        elif isinstance(request, NaoqiGetAnglesRequest):
            return self.get_angles(request.names, request.use_sensors)
        elif isinstance(request, NaoqiSetAnglesRequest):
            return self.set_angles(request.names, request.angles, request.speed)

        return SICMessage()

    def goToPosture(self, motion):
        self.posture.goToPosture(motion.target_posture, motion.speed)

    def run_animation(self, motion):
        self.animation.run(motion.animation_path)

    def move(self, motion):
        self.motion.move(motion.x, motion.y, motion.theta)

    def moveTo(self, motion):
        self.motion.moveTo(motion.x, motion.y, motion.theta)

    def getRobotVelocity(self):
        """Get robot velocity and return as a message with x, y, theta attributes."""
        velocity = self.motion.getRobotVelocity()
        # Create a message with the velocity values
        msg = NaoqiVelocityResponse(velocity[0], velocity[1], velocity[2])
        return msg

    def get_angles(self, names, use_sensors=True):
        angles = self.motion.getAngles(names, use_sensors)
        # Create a message with the angles
        msg = NaoqiAnglesResponse(names, angles)
        return msg

    def set_angles(self, names, angles, speed=0.5):
        """Set joint angles and return a confirmation message."""
        self.motion.setAngles(names, angles, speed)
        # Create a response message with the set angles, following the same pattern as get_angles
        msg = NaoqiSetAnglesResponse(names, angles, speed)
        return msg

    def setCollisionProtection(self, request):
        """Set collision protection for the specified target."""
        self.motion.setExternalCollisionProtectionEnabled(request.target, request.enable)

    def setMoveArmsEnabled(self, request):
        """Set whether the walking controller should move the arms."""
        try:  # NAOqi >= 2.4
            self.motion.setMoveArmsEnabled(request.left_enable, request.right_enable)
        except RuntimeError:  # NAOqi 2.3 / 2.1
            self.motion.setWalkArmsEnabled(request.left_enable, request.right_enable)

    def stop(self):
        """
        Stop the NAOqi motion actuator.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiMotionActuator, self).stop()


class NaoqiMotion(SICConnector):
    component_class = NaoqiMotionActuator


if __name__ == "__main__":
    SICComponentManager([NaoqiMotionActuator])