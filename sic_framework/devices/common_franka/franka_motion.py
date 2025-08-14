from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICRequest, SICMessage
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.utils import is_sic_instance

import panda_py
from panda_py import controllers

import threading

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
class FrankaMotionActuator(SICComponent):
    def __init__(self, *args, **kwargs):
        super(FrankaMotionActuator, self).__init__(*args, **kwargs)
        self.panda = panda_py.Panda("172.16.0.2")
        self.ctrl = controllers.CartesianImpedance(filter_coeff=1.0)
        self.panda.start_controller(self.ctrl)

    # it's the EE pose we want to send to set_control
    @staticmethod
    def get_inputs():
        return [FrankaPose]

    # it's outputting the current EE pose
    @staticmethod
    def get_output():
        return FrankaPose

    def on_message(self, message):
        if is_sic_instance(message, FrankaPose):
            # move EE to given pose (wrt robot base frame)
            self.ctrl.set_control(message.position, message.orientation)

    def on_request(self, request):
        if is_sic_instance(request, FrankaPoseRequest):
            # If streaming requested, just start sending current EE pose periodically
            if request.stream:
                # could start a background thread or timer to continuously send current pose
                self._start_streaming()
            return self.get_pose()

    def get_pose(self):
        # retrieve the current end-effector position and orientation in the robot base frame.
        x = self.panda.get_position()
        q = self.panda.get_orientation()
        return FrankaPose(position=x, orientation=q)

    def _start_streaming(self):
        def stream_loop():
            while True:
                pose = self.get_pose()
                self._redis.send_message(self.output_channel, pose)
        threading.Thread(target=stream_loop, daemon=True).start()

class FrankaMotion(SICConnector):
    component_class = FrankaMotionActuator


if __name__ == '__main__':
    SICComponentManager([FrankaMotionActuator])
