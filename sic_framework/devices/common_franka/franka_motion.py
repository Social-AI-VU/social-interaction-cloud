from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICRequest, SICMessage
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.utils import is_sic_instance

import panda_py
from panda_py import controllers

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

# TODO maybe an actuator is not a correct name here
class FrankaMotionActuator(SICActuator):
    def __init__(self, *args, **kwargs):
        super(FrankaMotionActuator, self).__init__(*args, **kwargs)
        self.panda = panda_py.Panda("172.16.0.2")
        # here we set the controller to Cartesian Impedance, which only requires position and orientation to control the end effector (EE)
        # see more details: https://jeanelsner.github.io/panda-py/panda_py.controllers.html#panda_py.controllers.CartesianImpedance.set_control
        self.ctrl = controllers.CartesianImpedance(filter_coeff=1.0)
        self.panda.start_controller(self.ctrl)
        # for streaming thread
        self._streaming = False
        self._stream_thread = None
    # it's the EE pose we want to send to set_control
    @staticmethod
    def get_inputs():
        return [FrankaPose]

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
