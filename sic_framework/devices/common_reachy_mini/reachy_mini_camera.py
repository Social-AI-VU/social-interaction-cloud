import cv2

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import CompressedImageMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor


class ReachyMiniCameraConf(SICConfMessage):
    """
    :param flip: cv2 flip code: 0 (vertical), >0 (horizontal), <0 (both). Default -1 (180 degrees, camera is mounted inverted).
    :param flip_rgb: Convert BGR to RGB. Default True (SDK returns BGR).
    """

    def __init__(self, flip=-1, flip_rgb=True):
        self.flip = flip
        self.flip_rgb = flip_rgb


class ReachyMiniCameraSensor(SICSensor):
    def __init__(self, *args, **kwargs):
        super(ReachyMiniCameraSensor, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance

    @staticmethod
    def get_conf():
        return ReachyMiniCameraConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return CompressedImageMessage

    def execute(self):
        try:
            frame = self.mini.media.get_frame()
        except Exception as e:
            self.logger.warning("Failed to grab frame: {}".format(e))
            return None

        if frame is None:
            return None

        if self.params.flip is not None:
            frame = cv2.flip(frame, self.params.flip)

        if self.params.flip_rgb:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        return CompressedImageMessage(frame)

    def _cleanup(self):
        pass


class ReachyMiniCamera(SICConnector):
    component_class = ReachyMiniCameraSensor


if __name__ == "__main__":
    SICComponentManager([ReachyMiniCameraSensor])
