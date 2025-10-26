import threading
import time

import numpy as np

from sic_framework import SICActuator, SICComponentManager, SICMessage, utils
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICRequest
from sic_framework.devices.common_naoqi.common_naoqi_motion import NaoqiMotionTools

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class StartRecording(SICRequest):
    def __init__(self, joints):
        """
        Initialize a request to record the motion of selected joints.

        For more information on joint chains, see robot documentation:
        - Nao: http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains
        - Pepper: http://doc.aldebaran.com/2-8/family/pepper_technical/bodyparts_pep.html

        :param list[str] joints: One or more joint chains or individual joints (e.g., ["Body"] or ["LArm", "HeadYaw"]).
        """
        super(StartRecording, self).__init__()
        self.joints = joints


class StopRecording(SICRequest):
    pass


class NaoqiMotionRecording(SICMessage):
    def __init__(self, recorded_joints, recorded_angles, recorded_times):
        """
        Create a motion recording message.

        Example:
            recorded_joints = ["HeadYaw", "HeadPitch", "LWrist"]
            recorded_angles = [[0.13, 0.21, 0.25], [0.21, 0.23, 0.31], [-1.0, 0.0, 0.1]]
            recorded_times  = [[0.1, 0.2, 0.3],  [0.1, 0.2, 0.3],  [0.1, 0.2, 0.3]]

        See: http://doc.aldebaran.com/2-1/naoqi/motion/control-joint-api.html#joint-control-api

        :param list[str] recorded_joints: Joint names (e.g., "HeadYaw"), not chains (e.g., "Body").
        :param list[list[float]] recorded_angles: Angles per joint, in radians.
        :param list[list[float]] recorded_times: Target times per angle, in seconds.
        """
        super(NaoqiMotionRecording, self).__init__()
        self.recorded_joints = recorded_joints
        self.recorded_angles = recorded_angles
        self.recorded_times = recorded_times

    def save(self, filename):
        """
        Save the recording to a file (e.g., "wave.motion").

        :param str filename: Target filename (preferably with .motion extension).
        """
        with open(filename, "wb") as f:
            f.write(self.serialize())

    @classmethod
    def load(cls, filename):
        """
        Load a motion recording.

        :param str filename: Path to a saved .motion file.
        :returns: Deserialized motion recording message.
        :rtype: NaoqiMotionRecording
        """
        with open(filename, "rb") as f:
            return cls.deserialize(f.read())


class PlayRecording(SICRequest):
    """
    Request to replay a previously recorded motion.
    """
    def __init__(self, motion_recording_message, playback_speed=1):
        """
        Play a recorded motion.

        :param NaoqiMotionRecording motion_recording_message: a NaoqiMotionRecording message.
        :param float playback_speed: Playback speed multiplier (e.g., 1.5 for 1.5x; 0.5 for half speed).
        """
        super(PlayRecording, self).__init__()
        self.motion_recording_message = motion_recording_message

        if playback_speed != 1:
            recorded_times = np.array(self.motion_recording_message.recorded_times)
            recorded_times = recorded_times / playback_speed
            self.motion_recording_message.recorded_times = recorded_times.tolist()



class NaoqiMotionRecorderConf(SICConfMessage):
    """
    Configuration for recording and replaying motions.
    """
    def __init__(
        self,
        replay_stiffness=0.6,
        replay_speed=0.75,
        use_interpolation=True,
        setup_time=0.5,
        use_sensors=False,
        samples_per_second=20,
    ):
        """
        Initialize recorder configuration options.

        There is a choice between `setAngles` (approximate) and `angleInterpolation` (exact but speed-limited).

        Note: `replay_speed` is used only when `use_interpolation=False`.
        Note: `setup_time` is used only when `use_interpolation=True`.

        :param replay_stiffness: Control how much power the robot should use to reach the given joint angles.
        :param replay_speed: Control how fast the robot should to reach the given joint angles. 
        :param use_interpolation: Use setAngles if False and angleInterpolation if True.
        :param setup_time: The time in seconds the robot has to reach the start position of the recording.
        :param use_sensors: If true, sensor angles will be returned, otherwise command angles are used.
        :param samples_per_second: How many times per second the joint positions are sampled.
        """
        SICConfMessage.__init__(self)
        self.replay_stiffness = replay_stiffness
        self.replay_speed = replay_speed
        self.use_interpolation = use_interpolation
        self.setup_time = setup_time
        self.use_sensors = use_sensors
        self.samples_per_second = samples_per_second


class NaoqiMotionRecorderActuator(SICActuator, NaoqiMotionTools):
    COMPONENT_STARTUP_TIMEOUT = 20  # allow robot to wake up

    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        NaoqiMotionTools.__init__(self, qi_session=self.session)

        self.motion = self.session.service("ALMotion")

        self.samples_per_second = self.params.samples_per_second

        self.recorded_joints = []
        self.recorded_angles = []
        self.recorded_times = []

        self.do_recording = threading.Event()
        self.record_start_time = None

        # A list of joint names (should not include chains)
        self.joints = None

        self.stream_thread = threading.Thread(target=self.record_motion)
        self.stream_thread.name = self.get_component_name()
        self.stream_thread.start()

    @staticmethod
    def get_conf():
        """
        Return the default configuration for this component.

        :returns: Recorder configuration.
        :rtype: NaoqiMotionRecorderConf
        """
        return NaoqiMotionRecorderConf()

    @staticmethod
    def get_inputs():
        return [StartRecording, StopRecording]

    @staticmethod
    def get_output():
        return NaoqiMotionRecording

    def record_motion(self):
        """
        A thread that starts to record the motion of the robot until an event is set.
        """
        try:

            while not self._signal_to_stop.is_set():

                # check both do_recording and _signal_to_stop periodically
                self.do_recording.wait(1)
                if not self.do_recording.is_set():
                    continue

                angles = self.motion.getAngles(self.joints, self.params.use_sensors)
                time_delta = time.time() - self.record_start_time

                for joint_idx, angle in enumerate(angles):
                    self.recorded_angles[joint_idx].append(angle)
                    self.recorded_times[joint_idx].append(time_delta)

                time.sleep(1 / float(self.samples_per_second))

        except Exception as e:
            self.logger.exception(e)
            self.stop()

    def reset_recording_variables(self, request):
        """
        Initialize variables that will be populated during recording.
        """
        self.record_start_time = time.time()

        self.joints = self.generate_joint_list(request.joints)

        self.recorded_angles = []
        self.recorded_times = []
        for _ in self.joints:
            self.recorded_angles.append([])
            self.recorded_times.append([])

    def execute(self, request):
        if request == StartRecording:
            self.reset_recording_variables(request)
            self.do_recording.set()
            return SICMessage()

        if request == StopRecording:
            self.do_recording.clear()
            return NaoqiMotionRecording(
                self.joints, self.recorded_angles, self.recorded_times
            )

        if request == PlayRecording:
            return self.replay_recording(request)

    def replay_recording(self, request):
        """
        Replay a recorded motion.
        """
        message = request.motion_recording_message

        joints = message.recorded_joints
        angles = message.recorded_angles
        times = message.recorded_times

        if self.params.use_interpolation:
            times = [(np.array(t) + self.params.setup_time).tolist() for t in times]

            self.motion.angleInterpolation(
                joints, angles, times, True
            )  # isAbsolute = bool

        else:
            # compute the average time delta (should be 1 / self.samples_per_second anyway)
            sleep_time = max(times[0]) / len(times[0])

            for a in np.array(angles).T.tolist():
                self.motion.setAngles(joints, a, self.params.replay_speed)
                time.sleep(sleep_time)

        return SICMessage()

    def stop(self, *args):
        """
        Stop the motion recorder actuator.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiMotionRecorderActuator, self).stop()


class NaoqiMotionRecorder(SICConnector):
    component_class = NaoqiMotionRecorderActuator
