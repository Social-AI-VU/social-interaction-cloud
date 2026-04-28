from reachy_mini.utils import create_head_pose

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.utils import is_sic_instance


class ReachyMiniMotionConf(SICConfMessage):
    pass


class ReachyMiniHeadRequest(SICRequest):
    """Move Reachy Mini's head to a target pose.

    Translation values are in millimeters when mm=True, meters otherwise.
    Rotation values are in degrees when degrees=True, radians otherwise.

    :param x: Translation along X axis.
    :param y: Translation along Y axis.
    :param z: Translation along Z axis.
    :param roll: Rotation around X axis.
    :param pitch: Rotation around Y axis.
    :param yaw: Rotation around Z axis.
    :param duration: Movement duration in seconds.
    :param method: Interpolation method ("linear", "minjerk", "ease_in_out", "cartoon").
    :param degrees: Whether rotation values are in degrees.
    :param mm: Whether translation values are in millimeters.
    """

    def __init__(self, x=0, y=0, z=0, roll=0, pitch=0, yaw=0,
                 duration=1.0, method="minjerk", degrees=True, mm=True):
        super(ReachyMiniHeadRequest, self).__init__()
        self.x = x
        self.y = y
        self.z = z
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.duration = duration
        self.method = method
        self.degrees = degrees
        self.mm = mm


class ReachyMiniAntennaRequest(SICRequest):
    """Move Reachy Mini's antennas.

    :param right: Right antenna angle in radians.
    :param left: Left antenna angle in radians.
    :param duration: Movement duration in seconds.
    :param method: Interpolation method.
    """

    def __init__(self, right=0.0, left=0.0, duration=0.5, method="minjerk"):
        super(ReachyMiniAntennaRequest, self).__init__()
        self.right = right
        self.left = left
        self.duration = duration
        self.method = method


class ReachyMiniBodyYawRequest(SICRequest):
    """Rotate Reachy Mini's body around the vertical axis.

    :param yaw: Target yaw angle in radians.
    :param duration: Movement duration in seconds.
    :param method: Interpolation method.
    """

    def __init__(self, yaw=0.0, duration=1.0, method="minjerk"):
        super(ReachyMiniBodyYawRequest, self).__init__()
        self.yaw = yaw
        self.duration = duration
        self.method = method


class ReachyMiniFullMotionRequest(SICRequest):
    """Combined motion command for head, antennas, and body.

    :param head: 4x4 pose matrix (numpy array) or None.
    :param antennas: [right, left] angles in radians or None.
    :param body_yaw: Body yaw in radians or None.
    :param duration: Movement duration in seconds.
    :param method: Interpolation method.
    """

    def __init__(self, head=None, antennas=None, body_yaw=None,
                 duration=1.0, method="minjerk"):
        super(ReachyMiniFullMotionRequest, self).__init__()
        self.head = head
        self.antennas = antennas
        self.body_yaw = body_yaw
        self.duration = duration
        self.method = method


class ReachyMiniSetTargetRequest(SICRequest):
    """Instant (non-interpolated) position command for real-time control.

    :param head: 4x4 pose matrix (numpy array) or None.
    :param antennas: [right, left] angles in radians or None.
    :param body_yaw: Body yaw in radians or None.
    """

    def __init__(self, head=None, antennas=None, body_yaw=None):
        super(ReachyMiniSetTargetRequest, self).__init__()
        self.head = head
        self.antennas = antennas
        self.body_yaw = body_yaw


class ReachyMiniMotionActuator(SICActuator):
    """Controls Reachy Mini head, antenna, and body motion."""

    def __init__(self, *args, **kwargs):
        super(ReachyMiniMotionActuator, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance

    @staticmethod
    def get_conf():
        return ReachyMiniMotionConf()

    @staticmethod
    def get_inputs():
        return [
            ReachyMiniHeadRequest,
            ReachyMiniAntennaRequest,
            ReachyMiniBodyYawRequest,
            ReachyMiniFullMotionRequest,
            ReachyMiniSetTargetRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        try:
            if is_sic_instance(request, ReachyMiniHeadRequest):
                self._move_head(request)
            elif is_sic_instance(request, ReachyMiniAntennaRequest):
                self._move_antennas(request)
            elif is_sic_instance(request, ReachyMiniBodyYawRequest):
                self._move_body(request)
            elif is_sic_instance(request, ReachyMiniFullMotionRequest):
                self._move_full(request)
            elif is_sic_instance(request, ReachyMiniSetTargetRequest):
                self._set_target(request)
        except Exception as e:
            self.logger.warning("Motion command failed: {}".format(e))

        return SICMessage()

    def _move_head(self, request):
        pose = create_head_pose(
            x=request.x, y=request.y, z=request.z,
            roll=request.roll, pitch=request.pitch, yaw=request.yaw,
            degrees=request.degrees, mm=request.mm,
        )
        self.mini.goto_target(
            head=pose,
            duration=request.duration,
            method=request.method,
            body_yaw=None,
        )

    def _move_antennas(self, request):
        self.mini.goto_target(
            antennas=[request.right, request.left],
            duration=request.duration,
            method=request.method,
            body_yaw=None,
        )

    def _move_body(self, request):
        self.mini.goto_target(
            body_yaw=request.yaw,
            duration=request.duration,
            method=request.method,
        )

    def _move_full(self, request):
        self.mini.goto_target(
            head=request.head,
            antennas=request.antennas,
            body_yaw=request.body_yaw,
            duration=request.duration,
            method=request.method,
        )

    def _set_target(self, request):
        self.mini.set_target(
            head=request.head,
            antennas=request.antennas,
            body_yaw=request.body_yaw,
        )

    def _cleanup(self):
        pass


class ReachyMiniMotion(SICConnector):
    component_class = ReachyMiniMotionActuator
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniMotionActuator], component_group="ReachyMini")
