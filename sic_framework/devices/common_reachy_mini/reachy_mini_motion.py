import threading

from reachy_mini.utils import create_head_pose

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.utils import is_sic_instance
from sic_framework.devices.common_reachy_mini.reachy_mini_autonomous import (
    ReachyMiniAutonomousActuator,
)


DEFAULT_ANIMATION_LIBRARIES = {
    "emotions": "pollen-robotics/reachy-mini-emotions-library",
    "dances": "pollen-robotics/reachy-mini-dances-library",
}


class ReachyMiniMotionConf(SICConfMessage):
    """
    :param animation_libraries: Mapping of library name to the Hugging Face
        dataset holding its recorded moves. Defaults to Pollen's emotions and
        dances libraries; add your own recorded-move datasets here.
    :param preload_animations: Download/load the libraries in the background
        on start, so the first animation request does not have to wait.
    """

    def __init__(self, animation_libraries=None, preload_animations=True):
        super(ReachyMiniMotionConf, self).__init__()
        if animation_libraries is None:
            animation_libraries = dict(DEFAULT_ANIMATION_LIBRARIES)
        self.animation_libraries = animation_libraries
        self.preload_animations = preload_animations


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


class ReachyMiniAnimationRequest(SICRequest):
    """Play a recorded animation, such as an emotion or a dance, by name.

    Either the short or full name works, like ``NaoqiAnimationRequest``:

    - ``"cheerful1"``, ``"sad1"``, ``"simple_nod"``: searched in all libraries
    - ``"emotions/cheerful1"``, ``"dances/simple_nod"``: from that library

    Use :class:`ReachyMiniGetAnimationsRequest` to list the available names.
    The request returns once the animation has finished.

    :param animation_name: The animation name or path.
    :param sound: Play the sound that comes with the animation, if any
        (most emotions have one).
    """

    def __init__(self, animation_name, sound=True):
        super(ReachyMiniAnimationRequest, self).__init__()
        self.animation_name = animation_name
        self.sound = sound


class ReachyMiniGetAnimationsRequest(SICRequest):
    """List the animations available to :class:`ReachyMiniAnimationRequest`.

    Replies with a :class:`ReachyMiniAnimationsMessage`.
    """

    pass


class ReachyMiniAnimationsMessage(SICMessage):
    """Available animations per library.

    :param animations: Dict of library name to a sorted list of animation names,
        e.g. ``{"emotions": ["amazed1", ...], "dances": ["chicken_peck", ...]}``.
    """

    def __init__(self, animations):
        super(ReachyMiniAnimationsMessage, self).__init__()
        self.animations = animations


class ReachyMiniMotionActuator(SICActuator):
    """Controls Reachy Mini head, antenna, and body motion."""

    def __init__(self, *args, **kwargs):
        super(ReachyMiniMotionActuator, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance

        self._animation_libraries = {}
        self._animation_lock = threading.Lock()
        if self.params.preload_animations:
            threading.Thread(
                target=self._preload_animations, name="ReachyMiniAnimationPreload", daemon=True,
            ).start()

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
            ReachyMiniAnimationRequest,
            ReachyMiniGetAnimationsRequest,
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
            elif is_sic_instance(request, ReachyMiniAnimationRequest):
                self._play_animation(request)
            elif is_sic_instance(request, ReachyMiniGetAnimationsRequest):
                return ReachyMiniAnimationsMessage(self._list_animations())
        except Exception as e:
            self.logger.warning("Motion command failed: {}".format(e))

        return SICMessage()

    def _move_head(self, request):
        pose = create_head_pose(
            x=request.x, y=request.y, z=request.z,
            roll=request.roll, pitch=request.pitch, yaw=request.yaw,
            degrees=request.degrees, mm=request.mm,
        )
        self._goto(head=pose, duration=request.duration, method=request.method)

    def _move_antennas(self, request):
        self._goto(
            antennas=[request.right, request.left],
            duration=request.duration,
            method=request.method,
        )

    def _move_body(self, request):
        self._goto(
            body_yaw=request.yaw,
            duration=request.duration,
            method=request.method,
        )

    def _move_full(self, request):
        self._goto(
            head=request.head,
            antennas=request.antennas,
            body_yaw=request.body_yaw,
            duration=request.duration,
            method=request.method,
        )

    def _set_target(self, request):
        autonomous = ReachyMiniAutonomousActuator.get_instance()
        if autonomous is not None:
            autonomous.set_target(head=request.head, antennas=request.antennas,
                                  body_yaw=request.body_yaw)
        else:
            self.mini.set_target(head=request.head, antennas=request.antennas,
                                 body_yaw=request.body_yaw)

    def _goto(self, head=None, antennas=None, body_yaw=None, duration=1.0, method="minjerk"):
        """Run an interpolated move, blended with the autonomous movement when it is running."""
        autonomous = ReachyMiniAutonomousActuator.get_instance()
        if autonomous is not None:
            autonomous.goto(head=head, antennas=antennas, body_yaw=body_yaw,
                            duration=duration, method=method)
        else:
            self.mini.goto_target(head=head, antennas=antennas, body_yaw=body_yaw,
                                  duration=duration, method=method)

    def _play_animation(self, request):
        move = self._find_animation(request.animation_name)
        sound_path = move.sound_path if request.sound else None
        autonomous = ReachyMiniAutonomousActuator.get_instance()
        if autonomous is not None:
            autonomous.play_animation(move, sound_path=sound_path)
        else:
            self.mini.play_move(move, initial_goto_duration=0.5, sound=request.sound)

    def _find_animation(self, name):
        """Resolve a short (``"sad1"``) or full (``"emotions/sad1"``) name to a recorded move."""
        library_name, _, short_name = name.rpartition("/")
        if library_name:
            if library_name not in self.params.animation_libraries:
                raise ValueError("Unknown animation library '{}'. Available: {}".format(
                    library_name, sorted(self.params.animation_libraries)))
            candidates = [library_name]
        else:
            candidates = list(self.params.animation_libraries)

        for candidate in candidates:
            library = self._get_animation_library(candidate)
            if short_name in library.moves:
                return library.get(short_name)
        raise ValueError(
            "Unknown animation '{}'. Use ReachyMiniGetAnimationsRequest to list the "
            "available animations.".format(name))

    def _list_animations(self):
        return {
            name: sorted(self._get_animation_library(name).list_moves())
            for name in self.params.animation_libraries
        }

    def _get_animation_library(self, name):
        """Load a library on first use; downloads it from Hugging Face if not cached yet."""
        from reachy_mini.motion.recorded_move import RecordedMoves

        with self._animation_lock:
            if name not in self._animation_libraries:
                dataset = self.params.animation_libraries[name]
                self.logger.info("Loading animation library '{}' ({})".format(name, dataset))
                self._animation_libraries[name] = RecordedMoves(dataset)
            return self._animation_libraries[name]

    def _preload_animations(self):
        for name in self.params.animation_libraries:
            try:
                self._get_animation_library(name)
            except Exception as e:
                self.logger.warning("Could not load animation library '{}': {}".format(name, e))

    def _cleanup(self):
        pass


class ReachyMiniMotion(SICConnector):
    component_class = ReachyMiniMotionActuator
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniMotionActuator], component_group="ReachyMini")
