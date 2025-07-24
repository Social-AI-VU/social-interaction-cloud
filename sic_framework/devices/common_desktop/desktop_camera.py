import platform

import cv2

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import CompressedImageMessage, SICConfMessage
from sic_framework.core.sensor_python2 import SICSensor


class DesktopCameraConf(SICConfMessage):
    def __init__(self, fx=1.0, fy=1.0, flip=None, device_id=0):
        """
        Sets desktop camera configuration parameters.

        See https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html#ga47a974309e9102f5f08231edc7e7529d
        :param fx: rescaling factor along x-axis (float)
        :param fy: rescaling factor along y-axis (float)
        :param device_id: The device ID of the camera for OpenCV to use. Default: 0

        See https://docs.opencv.org/3.4/d2/de8/group__core__array.html#gaca7be533e3dac7feb70fc60635adf441
        :param flip: flip code for vertical (0), horizontal (>0), or both (<0) flipping. Default is None (no flipping)
        """
        SICConfMessage.__init__(self)

        self.device_id = device_id
        self.fx = fx
        self.fy = fy
        self.flip = flip


class DesktopCameraSensor(SICSensor):
    def __init__(self, *args, **kwargs):
        super(DesktopCameraSensor, self).__init__(*args, **kwargs)
        if platform.system() == "Windows":
            self.cam = cv2.VideoCapture(self.params.device_id, cv2.CAP_DSHOW)
        else:
            self.cam = cv2.VideoCapture(self.params.device_id)

    @staticmethod
    def get_conf():
        return DesktopCameraConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return CompressedImageMessage

    def execute(self):
        # Check if camera has been released
        if not self.cam.isOpened():
            self.logger.error("Camera has been released")
            return None
        
        ret, frame = self.cam.read()
        
        # Check if frame is valid before processing
        if not ret or frame is None or frame.size == 0:
            self.logger.warning("Failed to grab frame from video device")
            return None
            
        try:
            frame = cv2.resize(frame, (0, 0), fx=self.params.fx, fy=self.params.fy)
        except cv2.error as e:
            self.logger.warning("OpenCV resize error: {e}".format(e=e))
            return None

        # Optionally flip image
        if self.params.flip is not None:
            try:
                frame = cv2.flip(frame, self.params.flip)
            except cv2.error as e:
                self.logger.warning("OpenCV flip error: {e}".format(e=e))
                return None

        return CompressedImageMessage(frame)

    def stop(self, *args):
        super(DesktopCameraSensor, self).stop(*args)
        if hasattr(self, 'cam') and self.cam is not None:
            self.cam.release()


class DesktopCamera(SICConnector):
    component_class = DesktopCameraSensor


if __name__ == "__main__":
    SICComponentManager([DesktopCameraSensor])
