import threading
import time

from sic_framework import (
    SICComponentManager,
    SICConfMessage,
    SICMessage,
    SICRequest,
    utils,
)
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.devices.common_naoqi.common_naoqi_motion import NaoqiMotionTools

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class StartStreaming(SICRequest):
    """
    Request to start streaming joint positions for specified joints.
    """
    def __init__(self, joints):
        """
        Start streaming the positions of the selected joints. For more information see robot documentation:
        For nao: http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains
        For pepper: http://doc.aldebaran.com/2-8/family/pepper_technical/bodyparts_pep.html


        :param joints: One of the robot's "Joint chains" such as ["Body"] or ["LArm", "HeadYaw"]
        :type joints: list[str]
        """
        super(StartStreaming, self).__init__()
        self.joints = joints


class StopStreaming(SICRequest):
    pass


class NaoJointAngles(SICMessage):
    """
    Message carrying joint names and their corresponding angles in radians.
    """
    def __init__(self, joints, angles):
        """
        Create a joint-angle message.

        :param list[str] joints: Joint names in the order of the angles.
        :param list[float] angles: Joint angles in radians.
        """
        self.joints = joints
        self.angles = angles


class NaoMotionStreamerConf(SICConfMessage):
    """
    Configuration for the NAOqi motion streaming service.
    """
    def __init__(
        self,
        stiffness=0.6,
        speed=0.75,
        stream_stiffness=0,
        use_sensors=False,
        samples_per_second=20,
    ):
        """
        Initialize configuration options for motion streaming.

        :param float stiffness: Control how much power the robot should use to reach the given joint angles
        :param float speed: Set the fraction of the maximum speed used to reach the target position.
        :param float stream_stiffness: Control the stiffness of the robot when streaming its joint positions.
        Note: Use stiffness, not stream_stiffness,  to control the stiffness of the robot when consuming a stream of
        joint postions.
        :param bool use_sensors: If true, sensor angles will be returned, otherwise command angles are used.
        :param int samples_per_second: How many times per second the joint positions are sampled.
        """
        SICConfMessage.__init__(self)
        self.stiffness = stiffness
        self.speed = speed
        self.stream_stiffness = stream_stiffness
        self.use_sensors = use_sensors
        self.samples_per_second = samples_per_second


class NaoqiMotionStreamerService(SICComponent, NaoqiMotionTools):
    """
    Stream NAOqi joint angles and process control requests.

    This component connects to a local NAOqi session, exposes start/stop streaming requests,
    and publishes `NaoJointAngles` messages at the requested rate.
    """
    def __init__(self, *args, **kwargs):
        """
        Set up the NAOqi session, motion service, and streaming thread.

        :param Any args: Positional arguments passed to the component base.
        :param Any kwargs: Keyword arguments passed to the component base.
        """
        SICComponent.__init__(self, *args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        NaoqiMotionTools.__init__(self, qi_session=self.session)

        self.motion = self.session.service("ALMotion")

        self.stiffness = 0
        self.samples_per_second = self.params.samples_per_second

        self.do_streaming = threading.Event()

        # A list of joint names (not chains)
        self.joints = self.generate_joint_list(["Body"])

        self.stream_thread = threading.Thread(target=self.stream_joints)
        self.stream_thread.name = self.get_component_name()
        self.stream_thread.start()

    @staticmethod
    def get_conf():
        """
        Return the default configuration for this component.

        :returns: Default configuration instance.
        :rtype: NaoMotionStreamerConf
        """
        return NaoMotionStreamerConf()

    @staticmethod
    def get_inputs():
        """
        List the message and request types accepted by this component.

        :returns: Supported inputs.
        :rtype: list[type]
        """
        return [NaoJointAngles, StartStreaming, StopStreaming]

    def on_request(self, request):
        """
        Handle start/stop streaming requests.

        :param SICRequest request: Incoming request instance.
        :returns: Acknowledgement message.
        :rtype: SICMessage
        """
        if request == StartStreaming:
            self.joints = self.generate_joint_list(request.joints)
            self.do_streaming.set()
            return SICMessage()

        if request == StopStreaming:
            self.do_streaming.clear()
            return SICMessage()

    def on_message(self, message):
        """
        Apply stiffness if needed and forward desired joint angles to the robot.

        :param NaoJointAngles message: Message containing joint names and desired angles.
        """
        if self.stiffness != self.params.stiffness:
            self.motion.setStiffnesses(self.joints, self.params.stiffness)
            self.stiffness = self.params.stiffness

        self.motion.setAngles(message.joints, message.angles, self.params.speed)

    @staticmethod
    def get_output():
        """
        Declare the message type produced by this component.

        :returns: Output message class.
        :rtype: type
        """
        return NaoJointAngles

    def stream_joints(self):
        """
        Background loop: sample joint angles and publish them at the configured rate.

        The loop respects `do_streaming` and component stop signals.

        :raises Exception: Logged and triggers `stop()` on unexpected errors.
        """
        # Set the stiffness value of a list of joint chain.
        # For Nao joint chains are: Head, RArm, LArm, RLeg, LLeg
        try:

            while not self._signal_to_stop.is_set():

                # check both do_streaming and _signal_to_stop periodically
                self.do_streaming.wait(1)
                if not self.do_streaming.is_set():
                    continue

                if self.stiffness != 0:
                    self.motion.setStiffnesses(self.joints, 0.0)
                    self.stiffness = 0

                angles = self.motion.getAngles(
                    self.joints, self.params.use_sensors
                )  # use_sensors=False

                self.output_message(NaoJointAngles(self.joints, angles))

                time.sleep(1 / float(self.samples_per_second))
            self._stopped.set()
        except Exception as e:
            self.logger.exception(e)
            self.stop()

    def stop(self, *args):
        """
        Stop the motion streamer, closing the NAOqi session and the component.

        :returns: None
        :rtype: None
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiMotionStreamerService, self).stop()


class NaoqiMotionStreamer(SICConnector):
    """
    Connector binding to `NaoqiMotionStreamerService`.
    """
    component_class = NaoqiMotionStreamerService


if __name__ == "__main__":
    SICComponentManager([NaoqiMotionStreamerService])
