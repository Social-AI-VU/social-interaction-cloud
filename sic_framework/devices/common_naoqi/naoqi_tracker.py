from sic_framework import utils
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest

if utils.PYTHON_VERSION_IS_2:
    import qi


class StartTrackRequest(SICRequest):
    """
    Request to register a target and start tracking it.
    """
    def __init__(
        self, target_name, size, mode="Head", effector="None", move_rel_position=None
    ):
        """
        Initialize a start-tracking request.

        See: http://doc.aldebaran.com/2-5/naoqi/trackers/index.html

        :param target_name: Name of the object to track (e.g., RedBall, Face).
        :param float size: Target size in meters (e.g., ball diameter or face width).
        :param str mode: Tracking mode default mode is "Head", other options: "WholeBody", "Move". See http://doc.aldebaran.com/2-5/naoqi/trackers/index.html#tracking-modes
        :param str effector: Effector to use ("Arms", "LArm", "RArm", or "None").
        :param move_rel_position: Set the robot position relative to target in Move mode
        """
        super(StartTrackRequest, self).__init__()
        self.target_name = target_name
        self.size = size
        self.mode = mode
        self.effector = effector
        self.move_rel_position = move_rel_position


class StopAllTrackRequest(SICRequest):
    """
    Request to stop tracking and unregister all targets.
    """

    pass


class RemoveTargetRequest(SICRequest):
    def __init__(self, target_name):
        """
        Initialize a request to remove a specific tracking target.

        :param str target_name: Name of the target to stop tracking.
        """
        super(RemoveTargetRequest, self).__init__()
        self.target_name = target_name


class RemoveAllTargetsRequest(SICRequest):
    """
    Request to remove all tracking targets.
    """

    pass


class NaoqiTrackerActuator(SICActuator):
    def __init__(self, *args, **kwargs):
        super(NaoqiTrackerActuator, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        self.tracker = self.session.service("ALTracker")
        self.posture = self.session.service("ALRobotPosture")
        self.motion = self.session.service("ALMotion")

    @staticmethod
    def get_conf():
        """
        Return the default configuration for this actuator.

        :returns: Generic configuration message.
        :rtype: SICConfMessage
        """
        return SICConfMessage()

    @staticmethod
    def get_inputs():
        return [
            StartTrackRequest,
            StopAllTrackRequest,
            RemoveTargetRequest,
            RemoveAllTargetsRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        if request == StartTrackRequest:
            self.logger.info("Start TrackRequest for {}".format(request.target_name))
            # add target to track
            self.tracker.registerTarget(request.target_name, request.size)
            # set mode
            self.tracker.setMode(request.mode)
            # for Move and WholeBody modes, the robot must be in a standing posture, ready to move
            if request.mode == "Move" or request.mode == "WholeBody":
                self.posture.goToPosture("Stand", 0.5)
            if request.mode == "Move":
                if request.move_rel_position is None:
                    self.logger.info(
                        "The relative position is not passed, "
                        "the value is either the default [0, 0, 0, 0, 0, 0] if never set "
                        "or the previous value passed"
                    )
                    self.logger.info(
                        "Get relative position {}".format(
                            self.tracker.getRelativePosition()
                        )
                    )
                else:
                    self.tracker.setRelativePosition(request.move_rel_position)
                    self.logger.info(
                        "Get relative position {}".format(
                            self.tracker.getRelativePosition()
                        )
                    )
            # set effector
            self.tracker.setEffector(request.effector)
            # start tracker
            self.tracker.track(request.target_name)
        elif request == StopAllTrackRequest:
            self.logger.info("Stop TrackRequest")
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()
            self.tracker.setEffector("None")
            self.posture.goToPosture("Stand", 0.5)
            self.motion.rest()
        elif request == RemoveTargetRequest:
            self.logger.info("Unregister target {}".format(request.target_name))
            self.tracker.unregisterTarget(request.target_name)
        elif request == RemoveAllTargetsRequest:
            self.tracker.unregisterAllTargets()

        return SICMessage()

    def stop(self, *args):
        """
        Stop the tracker actuator.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiTrackerActuator, self).stop()


class NaoqiTracker(SICConnector):
    component_class = NaoqiTrackerActuator


if __name__ == "__main__":
    SICComponentManager([NaoqiTrackerActuator])
