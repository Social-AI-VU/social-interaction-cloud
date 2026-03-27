from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import CompressedImageMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor


class ReachyMiniCameraConf(SICConfMessage):
    pass


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

        return CompressedImageMessage(frame)

    def _cleanup(self):
        pass


class ReachyMiniCamera(SICConnector):
    component_class = ReachyMiniCameraSensor


if __name__ == "__main__":
    SICComponentManager([ReachyMiniCameraSensor])
