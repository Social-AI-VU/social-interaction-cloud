import time
import threading
import panda_py
from panda_py import controllers

from sic_framework import SICComponentManager
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    SICRequest,
    SICMessage,
)
"""
Instead of using ROS, we use panda_py, which provides lightweight Python bindings for the Panda,
enabling direct control of Franka using libfranka. More details can be found here: https://github.com/JeanElsner/panda-py
"""


class StartTeachingRequest(SICRequest):
    """
    A request to start teaching mode
    """
    pass


class StopTeachingRequest(SICRequest):
    """
    A request to stop teaching mode
    """
    pass


class StartRecordingRequest(SICRequest):
    """
    Record motion of the joints, For more information see documentation
    https://github.com/JeanElsner/panda-py

    :param frequency: Number of data points recorded per second. Higher values capture finer motion detail

    """
    def __init__(self, frequency=1000):
        super(StartRecordingRequest, self).__init__()
        self.frequency = frequency


class StopRecordingRequest(SICRequest):
    """
    A request to stop recording joint motion.
    """
    pass


class GoHomeRequest(SICRequest):
    """
    A request to move the robot to its home position.
    """
    pass


class PlayRecordingRequest(SICRequest):
    """
    Play recorded joint positions and joint velocities.

    :param joint_recording: Object contains PandaJointsRecording.
    :param frequency: Number of data points recorded per second. This frequency should match how the initial trajectory was recorded/collected

    """
    def __init__(self, joint_recording, frequency=1000):
        super(PlayRecordingRequest, self).__init__()
        self.recorded_joints_pos = joint_recording.recorded_joints_pos
        self.recorded_joints_vel = joint_recording.recorded_joints_vel
        self.frequency = frequency


class PandaJointsRecording(SICMessage):
    """
    A SICMessage containing recorded joint positions and velocities.

    :param recorded_joints_pos: List of 7-element arrays representing recorded joint positions.
    :param recorded_joints_vel: List of 7-element arrays representing recorded joint velocities.
    """
    def __init__(self, recorded_joints_pos, recorded_joints_vel):
        super().__init__()
        self.recorded_joints_pos = recorded_joints_pos
        self.recorded_joints_vel = recorded_joints_vel

    def save(self, filename):
        """
        Save the recorded joint positions and velocities to a file.

        :param filename: The name of the file to save. In demo, it ends with ".motion".
        """
        with open(filename, 'wb') as f:
            f.write(self.serialize())

    @classmethod
    def load(cls, filename):
        """
        Load recorded joint positions and velocities from a ".motion".

        :param filename: The name of the file to load.
        :return: An instance of PandaJointsRecording containing joint positions and velocities data.
        """
        with open(filename, 'rb') as f:
            return cls.deserialize(f.read())


class FrankaMotionRecorderActuator(SICActuator):
    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)
        self.panda = panda_py.Panda("172.16.0.2")
        self.recorded_joints_pos = []
        self.recorded_joints_vel = []
        self.recording = threading.Event()
        self.record_thread = threading.Thread(target=self.record_motion)
        self.record_thread.start()

    @staticmethod
    def get_inputs():
        return [StartRecordingRequest, StopRecordingRequest, StartTeachingRequest, StopTeachingRequest]

    def record_motion(self):
        """
        Record joint motion when recording event is set.
        """
        try:
            while not self._stop_event.is_set():
                self.recording.wait(1)
                if not self.recording.is_set():
                    continue
                self.recorded_joints_pos.append(self.panda.get_state().q)
                self.recorded_joints_vel.append(self.panda.get_state().dq)
                time.sleep(1/self.frequency)

        except Exception as e:
                    self.logger.exception(e)
                    self.stop()

    def reset_recording_variables(self, request):
        """
        Reset recorded joint positions and velocities and set the recording frequency.

        :param request: The StartRecordingRequest containing the desired recording frequency.
        """
        self.recorded_joints_pos = []
        self.recorded_joints_vel = []
        self.frequency = request.frequency

    def replay_recording(self, request):
        """
        Replay recorded joint positions and velocities.

        :param request: The PlayRecordingRequest containing recorded joint positions and velocities.
        """
        # here we set the controller to Joint Position, which requires joint positions and velocities to control the joints
        # see more details: https://jeanelsner.github.io/panda-py/panda_py.controllers.html#panda_py.controllers.JointPosition.set_control
        ctrl = controllers.JointPosition()
        self.panda.start_controller(ctrl)
        i = 0
        with self.panda.create_context(frequency=request.frequency, max_runtime=100) as ctx:
            while ctx.ok() and i < len(request.recorded_joints_pos):
                ctrl.set_control(request.recorded_joints_pos[i], request.recorded_joints_vel[i])
                i += 1

    def execute(self, request):
        if request == StartRecordingRequest:
            self.reset_recording_variables(request)
            self.recording.set()
            return SICMessage()

        if request == StopRecordingRequest:
            self.recording.clear()
            if not self.recording.is_set():
                print("Stop recording")
            # print(len(self.recorded_joints_vel))
            # print(len(self.recorded_joints_pos))
            return PandaJointsRecording(self.recorded_joints_pos, self.recorded_joints_vel)

        if request == StartTeachingRequest:
            self.panda.teaching_mode(True)
            return SICMessage()

        if request == StopTeachingRequest:
            self.panda.teaching_mode(False)
            return SICMessage()

        if request == GoHomeRequest:
            self.panda.move_to_start()
            return SICMessage()

        if request == PlayRecordingRequest:
            self.replay_recording(request)
            return SICMessage()


class FrankaMotionRecorder(SICConnector):
    component_class = FrankaMotionRecorderActuator


if __name__ == '__main__':
    SICComponentManager([FrankaMotionRecorderActuator])


