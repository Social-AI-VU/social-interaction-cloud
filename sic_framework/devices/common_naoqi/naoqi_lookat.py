import threading

import numpy as np

from sic_framework import SICComponentManager, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICMessage, BoundingBoxesMessage
from sic_framework.core.sensor_python2 import SICSensor
from sic_framework.devices.common_naoqi.naoqi_motion_streamer import NaoJointAngles

if utils.PYTHON_VERSION_IS_2:
    from naoqi import ALProxy
    import qi


class NaoqiLookAtConf(SICConfMessage):
    def __init__(self, stiffness=.5,):
        """
        Speed is set to very low to avoid overshooting what to look at.
        """
        self.stiffness = stiffness



class LookAtMessage(SICMessage):
    """
    Make the robot look at the normalized image coordinates.
    range [0, 1.0]
    """
    _compress_images = False

    def __init__(self, x, y, camera_index, speed=0.1):
        self.x = x
        self.y = y
        self.camera_index = camera_index
        self.speed = speed


class NaoqiLookAtComponent(SICComponent):
    def __init__(self, *args, **kwargs):
        super(NaoqiLookAtComponent, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect('tcp://127.0.0.1:9559')

        self.video_service = self.session.service("ALVideoDevice")
        self.tracker = self.session.service('ALTracker')
        self.motion = self.session.service('ALMotion')

        self.joints = ["HeadYaw", "HeadPitch"]
        self.motion.setStiffnesses(self.joints, self.params.stiffness)

    @staticmethod
    def get_conf():
        return NaoqiLookAtConf()

    @staticmethod
    def get_inputs():
        return [LookAtMessage, BoundingBoxesMessage]

    @staticmethod
    def get_output():
        return AudioMessage

    def on_message(self, message):
        fov_h = 96
        fov_v = 60

        # Calculate change in radians (compared to center of fov)
        change_x = -float(np.deg2rad((message.x - 0.5) * fov_h)) / 2
        change_y = float(np.deg2rad((message.y - 0.5) * fov_v)) / 2

        # prevent overshoot of small changes
        if change_x < 0.08:
            change_x /= 2

        # Change angles faster in horizontal direction than vertical direction
        # TODO: maybe make these parameters
        self.motion.changeAngles(self.joints[0], change_x, max(0.04, change_x * 0.6))
        self.motion.changeAngles(self.joints[1], change_y * 0.3, 0.05)

    def stop(self, *args):
        self.session.close()
        super(NaoqiLookAtComponent, self).stop(*args)


class NaoqiLookAt(SICConnector):
    component_class = NaoqiLookAtComponent


if __name__ == '__main__':
    SICComponentManager([NaoqiLookAtComponent])
