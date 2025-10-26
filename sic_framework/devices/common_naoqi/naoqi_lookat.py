import threading

from sic_framework import SICComponentManager, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    BoundingBoxesMessage,
    SICConfMessage,
    SICMessage,
)
from sic_framework.core.sensor_python2 import SICSensor
from sic_framework.devices.common_naoqi.nao_motion_streamer import NaoJointAngles
from sic_framework.core import sic_logging

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class NaoqiLookAtConf(SICConfMessage):
    def __init__(
        self, camera_index=0, camera_y_max=480, camera_x_max=640, mirror_x=False
    ):
        """
        Initialize LookAt configuration.

        :param int camera_index: 
        :param int camera_y_max: 
        :param int camera_x_max: 
        :param bool mirror_x: Mirror the horizontal angle sign.
        """
        self.camera_index = camera_index  # 0 = top, 1 = bottom
        self.camera_y_max = camera_y_max

        self.camera_x_max = camera_x_max
        self.mirror_x = mirror_x


class LookAtMessage(SICMessage):
    """
    Message requesting the robot to look at normalized image coordinates.

    Coordinates are in range [0.0, 1.0], where (0,0) is top-left.
    """

    _compress_images = False

    def __init__(self, x, y):
        """
        Create a LookAt request message.

        :param float x: Horizontal normalized coordinate in [0.0, 1.0].
        :param float y: Vertical normalized coordinate in [0.0, 1.0].
        """
        self.x = x
        self.y = y


class NaoqiLookAtComponent(SICComponent):
    def __init__(self, *args, **kwargs):
        super(NaoqiLookAtComponent, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        self.video_service = self.session.service("ALVideoDevice")
        self.tracker = self.session.service("ALTracker")
        self.motion = self.session.service("ALMotion")

    @staticmethod
    def get_conf():
        """
        Return the default configuration for this component.

        :returns: Default LookAt configuration.
        :rtype: NaoqiLookAtConf
        """
        return NaoqiLookAtConf()

    @staticmethod
    def get_inputs():
        return [LookAtMessage, BoundingBoxesMessage]

    @staticmethod
    def get_output():
        return AudioMessage

    def on_message(self, message):
        """
        :param SICMessage message: Incoming message (`LookAtMessage` or `BoundingBoxesMessage`).
        """
        x, y = None, None
        if message == BoundingBoxesMessage:
            # track the most confident boundingbox
            if len(message.bboxes):
                bbox = message.bboxes[0]

                self.logger.debug("bbox:")
                self.logger.debug(bbox.x, bbox.y, bbox.confidence)

                for x in message.bboxes:
                    if bbox.confidence < x.confidence:
                        bbox = x

                x = bbox.x / self.params.camera_x_max
                y = bbox.y / self.params.camera_y_max

        elif message == LookAtMessage:
            y = message.y / self.params.camera_y_max
            x = message.x / self.params.camera_x_max

        if x is not None and y is not None:
            angles = self.video_service.getAngularPositionFromImagePosition(
                self.params.camera_index, [x, y]
            )
            if self.params.mirror_x:
                angles[0] = -angles[0]
            self.output_message(NaoJointAngles(["HeadYaw", "HeadPitch"], angles))

    def stop(self, *args):
        """
        Stop the LookAt component.
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiLookAtComponent, self).stop(*args)


class NaoqiLookAt(SICConnector):
    component_class = NaoqiLookAtComponent


if __name__ == "__main__":
    SICComponentManager([NaoqiLookAtComponent])
