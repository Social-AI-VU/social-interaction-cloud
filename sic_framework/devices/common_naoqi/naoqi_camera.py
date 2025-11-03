import argparse

from sic_framework import SICComponentManager, SICService, utils
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    CompressedImageMessage,
    SICConfMessage,
    SICMessage,
)
from sic_framework.core.sensor_python2 import SICSensor

if utils.PYTHON_VERSION_IS_2:
    import random

    import cv2
    import numpy as np
    import qi
    from naoqi import ALProxy
    from PIL import Image


class NaoqiCameraConf(SICConfMessage):
    def __init__(
        self,
        naoqi_ip="127.0.0.1",
        port=9559,
        cam_id=0,
        res_id=2,
        fps=30,
        brightness=None,
        contrast=None,
        saturation=None,
        hue=None,
        gain=None,
        hflip=None,
        vflip=None,
        auto_exposition=None,
        auto_white_bal=None,
        manual_exposure_val=None,
        auto_exp_algo=None,
        sharpness=None,
        back_light_comp=None,
        auto_focus=None,
        manual_focus_value=None,
    ):
        """
        Initialize camera configuration and optional device parameters.

        For parameter meaning and defaults, see:
        - http://doc.aldebaran.com/2-8/family/nao_technical/video_naov6.html#naov6-video
        - http://doc.aldebaran.com/2-1/family/robots/video_robot.html

        :param str naoqi_ip: NAOqi host IP.
        :param int port: NAOqi TCP port.
        :param int cam_id: Camera ID to use.
        :param int res_id: Resolution ID.
        :param int fps: Target frames per second.
        :param Optional[int] brightness: Camera brightness.
        :param Optional[int] contrast: Camera contrast.
        :param Optional[int] saturation: Camera color saturation.
        :param Optional[int] hue: Camera hue adjustment.
        :param Optional[int] gain: Camera gain level.
        :param Optional[int] hflip: Horizontal flip toggle.
        :param Optional[int] vflip: Vertical flip toggle.
        :param Optional[int] auto_exposition: Auto exposure toggle.
        :param Optional[int] auto_white_bal: Auto white balance toggle.
        :param Optional[int] manual_exposure_val: Manual exposure value.
        :param Optional[int] auto_exp_algo: Auto exposure algorithm.
        :param Optional[int] sharpness: Image sharpness.
        :param Optional[int] back_light_comp: Backlight compensation toggle.
        :param Optional[int] auto_focus: Auto focus toggle.
        :param Optional[int] manual_focus_value: Manual focus value.


        Parameter Defaults:
        brightness: 55
        contrast: 32
        saturation: 128
        hue: 0
        gain: 32
        hflip: 0
        vflip: 0
        auto_exposition: 1
        auto_white_bal: 1
        auto_exp_algo: 1
        sharpness: 0
        back_light_comp: 1
        auto_focus: 0
        manual_focus_value: 0
        """

        SICConfMessage.__init__(self)
        self.naoqi_ip = naoqi_ip
        self.port = port
        self.cam_id = cam_id
        self.res_id = res_id
        self.color_id = 11  # RGB
        self.fps = fps
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.hue = hue
        self.gain = gain
        self.hflip = hflip
        self.vflip = vflip
        self.auto_exposition = auto_exposition
        self.auto_white_bal = auto_white_bal
        self.manual_exposure_val = manual_exposure_val
        self.auto_exp_algo = auto_exp_algo
        self.sharpness = sharpness
        self.back_light_comp = back_light_comp
        self.auto_focus = auto_focus
        self.manual_focus_value = manual_focus_value


class BaseNaoqiCameraSensor(SICSensor):
    def __init__(self, *args, **kwargs):

        super(BaseNaoqiCameraSensor, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://{}:{}".format(self.params.naoqi_ip, self.params.port))

        self.video_service = self.session.service("ALVideoDevice")

        # Dont actively set default parameters, this causes weird behaviour because the parameters are ususally not at the documented default.
        if self.params.brightness is not None:
            self.video_service.setParameter(
                self.params.cam_id, 0, self.params.brightness
            )
        if self.params.contrast is not None:
            self.video_service.setParameter(self.params.cam_id, 1, self.params.contrast)
        if self.params.saturation is not None:
            self.video_service.setParameter(
                self.params.cam_id, 2, self.params.saturation
            )
        if self.params.hue is not None:
            self.video_service.setParameter(self.params.cam_id, 3, self.params.hue)
        if self.params.gain is not None:
            self.video_service.setParameter(self.params.cam_id, 6, self.params.gain)
        if self.params.hflip is not None:
            self.video_service.setParameter(self.params.cam_id, 7, self.params.hflip)
        if self.params.vflip is not None:
            self.video_service.setParameter(self.params.cam_id, 8, self.params.vflip)
        if self.params.auto_exposition is not None:
            self.video_service.setParameter(
                self.params.cam_id, 11, self.params.auto_exposition
            )
        if self.params.auto_white_bal is not None:
            self.video_service.setParameter(
                self.params.cam_id, 12, self.params.auto_white_bal
            )
        if self.params.manual_exposure_val is not None:
            self.video_service.setParameter(
                self.params.cam_id, 12, self.params.manual_exposure_val
            )
        if self.params.auto_exp_algo is not None:
            self.video_service.setParameter(
                self.params.cam_id, 22, self.params.auto_exp_algo
            )
        if self.params.sharpness is not None:
            self.video_service.setParameter(
                self.params.cam_id, 24, self.params.sharpness
            )
        if self.params.back_light_comp is not None:
            self.video_service.setParameter(
                self.params.cam_id, 34, self.params.back_light_comp
            )
        if self.params.auto_focus is not None:
            self.video_service.setParameter(
                self.params.cam_id, 40, self.params.auto_focus
            )
        if self.params.manual_focus_value is not None:
            self.video_service.setParameter(
                self.params.cam_id, 43, self.params.manual_focus_value
            )
        self.video_service.setParameter(0, 35, 1)  # Keep Alive parameter

        self.videoClient = self.video_service.subscribeCamera(
            "Camera_{}".format(random.randint(0, 100000)),
            self.params.cam_id,
            self.params.res_id,
            self.params.color_id,
            self.params.fps,
        )

    @staticmethod
    def get_conf():
        """
        Return the default configuration for a single camera sensor.

        :returns: Camera configuration instance.
        :rtype: NaoqiCameraConf
        """
        return NaoqiCameraConf()

    @staticmethod
    def get_inputs():
        """
        Declare that the sensor does not accept input messages.

        :returns: Empty list.
        :rtype: list
        """
        return []

    @staticmethod
    def get_output():
        """
        Declare the output message type produced by this sensor.

        :returns: Compressed image message class.

        """
        return CompressedImageMessage

    def execute(self):
        """
        Grab one image frame from the NAOqi camera and return it.

        :returns: Compressed image containing the RGB frame as a NumPy array.
        :rtype: CompressedImageMessage
        """
        try:
            # get the actual image from the NaoImage type
            naoImage = self.video_service.getImageRemote(self.videoClient)
            imageWidth = naoImage[0]
            imageHeight = naoImage[1]
            array = naoImage[6]
            image_string = str(bytearray(array))

            # Create a PIL Image from our pixel array.
            im = Image.frombytes("RGB", (imageWidth, imageHeight), image_string)
            return CompressedImageMessage(np.asarray(im))
        except Exception as e:
            if self._stopped.is_set() or self._signal_to_stop.is_set():
                return
            else:
                raise e

    def stop(self, *args):
        """
        Stop the camera sensor by closing the NAOqi session and the component.
        """
        self._signal_to_stop.set()
        try:
            if hasattr(self, 'videoClient') and self.videoClient:
                self.video_service.unsubscribe(self.videoClient)
        except Exception as e:
            print("Error unsubscribing from camera: {}".format(e))
        
        try:
            self.session.close()
        except Exception as e:
            print("Error closing session: {}".format(e))
            
        self._stopped.set()
        super(BaseNaoqiCameraSensor, self).stop(*args)


##################
# Top Camera
##################


class NaoqiTopCameraSensor(BaseNaoqiCameraSensor):
    def __init__(self, *args, **kwargs):
        super(NaoqiTopCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        """
        Return the default configuration for the top camera.

        :returns: Configuration with cam_id=0 and res_id=1.
        :rtype: NaoqiCameraConf
        """
        return NaoqiCameraConf(cam_id=0, res_id=1)


class NaoqiTopCamera(SICConnector):
    component_class = NaoqiTopCameraSensor


##################
# Bottom Camera
##################


class NaoqiBottomCameraSensor(BaseNaoqiCameraSensor):
    """
    Sensor for the NAO bottom camera (cam_id=1).
    """
    def __init__(self, *args, **kwargs):
        super(NaoqiBottomCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        """
        Return the default configuration for the bottom camera.

        :returns: Configuration with cam_id=1 and res_id=1.
        :rtype: NaoqiCameraConf
        """
        return NaoqiCameraConf(cam_id=1, res_id=1)


class NaoqiBottomCamera(SICConnector):
    component_class = NaoqiBottomCameraSensor


##################
# Stereo Pepper Camera
##################


class StereoImageMessage(SICMessage):
    _compress_images = True

    def __init__(self, left, right):
        """
        Create a stereo image message.

        :param numpy.ndarray left: Left image array.
        :param numpy.ndarray right: Right image array.
        """
        self.left_image = left
        self.right_image = right


class NaoStereoCameraConf(NaoqiCameraConf):

    def __init__(
        self,
        calib_params=None,
        naoqi_ip="127.0.0.1",
        port=9559,
        cam_id=0,
        res_id=2,
        color_id=11,
        fps=30,
        convert_bw=True,
        use_calib=True,
    ):

        super(NaoStereoCameraConf, self).__init__(
            naoqi_ip, port, cam_id, res_id, color_id, fps
        )  # TODO: correct?

        if calib_params is None:
            calib_params = {}

        self.cameramtrx = calib_params.get("cameramtrx", None)
        self.K = calib_params.get("K", None)
        self.D = calib_params.get("D", None)
        self.H1 = calib_params.get("H1", None)
        self.H2 = calib_params.get("H2", None)
        self.convert_bw = convert_bw  # Convert images to b&w before sending
        self.use_calib = (
            use_calib  # We don't want to rectify the images if we are calibrating
        )


class StereoPepperCameraSensor(BaseNaoqiCameraSensor):

    def __init__(self, *args, **kwargs):
        super(StereoPepperCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        # TODO: by default read calibration from disk
        return NaoStereoCameraConf(
            calib_params={
                "cameramtrx": None,
                "K": None,
                "D": None,
                "H1": None,
                "H2": None,
            },
            cam_id=3,
            res_id=15,
            convert_bw=True,
            use_calib=False,
        )

    def undistort(self, img):
        """
        Remove lens distortion using intrinsic matrix and distortion coefficients.

        :param numpy.ndarray img: Image to undistort.
        :returns: Undistorted image.
        :rtype: numpy.ndarray
        """
        assert self.params.K is not None, "Calibration parameter K not set"
        assert self.params.D is not None, "Calibration parameter D not set"
        return cv2.undistort(
            img, self.params.K, self.params.D, None, self.params.cameramtrx
        )

    def warp(self, img, is_left):
        """
        Apply perspective warp using rectification homography.

        :param numpy.ndarray img: Image to warp.
        :param bool is_left: Selects H1 for left and H2 for right.
        :returns: Warped image.
        :rtype: numpy.ndarray
        :raises AssertionError: If `H1` or `H2` is missing.
        """
        H_matrix = self.params.H1 if is_left else self.params.H2
        assert H_matrix is not None, "Calibration parameter H1 or H2 not set"
        return cv2.warpPerspective(img, H_matrix, img.shape[::-1])

    def rectify(self, img, is_left):
        """
        Undistort and warp an image for rectification.

        :param numpy.ndarray img: Image to rectify.
        :param bool is_left: Whether this is a left frame.
        :returns: Rectified image.
        :rtype: numpy.ndarray
        """
        if len(img.shape) == 2:
            return self.warp(self.undistort(img), is_left)

        img = np.concatenate(
            [
                self.rectify(img[..., i], is_left)[..., np.newaxis]
                for i in range(img.shape[-1])
            ],
            axis=2,
        )
        return img

    def execute(self):

        # Get the regular stereo image
        img_message = super(StereoPepperCameraSensor, self).execute().image

        if self.params.convert_bw:
            img_message = cv2.cvtColor(img_message, cv2.COLOR_BGR2GRAY)

        # Split the stereo image into separate left and right images
        left, right = (
            img_message[:, : img_message.shape[1] // 2, ...],
            img_message[:, img_message.shape[1] // 2 :, ...],
        )

        # Rectify the images to account for lens distortion and camera mis-alignment
        if self.params.use_calib:
            left = self.rectify(left, is_left=True)
            right = self.rectify(right, is_left=False)

        return StereoImageMessage(left, right)

    @staticmethod
    def get_output():
        """
        Declare the output message type for this sensor.

        :returns: StereoImageMessage type.
        """
        return StereoImageMessage


class StereoPepperCamera(SICConnector):

    component_class = StereoPepperCameraSensor


##################
# Depth Pepper Camera
##################


class DepthPepperCameraSensor(BaseNaoqiCameraSensor):

    def __init__(self, *args, **kwargs):
        super(DepthPepperCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        """
        Return the default configuration for the depth camera.

        :returns: Configuration with cam_id=2 and res_id=10.
        :rtype: NaoqiCameraConf
        """
        return NaoqiCameraConf(cam_id=2, res_id=10)


class DepthPepperCamera(SICConnector):

    component_class = DepthPepperCameraSensor


# Example: run the top and bottom camera sensors directly.
if __name__ == "__main__":
    SICComponentManager([NaoqiTopCameraSensor, NaoqiBottomCameraSensor])
