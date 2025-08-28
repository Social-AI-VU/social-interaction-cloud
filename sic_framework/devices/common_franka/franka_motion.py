from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICRequest, SICMessage
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.utils import is_sic_instance

import panda_py
from panda_py import controllers
from panda_py import libfranka


import threading
import time

class FrankaPoseRequest(SICRequest):
    """
    A request for obtaining the current end-effector (EE) pose relative to the robot base frame.
    """
    def __init__(self, stream=False):
        super(FrankaPoseRequest, self).__init__()
        self.stream = stream


class FrankaPose(SICMessage):
    """
    A SICMessage containing end-effector (EE) position and orientation in robot base frame

    :param position: end-effector position in robot base frame
    :param orientation: end-effector orientation (quaternion) in robot base frame
    """
    def __init__(self, position, orientation):
        super().__init__()
        self.position = position
        self.orientation = orientation


class FrankaGripperGraspRequest(SICRequest):
    """
    A SICRequest to command the gripper to grasp an object with a force-controlled command.

    see the api documentation for more details: https://jeanelsner.github.io/panda-py/panda_py.libfranka.html#panda_py.libfranka.Gripper.grasp

    :param width: The distance between the fingers in meters. The width must be between 0.0 and 0.085 m.
    :param speed: The speed of the gripper in meters per second. The speed must be between 0 and 0.1 m/s.
    :param force: The gripping force in Newton. The force must be between 5 and 70 N.
    :param epsilon_inner: The inner tolerance for the grasp width in meters.
    :param epsilon_outer: The outer tolerance for the grasp width in meters.
    """
    def __init__(self, width, speed=0.1, force=5, epsilon_inner=0.005, epsilon_outer=0.005):
        super().__init__()
        self.width = width
        self.speed = speed
        self.force = force
        self.epsilon_inner = epsilon_inner
        self.epsilon_outer = epsilon_outer

class FrankaGripperMoveRequest(SICRequest):
    """
    A SICRequest to command the gripper to move to a specific width.

    see the api documentation for more details: https://jeanelsner.github.io/panda-py/panda_py.libfranka.html#panda_py.libfranka.Gripper.move

    :param width: The distance between the fingers in meters. The width must be between 0.0 and 0.085 m.
    :param speed: The speed of the gripper in meters per second. The speed must be between 0 and 0.1 m/s.
    """
    def __init__(self, width, speed=0.1):
        super().__init__()
        self.width = width
        self.speed = speed

# TODO maybe an actuator is not a correct name here
class FrankaMotionActuator(SICActuator):
    def __init__(self, *args, **kwargs):
        super(FrankaMotionActuator, self).__init__(*args, **kwargs)
        hostname = "172.16.0.2"
        self.panda = panda_py.Panda(hostname)
        # here we set the controller to Cartesian Impedance, which only requires position and orientation to control the end effector (EE)
        # see more details: https://jeanelsner.github.io/panda-py/panda_py.controllers.html#panda_py.controllers.CartesianImpedance.set_control
        self.ctrl = controllers.CartesianImpedance(filter_coeff=1.0)
        self.panda.start_controller(self.ctrl)

        # gripper object
        self.gripper = libfranka.Gripper(hostname)

        # for streaming thread
        self._streaming = False
        self._stream_thread = None
    # it's the EE pose we want to send to set_control
    @staticmethod
    def get_inputs():
        return [
            FrankaPose,
            FrankaGripperGraspRequest,
            FrankaGripperMoveRequest,
            FrankaPoseRequest
        ]

    # it's outputting the current EE pose from _start_streaming
    @staticmethod
    def get_output():
        return FrankaPose

    def on_message(self, message):
        if is_sic_instance(message, FrankaPose):
            # move EE to given pose (wrt robot base frame)
            self.ctrl.set_control(message.position, message.orientation)

    def execute(self, request):
        if is_sic_instance(request, FrankaPoseRequest):
            # if steaming is set to True, send current EE pose continuously to the output channel
            if request.stream:
                # start background thread only once
                if not self._streaming:
                    self._streaming = True
                    self._stream_thread = threading.Thread(
                        target=self._stream_loop, daemon=True
                    )
                    self._stream_thread.start()
            return self.get_pose()
        if is_sic_instance(request, FrankaGripperGraspRequest):
            self.logger.info("Grasping with width: {}, speed: {}, force: {}, epsilon_inner: {}, epsilon_outer: {}".format(
                request.width, request.speed, request.force, request.epsilon_inner, request.epsilon_outer))

            self.gripper.grasp(request.width, request.speed, request.force, request.epsilon_inner, request.epsilon_outer)
        if is_sic_instance(request, FrankaGripperMoveRequest):
            self.gripper.move(request.width, request.speed)

        return SICMessage()


    def get_pose(self):
        # retrieve the current end-effector position and orientation in the robot base frame.
        x = self.panda.get_position()
        q = self.panda.get_orientation()
        return FrankaPose(position=x, orientation=q)

    def _stream_loop(self):
        while self._streaming:
            pose = self.get_pose()
            self.output_message(pose)
            # sleep for a short time to avoid flooding the output channel
            time.sleep(1/500)  # stream at 500 Hz


class FrankaMotion(SICConnector):
    component_class = FrankaMotionActuator


if __name__ == '__main__':
    SICComponentManager([FrankaMotionActuator])
